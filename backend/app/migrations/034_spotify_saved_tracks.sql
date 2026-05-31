-- 034: Spotify Saved Tracks (Like) tracking
-- カテゴリ: like (Spotify Web API, GET /v1/me/tracks)
-- 設計: Spotifyで❤️した楽曲を added_at の日付別に集計し、曲数を category=like に集約
-- 動機: 再生(Last.fm scrobble)とは別に「能動的にdigしている／音楽をいいと感じている」シグナルを独立して捕捉
-- 認証: 既存 spotify_podcast トークンの user-library-read スコープを共有（専用トークンは持たない）

CREATE TABLE IF NOT EXISTS spotify_saved_tracks (
    track_id TEXT PRIMARY KEY,
    track_name TEXT NOT NULL,
    artist_name TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL,
    saved_date TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spotify_saved_date ON spotify_saved_tracks(saved_date);

INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification,
     decay_half_life, score_method, sort_order)
VALUES
    ('spotify_saved', '好きな曲 (Spotify)', 'like', '❤️', '#E0245E', 'active', 'phase3', 'activity',
     30, '曲', 7, 1.0, 'event', 7, 'sum', 20);
