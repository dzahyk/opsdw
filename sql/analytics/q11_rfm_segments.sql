-- Q11 RFM customer segmentation
-- Business question: How do customers split into value / engagement segments as of the latest data date?
-- R = days since last delivered order (as of the latest order date), F = delivered orders, M = lifetime GMV.
-- Scores = ceil(4 x cume_dist()), 1..4 (4 = best). Unlike NTILE, tied customers always get the SAME score
-- (NTILE splits a tie across buckets by an arbitrary tiebreaker).
WITH as_of AS (
    SELECT max(d.date) AS as_of_date FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
), base AS (
    SELECT f.customer_key, (SELECT as_of_date FROM as_of) - max(d.date) AS recency_days,
           count(*) AS frequency, sum(f.gmv) AS monetary
    FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
    WHERE f.is_delivered
    GROUP BY f.customer_key
), scored AS (
    SELECT b.*, c.customer_id,
           ceil(4 * cume_dist() OVER (ORDER BY recency_days DESC))::int AS r_score,
           ceil(4 * cume_dist() OVER (ORDER BY frequency))::int         AS f_score,
           ceil(4 * cume_dist() OVER (ORDER BY monetary))::int          AS m_score
    FROM base b JOIN core.dim_customer c USING (customer_key)
), segmented AS (
    SELECT *, CASE WHEN r_score = 4 AND f_score >= 3 THEN 'champions'
                   WHEN r_score >= 2 AND f_score >= 3 THEN 'loyal'
                   WHEN r_score >= 3 AND f_score <= 2 THEN 'promising'
                   WHEN r_score <= 2 AND m_score >= 3 THEN 'at_risk'
                   ELSE 'hibernating' END AS segment
    FROM scored
)
SELECT segment, count(*) AS customers,
       round(avg(recency_days), 1) AS avg_recency_days,
       round(avg(frequency), 1)    AS avg_frequency,
       sum(monetary)               AS total_gmv
FROM segmented
GROUP BY segment
ORDER BY segment;
