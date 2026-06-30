-- 004_contracts_milestones.sql
-- Reference schema for negotiations, contracts, state transitions, and milestones.
-- Documentation only — Django migrations handle actual DDL.

CREATE TABLE IF NOT EXISTS negotiations (
    id                  UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    startup_id          UUID            NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
    founder_id          UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    investor_id         UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    shared_history      JSONB           NOT NULL DEFAULT '[]',
    deal_terms_so_far   JSONB           NOT NULL DEFAULT '{}',
    round_count         SMALLINT        NOT NULL DEFAULT 0,
    status              VARCHAR(20)     NOT NULL DEFAULT 'active',
    deal_summary        JSONB           NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_negotiation_startup_investor UNIQUE (startup_id, investor_id)
);

CREATE TABLE IF NOT EXISTS contracts (
    id                          UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    negotiation_id              UUID            NOT NULL UNIQUE REFERENCES negotiations(id) ON DELETE CASCADE,
    startup_id                  UUID            NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
    founder_id                  UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    investor_id                 UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    state                       VARCHAR(30)     NOT NULL DEFAULT 'drafting',
    deal_summary                JSONB           NOT NULL DEFAULT '{}',
    contract_text               TEXT,
    contract_sections           JSONB           NOT NULL DEFAULT '{}',
    payment_structure           VARCHAR(20)     NOT NULL DEFAULT 'lumpsum',
    valuation                   BIGINT,
    investment_amount           BIGINT,
    equity_pct                  NUMERIC(5,2),
    instrument                  VARCHAR(30),
    ai_review_notes             JSONB           NOT NULL DEFAULT '[]',
    ai_review_passed            BOOLEAN         NOT NULL DEFAULT FALSE,
    revision_requested_by       VARCHAR(20),
    docusign_envelope_id        VARCHAR(100),
    founder_signed_at           TIMESTAMPTZ,
    investor_signed_at          TIMESTAMPTZ,
    fully_executed_at           TIMESTAMPTZ,
    signed_document_url         TEXT,
    voided_reason                TEXT,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contracts_state ON contracts (state);
CREATE INDEX IF NOT EXISTS idx_contracts_envelope ON contracts (docusign_envelope_id);

CREATE TABLE IF NOT EXISTS contract_state_transitions (
    id              BIGSERIAL       PRIMARY KEY,
    contract_id     UUID            NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    from_state      VARCHAR(30)     NOT NULL,
    to_state        VARCHAR(30)     NOT NULL,
    triggered_by_id UUID            REFERENCES users(id) ON DELETE SET NULL,
    reason          TEXT,
    metadata        JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transitions_contract ON contract_state_transitions (contract_id, created_at);

-- Tamper-evident: no updates or deletes on the audit trail
CREATE OR REPLACE RULE cst_no_update AS ON UPDATE TO contract_state_transitions DO INSTEAD NOTHING;
CREATE OR REPLACE RULE cst_no_delete AS ON DELETE TO contract_state_transitions DO INSTEAD NOTHING;

CREATE TABLE IF NOT EXISTS milestones (
    id                  UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    contract_id         UUID            NOT NULL REFERENCES contracts(id) ON DELETE CASCADE,
    sequence            SMALLINT        NOT NULL,
    description         TEXT            NOT NULL,
    deadline_days       SMALLINT        NOT NULL,
    deadline_date       DATE,
    release_pct         NUMERIC(5,2)    NOT NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'pending',
    submission_notes    TEXT,
    submitted_at        TIMESTAMPTZ,
    approved_at         TIMESTAMPTZ,
    released_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_milestone_contract_seq UNIQUE (contract_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_milestones_status ON milestones (status);