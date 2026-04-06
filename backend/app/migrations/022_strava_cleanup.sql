-- strava系ソースを整理: strava一本化 + decay導入
-- strava_voluntary, strava_ride, strava_commute を廃止（データは残る）
-- strava にdecay_half_life=7を設定してスパイクを平滑化
UPDATE source_settings SET status = 'disabled' WHERE name IN ('自発的運動 (Strava)', 'ライド (Strava)', '通勤 (Strava)');
UPDATE source_settings SET decay_half_life = 7 WHERE name = '運動 (Strava)';
