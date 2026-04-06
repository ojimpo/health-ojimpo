-- Rename spotify_pod → spotify_podcast, update category/classification/decay
UPDATE source_settings SET
    id = 'spotify_podcast'
WHERE id = 'spotify_pod';

UPDATE source_settings SET
    category = 'podcast',
    classification = 'event',
    decay_half_life = 7,
    status = 'coming_soon'
WHERE id = 'spotify_podcast';

-- Raw table for Spotify podcast plays
CREATE TABLE IF NOT EXISTS spotify_podcast_plays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id TEXT NOT NULL,
    episode_name TEXT NOT NULL,
    show_name TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    played_at TEXT NOT NULL,
    played_date TEXT NOT NULL,
    UNIQUE(episode_id, played_at)
);
