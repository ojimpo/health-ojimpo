-- 通知の誤発火防止のための持続性ガード用テーブル。
-- 各 check_and_notify 呼び出し時の status を時系列保存し、
-- CAUTION/LOW 遷移検出時に直近N回連続を要求するためのソース。
CREATE TABLE IF NOT EXISTS status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    health_status TEXT NOT NULL,
    cultural_status TEXT NOT NULL,
    health_score REAL,
    cultural_score REAL
);
CREATE INDEX IF NOT EXISTS idx_status_history_observed_at
    ON status_history(observed_at DESC);
