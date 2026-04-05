-- ============================================================
-- Migration: Unified Retrieval Units + Email Metadata Tables
-- Milestone: 9.13 — Yahoo Mail Parser
-- ============================================================
--
-- This migration introduces two things:
--
-- 1. retrieval_units — a unified retrieval surface that all content
--    sources write to. One table, one embedding column, one search.
--    Replaces the pattern of extending match_chunks with LEFT JOINs
--    for each new source.
--
-- 2. Email-specific metadata tables — email_conversations and
--    email_messages store structural metadata. The retrievable
--    content lives in retrieval_units.
--
-- After backfilling existing sources (Joplin chunks, iMessage bursts)
-- into retrieval_units, the match_chunks RPC can be simplified to
-- a single-table vector search.
--
-- ============================================================

-- ============================================================
-- 1. Unified Retrieval Units
-- ============================================================

CREATE TABLE IF NOT EXISTS retrieval_units (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Source identification
    source_type     TEXT NOT NULL,       -- "joplin" | "imessage" | "email" | "obsidian"
    source_id       TEXT NOT NULL,       -- ID in source-specific table (burst_id, chunk_id, etc.)

    -- Retrievable content
    body            TEXT NOT NULL,       -- the text that gets embedded and searched
    embedding       vector(1536),       -- OpenAI text-embedding-3-small

    -- Display metadata (for Reflections panel)
    title           TEXT,               -- subject line, note title, etc.
    notebook        TEXT,               -- "yahoo-mail", journal notebook name, etc.
    created_at      TIMESTAMPTZ,        -- when the content was created
    updated_at      TIMESTAMPTZ,        -- when the content was last modified

    -- Participant and privacy metadata
    participants    TEXT[],             -- email addresses / phone numbers
    privacy_tier    INTEGER DEFAULT 2,  -- 2=personal, 3=bilateral, 4=family
    dominant_sender TEXT,               -- primary sender for attribution

    -- Thread/conversation context
    thread_id       TEXT,               -- thread root / conversation ID
    thread_type     TEXT,               -- "bilateral" | "group"

    -- Flexible source-specific metadata
    metadata        JSONB DEFAULT '{}', -- message_ids, attachments, archetype, etc.

    -- Deduplication
    UNIQUE(source_type, source_id)
);

-- Indexes for retrieval
CREATE INDEX IF NOT EXISTS idx_retrieval_units_embedding
    ON retrieval_units USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_retrieval_units_source_type
    ON retrieval_units(source_type);

CREATE INDEX IF NOT EXISTS idx_retrieval_units_privacy_tier
    ON retrieval_units(privacy_tier);

CREATE INDEX IF NOT EXISTS idx_retrieval_units_created_at
    ON retrieval_units(created_at);

CREATE INDEX IF NOT EXISTS idx_retrieval_units_notebook
    ON retrieval_units(notebook);

CREATE INDEX IF NOT EXISTS idx_retrieval_units_thread_id
    ON retrieval_units(thread_id);


-- ============================================================
-- 2. Email Conversations (structural metadata)
-- ============================================================
-- A conversation is defined by its exact participant set.
-- Same participants = same conversation, regardless of topic.

CREATE TABLE IF NOT EXISTS email_conversations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    participant_hash    TEXT NOT NULL UNIQUE,   -- SHA256 of sorted participant list
    participants        TEXT[] NOT NULL,         -- sorted email addresses
    participant_count   INTEGER NOT NULL,
    first_message_at    TIMESTAMPTZ,
    last_message_at     TIMESTAMPTZ,
    message_count       INTEGER DEFAULT 0,
    burst_count         INTEGER DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_conversations_participants
    ON email_conversations USING GIN (participants);


-- ============================================================
-- 3. Email Messages (atomic message records)
-- ============================================================
-- One row per email. Stores metadata only — the retrievable
-- content lives in retrieval_units at the burst level.

CREATE TABLE IF NOT EXISTS email_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id      TEXT NOT NULL UNIQUE,    -- RFC2822 Message-ID header
    conversation_id UUID REFERENCES email_conversations(id),
    subject         TEXT,
    from_addr       TEXT NOT NULL,
    from_name       TEXT,
    to_addrs        TEXT[],
    cc_addrs        TEXT[],
    date            TIMESTAMPTZ,
    direction       TEXT,                    -- "sent" | "received"
    thread_root     TEXT,                    -- first Message-ID in References chain
    in_reply_to     TEXT,                    -- In-Reply-To header
    has_attachments BOOLEAN DEFAULT FALSE,
    source_file     TEXT,                    -- MBOX file path
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_email_messages_conversation
    ON email_messages(conversation_id);

CREATE INDEX IF NOT EXISTS idx_email_messages_from
    ON email_messages(from_addr);

CREATE INDEX IF NOT EXISTS idx_email_messages_date
    ON email_messages(date);

CREATE INDEX IF NOT EXISTS idx_email_messages_thread_root
    ON email_messages(thread_root);


-- ============================================================
-- 4. Match function for retrieval_units
-- ============================================================
-- Simple vector search — no joins needed.
-- Replaces the multi-join match_chunks pattern for new queries.

DROP FUNCTION IF EXISTS match_retrieval_units(vector, integer, text, integer);

CREATE OR REPLACE FUNCTION match_retrieval_units(
    query_embedding vector(1536),
    match_count integer DEFAULT 5,
    filter_notebook text DEFAULT NULL,
    max_privacy_tier integer DEFAULT 2
)
RETURNS TABLE (
    id              UUID,
    source_type     TEXT,
    source_id       TEXT,
    body            TEXT,
    title           TEXT,
    notebook        TEXT,
    created_at      TIMESTAMPTZ,
    participants    TEXT[],
    privacy_tier    INTEGER,
    dominant_sender TEXT,
    thread_id       TEXT,
    thread_type     TEXT,
    metadata        JSONB,
    similarity      FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        ru.id,
        ru.source_type,
        ru.source_id,
        ru.body,
        ru.title,
        ru.notebook,
        ru.created_at,
        ru.participants,
        ru.privacy_tier,
        ru.dominant_sender,
        ru.thread_id,
        ru.thread_type,
        ru.metadata,
        1 - (ru.embedding <=> query_embedding) AS similarity
    FROM retrieval_units ru
    WHERE ru.embedding IS NOT NULL
      AND ru.privacy_tier <= max_privacy_tier
      AND (filter_notebook IS NULL OR ru.notebook = filter_notebook)
    ORDER BY ru.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;


-- ============================================================
-- 5. Contacts + Contact Identifiers (Entity Layer seed)
-- ============================================================
-- Cross-channel identity registry. Not email-specific —
-- serves all content sources.

CREATE TABLE IF NOT EXISTS contacts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    canonical_name  TEXT NOT NULL,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS contact_identifiers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id      UUID NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    identifier_type TEXT NOT NULL,       -- "email" | "phone" | "apple_id" | "display_name"
    identifier_value TEXT NOT NULL,
    source          TEXT,               -- "yahoo_mail" | "imessage" | "manual"
    date_first_seen TEXT,
    date_last_seen  TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(identifier_type, identifier_value)
);

CREATE INDEX IF NOT EXISTS idx_contact_identifiers_contact
    ON contact_identifiers(contact_id);

CREATE INDEX IF NOT EXISTS idx_contact_identifiers_value
    ON contact_identifiers(identifier_value);
