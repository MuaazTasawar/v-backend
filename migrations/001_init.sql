-- 001_init.sql
-- Foundational PostgreSQL extensions and shared utilities
-- Run once when the database is first created.

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Enable pg_trgm for fuzzy text search (used in matchmaking)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Enable btree_gin for composite GIN indexes
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Shared audit log table (append-only, referenced by contracts and financials)
CREATE TABLE IF NOT EXISTS audit_log (
    id            BIGSERIAL PRIMARY KEY,
    entity_type   VARCHAR(100)  NOT NULL,
    entity_id     UUID          NOT NULL,
    action        VARCHAR(100)  NOT NULL,
    actor_id      UUID,
    actor_role    VARCHAR(50),
    old_state     JSONB,
    new_state     JSONB,
    metadata      JSONB         DEFAULT '{}',
    ip_address    INET,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Index audit log for fast entity lookups
CREATE INDEX IF NOT EXISTS idx_audit_log_entity
    ON audit_log (entity_type, entity_id, created_at DESC);

-- Prevent any UPDATE or DELETE on audit_log (tamper-evident)
CREATE OR REPLACE RULE audit_log_no_update AS
    ON UPDATE TO audit_log DO INSTEAD NOTHING;

CREATE OR REPLACE RULE audit_log_no_delete AS
    ON DELETE TO audit_log DO INSTEAD NOTHING;