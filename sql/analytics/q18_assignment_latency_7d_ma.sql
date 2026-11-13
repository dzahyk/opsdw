-- Q18 Courier assignment latency with a 7-day moving average
-- Business question: How long do orders wait for a courier, and what is the smoothed weekly trend?
-- MA is order-weighted (sum of minutes / number of orders over the 7 calendar days ending that day),
-- using a RANGE frame on the date so days without orders do not shift the window.
WITH daily AS (
    SELECT d.date AS day, count(*) AS orders_assigned, sum(f.assign_latency_min) AS latency_sum
    FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
    WHERE f.assigned_at IS NOT NULL
    GROUP BY d.date
)
SELECT day, orders_assigned,
       round(latency_sum / orders_assigned, 2) AS avg_latency_min,
       round(sum(latency_sum) OVER w / sum(orders_assigned) OVER w, 2) AS ma7_latency_min
FROM daily
WINDOW w AS (ORDER BY day RANGE BETWEEN interval '6 days' PRECEDING AND CURRENT ROW)
ORDER BY day;
