-- 002_create_messages.sql
--
-- Every message in a conversation, in order.
--
-- content is JSONB holding the FULL message as the LLM API sees it —
-- a list of content blocks, e.g.
--   [{"type": "text", "text": "Add milk"}]                        (user)
--   [{"type": "tool_use", "id": "t1", "name": "create_todo", ...}] (assistant)
--   [{"type": "tool_result", "tool_use_id": "t1", ...}]           (user)
--   [{"type": "text", "text": "Added Buy milk."}]                  (assistant)
--
-- The Go agent saved only the text, so on the next message the model
-- saw "Added it" with no tool call behind it and thought it had lied
-- (the 1c.6 bug). Keeping the tool_use / tool_result blocks fixes that.

CREATE TABLE messages (
    id              BIGINT      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,  -- also the order
    conversation_id UUID        NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role            TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    content         JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Loading a conversation = "messages of conversation X, in order".
CREATE INDEX messages_conversation_id_idx ON messages (conversation_id, id);
