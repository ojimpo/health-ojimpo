-- Remove duplicate kashidashi_cd records with old category='music'
-- After category rename to 'cd', the adapter still inserted with 'music',
-- causing duplicate rows that bypassed UNIQUE(date, source, category)
DELETE FROM activity_records WHERE source = 'kashidashi_cd' AND category = 'music';
