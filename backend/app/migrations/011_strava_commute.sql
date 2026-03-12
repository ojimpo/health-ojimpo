-- Strava: 3-source split (exercise/commute/ride bonus)
-- Commute vs non-commute distinguished by commute flag (not gear)
-- gear_id stored for future reference only
ALTER TABLE strava_activities ADD COLUMN gear_id TEXT;

-- strava: all non-commute activities in minutes (baseline)
UPDATE source_settings SET
    classification = 'baseline',
    base_value = 210,
    base_unit = 'min',
    aggregation_period = 7
WHERE id = 'strava';

-- strava_commute: commute rides in minutes (baseline)
INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, display_type, classification, phase, status,
     color, show_personal, show_shared, aggregation_period, base_value,
     base_unit, spontaneity_coefficient, sort_order, score_method)
VALUES
    ('strava_commute', '通勤 (Strava)', 'commute', '🚲', 'activity',
     'baseline', 'phase2', 'active', '#FF79C6', 1, 1, 7, 100, 'min',
     1.0, 18, 'sum');

-- Update existing strava_commute if it already exists with old values
UPDATE source_settings SET
    base_value = 100,
    base_unit = 'min',
    aggregation_period = 7
WHERE id = 'strava_commute';

-- strava_ride: non-commute Ride distance bonus (event)
INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, display_type, classification, phase, status,
     color, show_personal, show_shared, aggregation_period, base_value,
     base_unit, spontaneity_coefficient, sort_order, score_method)
VALUES
    ('strava_ride', 'ライド (Strava)', 'exercise', '🚴', 'activity',
     'event', 'phase2', 'active', '#FF3366', 1, 1, 7, 50, 'km',
     1.0, 17, 'sum');
