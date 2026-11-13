-- Q02 Year-over-year GMV growth by month
-- Business question: For each month that has a same-month-last-year comparison, how much did GMV grow YoY?
-- Techniques: month spine + self-join on (month - 1 year) (robust to gaps, unlike LAG(12)).
WITH monthly AS (
    SELECT d.month_start AS month, sum(f.gmv) AS gmv
    FROM core.fact_orders f JOIN core.dim_date d ON d.date_key = f.created_date_key
    GROUP BY d.month_start
), spine AS (
    SELECT generate_series(min(month), max(month), interval '1 month')::date AS month FROM monthly
), filled AS (
    SELECT s.month, coalesce(m.gmv, 0) AS gmv FROM spine s LEFT JOIN monthly m USING (month)
)
SELECT cur.month, cur.gmv, prev.gmv AS gmv_same_month_last_year,
       round(100.0 * (cur.gmv - prev.gmv) / nullif(prev.gmv, 0), 2) AS yoy_growth_pct
FROM filled cur
JOIN filled prev ON prev.month = (cur.month - interval '1 year')::date
ORDER BY cur.month;
