-- Q14 Year-to-date cumulative GMV by city
-- Business question: How is each city tracking against its year-to-date GMV, month by month?
-- Techniques: running SUM() OVER (PARTITION BY city, year ORDER BY month).
WITH m AS (
    SELECT c.city_name, d.year, d.month_start AS month, sum(f.gmv) AS gmv
    FROM core.fact_orders f
    JOIN core.dim_date d ON d.date_key = f.created_date_key
    JOIN core.dim_city c USING (city_key)
    GROUP BY 1, 2, 3
)
SELECT city_name, month, gmv,
       sum(gmv) OVER (PARTITION BY city_name, year ORDER BY month ROWS UNBOUNDED PRECEDING) AS ytd_gmv
FROM m
ORDER BY city_name, month;
