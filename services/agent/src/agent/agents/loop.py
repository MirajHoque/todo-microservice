"""agents/loop.py — the agent loop, shared by every agent.

An "agent" here is just: a name + a system prompt + some tools (and
the Python functions behind them). Every agent runs the same loop:

  1. send system prompt + messages + tool definitions to the model
  2. the model answers. If its message has `tool_calls`, it wants one
     or MORE tools run; otherwise its text is the final answer
  3. run every requested tool (in parallel), add one
     {"role": "tool", "tool_call_id": ...} message per result, go to 1

The agents (orchestrator.py, todo.py, planner.py) only differ in
prompt and tools. Works with ANY model on OpenRouter that supports
tool calling — this is OpenRouter's unified chat format.

Two things keep it safe and cheap:

- Budget: every LLM call, by ANY agent, while answering one chat
  message takes one step from a shared Budget (AGENT_MAX_STEPS).
  Without it, an orchestrator with 10 steps could start sub-agents
  with 10 steps each — 100 paid calls for one message.
  When it runs out, the agent the user talks to gets ONE extra
  "wrap-up" call with tools switched off, so the user hears what was
  really done instead of a bare "too many steps".

- A tool never raises: whatever goes wrong (bad arguments, the api
  says no, a sub-agent's model is down, a bug) becomes a result
  starting with "error:". The model reads it and can explain or retry,
  and every tool call in the history always has its result (models
  reject a history where one is missing).
"""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from openrouter import OpenRouter
from openrouter import errors as openrouter_errors
from openrouter.components import ChatToolCall

from agent.auth import Caller
from agent.config import Settings
from agent.log import get_logger
from agent.todo_client import TodoAPIError, TodoClient

log = get_logger(__name__)

Message = dict[str, Any]  # one message in OpenRouter's chat format
SaveFn = Callable[[Message], Awaitable[None]]  # stores one message (routes/chat.py)

TOO_MANY_STEPS = "Sorry, that took too many steps. Please try a simpler request."
WRAP_UP = (
    "\n\nThe step limit for this message is reached: you cannot call tools any more. "
    "Tell the user briefly what was done and what was not."
)


class LLMError(Exception):
    """The model/provider failed in a way the SDK reports as a normal answer."""


# "The model or provider failed" (as opposed to a bug in our code).
LLM_FAILURES = (
    openrouter_errors.OpenRouterError,  # an error answer from OpenRouter (4xx/5xx)
    openrouter_errors.NoResponseError,  # network error / timeout
    LLMError,
)


@dataclass
class Budget:
    """LLM calls left for this chat message — shared by ALL agents."""

    left: int

    def take(self) -> bool:
        if self.left <= 0:
            return False
        self.left -= 1
        return True


@dataclass
class Run:
    """What every agent working on one chat message shares."""

    llm: OpenRouter
    settings: Settings
    todos: TodoClient  # the api's todo endpoints …
    caller: Caller  # … called as this user, with their JWT
    budget: Budget


# A tool's Python side: gets the Run and the model's arguments, returns
# text for the model to read.
ToolFn = Callable[[Run, dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str  # the model reads this to decide WHEN to use the tool
    properties: dict[str, Any]  # JSON Schema of the arguments: WHAT to pass
    fn: ToolFn
    required: tuple[str, ...] = ()

    def definition(self) -> dict[str, Any]:
        """The tool as sent to the model. strict + additionalProperties false:
        providers that support it guarantee the arguments match the schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": list(self.required),
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }


@dataclass(frozen=True)
class Agent:
    name: str  # in every log line ("agent": "todo")
    system_prompt: str
    tools: tuple[Tool, ...] = field(default=())
    # How hard reasoning models think; ignored by models without it.
    reasoning_effort: str = "medium"

    async def run(
        self,
        run: Run,
        messages: list[Message],
        save: SaveFn | None = None,
        wrap_up: bool = False,
    ) -> str:
        """Answer the last message in `messages`; returns the reply text.

        `save` (orchestrator only) stores each new message the moment it
        exists, so the stored history always matches what really happened.
        Sub-agents start fresh for every task and store nothing.
        `wrap_up`: if the budget runs out, make one last call without tools.
        """
        messages = list(messages)
        step = 0
        while run.budget.take():
            step += 1
            choice = await self._ask(run, messages, step)

            # Keep the model's message exactly as received — content,
            # tool_calls, reasoning_details. Replayed unchanged.
            reply_msg = choice.message
            assistant = reply_msg.model_dump(mode="json", by_alias=True, exclude_none=True)
            messages.append(assistant)
            if save:
                await save(assistant)

            # Decide by the message, not finish_reason: some providers say
            # "stop" even when the message contains tool calls.
            if reply_msg.tool_calls:
                results = await asyncio.gather(  # several calls in one turn: run together
                    *(self._run_tool(run, call) for call in reply_msg.tool_calls)
                )
                for tool_message in results:  # one message per result, in order
                    messages.append(tool_message)
                    if save:
                        await save(tool_message)
                continue

            return _final_text(choice)

        log.warning("out of steps", extra={"action": "agent_max_steps", "agent": self.name})
        if not wrap_up:
            return TOO_MANY_STEPS

        # One last call, outside the budget. Tools stay defined (providers
        # reject a history with tool calls otherwise) but tool_choice
        # "none" forbids using them: the model must answer in words.
        choice = await self._ask(run, messages, step + 1, tool_choice="none")
        if choice.message.tool_calls:  # ignored "none": never store a call without a result
            return TOO_MANY_STEPS
        assistant = choice.message.model_dump(mode="json", by_alias=True, exclude_none=True)
        if save:
            await save(assistant)
        return _final_text(choice)

    async def _ask(self, run: Run, messages: list[Message], step: int, tool_choice=None):
        """One LLM call; returns the first choice (its message is the answer)."""
        system = self.system_prompt + (WRAP_UP if tool_choice == "none" else "")
        start = time.perf_counter()
        result = await run.llm.chat.send_async(
            model=run.settings.agent_model,
            # The system prompt isn't stored: always the current version.
            messages=[{"role": "system", "content": system}, *messages],
            tools=[t.definition() for t in self.tools],
            tool_choice=tool_choice,
            max_tokens=run.settings.llm_max_tokens,
            reasoning_effort=self.reasoning_effort,
        )
        if not result.choices:
            raise LLMError("the model returned no answer")
        choice = result.choices[0]
        usage = result.usage
        log.info(
            "llm call",
            extra={
                "action": "llm_call",
                "agent": self.name,
                "model": result.model,  # the model that actually answered
                "step": step,
                "steps_left": run.budget.left,  # shared by all agents
                "finish_reason": choice.finish_reason,
                "input_tokens": usage.prompt_tokens if usage else None,
                "output_tokens": usage.completion_tokens if usage else None,
                "cost_usd": usage.cost if usage else None,  # the real price
                "duration_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        if choice.finish_reason == "error":
            raise LLMError("the model provider reported an error")
        return choice

    async def _run_tool(self, run: Run, call: ChatToolCall) -> Message:
        """Run one tool call; return its {"role": "tool", ...} message. Never raises."""
        name = call.function.name
        start = time.perf_counter()
        tool = next((t for t in self.tools if t.name == name), None)
        try:
            if tool is None:
                raise ValueError(f"unknown tool {name!r}")
            args = json.loads(call.function.arguments or "{}")  # arguments arrive as JSON text
            if not isinstance(args, dict):
                raise ValueError("arguments must be a JSON object")
            output = await tool.fn(run, args)
        except TodoAPIError as exc:  # the api said no (404, 400, …) — its own message
            output = f"error: {exc.message}"
        except (KeyError, TypeError, ValueError) as exc:  # bad JSON, missing/odd arguments
            output = f"error: invalid arguments for {name}: {exc}"
        except LLM_FAILURES as exc:  # a sub-agent's model failed
            log.error("sub-agent failed", extra={"agent": self.name, "error": str(exc)[:300]})
            output = f"error: {name} failed — the model did not respond"
        except Exception:  # a bug: log it, but keep the conversation valid
            log.exception("tool crashed", extra={"agent": self.name, "tool": name})
            output = f"error: {name} failed unexpectedly"

        log.info(
            "tool call",
            extra={
                "action": "tool_call",
                "agent": self.name,
                "tool": name,
                "ok": not output.startswith("error:"),
                "duration_ms": round((time.perf_counter() - start) * 1000),
            },
        )
        return {"role": "tool", "tool_call_id": call.id, "content": output}


def _final_text(choice: Any) -> str:
    """The reply text of a final (no tool calls) answer."""
    msg = choice.message
    if msg.refusal or choice.finish_reason == "content_filter":
        return "Sorry, I can't help with that."
    reply = _text(msg.content).strip()
    if choice.finish_reason == "length":
        reply += "\n\n(My answer was cut off. Please ask again more specifically.)"
    return reply or "Done."


def _text(content: Any) -> str:
    """Message content is usually a string, but may be a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""
