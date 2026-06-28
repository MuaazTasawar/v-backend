-- 002_users_profiles.sql
-- Raw SQL reference schema for the users table.
-- Django manages the actual migrations via `python manage.py migrate`.
-- This file documents the intended schema for DBA review and manual inspection.

-- NOTE: Django's migration system will create these tables automatically.
-- This file is for documentation and can be run on a fresh DB before
-- Django migrations if preferred.

CREATE TABLE IF NOT EXISTS users (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(254)    NOT NULL UNIQUE,
    full_name       VARCHAR(255)    NOT NULL,
    password        VARCHAR(128)    NOT NULL,
    role            VARCHAR(30)     NOT NULL DEFAULT 'founder'
                                    CHECK (role IN ('founder','investor','automation_engineer','admin')),
    auth_provider   VARCHAR(20)     NOT NULL DEFAULT 'local'
                                    CHECK (auth_provider IN ('local','google','linkedin')),
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    is_staff        BOOLEAN         NOT NULL DEFAULT FALSE,
    is_superuser    BOOLEAN         NOT NULL DEFAULT FALSE,
    is_verified     BOOLEAN         NOT NULL DEFAULT FALSE,
    is_onboarded    BOOLEAN         NOT NULL DEFAULT FALSE,
    avatar_url      TEXT,
    fcm_token       TEXT,
    date_joined     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    last_login      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_role  ON users (role);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       UUID        NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_evtoken_user UNIQUE (user_id)
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token       UUID        NOT NULL UNIQUE DEFAULT uuid_generate_v4(),
    is_used     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prt_user_unused
    ON password_reset_tokens (user_id, is_used)
    WHERE is_used = FALSE;