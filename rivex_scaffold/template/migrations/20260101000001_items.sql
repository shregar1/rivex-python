-- Migration: items table.
-- Created by the {{project_name}} template.

CREATE TABLE IF NOT EXISTS items (
    id          BIGSERIAL    PRIMARY KEY,
    urn         UUID         NOT NULL UNIQUE,
    title       VARCHAR(200) NOT NULL,
    description VARCHAR(2000) NOT NULL DEFAULT '',
    is_completed BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    is_deleted  BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS items_is_deleted_idx ON items (is_deleted);
CREATE INDEX IF NOT EXISTS items_created_at_idx ON items (created_at);
