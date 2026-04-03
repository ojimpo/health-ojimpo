-- NextDNS SNS: daily SNS service query counts
CREATE TABLE IF NOT EXISTS nextdns_sns (
    date TEXT NOT NULL,
    service TEXT NOT NULL,
    queries INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (date, service)
);
