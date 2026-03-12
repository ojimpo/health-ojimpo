-- Oura: daily_avg scoring with category weights
-- Readiness 0.6 / Sleep 0.4 (Readiness already includes sleep components)
-- base_value = 80 (weighted expected: 80*0.6 + 80*0.4 = 80)
-- Safe to re-run (UPDATE is idempotent)
UPDATE source_settings
SET score_method = 'daily_avg',
    base_value = 80,
    category_weights = '{"readiness": 0.6, "sleep": 0.4}'
WHERE id = 'oura';
