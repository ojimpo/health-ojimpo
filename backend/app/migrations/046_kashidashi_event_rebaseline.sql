-- 046: CD貸出(kashidashi_cd)を event に再分類し、episodic ソースの規約(90日/half_life 30)へ揃える。
--
-- 経緯1（分類）:
--   classification=baseline は「ゼロが異常」という意味だが、図書館でCDを借りるのは
--   通館したときにまとめて4枚、という間欠的な行動で「今週0枚」は異常ではない。
--   実測でも 2026-06 以降は約13日に1回のペースで、filmarks(15日に1回) と同じ形をしている。
--   baseline のままだと健康軸(7カテゴリの平均)に常時参加し、借りていない期間は一桁
--   スコアで固定されて軸を約13点押し下げ続けていた（2026-08-16 時点で健康56.2のうち
--   CD貸出7.5と音楽8.0の2カテゴリだけで低下分の88%を占めていた）。
--
-- 経緯2（減衰）:
--   7日/half_life 7 は「ほぼ毎日やること」向けの設定。2週間に1回の行動だと次に借りる頃
--   には前回分が28%まで減衰しており、6月以降スコアが常時5〜7点に張り付いて情報量が
--   無くなっていた。
--
-- 経緯3（基準値）:
--   16枚/7日 は 2.29枚/日 相当。最も集中していた 2026-03〜05 ですら 1.63枚/日 で、
--   ピーク時でも届かない過大な設定だった。48枚/90日 = 週1回の通館 × 4枚 に置き直す。
--
-- 対応:
--   classification: baseline -> event
--     （健康軸から外れる。display_type=activity は変えないので、文化スコアと
--       積み上げチャートには従来どおり参加する）
--   aggregation_period / decay_half_life: 7/7 -> 90/30
--     （gcal_private, gcal_live, bookmeter, filmarks と同じ episodic 規約）
--   base_value: 16 -> 48
--
-- baseline_history は使わず遡及適用する（042 と同じ方針）。計測方法は何も変わって
-- おらず較正の判断を変えただけなので、日付で切ると境界に人工的な段差が出る。
--
-- 副作用（意図したもの）: 週次ソースヘルスレポートの途絶しきい値が baseline系3日から
-- event系45日になり、借りていない期間に出続けていた 🟡 が消える。取得量の急減チェック
-- (source_health._volume_checkable) の対象からも外れる。kashidashi の収集自体は健全で
-- あることを 2026-08-16 に確認済み（減少は本物の行動変化）。
UPDATE source_settings
SET classification = 'event',
    base_value = 48,
    aggregation_period = 90,
    decay_half_life = 30
WHERE id = 'kashidashi_cd';
