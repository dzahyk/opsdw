-- Q13 Commission: point-in-time tier (SCD2) vs naive current tier
-- Business question: How much would historical commission revenue be mis-stated if we applied each merchant's CURRENT
-- tier instead of the tier valid when the order was placed? (why dim_merchant is SCD2)
WITH x AS (
    SELECT pit.commission_tier AS tier_at_order_time, pit.commission_rate AS rate_at_order_time,
           f.commission_amount AS commission_pit,
           round(f.items_amount * cur.commission_rate, 2) AS commission_current_tier
    FROM core.fact_orders f
    JOIN core.dim_merchant pit ON pit.merchant_key = f.merchant_key
    JOIN core.dim_merchant cur ON cur.merchant_id = f.merchant_id AND cur.is_current
    WHERE f.is_delivered AND f.merchant_key > 0
)
SELECT CASE WHEN grouping(tier_at_order_time) = 1 THEN 'ALL' ELSE tier_at_order_time END AS tier_at_order_time,
       count(*)                     AS delivered_orders,
       sum(commission_pit)          AS commission_point_in_time,
       sum(commission_current_tier) AS commission_if_current_tier,
       sum(commission_current_tier) - sum(commission_pit) AS restatement_error
FROM x
GROUP BY ROLLUP (tier_at_order_time)
ORDER BY grouping(tier_at_order_time), max(rate_at_order_time) DESC;
