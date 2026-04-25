-- 027: Claude Code を時間ベース・複数端末対応に変更
-- 旧: claude_local_usage（トークン数、単一ホスト前提）→ display_type=card_only
-- 新: claude_session_minutes（分、host分離）→ display_type=activity, 文化スコア参加

CREATE TABLE IF NOT EXISTS claude_session_minutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    host TEXT NOT NULL,
    minutes REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(date, host)
);

CREATE INDEX IF NOT EXISTS idx_claude_session_minutes_date ON claude_session_minutes(date);

-- claude: トークンベースから時間ベースに切替、グラフに復帰
UPDATE source_settings SET
    display_type = 'activity',
    base_value = 300,
    base_unit = 'min',
    decay_half_life = 7
WHERE id = 'claude';

-- github: ソースから外す（Claude Code時間で全コーディングをカバー）
UPDATE source_settings SET status = 'disabled' WHERE id = 'github';

-- 旧テーブルのactivity_recordsをクリーンアップ（再集計で正しい値に置き換わる）
DELETE FROM activity_records WHERE source = 'claude';
DELETE FROM activity_records WHERE source = 'github';
