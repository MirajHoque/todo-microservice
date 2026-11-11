-- 004: step 2g — the user now talks to the orchestrator agent.
--
-- Stored conversations from step 2e contain calls to the old single
-- agent's tools (create_todo, list_todos, …). The orchestrator only
-- has delegate_to_todo_agent / delegate_to_planner_agent, and some
-- providers reject a history with calls to tools they weren't given.
-- These are local test chats only, so we simply start over.
DELETE FROM conversations;  -- messages go too (ON DELETE CASCADE)
