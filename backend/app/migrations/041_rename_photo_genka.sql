-- 041: photo_genka のソース名を「カメラ (X-E5)」に変更
-- トレンドコメントはソース名の「 (」より前をラベルにするため、040 の命名
-- （写真 (iPhone) / 写真 (X-E5)）では「写真」のコメントが2行出て紛らわしかった。
-- 運動カテゴリの「運動 (Strava)」「歩数 (Oura)」と同じく、同一カテゴリ内で
-- 先頭語が重ならないようにする。

UPDATE source_settings SET name = 'カメラ (X-E5)' WHERE id = 'photo_genka';
