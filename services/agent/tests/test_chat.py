"""Chat tests: the orchestrator and its agents, with a FAKE model and a FAKE todo api.

The fakes live in fakes.py; the `chat` fixture (conftest.py) swaps them
into the app. So every path is tested for free, the same way every time.
Real OpenRouter calls are made by hand, not in these tests.
"""

import jwt
import psycopg
from fakes import answer, call, roles
from fastapi.testclient import TestClient
from helpers import auth, make_token

from agent.agents.loop import TOO_MANY_STEPS
from agent.config import get_settings
from agent.main import app

CHAT = "/api/v1/agent/chat"

# ── The orchestrator alone ───────────────────────────────────


def test_small_talk_needs_no_sub_agent(chat):
    send, history, model, api = chat(orchestrator=[answer("Hi! How can I help?")])

    res = send("hello")
    assert res.status_code == 200
    assert res.json() == {"reply": "Hi! How can I help?"}

    assert [name for name, _ in model.requests] == ["orchestrator"]  # one LLM call only
    assert api.seen == []
    sent = model.calls("orchestrator")[0]
    tools = [t["function"]["name"] for t in sent["tools"]]
    assert tools == ["delegate_to_todo_agent", "delegate_to_planner_agent"]
    assert sent["messages"][1:] == [{"role": "user", "content": "hello"}]
    assert roles(history()) == ["user", "assistant"]


# ── Delegating to the todo agent ─────────────────────────────


def test_todo_task_is_delegated_and_everything_is_stored(chat):
    task = 'Create "Buy milk" with priority high'
    send, history, model, api = chat(
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_todo_agent", task=task)]),
            answer("Added Buy milk (high)."),
        ],
        todo=[
            answer(tool_calls=[call("c1", "create_todo", title="Buy milk", priority="high")]),
            answer("Created [id: t1] Buy milk (high)."),
        ],
    )

    assert send("add buy milk, it's urgent").json() == {"reply": "Added Buy milk (high)."}

    # Order: orchestrator → todo → todo → orchestrator.
    assert [n for n, _ in model.requests] == ["orchestrator", "todo", "todo", "orchestrator"]

    # The todo agent got ONLY the task — not the user's conversation.
    first = model.calls("todo")[0]
    assert first["messages"][1:] == [{"role": "user", "content": task}]
    assert [t["function"]["name"] for t in first["tools"]] == [
        "list_todos",
        "create_todo",
        "complete_todo",
        "delete_todo",
    ]

    # The todo was really created — through the api, as the user.
    assert [t["title"] for t in api.todos.values()] == ["Buy milk"]
    assert api.seen[0][1].startswith("Bearer ey")  # the user's own JWT

    # The orchestrator got the todo agent's report as its tool result.
    result = model.calls("orchestrator")[1]["messages"][-1]
    assert result == {
        "role": "tool",
        "tool_call_id": "o1",
        "content": "Created [id: t1] Buy milk (high).",
    }

    # Stored: only the orchestrator's conversation (the delegation + report).
    stored = history()
    assert roles(stored) == ["user", "assistant", "tool", "assistant"]
    assert stored[1]["tool_calls"][0]["function"]["name"] == "delegate_to_todo_agent"


def test_next_message_replays_delegations_and_reasoning(chat):
    # The orchestrator must SEE what it delegated before (or it thinks it
    # never did it — the 1c.6 bug), and get its reasoning_details back.
    reasoning = [{"type": "reasoning.encrypted", "data": "secret-thoughts", "index": 0}]
    send, _, model, _ = chat(
        orchestrator=[
            answer(
                None,
                tool_calls=[call("o1", "delegate_to_todo_agent", task="Create Buy milk")],
                reasoning_details=reasoning,
            ),
            answer("Added."),
            answer("Yes, I added Buy milk."),
        ],
        todo=[answer("Created [id: t1] Buy milk (medium).")],
    )
    send("add buy milk")
    send("did you add it?")

    replayed = model.calls("orchestrator")[2]["messages"][1:]  # skip the system prompt
    assert roles(replayed) == ["user", "assistant", "tool", "assistant", "user"]
    assert replayed[1]["tool_calls"][0]["id"] == "o1"
    assert replayed[1]["reasoning_details"] == reasoning  # exactly as received
    assert "[id: t1]" in replayed[2]["content"]  # the id is remembered for "mark it done"


def test_todo_agent_errors_reach_the_orchestrator(chat):
    send, _, model, _ = chat(
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_todo_agent", task="Complete [id: x]")]),
            answer("I couldn't find that todo."),
        ],
        todo=[
            answer(tool_calls=[call("c1", "complete_todo", todo_id="x")]),
            answer("Error: todo not found."),
        ],
    )
    assert send("finish my report").json()["reply"] == "I couldn't find that todo."
    assert model.calls("todo")[1]["messages"][-1]["content"] == "error: todo not found"  # the api's
    assert model.calls("orchestrator")[1]["messages"][-1]["content"] == "Error: todo not found."


def test_bad_tool_arguments_are_reported_not_crashed(chat):
    broken = {
        "id": "c1",
        "type": "function",
        "function": {"name": "create_todo", "arguments": "{oops"},
    }
    send, _, model, _ = chat(
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_todo_agent", task="Add milk")]),
            answer("Done."),
        ],
        todo=[answer(tool_calls=[broken]), answer("Could not add it.")],
    )
    assert send("add milk").status_code == 200
    assert model.calls("todo")[1]["messages"][-1]["content"].startswith("error: invalid arguments")


def test_unknown_tool_is_reported(chat):
    # The orchestrator tries a tool only the todo agent has.
    send, _, model, _ = chat(
        orchestrator=[answer(tool_calls=[call("o1", "create_todo", title="x")]), answer("Oops.")]
    )
    assert send("add x").status_code == 200
    result = model.calls("orchestrator")[1]["messages"][-1]["content"]
    assert result == "error: invalid arguments for create_todo: unknown tool 'create_todo'"


def test_works_with_other_models_and_stop_with_tool_calls(chat):
    # A non-Claude model whose provider reports finish_reason "stop" even
    # though the message has tool calls — the loop must still run them.
    send, _, _, api = chat(
        model="openai/gpt-5",
        orchestrator=[
            answer(
                tool_calls=[call("o1", "delegate_to_todo_agent", task="Create Milk, low")],
                finish_reason="stop",
            ),
            answer("Done, added Milk."),
        ],
        todo=[
            answer(
                tool_calls=[call("c1", "create_todo", title="Milk", priority="low")],
                finish_reason="stop",
            ),
            answer("Created Milk."),
        ],
    )
    assert send("add milk").json() == {"reply": "Done, added Milk."}
    assert [t["title"] for t in api.todos.values()] == ["Milk"]


# ── The planner ──────────────────────────────────────────────


def test_planner_plans_but_cannot_change_anything(chat):
    plan = "1. Book movers (high)\n2. Pack books (medium)"
    send, history, model, api = chat(
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_planner_agent", goal="Move flat in May")]),
            answer(f"Here's a plan:\n{plan}\nShall I add these?"),
        ],
        planner=[answer(tool_calls=[call("p1", "list_todos")]), answer(plan)],
    )
    assert "Book movers" in send("help me plan my move in May").json()["reply"]

    first = model.calls("planner")[0]
    assert first["messages"][1:] == [{"role": "user", "content": "Move flat in May"}]
    # Least privilege: the planner was only given the read-only tool …
    assert [t["function"]["name"] for t in first["tools"]] == ["list_todos"]
    # … so the api only saw reads, and nothing was added.
    assert [method for method, _ in api.seen] == ["GET"]
    assert api.todos == {}
    assert roles(history()) == ["user", "assistant", "tool", "assistant"]


def test_plan_then_add_it(chat):
    plan = "1. Book movers (high)\n2. Pack books (medium)"
    send, _, model, api = chat(
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_planner_agent", goal="Move flat")]),
            answer(f"{plan}\nShall I add these?"),
            # 2nd message: "yes" → the todo agent gets the exact list.
            answer(
                tool_calls=[
                    call("o2", "delegate_to_todo_agent", task=f"Create these todos:\n{plan}")
                ]
            ),
            answer("Added both steps."),
        ],
        planner=[answer(plan)],
        todo=[
            answer(
                tool_calls=[
                    call("a", "create_todo", title="Book movers", priority="high"),
                    call("b", "create_todo", title="Pack books", priority="medium"),
                ]
            ),
            answer("Created [id: t1] Book movers (high), [id: t2] Pack books (medium)."),
        ],
    )
    send("plan my move")
    assert api.todos == {}  # nothing added until the user agrees
    assert send("yes, add them").json() == {"reply": "Added both steps."}
    assert sorted(t["title"] for t in api.todos.values()) == ["Book movers", "Pack books"]
    # The orchestrator saw the plan in its history when the user said "yes".
    third = model.calls("orchestrator")[2]["messages"]
    assert any(m["role"] == "tool" and m["content"] == plan for m in third)


def test_both_agents_at_once_each_get_a_result(chat):
    send, history, model, _ = chat(
        orchestrator=[
            answer(
                tool_calls=[
                    call("a", "delegate_to_todo_agent", task="List my todos"),
                    call("b", "delegate_to_planner_agent", goal="Plan a party"),
                ]
            ),
            answer("Here you go."),
        ],
        todo=[answer("The list is empty.")],
        planner=[answer("1. Invite friends (high)")],
    )
    send("what's on my list, and plan a party")

    results = model.calls("orchestrator")[1]["messages"][-2:]
    assert [(m["tool_call_id"], m["content"]) for m in results] == [
        ("a", "The list is empty."),
        ("b", "1. Invite friends (high)"),
    ]
    assert len(history()) == 5  # user, assistant, tool, tool, assistant


# ── Limits and failures ──────────────────────────────────────


def test_step_budget_is_shared_by_all_agents(chat):
    # Empty scripts: the orchestrator keeps delegating and the todo agent
    # keeps listing — forever. ONE budget must stop all of them.
    send, history, model, _ = chat()
    res = send("loop please")
    assert res.status_code == 200
    # The fake even ignores tool_choice "none" in the wrap-up call → the
    # plain "too many steps", and that tool call is NOT stored.
    assert "too many steps" in res.json()["reply"]
    # Not steps × agents: the budget, plus the orchestrator's one wrap-up call.
    assert len(model.requests) == get_settings().agent_max_steps + 1

    # The stored history is still valid: every tool call has its result.
    stored = history()
    call_ids = [c["id"] for m in stored for c in m.get("tool_calls", [])]
    result_ids = [m["tool_call_id"] for m in stored if m["role"] == "tool"]
    assert call_ids == result_ids


def test_out_of_steps_the_orchestrator_still_says_what_happened(chat):
    # The todo agent burns the whole budget; then the orchestrator gets one
    # extra call with tools switched off, and its words are the reply.
    send, history, model, _ = chat(
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_todo_agent", task="List todos")]),
            answer("I ran out of steps before finishing — please try again."),
        ]
    )
    res = send("list my todos")
    assert res.json() == {"reply": "I ran out of steps before finishing — please try again."}

    wrap_up = model.calls("orchestrator")[-1]
    assert wrap_up["tool_choice"] == "none"  # tools forbidden …
    assert len(wrap_up["tools"]) == 2  # … but still defined (the history has tool calls)
    assert "step limit" in wrap_up["messages"][0]["content"]
    assert wrap_up["messages"][-1]["content"] == TOO_MANY_STEPS  # the todo agent's report
    assert roles(history()) == ["user", "assistant", "tool", "assistant"]
    assert "tool_choice" not in model.calls("orchestrator")[0]  # normal calls: unchanged


def test_sub_agent_down_is_reported_not_502(chat):
    # The todo agent's model fails, the orchestrator's works: the user
    # gets an answer, and the history stays valid.
    send, history, model, _ = chat(
        fail={"todo": 500},
        orchestrator=[
            answer(tool_calls=[call("o1", "delegate_to_todo_agent", task="List todos")]),
            answer("Sorry, I can't reach your list right now."),
        ],
    )
    res = send("what's on my list?")
    assert res.status_code == 200
    assert res.json()["reply"] == "Sorry, I can't reach your list right now."
    tool_result = model.calls("orchestrator")[1]["messages"][-1]["content"]
    assert tool_result == "error: delegate_to_todo_agent failed — the model did not respond"
    assert roles(history()) == ["user", "assistant", "tool", "assistant"]


def test_llm_down_is_502_and_user_message_is_kept(chat):
    send, history, model, _ = chat(fail={"orchestrator": 500})
    res = send("hello?")
    assert res.status_code == 502
    assert 2 <= len(model.requests) <= 5  # the SDK retried a few times, then gave up
    assert res.json()["error"] == "agent failed to respond"
    # Append-only: the user's message stays; the next message simply follows it.
    assert roles(history()) == ["user"]


def test_no_credits_is_502(chat):
    send, _, _, _ = chat(orchestrator=[402])  # OpenRouter: "requires more credits"
    assert send("hello?").status_code == 502


def test_refusal(chat):
    send, _, _, _ = chat(orchestrator=[answer(None, refusal="I can't help with that.")])
    assert send("something not allowed").json() == {"reply": "Sorry, I can't help with that."}


def test_cut_off_answer_says_so(chat):
    send, _, _, _ = chat(orchestrator=[answer("Here is the start of", finish_reason="length")])
    assert "cut off" in send("write a lot").json()["reply"]


def test_unanswered_tool_call_is_closed_before_replay(chat, database_url):
    # The service died after saving a tool call but before its result.
    # The next message must still work: a placeholder result is sent.
    send, _, model, _ = chat(orchestrator=[answer("ok"), answer("Back again.")])
    send("hi")  # creates the conversation
    with psycopg.connect(database_url, autocommit=True) as conn:
        conv_id = conn.execute("SELECT id FROM conversations").fetchone()[0]
        dangling = {
            "role": "assistant",
            "content": None,
            "tool_calls": [call("lost", "delegate_to_todo_agent", task="x")],
        }
        conn.execute(
            "INSERT INTO messages (conversation_id, role, message) VALUES (%s, 'assistant', %s)",
            (conv_id, psycopg.types.json.Jsonb(dangling)),
        )
    assert send("are you there?").status_code == 200
    replayed = model.calls("orchestrator")[1]["messages"][1:]
    assert roles(replayed) == ["user", "assistant", "assistant", "tool", "user"]
    assert replayed[3]["tool_call_id"] == "lost"
    assert replayed[3]["content"].startswith("error: interrupted")


# ── Request checks ───────────────────────────────────────────


def test_empty_message_is_400(chat):
    send, _, model, _ = chat()
    res = send("   ")
    assert res.status_code == 400
    assert res.json()["error"] == "message is required"
    assert model.requests == []  # no money spent


def test_needs_a_token(db_client):
    res = db_client.post(CHAT, json={"message": "hi"})
    assert res.status_code == 401


def test_second_message_while_busy_is_409(chat, database_url):
    _, _, model, _ = chat(orchestrator=[answer("hi")])
    token = make_token()
    user_id = jwt.decode(token, options={"verify_signature": False})["user_id"]

    # Pretend another message from this user is still being answered:
    # hold the same advisory lock from another connection.
    with psycopg.connect(database_url, autocommit=True) as other:
        other.execute("SELECT pg_advisory_lock(1, hashtext(%s))", (user_id,))
        res = TestClient(app).post(CHAT, json={"message": "hi"}, headers=auth(token))
        assert res.status_code == 409
        assert res.json()["error"] == "still answering your previous message"
    assert model.requests == []
