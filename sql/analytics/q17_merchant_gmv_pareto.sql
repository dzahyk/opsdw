-- Q17 Merchant GMV concentration (Pareto)
-- Business question: How concentrated is GMV: how many merchants make up 80% of GMV, and what share do the top 20% hold?
-- Techniques: cumulative window share, ceil-based top-N.
WITH m AS (
    SELECT merchant_id, sum(gmv) AS gmv FROM core.fact_orders WHERE is_delivered GROUP BY merchant_id HAVING sum(gmv) > 0
), cum AS (
    SELECT merchant_id, gmv,
           row_number() OVER (ORDER BY gmv DESC, merchant_id) AS rnk,
           sum(gmv) OVER (ORDER BY gmv DESC, merchant_id ROWS UNBOUNDED PRECEDING) / sum(gmv) OVER () AS cum_share,
           count(*) OVER () AS n
    FROM m
)
SELECT max(n) AS merchants_with_gmv,
       min(rnk) FILTER (WHERE cum_share >= 0.8) AS merchants_for_80pct_gmv,
       round(100.0 * min(rnk) FILTER (WHERE cum_share >= 0.8) / max(n), 2) AS pct_merchants_for_80pct_gmv,
       ceil(0.2 * max(n))::int AS top_20pct_merchant_count,
       round(100.0 * sum(gmv) FILTER (WHERE rnk <= ceil(0.2 * n)) / sum(gmv), 2) AS top_20pct_gmv_share_pct
FROM cum;
