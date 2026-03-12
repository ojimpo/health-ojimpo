-- score_method: 'sum' (default) or 'daily_avg'
-- Column may already exist from previous run; handled by init_db error recovery
ALTER TABLE source_settings ADD COLUMN score_method TEXT NOT NULL DEFAULT 'sum';
