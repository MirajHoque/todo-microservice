"""agents/planner.py — the planner agent: turns a goal into steps.

"Help me plan my move" → a short numbered list of concrete todos
with priorities. The orchestrator shows the plan to the user and,
if they want it, asks the todo agent to add the steps.

Least privilege: the planner can READ the list (to avoid duplicates)
but has no tool to change it. Even if the model got confused — or
was tricked by text in a todo title — it simply can't add or delete
anything. Only the todo agent can.
"""

from agent.agents.loop import Agent, Run
from agent.agents.todo import LIST_TODOS

SYSTEM_PROMPT = """You are the planning agent inside a todo app. You get a goal from the \
orchestrator (another AI agent) and turn it into a short, practical plan.

- First call list_todos to see what the user already has. Don't repeat existing todos; \
mention related ones instead.
- Plan 3 to 7 concrete steps, in the order to do them. Each step is a short todo title \
starting with a verb, with a priority: high = urgent or blocks other steps, medium = \
normal, low = nice to have.
- You cannot change the list, only suggest. Never say anything was added.
- Reply only with the plan, as a numbered list: `1. Title (priority) - optional short note`."""

AGENT = Agent(
    name="planner",
    system_prompt=SYSTEM_PROMPT,
    reasoning_effort="medium",  # planning is the part that benefits from thinking
    tools=(LIST_TODOS,),  # read-only on purpose
)


async def run(run: Run, goal: str) -> str:
    """Plan one goal for the orchestrator; returns the plan as text."""
    return await AGENT.run(run, [{"role": "user", "content": goal}])
