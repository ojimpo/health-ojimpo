-- 指数減衰: decay_half_life (日) を source_settings に追加
-- NULL = 従来の窓方式、値あり = 指数減衰方式
ALTER TABLE source_settings ADD COLUMN decay_half_life REAL DEFAULT NULL;

-- 90日イベントソース（gcal, bookmeter, filmarks）のみ decay を適用
-- 7日ソース・30日ソースは窓方式のまま（NULL）
-- 理由: スパース活動ソースに decay を適用すると「来ない日のゼロ」が
--       過小評価につながるため。90日イベント系のスパイク問題のみ解消を目的とする。
UPDATE source_settings SET decay_half_life = 30 WHERE id IN ('gcal_live', 'gcal_holiday', 'bookmeter', 'filmarks');
