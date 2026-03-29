-- Notification subscribers (LINE / Email)
CREATE TABLE IF NOT EXISTS notification_subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    display_name TEXT,
    verified INTEGER NOT NULL DEFAULT 0,
    verification_token TEXT,
    verification_expires_at TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(channel, channel_id)
);
CREATE INDEX IF NOT EXISTS idx_subscribers_active ON notification_subscribers(channel, active, verified);

-- Notification send log
CREATE TABLE IF NOT EXISTS notification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    triggered_at TEXT NOT NULL DEFAULT (datetime('now')),
    health_status TEXT,
    cultural_status TEXT,
    transition_type TEXT NOT NULL,
    subscribers_notified INTEGER NOT NULL DEFAULT 0,
    errors TEXT
);

-- Last known status (single row, for transition detection)
CREATE TABLE IF NOT EXISTS status_snapshot (
    id INTEGER PRIMARY KEY DEFAULT 1,
    health_status TEXT NOT NULL DEFAULT 'NORMAL',
    cultural_status TEXT NOT NULL DEFAULT 'RICH',
    health_score REAL DEFAULT 0,
    cultural_score REAL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO status_snapshot (id, health_status, cultural_status) VALUES (1, 'NORMAL', 'RICH');
