-- 003_openrouter_message_format.sql
--
-- Messages are now stored in OpenRouter's unified chat format (works
-- for any model/provider) instead of Anthropic content blocks. Each
-- row holds ONE whole message, exactly as sent to / received from
-- the model:
--   {"role": "user", "content": "Add milk"}
--   {"role": "assistant", "content": "...", "tool_calls": [...], "reasoning_details": [...]}
--   {"role": "tool", "tool_call_id": "call_1", "content": "{\"created\": ...}"}
--
-- A new file instead of editing 001/002: migrations that already ran
-- somewhere must never change.

-- Conversations saved in the old format can't be replayed in the new
-- one. They're chat history only (the todos live in the api) — start fresh.
DELETE FROM conversations;  -- messages go too (ON DELETE CASCADE)

ALTER TABLE messages RENAME COLUMN content TO message;

-- Tool results are their own messages now: role "tool".
ALTER TABLE messages DROP CONSTRAINT messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check
    CHECK (role IN ('user', 'assistant', 'tool'));
