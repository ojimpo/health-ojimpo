-- Claude Code local log からのトークン使用量（~/.claude/projects/**/*.jsonl）
CREATE TABLE IF NOT EXISTS claude_local_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date)
);
CREATE INDEX IF NOT EXISTS idx_claude_local_usage_date ON claude_local_usage(date);
