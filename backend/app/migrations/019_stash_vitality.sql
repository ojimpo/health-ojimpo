-- Stash vitality: daily play counts and o counts from local media manager
CREATE TABLE IF NOT EXISTS stash_vitality (
    date TEXT PRIMARY KEY,
    play_count INTEGER NOT NULL DEFAULT 0,
    o_count INTEGER NOT NULL DEFAULT 0
);
