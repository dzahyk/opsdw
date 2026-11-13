-- Q06 Delivery time percentiles by city
-- Business question: What is the typical (P50) and tail (P90/P95) end-to-end delivery time per city?
-- delivery_minutes = delivered_at - created_at. percentile_cont = linear interpolation (same as Excel/DAX PERCENTILE.INC).
SELECT CASE WHEN grouping(c.city_name) = 1 THEN 'All cities' ELSE c.city_name END AS city,
       count(*) AS delivered_orders,
       round(percentile_cont(0.50) WITHIN GROUP (ORDER BY f.delivery_minutes)::numeric, 2) AS p50_minutes,
       round(percentile_cont(0.90) WITHIN GROUP (ORDER BY f.delivery_minutes)::numeric, 2) AS p90_minutes,
       round(percentile_cont(0.95) WITHIN GROUP (ORDER BY f.delivery_minutes)::numeric, 2) AS p95_minutes
FROM core.fact_orders f
JOIN core.dim_city c USING (city_key)
WHERE f.is_delivered
GROUP BY GROUPING SETS ((c.city_name), ())
ORDER BY grouping(c.city_name), c.city_name;
