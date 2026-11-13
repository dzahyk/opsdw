-- Q01 Monthly GMV and month-over-month growth
-- Business question: How much delivered GMV did the platform make each month, and how did it move vs the previous month?
-- Grain: calendar month of order creation (WIB). Techniques: month spine via generate_series (missing months = 0), LAG.
WITH monthly AS (
    SELECT d.month_start AS month,
           count(*) FILTER (WHERE f.is_delivered) AS delivered_orders,
           sum(f.gmv)                             AS gmv
    FROM core.fact_orders f
    JOIN core.dim_date d ON d.date_key = f.created_date_key
    GROUP BY d.month_start
), spine AS (
    SELECT generate_series(min(month), max(month), interval '1 month')::date AS month FROM monthly
), filled AS (
    SELECT s.month, coalesce(m.delivered_orders, 0) AS delivered_orders, coalesce(m.gmv, 0) AS gmv
    FROM spine s LEFT JOIN monthly m USING (month)
)
SELECT month, delivered_orders, gmv,
       lag(gmv) OVER w                                                     AS prev_month_gmv,
       round(100.0 * (gmv - lag(gmv) OVER w) / nullif(lag(gmv) OVER w, 0), 2) AS mom_growth_pct
FROM filled
WINDOW w AS (ORDER BY month)
ORDER BY month;
