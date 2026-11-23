CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'researcher' CHECK (role IN ('admin', 'researcher')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'disabled')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    email_verified_at TEXT,
    last_login_at TEXT,
    CHECK (length(trim(username)) > 0),
    CHECK (length(trim(email)) > 0),
    CHECK (length(trim(password_hash)) > 0)
);

CREATE TABLE auth_sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    CHECK (length(trim(token_hash)) > 0)
);
CREATE INDEX auth_sessions_user_expiry ON auth_sessions (user_id, expires_at);
