-- Q03 Order lifecycle funnel by city
-- Business question: Where in the lifecycle (assignment, pickup, delivery) do orders drop out, per city?
-- Step rates are conditional on reaching the previous step. Techniques: FILTER aggregates, GROUPING SETS for a total row.
SELECT CASE WHEN grouping(c.city_name) = 1 THEN 'All cities' ELSE c.city_name END AS city,
       count(*)                                        AS created,
       count(f.assigned_at)                            AS assigned,
       count(f.picked_up_at)                           AS picked_up,
       count(f.delivered_at)                           AS delivered,
       round(100.0 * count(f.assigned_at)  / nullif(count(*), 0), 2)              AS pct_assigned,
       round(100.0 * count(f.picked_up_at) / nullif(count(f.assigned_at), 0), 2)  AS pct_picked_up_of_assigned,
       round(100.0 * count(f.delivered_at) / nullif(count(f.picked_up_at), 0), 2) AS pct_delivered_of_picked_up,
       round(100.0 * count(f.delivered_at) / nullif(count(*), 0), 2)              AS pct_end_to_end
FROM core.fact_orders f
JOIN core.dim_city c USING (city_key)
GROUP BY GROUPING SETS ((c.city_name), ())
ORDER BY grouping(c.city_name), c.city_name;
