-- Q16 Churn risk of repeat customers by acquisition channel
-- Business question: Which acquisition channels' repeat customers (>= 2 delivered orders) have gone quiet, i.e. their
-- last delivered order is more than 30 days before the latest data date (none in [as_of - 30, as_of])?
WITH as_of AS (
    SELECT max(created_at AT TIME ZONE 'Asia/Jakarta')::date AS as_of_date FROM core.fact_orders
), repeaters AS (
    SELECT f.customer_key, count(*) AS orders, sum(f.gmv) AS lifetime_gmv,
           max(f.created_at AT TIME ZONE 'Asia/Jakarta')::date AS last_order_date
    FROM core.fact_orders f WHERE f.is_delivered
    GROUP BY f.customer_key HAVING count(*) >= 2
)
SELECT c.acquisition_channel,
       count(*) AS repeat_customers,
       count(*) FILTER (WHERE r.last_order_date < a.as_of_date - 30) AS at_risk_customers,
       round(100.0 * count(*) FILTER (WHERE r.last_order_date < a.as_of_date - 30) / count(*), 2) AS at_risk_pct,
       coalesce(sum(r.lifetime_gmv) FILTER (WHERE r.last_order_date < a.as_of_date - 30), 0) AS at_risk_lifetime_gmv
FROM repeaters r
JOIN core.dim_customer c USING (customer_key)
CROSS JOIN as_of a
GROUP BY c.acquisition_channel
ORDER BY c.acquisition_channel;
