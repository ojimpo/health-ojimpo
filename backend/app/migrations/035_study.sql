-- 035: study カテゴリ (勉強) の新設
-- ソース: studyplus（メイン）+ duolingo（語学・第2ソース）
-- 設計:
--   日常の能動的な学習（資格・技術書・JTEX工業数学などの通信講座・語学）を
--   時間ベースで捕捉する文化的指標。読書(reading)とは別軸の「スキル習得」シグナル。
--
--   - studyplus: 学習記録アプリ Studyplus に記録した教材別の学習時間を集約。
--     JTEX や紙の技術書のようにオンライン痕跡を持たない学習も、Studyplus に記録すれば
--     ここで一元的に捕捉できる。取得経路は sync-gateway（OpenClaw がスクレイプ →
--     source_slug='studyplus' で日次合計分(payload.minutes)を1レコード/日で ingest）。
--     SyncGatewayAdapter の value_field='minutes' で件数ではなく分を SUM する。
--   - duolingo: 非公式 API（xp_summaries）から日次のセッション時間を取得し分換算。
--     ブラウザ不要の JSON API なので gateway を経由せず直叩き（coding=claude+github と同じ構造）。
--
-- 分類: event（ゼロでも正常）+ display_type=activity → 文化スコアのみに参加（健康スコアには非参加）。
-- decay_half_life=7 でバーストを平滑化、base_value は時間(分)/週。後で実値を見て調整する。

CREATE TABLE IF NOT EXISTS duolingo_daily (
    date TEXT PRIMARY KEY,        -- YYYY-MM-DD (JST)
    minutes REAL NOT NULL,        -- 推定学習時間(分)
    gained_xp INTEGER NOT NULL DEFAULT 0,
    num_sessions INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification,
     decay_half_life, score_method, sort_order)
VALUES
    ('studyplus', '勉強 (Studyplus)', 'study', '📚', '#5C6BC0', 'coming_soon', 'phase3', 'activity',
     210, '分', 7, 1.0, 'event', 7, 'sum', 27);

INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification,
     decay_half_life, score_method, sort_order)
VALUES
    ('duolingo', '語学 (Duolingo)', 'study', '🦉', '#58CC02', 'coming_soon', 'phase3', 'activity',
     70, '分', 7, 1.0, 'event', 7, 'sum', 28);
