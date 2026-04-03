-- NextDNS shopping: daily EC site query counts
CREATE TABLE IF NOT EXISTS nextdns_shopping (
    date TEXT NOT NULL,
    domain TEXT NOT NULL,
    queries INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, domain)
);
