-- Q12 New-customer repeat rate within 30 days
-- Business question: Of customers whose first delivered order was in month M, what share placed a second delivered
-- order within 30 days of the first? is_mature = every cohort member has had a full 30-day window in the data.
WITH ranked AS (
    SELECT f.customer_key, f.created_at,
           row_number() OVER (PARTITION BY f.customer_key ORDER BY f.created_at, f.order_id) AS n
    FROM core.fact_orders f WHERE f.is_delivered
), firsts AS (
    SELECT r1.customer_key, r1.created_at AS first_at,
           date_trunc('month', r1.created_at AT TIME ZONE 'Asia/Jakarta')::date AS cohort_month,
           r2.created_at AS second_at
    FROM ranked r1 LEFT JOIN ranked r2 ON r2.customer_key = r1.customer_key AND r2.n = 2
    WHERE r1.n = 1
)
SELECT cohort_month,
       count(*) AS new_customers,
       count(*) FILTER (WHERE second_at <= first_at + interval '30 days') AS repeated_within_30d,
       round(100.0 * count(*) FILTER (WHERE second_at <= first_at + interval '30 days') / count(*), 2) AS repeat_rate_pct,
       (cohort_month + interval '1 month' + interval '30 days')::date
           <= (SELECT max(created_at AT TIME ZONE 'Asia/Jakarta')::date FROM core.fact_orders) + 1 AS is_mature
FROM firsts
GROUP BY cohort_month
ORDER BY cohort_month;
