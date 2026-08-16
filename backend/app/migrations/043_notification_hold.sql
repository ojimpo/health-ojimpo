-- 043: 友人への警告配信の「本人事前確認」ゲート（2026-08-16）
-- 背景: 健康/文化スコアの低下を検出すると、持続性ガードを抜けた時点で友人へ
--   即座に配信されていた。スコアは誤検知しうる（計測断・旅行・機材の入れ替え等）ので、
--   まず本人のLINEに確認を出し、「大丈夫」と答えたら配信しない。
--   本人が何も答えないまま一定時間が過ぎた場合だけ、実際に友人へ配信する。
--   「応答できない状態そのものが警告のシグナル」なので、無応答はGOとして扱う。
-- status:
--   pending       確認中（本人の応答待ち）
--   suppressed    本人が「配信しない」を選んだ
--   released      本人が「今すぐ配信」を選んだ
--   auto_released 無応答のまま期限を過ぎたので自動配信した
--   recovered     期限前にスコアが戻ったので取り消した
--   superseded    より重い遷移が発生し、新しい確認に置き換えられた

CREATE TABLE IF NOT EXISTS notification_holds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    transitions TEXT NOT NULL,          -- JSON配列（notification.py の遷移文字列）
    severity TEXT NOT NULL,             -- 'critical' | 'normal'（待ち時間の切り替え用）
    health_status TEXT NOT NULL,
    cultural_status TEXT NOT NULL,
    health_score REAL,
    cultural_score REAL,
    prompts_sent INTEGER NOT NULL DEFAULT 0,
    last_prompt_at TEXT,
    snoozes INTEGER NOT NULL DEFAULT 0,
    release_after TEXT NOT NULL,        -- この時刻を過ぎても無応答なら配信（UTC）
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_notification_holds_status
    ON notification_holds(status, id DESC);
