-- 038: 運動カテゴリに Oura 歩数を第2ソースとして追加
-- 背景: Strava は意図的なトレーニングしか捕捉できず、旅行・外出などで
--   体を動かしていても運動スコアが急落し、健康スコアを引き下げる誤検知が
--   起きていた。Oura の日次歩数は「運動ゼロでも体が動いているか」を拾う。
--   カテゴリ内平均の集約方式により exercise = (strava + oura_steps) / 2 と
--   なり、指標の重みは1カテゴリのまま変わらない。
-- activity_score ではなく歩数を使う理由: Oura の activity score は 86〜96 の
--   狭い範囲に圧縮されており基準値比に正規化すると常に ~100 でシグナルに
--   ならない。歩数は 3千〜1.5万/日 と実分散がある（2026-07 実測）。
-- base_value 56000歩/週 = 8000歩/日。decay_half_life=7 で strava と揃える。

CREATE TABLE IF NOT EXISTS oura_activity_daily (
    date TEXT PRIMARY KEY,        -- YYYY-MM-DD
    steps INTEGER,
    activity_score INTEGER,
    active_calories INTEGER,
    high_activity_minutes REAL,
    medium_activity_minutes REAL,
    low_activity_minutes REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification,
     decay_half_life, score_method, sort_order)
VALUES
    ('oura_steps', '歩数 (Oura)', 'exercise', '👟', '#5AC8FA', 'active', 'phase2', 'activity',
     56000, '歩', 7, 1.0, 'baseline', 7, 'sum', 29);
