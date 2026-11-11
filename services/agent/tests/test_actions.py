"""Guardrail tests (step 2i.1): deleting needs the user's click.

The agent's delete_todo only PROPOSES. The chat answer carries a
pending_action; only POST /actions/{id}/confirm — which the model has
no tool for — deletes. These tests prove the model alone can't delete.
"""

import uuid

import psycopg
from fakes import answer, call, roles
from helpers import auth, make_token

ACTIONS = "/api/v1/agent/actions"


def deleting(*todo_ids: str) -> dict:
    """Scripts where the orchestrator delegates and the todo agent calls delete_todo."""
    return {
        "orchestrator": [
            answer(tool_calls=[call("o1", "delegate_to_todo_agent", task="Delete them")]),
            answer("Press Confirm to delete them."),
        ],
        "todo": [
            answer(
                tool_calls=[call(f"d{i}", "delete_todo", todo_id=t) for i, t in enumerate(todo_ids)]
            ),
            answer("Waiting for the user to confirm."),
        ],
    }


def with_todos(api, *titles: str) -> None:
    for i, title in enumerate(titles, start=1):
        api.todos[f"t{i}"] = {"id": f"t{i}", "title": title, "priority": "low", "done": False}


def test_delete_only_proposes(chat):
    send, _, model, api = chat(**deleting("t1"))
    with_todos(api, "Buy milk")

    body = send("delete buy milk").json()

    assert body["reply"] == "Press Confirm to delete them."
    assert [t["title"] for t in body["pending_action"]["todos"]] == ["Buy milk"]
    assert "t1" in api.todos  # NOT deleted …
    assert "DELETE" not in [method for method, _ in api.seen]  # … the api never got a DELETE
    result = model.calls("todo")[1]["messages"][-1]["content"]
    assert "NOT deleted" in result  # the model is told so


def test_confirm_deletes_once(db_client, chat):
    token = make_token()
    send, history, _, api = chat(token=token, **deleting("t1"))
    with_todos(api, "Buy milk")
    action = send("delete buy milk").json()["pending_action"]

    res = db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=auth(token))
    assert res.status_code == 200
    assert res.json() == {"reply": 'Deleted "Buy milk".'}
    assert api.todos == {}  # deleted — through the api, as the user
    assert ("DELETE", f"Bearer {token}") in api.seen

    # The orchestrator will know on the next message.
    last = history()[-1]
    assert last["role"] == "user"
    assert last["content"].startswith("[app] The user pressed Confirm.")

    # Double click / second tab: works only once.
    again = db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=auth(token))
    assert again.status_code == 404


def test_cancel_keeps_the_todo(db_client, chat):
    token = make_token()
    send, history, _, api = chat(token=token, **deleting("t1"))
    with_todos(api, "Buy milk")
    action = send("delete buy milk").json()["pending_action"]

    res = db_client.delete(f"{ACTIONS}/{action['id']}", headers=auth(token))
    assert res.json() == {"reply": 'Okay, I kept "Buy milk".'}
    assert "t1" in api.todos
    assert "pressed Cancel" in history()[-1]["content"]
    # Cancelled = gone: it can't be confirmed afterwards.
    assert (
        db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=auth(token)).status_code == 404
    )


def test_several_deletes_become_one_confirmation(chat):
    send, _, _, api = chat(**deleting("t1", "t2", "t1"))  # t1 twice: listed once
    with_todos(api, "Buy milk", "Call mom")
    action = send("delete both").json()["pending_action"]
    assert [t["title"] for t in action["todos"]] == ["Buy milk", "Call mom"]
    assert len(api.todos) == 2


def test_nobody_else_can_confirm(db_client, chat):
    send, _, _, api = chat(**deleting("t1"))  # the owner
    with_todos(api, "Buy milk")
    action = send("delete buy milk").json()["pending_action"]

    stranger = auth(make_token())  # another user, valid token
    assert db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=stranger).status_code == 404
    assert db_client.delete(f"{ACTIONS}/{action['id']}", headers=stranger).status_code == 404
    assert "t1" in api.todos


def test_expired_action_does_nothing(db_client, chat, database_url):
    token = make_token()
    send, _, _, api = chat(token=token, **deleting("t1"))
    with_todos(api, "Buy milk")
    action = send("delete buy milk").json()["pending_action"]
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("UPDATE pending_actions SET expires_at = now() - interval '1 second'")

    res = db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=auth(token))
    assert res.status_code == 404
    assert "expired" in res.json()["error"]
    assert "t1" in api.todos


def test_logout_drops_the_pending_action(db_client, chat):
    token = make_token()
    send, _, _, api = chat(token=token, **deleting("t1"))
    with_todos(api, "Buy milk")
    action = send("delete buy milk").json()["pending_action"]

    db_client.delete("/api/v1/agent/conversation", headers=auth(token))  # web does this on logout
    res = db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=auth(token))
    assert res.status_code == 404
    assert "t1" in api.todos


def test_unknown_todo_is_not_proposed(chat):
    send, _, model, _ = chat(**deleting("nope"))  # the list is empty
    body = send("delete nope").json()
    assert "pending_action" not in body  # nothing to confirm
    assert model.calls("todo")[1]["messages"][-1]["content"] == "error: todo not found"


def test_already_gone_counts_as_deleted(db_client, chat):
    token = make_token()
    send, _, _, api = chat(token=token, **deleting("t1"))
    with_todos(api, "Buy milk")
    action = send("delete buy milk").json()["pending_action"]
    api.todos.clear()  # deleted in the todo list meanwhile

    res = db_client.post(f"{ACTIONS}/{action['id']}/confirm", headers=auth(token))
    assert res.json() == {"reply": 'Deleted "Buy milk".'}


def test_actions_need_a_token_and_a_valid_id(db_client):
    some_id = uuid.uuid4()
    assert db_client.post(f"{ACTIONS}/{some_id}/confirm").status_code == 401
    assert (
        db_client.post(f"{ACTIONS}/not-a-uuid/confirm", headers=auth(make_token())).status_code
        == 400  # validation errors are 400, like the Go api
    )


def test_normal_answers_have_no_pending_action(chat):
    send, history, _, _ = chat(orchestrator=[answer("Hi!")])
    assert send("hi").json() == {"reply": "Hi!"}
    assert roles(history()) == ["user", "assistant"]
