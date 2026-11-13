-- Q09 Top 3 merchants by GMV per city per month
-- Business question: Which merchants drive GMV in each city each month (ties share a rank)?
-- Grouped by the NATURAL merchant_id: grouping by the SCD2 surrogate key would split a merchant across its versions.
WITH m AS (
    SELECT d.month_start AS month, c.city_name, f.merchant_id, sum(f.gmv) AS gmv
    FROM core.fact_orders f
    JOIN core.dim_date d ON d.date_key = f.created_date_key
    JOIN core.dim_city c USING (city_key)
    WHERE f.is_delivered
    GROUP BY 1, 2, 3
), ranked AS (
    SELECT m.*, dense_rank() OVER (PARTITION BY month, city_name ORDER BY gmv DESC) AS gmv_rank FROM m
)
SELECT r.month, r.city_name, r.gmv_rank, r.merchant_id, cur.merchant_name, r.gmv
FROM ranked r
LEFT JOIN core.dim_merchant cur ON cur.merchant_id = r.merchant_id AND cur.is_current   -- keep merchants whose record is late
WHERE r.gmv_rank <= 3
ORDER BY r.month, r.city_name, r.gmv_rank, r.merchant_id;
