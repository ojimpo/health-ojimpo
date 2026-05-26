-- 外出判定の精度を上げるため「自宅IP判定」を追加。
-- 旧 cellular_queries は cellular ネットワーク経由のクエリ数（≒移動中）。
-- 新 outing_queries は「自宅IP以外（cellular + 会社/カフェWi-Fi + ホテル等）」のクエリ数。
-- 自宅判定: network.cellular=false AND geo.city IN OUTING_HOME_CITIES
ALTER TABLE nextdns_outing ADD COLUMN outing_queries INTEGER DEFAULT 0;
ALTER TABLE nextdns_outing ADD COLUMN home_queries INTEGER DEFAULT 0;

-- 既存データの暫定値：cellular_queries を outing_queries にコピー（旧ロジック相当）。
-- これは再fetchで上書きされ、再fetch可能な範囲（NextDNS保持期間内）は新ロジックの値になる。
UPDATE nextdns_outing SET outing_queries = cellular_queries WHERE outing_queries = 0;
UPDATE nextdns_outing SET home_queries = total_queries - cellular_queries WHERE home_queries = 0;
