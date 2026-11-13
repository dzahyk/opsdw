-- Dashboard dataset, non-additive part (percentile, distinct count): these cannot be rolled up
-- from the mart, so they are evaluated on order rows for every (month, city) AND (month, all cities).
SELECT d.year_month, CASE WHEN grouping(c.city_code) = 1 THEN 'ALL' ELSE c.city_code END AS city_code,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY f.delivery_minutes) AS p90_delivery_minutes,
       count(DISTINCT f.customer_key) AS monthly_active_customers
FROM bi.fact_orders f
JOIN bi.dim_date d ON d.date_key = f.created_date_key
JOIN bi.dim_city c ON c.city_key = f.city_key
WHERE f.is_delivered = 1
GROUP BY GROUPING SETS ((d.year_month, c.city_code), (d.year_month));
