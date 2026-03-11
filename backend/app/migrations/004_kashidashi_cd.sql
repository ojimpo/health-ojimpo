-- Replace kashidashi (book+CD mixed) with kashidashi_cd (CD only, music category)
-- Old kashidashi data included book lending which is now covered by bookmeter

-- Remove old kashidashi source and its records
DELETE FROM activity_records WHERE source = 'kashidashi';
DELETE FROM source_settings WHERE id = 'kashidashi';

-- Add new kashidashi_cd source (CD lending as music indicator)
-- Base: 20 CDs/week (4/day * 5 weekdays)
INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification)
VALUES
    ('kashidashi_cd', 'CD貸出 (kashidashi)', 'music', '💿', '#00BFFF', 'active', 'mvp', 'activity',
     20, '枚', 7, 1.0, 'baseline');
