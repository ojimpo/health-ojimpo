-- NextDNS outing estimation: daily cellular query counts from mobile device
CREATE TABLE IF NOT EXISTS nextdns_outing (
    date TEXT PRIMARY KEY,
    cellular_queries INTEGER NOT NULL DEFAULT 0,
    total_queries INTEGER NOT NULL DEFAULT 0
);
