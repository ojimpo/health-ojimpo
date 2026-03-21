-- Rename gcal_holiday to gcal_private
-- Disable FK checks during rename
PRAGMA foreign_keys = OFF;
UPDATE activity_records SET source = 'gcal_private' WHERE source = 'gcal_holiday';
UPDATE gcal_events SET source = 'gcal_private' WHERE source = 'gcal_holiday';
UPDATE oauth_tokens SET source_id = 'gcal_private' WHERE source_id = 'gcal_holiday';
UPDATE source_settings SET id = 'gcal_private', name = 'プライベート予定 (Google Calendar)', category = '予定' WHERE id = 'gcal_holiday';
PRAGMA foreign_keys = ON;
