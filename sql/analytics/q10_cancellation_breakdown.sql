-- Q10 Cancellation breakdown by lifecycle stage and reason
-- Business question: At which stage and for which reasons are orders cancelled, and how big is each slice?
-- Techniques: GROUPING SETS for reason detail, stage subtotals and a grand total in one pass.
WITH totals AS (
    SELECT count(*) AS all_orders, count(*) FILTER (WHERE is_cancelled) AS all_cancelled FROM core.fact_orders
)
SELECT CASE WHEN grouping(f.cancel_stage) = 1 THEN 'ALL' ELSE f.cancel_stage END  AS cancel_stage,
       CASE WHEN grouping(f.cancel_reason) = 1 THEN 'ALL' ELSE f.cancel_reason END AS cancel_reason,
       count(*)                                          AS cancelled_orders,
       round(100.0 * count(*) / max(t.all_cancelled), 2) AS pct_of_cancellations,
       round(100.0 * count(*) / max(t.all_orders), 2)    AS pct_of_all_orders
FROM core.fact_orders f CROSS JOIN totals t
WHERE f.is_cancelled
GROUP BY GROUPING SETS ((f.cancel_stage, f.cancel_reason), (f.cancel_stage), ())
ORDER BY grouping(f.cancel_stage), f.cancel_stage, grouping(f.cancel_reason), f.cancel_reason;
