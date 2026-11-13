-- Recompute only the dates touched by this run (pre- and post-image of affected orders).
CREATE TEMP TABLE aff_dates_u ON COMMIT DROP AS SELECT DISTINCT date_key FROM aff_dates;
ANALYZE aff_dates_u;
DELETE FROM mart.city_daily m USING aff_dates_u a WHERE m.date_key = a.date_key;
INSERT INTO mart.city_daily
SELECT f.created_date_key, f.city_key,
       count(*),
       count(*) FILTER (WHERE f.is_delivered),
       count(*) FILTER (WHERE f.is_cancelled),
       count(*) FILTER (WHERE f.is_on_time),
       sum(f.gmv),
       sum(f.commission_amount),
       coalesce(sum(f.delivery_minutes) FILTER (WHERE f.is_delivered), 0)
FROM core.fact_orders f
JOIN aff_dates_u a ON a.date_key = f.created_date_key
GROUP BY f.created_date_key, f.city_key;
