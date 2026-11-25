-- scrobble-gateway 移行（2026-10-05）のロールバック期間終了に伴う旧資産の撤去。
-- scrobble の完全な履歴は scrobble-gateway が保持し、health-ojimpo は
-- lastfm_daily_plays（migration 050）の日次件数だけを使う。
DROP TABLE IF EXISTS lastfm_scrobbles;
