-- 047: ソースの「計測が壊れているか」を持つ（2026-08-16）
--
-- 背景:
--   スコアは「やっていない」と「計測が壊れている」を区別できていなかった。
--   Last.fm は 2026-07-24 に Spotify 連携が失効して scrobble が 100〜140件/日 →
--   週数件に崩壊したが、トークンは有効・ingest も成功・レコードも存在したため、
--   データ上は「音楽を聴く量が98%減った」という正常な観測と完全に同じ形だった。
--   その結果、音楽カテゴリが 131 → 8 になり健康スコアが誤って CAUTION に落ちた
--   （同期間の主観フィードバックは good/normal のみ、bad はゼロ）。
--
-- 設計の肝 — 除外は「値が低いこと」を条件にしない:
--   値の低さで除外すると、本物の活動低下まで一緒に消えてしまい、健康軸の
--   存在意義が無くなる。除外には必ず「計測が壊れている積極的な証拠」を要求する。
--     reason='token'         OAuthトークンの失効（実refreshで確認済み）
--     reason='ingest_failed' 直近のingestが失敗
--     reason='user_reported' 取得量の急減を検知してLINEで聞き、本人が「壊れている」と答えた
--   取得量の急減それ自体は証拠にしない（本物の低下と区別がつかないため）。
--   曖昧なケースは本人にしか判断できないので聞く。
--
-- 反映のされ方:
--   カテゴリのスコアは broken でないソースだけの平均を採る（運動=strava+oura_steps、
--   活力=nextdns+stash のように片方だけ壊れても、生きている側で計測が続く）。
--   カテゴリ内の全ソースが broken になったらそのカテゴリは UNKNOWN として軸集計から
--   外す。ただし UNKNOWN が増えたときスコアが「良く」なってはいけないので、
--   計測できているカテゴリが一定数を割ったら軸自体を UNKNOWN 扱いにする
--   （services/measurement_state.py の MIN_MEASURABLE_CATEGORIES）。
--
-- 復帰:
--   データが正常な量で戻ったら自動で 'ok' に戻す。本人が申告した場合も同じで、
--   解除操作は要求しない（申告しっぱなしで永久に除外され続けるのを防ぐ）。

CREATE TABLE IF NOT EXISTS source_measurement_state (
    source_id   TEXT PRIMARY KEY,
    state       TEXT NOT NULL DEFAULT 'ok',   -- 'ok' | 'broken'
    reason      TEXT,                          -- 'token' | 'ingest_failed' | 'user_reported'
    detail      TEXT,
    detected_at TEXT,                          -- broken になった時刻（UTC）
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    asked_at    TEXT                           -- 取得量急減をLINEで聞いた最終時刻（連投防止）
);

CREATE INDEX IF NOT EXISTS idx_source_measurement_state_state
    ON source_measurement_state(state);
