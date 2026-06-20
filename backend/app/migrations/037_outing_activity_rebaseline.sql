-- 外出 activity カード(nextdns_outing_activity)が常に200点超で張り付いていた問題の修正。
-- 原因: base_value=63000 は 2026-04-04 設定の「旧 cellular クエリ方式(≒9000q/日×7)」由来。
--       2026-05-26 に外出判定を「自宅都市以外=外出(会社Wi-Fi含む)」へ変えて外出クエリが激増
--       (新ロジック後 中央値18,867q/日)したのに base_value が置き去りで、約2倍に膨張していた。
-- 対応: 新ロジックの再fetchデータが始まる日(2026-04-26、5/26に30日分再fetちした境界)を
--       effective_from として baseline_history に新基準を記録。中央値~17,000q/日×7 ≒ 132,000 を
--       100点に対応させる。baseline_history 優先で日付対応のため、2026-04-25 以前(旧ロジック
--       ~9,000q/日)は旧 63000 のまま正しく~100点で再現され、境界で段差が出ない。
--       ※ effective_from を新ロジック開始日(4/26)に合わせるのが肝。ここを5/27等にすると
--         4/26〜境界の新ロジック高クエリが旧基準で計算され187等に膨張する人工的な段差が出る。
-- baseline_history は (source_id, effective_from) に UNIQUE 制約が無く、init_db は
-- 毎起動で全マイグレーションを再実行するため、素の INSERT だと重複行が増える。
-- WHERE NOT EXISTS で冪等化する。
INSERT INTO baseline_history (source_id, effective_from, base_value, base_unit, memo)
SELECT
    'nextdns_outing_activity',
    '2026-04-26',
    132000,
    'queries',
    '新外出ロジック(自宅都市以外=外出)へ再較正。実測中央値~17000q/日×7。4/26は5/26の30日再fetch境界=新ロジックデータ開始日。旧63000は旧cellular方式由来で2倍膨張していた'
WHERE NOT EXISTS (
    SELECT 1 FROM baseline_history
    WHERE source_id = 'nextdns_outing_activity' AND effective_from = '2026-04-26'
);

-- source_settings 側の現在値も合わせる(設定画面表示・履歴非対応コード経路のため)。
UPDATE source_settings SET base_value = 132000 WHERE id = 'nextdns_outing_activity';
