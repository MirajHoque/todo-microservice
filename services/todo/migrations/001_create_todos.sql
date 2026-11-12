-- Migration: 001_create_todos
-- Creates the todos table in the todo service's own database (todo_db).
--
-- user_id has NO foreign key. The users live in another database
-- (auth_db, owned by the auth service), and a foreign key only works
-- inside one database. This service gets user_id from the JWT that
-- the auth service signed — that is its proof the user exists.
--
-- What we give up: "ON DELETE CASCADE". Deleting an account no longer
-- deletes its todos automatically; the auth service will have to TELL
-- this service (an event — see Kafka in the roadmap).

CREATE TABLE IF NOT EXISTS todos (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL,
    title       TEXT        NOT NULL CHECK (char_length(title) <= 255),
    description TEXT        NOT NULL DEFAULT '',
    priority    TEXT        NOT NULL DEFAULT 'medium'
                            CHECK (priority IN ('low', 'medium', 'high')),
    done        BOOLEAN     NOT NULL DEFAULT FALSE,
    done_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index on user_id because every todo list query does: WHERE user_id = $1
CREATE INDEX IF NOT EXISTS idx_todos_user_id ON todos(user_id);

-- Index on done so we can efficiently filter: WHERE user_id = $1 AND done = false
CREATE INDEX IF NOT EXISTS idx_todos_user_done ON todos(user_id, done);

-- Automatically update updated_at on every row change.
-- (In the monolith this function was created by the users migration and
-- reused here. Each database needs its own copy now.)
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER todos_updated_at
    BEFORE UPDATE ON todos
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
