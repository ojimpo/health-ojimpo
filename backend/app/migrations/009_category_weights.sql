-- Category-level weights for daily_avg scoring (JSON)
-- Column may already exist from previous run; handled by init_db error recovery
ALTER TABLE source_settings ADD COLUMN category_weights TEXT DEFAULT NULL;
