-- 039: 主観フィードバック（LINEで毎晩、絶対評価3択の調子を記録）
-- 背景: スコアリングモデルには「正解データ」がない。毎晩 LINE Quick Reply で
--   「今日の調子は？」（良い/普通/悪い）を本人だけに送り、回答をその日の
--   健康/文化スコアのスナップショットと共に保存する。蓄積後、
--   カテゴリ重み・しきい値の校正（誤検知の判定）に使う。
-- 形式は「昨日比 yes/no」ではなく絶対評価: 相対回答は微分値になり、
--   その日の絶対スコアと直接突き合わせられないため（2026-07-08 決定）。
-- 未回答の日はレコードなし（ペナルティなし）。

CREATE TABLE IF NOT EXISTS subjective_feedback (
    date TEXT PRIMARY KEY,        -- 質問対象日 YYYY-MM-DD
    answer TEXT NOT NULL CHECK (answer IN ('good', 'normal', 'bad')),
    answered_at TEXT NOT NULL DEFAULT (datetime('now')),
    -- 回答時点のスコアスナップショット（後の校正で「スコア vs 主観」を比較する用）
    health_score REAL,
    cultural_score REAL,
    health_status TEXT,
    cultural_status TEXT
);
