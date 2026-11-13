-- Dashboard dataset, additive part: read from the PERIODIC SNAPSHOT MART (not the fact table).
-- Ratios are NOT computed here: the builder sums numerators and denominators first and divides
-- last, which is the only correct way to roll a ratio up from cities to "All cities".
SELECT d.year_month, c.city_code,
       sum(m.orders_created)    AS orders_created,
       sum(m.orders_delivered)  AS delivered_orders,
       sum(m.orders_cancelled)  AS cancelled_orders,
       sum(m.orders_on_time)    AS on_time_orders,
       sum(m.gmv)               AS gmv,
       sum(m.commission_amount) AS commission_revenue
FROM mart.city_daily m
JOIN core.dim_date d ON d.date_key = m.date_key
JOIN core.dim_city c ON c.city_key = m.city_key
GROUP BY d.year_month, c.city_code
ORDER BY 1, 2;
