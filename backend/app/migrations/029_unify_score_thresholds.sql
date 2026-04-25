-- 029: health/cultural の閾値を score_* に統合（4個 → 2個）
-- SCORE モードチャートで両方が同じ右Y軸 [0,140] を共有しバンドを描いているため、
-- 別々の閾値を持つと表示と判定がズレる。視覚と一致させて単一設定に統合する。

-- 新キーを挿入（フレッシュDB向けのデフォルト）
INSERT OR IGNORE INTO global_settings (key, value) VALUES
    ('score_normal_threshold', '70'),
    ('score_caution_threshold', '40');

-- 旧キーが残っていればその値を引き継ぐ（カスタマイズ済みの環境対応）
UPDATE global_settings
SET value = (SELECT value FROM global_settings WHERE key = 'health_normal_threshold')
WHERE key = 'score_normal_threshold'
  AND EXISTS (SELECT 1 FROM global_settings WHERE key = 'health_normal_threshold');

UPDATE global_settings
SET value = (SELECT value FROM global_settings WHERE key = 'health_caution_threshold')
WHERE key = 'score_caution_threshold'
  AND EXISTS (SELECT 1 FROM global_settings WHERE key = 'health_caution_threshold');

-- 旧キーを削除
DELETE FROM global_settings WHERE key IN (
    'health_normal_threshold',
    'health_caution_threshold',
    'cultural_rich_threshold',
    'cultural_moderate_threshold'
);