-- 005_create_pending_actions.sql — step 2i.1, human-in-the-loop.
--
-- The agent can't delete todos. Its delete_todo tool only PROPOSES:
-- the proposal waits here until the user presses Confirm or Cancel in
-- the app (routes/actions.py). The model has no tool that can confirm,
-- so even a confused or tricked model can't delete anything.
--
-- One waiting proposal per conversation: a newer one replaces it.
-- Clearing the conversation (logout) removes it too (CASCADE).

CREATE TABLE pending_actions (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        NOT NULL UNIQUE REFERENCES conversations (id) ON DELETE CASCADE,
    kind            TEXT        NOT NULL CHECK (kind IN ('delete_todos')),
    todos           JSONB       NOT NULL,  -- [{"id": "...", "title": "..."}]
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL   -- an old button must not work forever
);
