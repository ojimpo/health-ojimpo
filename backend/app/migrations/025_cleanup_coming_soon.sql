-- Clean up FK references before deleting source_settings rows
DELETE FROM oauth_tokens WHERE source_id IN ('strava_commute', 'strava_ride', 'strava_voluntary', 'instagram', 'twitter', 'spotify_pod', 'gcal_holiday', 'gmail', 'openai');
DELETE FROM baseline_history WHERE source_id IN ('strava_commute', 'strava_ride', 'strava_voluntary', 'instagram', 'twitter', 'spotify_pod', 'gcal_holiday', 'gmail', 'openai');

-- Remove obsolete/replaced/disabled entries
DELETE FROM source_settings WHERE id = 'spotify_pod';
DELETE FROM source_settings WHERE id = 'gcal_holiday';
DELETE FROM source_settings WHERE id = 'gmail';
DELETE FROM source_settings WHERE id = 'openai';
DELETE FROM source_settings WHERE id = 'strava_commute';
DELETE FROM source_settings WHERE id = 'strava_ride';
DELETE FROM source_settings WHERE id = 'strava_voluntary';
DELETE FROM source_settings WHERE id = 'instagram';
DELETE FROM source_settings WHERE id = 'twitter';
DELETE FROM source_settings WHERE id = 'bathmat';
