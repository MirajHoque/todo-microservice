"""agents/orchestrator.py — the agent the user talks to.

"Agents as tools": the orchestrator is an ordinary agent whose tools
happen to be OTHER agents.

  user ──▶ orchestrator ──┬─ delegate_to_todo_agent(task)    ──▶ todo agent    ──▶ api
                          └─ delegate_to_planner_agent(goal) ──▶ planner agent ──▶ api (read)

  "hi"                       → answers itself, no sub-agent (cheapest)
  "add milk, urgent"         → todo agent
  "help me plan my move"     → planner → shows the plan, asks to add it
  "yes, add them"            → todo agent, with the exact list

Why split it up instead of one big agent with every tool?
  - each agent gets a short, focused prompt and only the tools it
    needs (the planner can't change anything)
  - adding an agent later = one more delegate_to_… tool here; the
    others don't change

Memory: only the orchestrator's conversation is stored (its
delegate_… calls and the agents' reports are in it, so it remembers
what was done). Sub-agents start fresh for every task, which is why
the orchestrator must write each task out in full.
"""

from typing import Any

from agent.agents import planner, todo
from agent.agents.loop import Agent, Message, Run, SaveFn, Tool

SYSTEM_PROMPT = """You are the assistant in a todo app, talking to the user. You \
coordinate two specialist agents, which you call through your tools:
- delegate_to_todo_agent: shows, adds, completes or deletes the user's todos. It is the \
ONLY way to read or change the list.
- delegate_to_planner_agent: breaks a bigger goal ("plan my move", "prepare for my \
exam") into concrete steps. It only suggests; it adds nothing.

How to work:
- Greetings, thanks and questions about what you can do: answer yourself, without tools.
- Stay on topic: you only help with the user's todo list and with planning tasks. For \
anything else (essays, code, homework, general knowledge, other services) say in one \
sentence that you can only help with todos and planning — don't do the task, not even \
partly.
- The agents do NOT see this conversation. Give each one a complete, self-contained \
instruction: exact titles, priorities, and todo ids from earlier reports when you have \
them.
- Send related work as ONE task (for example all the todos to create, as one list), \
not one delegation per todo.
- When the user wants a plan: get it from the planner, show it, and ask whether to add \
it as todos, unless they already asked for that. When they agree, send the todo agent \
the exact list to create.
- Only tell the user what an agent actually reported. If an agent reports an error, \
explain it plainly.
- Deleting needs the user's click: the app shows Confirm and Cancel buttons under your \
reply. When the todo agent reports todos waiting for confirmation, say which ones and ask \
the user to press Confirm. Never say they are deleted. A typed "yes" doesn't delete; \
point them to the button.
- Messages starting with [app] come from the app and report what the user clicked.
- Keep replies short and friendly. Never show todo ids to the user."""


async def _delegate_todo(run: Run, args: dict[str, Any]) -> str:
    return await todo.run(run, args["task"])


async def _delegate_planner(run: Run, args: dict[str, Any]) -> str:
    return await planner.run(run, args["goal"])


AGENT = Agent(
    name="orchestrator",
    system_prompt=SYSTEM_PROMPT,
    reasoning_effort="low",  # mostly routing; the planner does the hard thinking
    # Replies to the user are short. Even if the model ignored "stay on
    # topic" and wrote an essay, this caps what one answer can cost.
    max_tokens=4000,
    tools=(
        Tool(
            "delegate_to_todo_agent",
            "Give the todo agent one job on the user's todo list: list, add, complete "
            "or delete todos. Returns its report of what it did.",
            {
                "task": {
                    "type": "string",
                    "description": 'The complete instruction, e.g. \'Create "Buy milk" '
                    "with priority high' or 'Mark [id: 42] \"Buy milk\" as done'",
                }
            },
            _delegate_todo,
            required=("task",),
        ),
        Tool(
            "delegate_to_planner_agent",
            "Ask the planner agent to break a goal into a short list of concrete, "
            "prioritized steps. It only suggests a plan; it changes nothing.",
            {
                "goal": {
                    "type": "string",
                    "description": "The goal, with useful details from the conversation "
                    "(deadline, constraints, preferences)",
                }
            },
            _delegate_planner,
            required=("goal",),
        ),
    ),
)


async def run(run: Run, history: list[Message], save: SaveFn) -> str:
    """Answer the last user message in `history`, saving every new message."""
    # wrap_up: if the step budget runs out, still tell the user what was done.
    return await AGENT.run(run, history, save, wrap_up=True)
