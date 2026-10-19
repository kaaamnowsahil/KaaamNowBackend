-- Figma SH · Language: app languages a user can pick.
CREATE TABLE IF NOT EXISTS languages (
    code         VARCHAR(8) PRIMARY KEY,
    english_name VARCHAR(64) NOT NULL,
    native_name  VARCHAR(64) NOT NULL,
    sort_order   INTEGER NOT NULL DEFAULT 0,
    is_active    BOOLEAN NOT NULL DEFAULT true
);
