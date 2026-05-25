-- 031: Steam playtime tracking
-- カテゴリ: game (Steam Web API)
-- 設計: タイトルは内部的に track するが、aggregate 時に全タイトル合算で category=game に集約
-- 動機: ゲームプレイで他の文化的活動が減った時に cultural スコアの説明力を上げる

CREATE TABLE IF NOT EXISTS steam_titles (
    appid INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    release_date TEXT,
    last_playtime_forever INTEGER NOT NULL DEFAULT 0,
    first_seen_date TEXT NOT NULL,
    backfilled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS steam_playtime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    appid INTEGER NOT NULL,
    minutes REAL NOT NULL DEFAULT 0,
    UNIQUE(date, appid)
);
CREATE INDEX IF NOT EXISTS idx_steam_playtime_date ON steam_playtime(date);
CREATE INDEX IF NOT EXISTS idx_steam_playtime_appid ON steam_playtime(appid, date);

INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification,
     decay_half_life, score_method, sort_order)
VALUES
    ('steam', 'ゲーム (Steam)', 'game', '🎮', '#66C0F4', 'active', 'phase3', 'activity',
     300, 'minutes', 7, 1.0, 'event', 7, 'sum', 18);

-- Forza Horizon 6: Steam Store API では 2026-05-18 だがユーザーの実プレイ開始日は 2026-05-19
-- backfilled=0 でアダプタの初回 ingest 時にこの release_date 起点でバックフィルされる
INSERT OR IGNORE INTO steam_titles
    (appid, name, release_date, last_playtime_forever, first_seen_date, backfilled)
VALUES
    (2483190, 'Forza Horizon 6', '2026-05-19', 0, '2026-05-19', 0);
