-- Q05 Rolling 28-day active customers
-- Business question: How many distinct customers had at least one delivered order in the trailing 28 days, for each of the
-- latest 30 days in the data? (distinct counts are non-additive, so this cannot be summed from daily counts)
-- Techniques: date spine + range join, COUNT(DISTINCT).
WITH bounds AS (
    SELECT max(d.date) AS last_day FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
), days AS (
    SELECT generate_series(last_day - 29, last_day, interval '1 day')::date AS day FROM bounds
), delivered AS (
    SELECT f.customer_key, d.date AS order_day
    FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
    WHERE f.is_delivered AND d.date >= (SELECT last_day - 29 - 27 FROM bounds)
)
SELECT days.day, count(DISTINCT x.customer_key) AS active_customers_28d
FROM days
LEFT JOIN delivered x ON x.order_day BETWEEN days.day - 27 AND days.day
GROUP BY days.day
ORDER BY days.day;
