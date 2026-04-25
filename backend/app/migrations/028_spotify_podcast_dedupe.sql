-- 028: spotify_podcast_plays の重複を解消し、episode_id単独のUNIQUE INDEXを追加
-- 既存UNIQUE(episode_id, played_at) はscan時刻が違うと重複が入ってしまうため不十分。
-- 同一エピソードは1度しか聴取記録しない方針なので episode_id 単独で一意化する。

-- 同じepisode_idで複数レコードがある場合、最小idのみ残す
DELETE FROM spotify_podcast_plays
WHERE id NOT IN (
    SELECT MIN(id) FROM spotify_podcast_plays GROUP BY episode_id
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_spotify_podcast_plays_episode_id
    ON spotify_podcast_plays(episode_id);
