-- 003_startups.sql
-- Reference schema for startups, pitch sessions, documents, PoC deployments, and matchmaking.
-- Documentation only — Django migrations handle actual DDL.

CREATE TABLE IF NOT EXISTS startups (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    founder_id              UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                    VARCHAR(255)    NOT NULL,
    tagline                 VARCHAR(500),
    logo_url                TEXT,
    funding_stage           VARCHAR(20)     NOT NULL DEFAULT 'pre_seed',
    funding_ask             BIGINT          NOT NULL DEFAULT 0,
    equity_offered_pct      NUMERIC(5,2)    NOT NULL DEFAULT 0,
    status                  VARCHAR(20)     NOT NULL DEFAULT 'draft',
    pitch_context           JSONB           NOT NULL DEFAULT '{}',
    jira_workspace_url      TEXT,
    jira_project_key        VARCHAR(50),
    jira_access_token       TEXT,
    notion_workspace_id     VARCHAR(100),
    notion_access_token     TEXT,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_startups_status ON startups (status);
CREATE INDEX IF NOT EXISTS idx_startups_stage  ON startups (funding_stage);
CREATE INDEX IF NOT EXISTS idx_startups_founder ON startups (founder_id);

CREATE TABLE IF NOT EXISTS pitch_sessions (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    startup_id              UUID            NOT NULL UNIQUE REFERENCES startups(id) ON DELETE CASCADE,
    founder_id              UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    conversation_history    JSONB           NOT NULL DEFAULT '[]',
    current_phase           VARCHAR(50)     NOT NULL DEFAULT 'problem',
    status                  VARCHAR(20)     NOT NULL DEFAULT 'in_progress',
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS generated_documents (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    startup_id              UUID            NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
    document_type           VARCHAR(30)     NOT NULL,
    status                  VARCHAR(20)     NOT NULL DEFAULT 'pending',
    file_url                TEXT,
    content_json            JSONB           NOT NULL DEFAULT '{}',
    error_message           TEXT,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_doc_per_startup_type UNIQUE (startup_id, document_type)
);

CREATE TABLE IF NOT EXISTS poc_deployments (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    startup_id              UUID            NOT NULL UNIQUE REFERENCES startups(id) ON DELETE CASCADE,
    status                  VARCHAR(20)     NOT NULL DEFAULT 'pending',
    live_url                TEXT,
    s3_bucket_path          VARCHAR(500),
    generated_html          TEXT,
    error_message           TEXT,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_context_files (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    startup_id              UUID            NOT NULL UNIQUE REFERENCES startups(id) ON DELETE CASCADE,
    content                 JSONB           NOT NULL DEFAULT '{}',
    chroma_collection_name  VARCHAR(255),
    is_indexed              BOOLEAN         NOT NULL DEFAULT FALSE,
    indexed_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Matchmaking
CREATE TABLE IF NOT EXISTS match_scores (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    investor_id             UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    startup_id              UUID            NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
    overall_score           NUMERIC(5,2)    NOT NULL,
    industry_score          NUMERIC(5,2)    NOT NULL DEFAULT 0,
    stage_score             NUMERIC(5,2)    NOT NULL DEFAULT 0,
    ticket_size_score       NUMERIC(5,2)    NOT NULL DEFAULT 0,
    risk_score              NUMERIC(5,2)    NOT NULL DEFAULT 0,
    breakdown               JSONB           NOT NULL DEFAULT '{}',
    computed_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_match_investor_startup UNIQUE (investor_id, startup_id)
);

CREATE INDEX IF NOT EXISTS idx_match_scores_investor ON match_scores (investor_id, overall_score DESC);

CREATE TABLE IF NOT EXISTS saved_startups (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    investor_id             UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    startup_id              UUID            NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_saved_investor_startup UNIQUE (investor_id, startup_id)
);

CREATE TABLE IF NOT EXISTS interest_signals (
    id                      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    investor_id             UUID            NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    startup_id              UUID            NOT NULL REFERENCES startups(id) ON DELETE CASCADE,
    proposed_amount         BIGINT,
    message                 TEXT,
    status                  VARCHAR(20)     NOT NULL DEFAULT 'pending',
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_interest_investor_startup UNIQUE (investor_id, startup_id)
);

CREATE INDEX IF NOT EXISTS idx_interest_startup_status ON interest_signals (startup_id, status);