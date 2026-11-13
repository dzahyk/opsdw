-- K08 Commission Revenue (IDR) — canonical SQL definition (source of truth for kpis/kpis.yml).
-- Grain of the result: calendar month of order creation (WIB) x city, plus an 'ALL' city total per month.
SELECT d.year_month,
       CASE WHEN grouping(c.city_code) = 1 THEN 'ALL' ELSE c.city_code END AS city_code,
       sum(f.commission_amount) AS value
FROM core.fact_orders f
JOIN core.dim_date d ON d.date_key = f.created_date_key
JOIN core.dim_city c ON c.city_key = f.city_key
GROUP BY GROUPING SETS ((d.year_month, c.city_code), (d.year_month))
ORDER BY 1, 2;
