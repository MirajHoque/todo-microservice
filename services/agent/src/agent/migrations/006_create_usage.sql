-- 006_create_usage.sql — step 2i.2, rate limit + daily cost cap.
--
-- One row per user per hour: how many chat messages they sent and
-- what their LLM calls cost. The chat checks it BEFORE calling any
-- model (usage.py):
--   messages in the current hour  >= CHAT_MESSAGES_PER_HOUR → 429
--   cost since midnight UTC        >= DAILY_COST_LIMIT_USD   → 429
--
-- Deliberately NOT linked to conversations: logging out clears the
-- conversation, and that must not reset the limits.

CREATE TABLE usage (
    user_id   UUID          NOT NULL,
    hour      TIMESTAMPTZ   NOT NULL,           -- start of the hour (date_trunc)
    messages  INTEGER       NOT NULL DEFAULT 0,
    llm_calls INTEGER       NOT NULL DEFAULT 0,
    cost_usd  NUMERIC(12, 6) NOT NULL DEFAULT 0, -- exact money math, not float
    PRIMARY KEY (user_id, hour)
);
