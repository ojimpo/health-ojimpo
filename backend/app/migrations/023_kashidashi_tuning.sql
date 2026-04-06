-- kashidashi_cd: musicから独立カテゴリ化 + base_value調整 + decay導入
-- 音楽（聴く行為）とCD貸出（図書館で借りる行為）は性質が異なるため分離
-- 週20枚（上限）→16枚（実態：週4回×4枚）に修正
-- decay_half_life=7でバースト的な貸出パターンを平滑化
UPDATE source_settings SET category = 'cd', base_value = 16, decay_half_life = 7, color = '#FF79C6' WHERE name = 'CD貸出 (kashidashi)';
UPDATE activity_records SET category = 'cd' WHERE source = 'kashidashi_cd';

-- カテゴリカラーをサービスブランドに合わせて統一
UPDATE source_settings SET color = '#FC4C02' WHERE category = 'exercise';
UPDATE source_settings SET color = '#FF3366' WHERE category = 'calendar';
UPDATE source_settings SET color = '#7C3AED' WHERE category = 'live';
UPDATE source_settings SET color = '#FFD700' WHERE category = 'movie';
UPDATE source_settings SET color = '#D4A574' WHERE category = 'vitality';
UPDATE source_settings SET color = '#66BB6A' WHERE category = 'outing_activity';
UPDATE source_settings SET color = '#66BB6A' WHERE category = 'outing';
