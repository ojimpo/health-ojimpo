-- GitHub daily commit data
CREATE TABLE IF NOT EXISTS github_commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    commits INTEGER NOT NULL DEFAULT 0,
    repos TEXT,  -- JSON array of repo names
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);
CREATE INDEX IF NOT EXISTS idx_github_commits_date ON github_commits(date);

-- OpenAI Usage API daily token data
CREATE TABLE IF NOT EXISTS openai_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);
CREATE INDEX IF NOT EXISTS idx_openai_usage_date ON openai_usage(date);
