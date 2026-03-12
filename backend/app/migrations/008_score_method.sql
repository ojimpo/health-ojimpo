-- Add score_method column to source_settings
-- 'sum' (default): SUM over period / base_value (weekly total)
-- 'daily_avg': AVG of daily values / base_value (daily expected)
ALTER TABLE source_settings ADD COLUMN score_method TEXT NOT NULL DEFAULT 'sum';

-- Oura uses daily average scoring (readiness + sleep are daily 0-100 scores)
-- base_value = 160 = expected daily total (readiness 80 + sleep 80)
UPDATE source_settings SET score_method = 'daily_avg', base_value = 160 WHERE id = 'oura';
