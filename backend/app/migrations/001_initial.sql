-- Last.fm raw scrobble data
CREATE TABLE IF NOT EXISTS lastfm_scrobbles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    track_name TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    album_name TEXT,
    scrobbled_at INTEGER NOT NULL,
    scrobbled_date TEXT NOT NULL,
    duration_seconds INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(artist_name, track_name, scrobbled_at)
);
CREATE INDEX IF NOT EXISTS idx_scrobbles_date ON lastfm_scrobbles(scrobbled_date);
CREATE INDEX IF NOT EXISTS idx_scrobbles_at ON lastfm_scrobbles(scrobbled_at);

-- Normalized daily activity records (common schema)
CREATE TABLE IF NOT EXISTS activity_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    minutes REAL NOT NULL DEFAULT 0,
    raw_value REAL NOT NULL DEFAULT 0,
    raw_unit TEXT NOT NULL,
    metadata TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, source)
);
CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_records(date);
CREATE INDEX IF NOT EXISTS idx_activity_source ON activity_records(source, date);

-- Per-source configuration (seeded with all 17 sources)
CREATE TABLE IF NOT EXISTS source_settings (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    icon TEXT NOT NULL,
    display_type TEXT NOT NULL DEFAULT 'activity',
    classification TEXT NOT NULL DEFAULT 'baseline',
    phase TEXT NOT NULL DEFAULT 'mvp',
    status TEXT NOT NULL DEFAULT 'coming_soon',
    color TEXT NOT NULL,
    show_personal INTEGER NOT NULL DEFAULT 1,
    show_shared INTEGER NOT NULL DEFAULT 1,
    aggregation_period INTEGER NOT NULL DEFAULT 7,
    base_value REAL NOT NULL DEFAULT 100,
    base_unit TEXT NOT NULL DEFAULT '',
    spontaneity_coefficient REAL NOT NULL DEFAULT 1.0,
    sort_order INTEGER NOT NULL DEFAULT 0
);

-- Baseline value history with periods
CREATE TABLE IF NOT EXISTS baseline_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES source_settings(id),
    effective_from TEXT NOT NULL,
    base_value REAL NOT NULL,
    base_unit TEXT NOT NULL,
    memo TEXT
);
CREATE INDEX IF NOT EXISTS idx_baseline_source ON baseline_history(source_id, effective_from);

-- Global settings (thresholds, shared view config)
CREATE TABLE IF NOT EXISTS global_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ingestion log
CREATE TABLE IF NOT EXISTS ingest_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    records_fetched INTEGER DEFAULT 0,
    records_stored INTEGER DEFAULT 0,
    error_message TEXT,
    last_timestamp INTEGER
);
CREATE INDEX IF NOT EXISTS idx_ingest_source ON ingest_log(source, completed_at);

-- Seed: 17 data sources
INSERT OR IGNORE INTO source_settings (id, name, category, icon, display_type, classification, phase, status, color, show_personal, show_shared, aggregation_period, base_value, base_unit, spontaneity_coefficient, sort_order) VALUES
    ('lastfm',      '音楽 (Last.fm)',           '音楽',    '♫', 'activity', 'baseline', 'mvp',    'active',      '#00F0FF', 1, 1, 7,  700, 'minutes', 0.6, 1),
    ('strava',      '運動 (Strava)',             '運動',    '🚴', 'activity', 'both',     'phase2', 'coming_soon', '#FF3366', 1, 1, 30, 200, 'km',      1.0, 2),
    ('oura',        '睡眠 (Oura)',               '睡眠',    '😴', 'state',    'baseline', 'phase2', 'coming_soon', '#BD93F9', 1, 0, 7,  80,  'score',   1.0, 3),
    ('intervals',   'フィットネス (intervals.icu)','フィットネス','💪','state', 'baseline', 'phase2', 'coming_soon', '#50FA7B', 1, 0, 30, 50,  'CTL',     1.0, 4),
    ('instagram',   'Instagram',                 'SNS',     '📸', 'activity', 'baseline', 'phase2', 'coming_soon', '#FF9500', 1, 1, 7,  420, 'minutes', 0.6, 5),
    ('twitter',     'Twitter',                   'SNS',     '🐦', 'activity', 'baseline', 'phase2', 'coming_soon', '#1DA1F2', 1, 1, 7,  210, 'minutes', 0.6, 6),
    ('gcal_private','プライベート予定 (Google Calendar)', '予定',    '🏖️', 'activity', 'event',    'phase2', 'coming_soon', '#FFB86C', 1, 1, 90, 6,   '回',      1.2, 7),
    ('gcal_live',   'ライブ (Google Calendar)',   'ライブ',  '🎵', 'activity', 'event',    'phase2', 'coming_soon', '#FF79C6', 1, 1, 90, 3,   '回',      1.2, 8),
    ('gmail',       '買い物 (Gmail)',             '買い物',  '🛒', 'activity', 'baseline', 'phase2', 'coming_soon', '#8BE9FD', 1, 0, 30, 10,  '回',      0.6, 9),
    ('kashidashi',  '図書館 (kashidashi)',        '読書',    '📚', 'activity', 'event',    'phase2', 'coming_soon', '#ADFF2F', 1, 1, 90, 12,  '冊',      1.0, 10),
    ('bookmeter',   '読書メーター',              '読書',    '📖', 'activity', 'event',    'phase3', 'coming_soon', '#ADFF2F', 1, 1, 90, 21,  '冊',      1.0, 11),
    ('filmarks',    '映画 (Filmarks)',            '映画',    '🎬', 'activity', 'event',    'phase3', 'coming_soon', '#FF9500', 1, 1, 90, 6,   '本',      1.0, 12),
    ('github',      'GitHub',                    'コーディング','💻','activity','event',   'phase3', 'coming_soon', '#50FA7B', 1, 1, 7,  30,  'commits', 1.0, 13),
    ('claude',      'Claude Code',               'コーディング','🤖','activity','event',   'phase3', 'coming_soon', '#D4A574', 1, 0, 7,  100, 'k tokens',1.0, 14),
    ('openai',      'OpenAI',                    'コーディング','🧠','activity','event',   'phase3', 'coming_soon', '#74AA9C', 1, 0, 7,  100, 'k tokens',1.0, 15),
    ('bathmat',     '体重 (Smart Bath Mat)',      '体重',    '⚖️', 'state',    'baseline', 'phase3', 'coming_soon', '#F8F8F2', 1, 0, 7,  1,   '回/日',   1.0, 16),
    ('spotify_pod', 'Podcasts (Spotify)',         '音楽',    '🎧', 'activity', 'baseline', 'phase3', 'coming_soon', '#1DB954', 1, 1, 7,  210, 'minutes', 0.6, 17);

-- Seed: Global settings defaults
INSERT OR IGNORE INTO global_settings (key, value) VALUES
    ('score_normal_threshold', '70'),
    ('score_caution_threshold', '40'),
    ('shared_view_token', hex(randomblob(16))),
    ('shared_view_enabled', 'true');
