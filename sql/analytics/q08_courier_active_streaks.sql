-- Q08 Courier longest consecutive active-day streak (gaps and islands)
-- Business question: Which couriers work the longest unbroken runs of days (fatigue / reliability signal)?
-- Active day = local (WIB) date with >= 1 delivered order. Island key = day - row_number() days.
WITH active AS (
    SELECT DISTINCT f.courier_key, (f.delivered_at AT TIME ZONE 'Asia/Jakarta')::date AS day
    FROM core.fact_orders f
    WHERE f.is_delivered AND f.courier_key > 0
), islands AS (
    SELECT courier_key, day,
           day - (row_number() OVER (PARTITION BY courier_key ORDER BY day))::int AS island
    FROM active
), streaks AS (
    SELECT courier_key, min(day) AS streak_start, max(day) AS streak_end, count(*) AS streak_days
    FROM islands GROUP BY courier_key, island
), ranked AS (
    SELECT s.*, row_number() OVER (PARTITION BY courier_key ORDER BY streak_days DESC, streak_start) AS rn,
           sum(streak_days) OVER (PARTITION BY courier_key) AS active_days
    FROM streaks s
)
SELECT r.courier_id, k.active_days, k.streak_days AS longest_streak_days, k.streak_start, k.streak_end
FROM ranked k JOIN core.dim_courier r USING (courier_key)
WHERE k.rn = 1
ORDER BY longest_streak_days DESC, k.active_days DESC, r.courier_id
LIMIT 10;
