-- NextDNS Vitality Index: aggregate daily query counts only (no domain names stored)
CREATE TABLE IF NOT EXISTS nextdns_vitality (
    date TEXT PRIMARY KEY,
    queries INTEGER NOT NULL DEFAULT 0
);
