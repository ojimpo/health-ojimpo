-- Spotify recently-played の再生履歴（Last.fm 監視用の影データ）
-- スコアには一切参加しない。Last.fm scrobble との乖離検知にのみ使う。
-- 背景: 2026-07 に Last.fm の Spotify 連携が失効し、scrobble が届かないまま
-- 健康スコアが誤って CAUTION に落ちた。Spotify 側の再生記録と突き合わせれば
-- 「聴いているのに scrobble が無い」を翌日には確定できる。
CREATE TABLE IF NOT EXISTS spotify_play_history (
    played_at TEXT NOT NULL,        -- ISO8601 UTC（Spotify API の値そのまま）
    track_id TEXT NOT NULL,
    track_name TEXT NOT NULL DEFAULT '',
    artist_name TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    play_date TEXT NOT NULL,        -- UTC 日付（lastfm_scrobbles.scrobbled_date と同じ基準）
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (played_at, track_id)
);

CREATE INDEX IF NOT EXISTS idx_spotify_play_history_date
    ON spotify_play_history(play_date);
