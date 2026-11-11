"""agents — the AI agents of this service.

loop.py          the agent loop every agent runs (+ Budget, Tool, Agent)
orchestrator.py  the agent the user talks to; delegates to the others
todo.py          the only agent that changes todos (via the api)
planner.py       turns a goal into steps; can read the list, not change it
"""
