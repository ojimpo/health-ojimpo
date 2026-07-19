-- 040: 写真カテゴリ (photo) — iPhone撮影 (Immich) + X-E5撮影 (photo-genka) の2ソース
-- 設計: 運動カテゴリ (strava + oura_steps) と同じ「1カテゴリ複数ソース」方式。
--   カテゴリ内平均なので、ソースを2つにしても文化スコア上の重みは1カテゴリ分のまま。
-- スクショ除外: Immich 側は make=Apple + type=IMAGE で絞る（スクリーンショット・保存画像は
--   EXIF にカメラ情報が無いため自然に落ちる）。
-- 「ちゃんとしたカメラに色をつける」: X-E5 は基準値を低め (15枚/週) に設定し、
--   1枚あたりのスコア寄与を iPhone (45枚/週 = 実測 過去13ヶ月平均) の3倍にする。
-- X-E5 の枚数は Immich アセット数ではなくカメラ内シャッターカウンタ (ImageCount) の
--   日次差分 (photo-genka /api/daily-shots)。撮影行為そのものを数える。

INSERT OR IGNORE INTO source_settings
    (id, name, category, icon, color, status, phase, display_type,
     base_value, base_unit, aggregation_period, spontaneity_coefficient, classification,
     decay_half_life, score_method, sort_order)
VALUES
    ('immich_photos', '写真 (iPhone)', 'photo', '📱', '#A2AAAD', 'active', 'phase3', 'activity',
     45, '枚', 7, 1.0, 'event', 7, 'sum', 30),
    ('photo_genka', '写真 (X-E5)', 'photo', '📷', '#01916D', 'active', 'phase3', 'activity',
     15, '枚', 7, 1.0, 'event', 7, 'sum', 31);
