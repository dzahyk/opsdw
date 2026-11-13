-- Q07 On-time delivery rate by month and city
-- Business question: What share of delivered orders arrived within the promised time, by month and city?
-- On time = delivered_at <= created_at + promised_minutes (boundary counts as on time).
SELECT d.month_start AS month, c.city_name,
       count(*)                                  AS delivered_orders,
       count(*) FILTER (WHERE f.is_on_time)      AS on_time_orders,
       round(100.0 * count(*) FILTER (WHERE f.is_on_time) / count(*), 2) AS on_time_pct
FROM core.fact_orders f
JOIN core.dim_date d ON d.date_key = f.created_date_key
JOIN core.dim_city c USING (city_key)
WHERE f.is_delivered
GROUP BY d.month_start, c.city_name
ORDER BY d.month_start, c.city_name;
