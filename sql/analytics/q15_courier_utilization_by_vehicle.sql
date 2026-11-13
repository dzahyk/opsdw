-- Q15 Courier utilisation by vehicle type
-- Business question: How productive is each vehicle type (orders per active courier-day, delivery speed)?
-- Active courier-day = distinct (courier, WIB delivery date) with >= 1 delivered order.
SELECT r.vehicle_type,
       count(DISTINCT f.courier_key) AS couriers,
       count(DISTINCT (f.courier_key, (f.delivered_at AT TIME ZONE 'Asia/Jakarta')::date)) AS active_courier_days,
       count(*) AS delivered_orders,
       round(count(*)::numeric / count(DISTINCT (f.courier_key, (f.delivered_at AT TIME ZONE 'Asia/Jakarta')::date)), 2)
           AS orders_per_courier_day,
       round(avg(f.delivery_minutes), 2) AS avg_delivery_minutes
FROM core.fact_orders f
JOIN core.dim_courier r USING (courier_key)
WHERE f.is_delivered AND f.courier_key > 0
GROUP BY r.vehicle_type
ORDER BY delivered_orders DESC, r.vehicle_type;
