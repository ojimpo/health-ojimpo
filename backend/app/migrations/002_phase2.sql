-- Phase 2: Multi-source support

-- OAuth2 token storage
CREATE TABLE IF NOT EXISTS oauth_tokens (
    source_id TEXT PRIMARY KEY REFERENCES source_settings(id),
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT DEFAULT 'Bearer',
    expires_at INTEGER,
    scope TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Strava raw activity data
CREATE TABLE IF NOT EXISTS strava_activities (
    id INTEGER PRIMARY KEY,
    activity_type TEXT NOT NULL,
    name TEXT,
    distance_meters REAL,
    moving_time_seconds INTEGER,
    elapsed_time_seconds INTEGER,
    total_elevation_gain REAL,
    commute INTEGER DEFAULT 0,
    start_date TEXT NOT NULL,
    start_date_local TEXT NOT NULL,
    timezone TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_strava_date ON strava_activities(start_date_local);

-- Oura daily summary
CREATE TABLE IF NOT EXISTS oura_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    readiness_score INTEGER,
    sleep_score INTEGER,
    stress_level TEXT,
    sleep_total_seconds INTEGER,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- intervals.icu daily wellness
CREATE TABLE IF NOT EXISTS intervals_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    ctl REAL,
    atl REAL,
    tsb REAL,
    ftp REAL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Screen time daily (Instagram/Twitter via iOS Shortcut webhook)
CREATE TABLE IF NOT EXISTS screen_time_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    minutes REAL NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source)
);

-- Google Calendar events
CREATE TABLE IF NOT EXISTS gcal_events (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    summary TEXT,
    start_date TEXT NOT NULL,
    end_date TEXT,
    calendar_id TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gcal_date ON gcal_events(start_date);

-- Gmail purchase confirmation emails
CREATE TABLE IF NOT EXISTS gmail_purchases (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    store TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_gmail_date ON gmail_purchases(date);

-- Fix activity_records unique constraint: (date, source) -> (date, source, category)
-- Required for Oura writing sleep/readiness/stress as separate rows
CREATE TABLE IF NOT EXISTS activity_records_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    minutes REAL NOT NULL DEFAULT 0,
    raw_value REAL NOT NULL DEFAULT 0,
    raw_unit TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source, category)
);
INSERT OR IGNORE INTO activity_records_new (id, date, source, category, minutes, raw_value, raw_unit, metadata, created_at)
    SELECT id, date, source, category, minutes, raw_value, raw_unit, metadata, created_at FROM activity_records;
DROP TABLE IF EXISTS activity_records;
ALTER TABLE activity_records_new RENAME TO activity_records;
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_records(date);
CREATE INDEX IF NOT EXISTS idx_activity_source ON activity_records(source, date);
CREATE INDEX IF NOT EXISTS idx_activity_category ON activity_records(category, date);

-- Normalize category values to English keys (matches ChartDataPoint fields)
UPDATE activity_records SET category = 'music' WHERE category = '音楽';
UPDATE source_settings SET category = 'music' WHERE category = '音楽';
UPDATE source_settings SET category = 'exercise' WHERE category = '運動';
UPDATE source_settings SET category = 'sleep' WHERE category = '睡眠';
UPDATE source_settings SET category = 'fitness' WHERE category = 'フィットネス';
UPDATE source_settings SET category = 'sns' WHERE category = 'SNS';
UPDATE source_settings SET category = 'calendar' WHERE category = '予定';
UPDATE source_settings SET category = 'live' WHERE category = 'ライブ';
UPDATE source_settings SET category = 'shopping' WHERE category = '買い物';
UPDATE source_settings SET category = 'reading' WHERE category = '読書';
UPDATE source_settings SET category = 'movie' WHERE category = '映画';
UPDATE source_settings SET category = 'coding' WHERE category = 'コーディング';
UPDATE source_settings SET category = 'weight' WHERE category = '体重';
