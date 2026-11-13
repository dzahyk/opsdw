-- Periodic snapshot mart: ADDITIVE measures only, per day x city (by order
-- created date). Non-additive KPIs (distinct customers, percentiles) are
-- deliberately not stored here; they are computed from the fact table.
CREATE TABLE IF NOT EXISTS mart.city_daily (
    date_key               integer  NOT NULL,
    city_key               smallint NOT NULL,
    orders_created         integer  NOT NULL,
    orders_delivered       integer  NOT NULL,
    orders_cancelled       integer  NOT NULL,
    orders_on_time         integer  NOT NULL,
    gmv                    numeric(16,2) NOT NULL,
    commission_amount      numeric(16,2) NOT NULL,
    delivery_minutes_sum   numeric(16,2) NOT NULL,
    PRIMARY KEY (date_key, city_key)
);
