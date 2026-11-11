-- 001_create_conversations.sql
--
-- One conversation per user (for now): the chat history the agent
-- remembers. Stored in Postgres, not in the process's memory, so
-- (1) it survives restarts and (2) ANY copy of the agent service can
-- answer the next message — on Kubernetes there may be several.
--
-- user_id has NO foreign key to a users table: users live in another
-- service's database (the api's `todo` db), which this service can't
-- even connect to. The id comes from the user's JWT instead.

CREATE TABLE conversations (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL UNIQUE,  -- UNIQUE: one conversation per user
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
