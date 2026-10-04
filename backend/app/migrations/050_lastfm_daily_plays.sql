-- Last.fm の日ごとの再生件数（UTC 日付）。scrobble-gateway から受け取る派生値。
-- 背景: Last.fm の API キーと scrobble の完全な履歴は scrobble-gateway
-- （~/dev/scrobble-gateway）に一本化した。health-ojimpo が Last.fm から使っていたのは
-- 日ごとの件数だけ（日次の再生時間・ダッシュボード・Spotify との乖離検知）なので、
-- それだけを持つ。lastfm_scrobbles はロールバック期間が終わるまで凍結して残す。
CREATE TABLE IF NOT EXISTS lastfm_daily_plays (
    date TEXT PRIMARY KEY,          -- UTC 日付（lastfm_scrobbles.scrobbled_date と同じ基準）
    plays INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 切り替えの瞬間にダッシュボードが空にならないよう、既存の scrobble から埋めておく。
-- 正しい値は最初の取り込み（全期間の取り直し）で scrobble-gateway の値に上書きされる。
INSERT OR IGNORE INTO lastfm_daily_plays (date, plays)
SELECT scrobbled_date, COUNT(*) FROM lastfm_scrobbles GROUP BY scrobbled_date;
