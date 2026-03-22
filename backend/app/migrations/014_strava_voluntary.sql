-- Strava: merge commute into base exercise, rename ride bonus to voluntary
-- strava now includes ALL activities (commute + non-commute)
-- strava_voluntary replaces strava_ride: non-commute activities in minutes (event bonus)
-- strava_commute is disabled (absorbed into strava)

-- Update strava: base_value adjusted for combined commute + non-commute
UPDATE source_settings SET
    base_value = 180,
    base_unit = 'min'
WHERE id = 'strava';

-- Disable strava_commute (absorbed into strava)
UPDATE source_settings SET status = 'disabled' WHERE id = 'strava_commute';

-- Disable old strava_ride (replaced by strava_voluntary)
UPDATE source_settings SET status = 'disabled' WHERE id = 'strava_ride';

-- Create strava_voluntary: non-commute activities in minutes (event bonus)
INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, display_type, classification, phase, status,
     color, show_personal, show_shared, aggregation_period, base_value,
     base_unit, spontaneity_coefficient, sort_order, score_method)
VALUES
    ('strava_voluntary', '自発的運動 (Strava)', 'exercise', '🏃', 'activity',
     'event', 'phase2', 'active', '#FF3366', 1, 1, 7, 120, 'min',
     1.0, 17, 'sum');
