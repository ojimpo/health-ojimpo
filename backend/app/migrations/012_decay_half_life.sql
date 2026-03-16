-- 指数減衰: decay_half_life (日) を source_settings に追加
-- NULL = 従来の窓方式、値あり = 指数減衰方式
ALTER TABLE source_settings ADD COLUMN decay_half_life REAL DEFAULT NULL;

-- 各ソースの半減期を設定
-- 基本方針: aggregation_period が短い(7日)ソースは7日、長い(90日)は30日
-- daily_avg ソース(oura)は NULL のまま（既存ロジックを維持）
UPDATE source_settings SET decay_half_life = 7   WHERE id IN ('lastfm', 'instagram', 'twitter', 'github', 'claude', 'openai', 'strava', 'strava_commute', 'strava_ride', 'spotify_pod', 'kashidashi_cd');
UPDATE source_settings SET decay_half_life = 30  WHERE id IN ('gcal_live', 'gcal_holiday', 'bookmeter', 'filmarks', 'gmail');
UPDATE source_settings SET decay_half_life = 14  WHERE id IN ('intervals');
-- oura, bathmat は daily_avg / 特殊ソースなので NULL のまま
