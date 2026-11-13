-- Q04 Monthly cohort retention
-- Business question: Of the customers whose first delivered order was in month M, what share ordered again in month M+k?
-- Cohort = month of first DELIVERED order. Full matrix (zeros included) up to the last month in the data.
WITH cust_month AS (
    SELECT DISTINCT f.customer_key, d.month_start AS month
    FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
    WHERE f.is_delivered
), cohort AS (
    SELECT customer_key, min(month) AS cohort_month FROM cust_month GROUP BY customer_key
), sizes AS (
    SELECT cohort_month, count(*) AS cohort_size FROM cohort GROUP BY cohort_month
), grid AS (
    SELECT s.cohort_month, s.cohort_size, g.month,
           (extract(year FROM age(g.month, s.cohort_month)) * 12 + extract(month FROM age(g.month, s.cohort_month)))::int AS months_since
    FROM sizes s
    CROSS JOIN LATERAL generate_series(s.cohort_month, (SELECT max(month) FROM cust_month), interval '1 month') AS g(month)
)
SELECT g.cohort_month, g.cohort_size, g.months_since,
       count(cm.customer_key)                                   AS active_customers,
       round(100.0 * count(cm.customer_key) / g.cohort_size, 2) AS retention_pct
FROM grid g
LEFT JOIN cohort c   ON c.cohort_month = g.cohort_month
LEFT JOIN cust_month cm ON cm.customer_key = c.customer_key AND cm.month = g.month
GROUP BY g.cohort_month, g.cohort_size, g.months_since
ORDER BY g.cohort_month, g.months_since;
