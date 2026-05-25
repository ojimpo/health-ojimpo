-- 030: GitHub ソースを coding カテゴリの第2ソースとして復活させる
-- 廃止経緯: 2026-04-25 に Claude Code 時間ベースで全コーディングをカバーする方針で disabled 化
-- 復活理由: OSS コントリビューションを文化的指標として捕捉したいユーザー要望
-- カテゴリ内平均方式（2026-05-16〜）なので、claude と github の二重カウントは起きない
UPDATE source_settings
SET status = 'active',
    display_type = 'activity',
    base_value = 14,
    aggregation_period = 7,
    decay_half_life = 7
WHERE id = 'github';
