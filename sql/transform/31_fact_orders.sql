-- Accumulating snapshot rebuild for affected orders only: orders whose header
-- changed, orders that received new (possibly late) events, and orders of
-- merchants whose SCD2 history was rebuilt (re-keying).
CREATE TEMP TABLE aff_dates ON COMMIT DROP AS          -- pre-image dates, for the mart refresh
SELECT DISTINCT f.created_date_key AS date_key FROM core.fact_orders f JOIN aff_orders a USING (order_id);

CREATE TEMP TABLE ev_agg ON COMMIT DROP AS
SELECT e.order_id,
       min(e.event_at) FILTER (WHERE e.event_type = 'assigned')  AS assigned_at,
       min(e.event_at) FILTER (WHERE e.event_type = 'picked_up') AS picked_up_at,
       min(e.event_at) FILTER (WHERE e.event_type = 'delivered') AS delivered_at,
       min(e.event_at) FILTER (WHERE e.event_type = 'cancelled') AS cancelled_at,
       count(*)        FILTER (WHERE e.event_type = 'assigned')  AS assignment_count,
       (array_agg(e.courier_id ORDER BY e.event_at DESC, e.event_id DESC) FILTER (WHERE e.event_type = 'assigned'))[1] AS courier_id,
       (array_agg(e.cancel_reason ORDER BY e.event_at, e.event_id) FILTER (WHERE e.event_type = 'cancelled'))[1] AS cancel_reason,
       (array_agg(e.rating ORDER BY e.event_at DESC, e.event_id DESC) FILTER (WHERE e.event_type = 'rated'))[1] AS rating
FROM staging.order_events e JOIN aff_orders a USING (order_id)
GROUP BY e.order_id;
ALTER TABLE ev_agg ADD PRIMARY KEY (order_id);
ANALYZE ev_agg;

CREATE TEMP TABLE new_fact ON COMMIT DROP AS
WITH base AS (
    SELECT o.*, ev.assigned_at, ev.picked_up_at, ev.delivered_at,
           CASE WHEN ev.delivered_at IS NULL THEN ev.cancelled_at END AS cancelled_at,   -- delivery wins over a stray cancel
           coalesce(ev.assignment_count, 0) AS assignment_count, ev.courier_id AS ev_courier_id,
           ev.cancel_reason, ev.rating
    FROM staging.orders o
    JOIN aff_orders a USING (order_id)
    LEFT JOIN ev_agg ev USING (order_id)
)
SELECT b.order_id,
       dcu.customer_key,
       coalesce(dm.merchant_key, -1)                           AS merchant_key,
       coalesce(dco.courier_key, -1)                           AS courier_key,
       ci.city_key,
       to_char(b.created_at AT TIME ZONE 'Asia/Jakarta', 'YYYYMMDD')::int AS created_date_key,
       b.customer_id, b.merchant_id, b.created_at, b.assigned_at, b.picked_up_at, b.delivered_at, b.cancelled_at,
       CASE WHEN b.delivered_at IS NOT NULL THEN 'delivered'
            WHEN b.cancelled_at IS NOT NULL THEN 'cancelled'
            WHEN b.picked_up_at IS NOT NULL THEN 'picked_up'
            WHEN b.assigned_at  IS NOT NULL THEN 'assigned'
            ELSE 'created' END                                 AS order_status,
       CASE WHEN b.cancelled_at IS NULL THEN NULL
            WHEN b.picked_up_at IS NOT NULL AND b.picked_up_at <= b.cancelled_at THEN 'after_pickup'
            WHEN b.assigned_at  IS NOT NULL AND b.assigned_at  <= b.cancelled_at THEN 'after_assignment'
            ELSE 'before_assignment' END                       AS cancel_stage,
       CASE WHEN b.cancelled_at IS NOT NULL THEN b.cancel_reason END AS cancel_reason,
       b.delivered_at IS NOT NULL                              AS is_delivered,
       b.cancelled_at IS NOT NULL                              AS is_cancelled,
       b.items_amount, b.delivery_fee, b.discount_amount,
       CASE WHEN b.delivered_at IS NOT NULL THEN b.items_amount + b.delivery_fee - b.discount_amount ELSE 0 END AS gmv,
       dm.commission_rate,
       CASE WHEN b.delivered_at IS NOT NULL THEN round(b.items_amount * coalesce(dm.commission_rate, 0), 2) ELSE 0 END
                                                               AS commission_amount,
       b.payment_method, b.distance_km, b.promised_minutes,
       round(extract(epoch FROM b.assigned_at - b.created_at)::numeric / 60, 2)  AS assign_latency_min,
       round(extract(epoch FROM b.delivered_at - b.created_at)::numeric / 60, 2) AS delivery_minutes,
       CASE WHEN b.delivered_at IS NOT NULL
            THEN b.delivered_at <= b.created_at + make_interval(mins => b.promised_minutes) END AS is_on_time,
       b.assignment_count, b.rating,
       b.updated_at                                            AS source_updated_at,
       (SELECT run_id FROM ctx)                                AS last_run_id
FROM base b
JOIN core.dim_customer dcu ON dcu.customer_id = b.customer_id
JOIN core.dim_city ci       ON ci.city_code = b.city_code
LEFT JOIN core.dim_merchant dm
       ON dm.merchant_id = b.merchant_id AND b.created_at >= dm.valid_from AND b.created_at < dm.valid_to
LEFT JOIN core.dim_courier dco ON dco.courier_id = b.ev_courier_id;

MERGE INTO core.fact_orders f
USING new_fact n ON f.order_id = n.order_id
WHEN MATCHED AND (
     f.customer_key, f.merchant_key, f.courier_key, f.city_key, f.created_date_key, f.customer_id, f.merchant_id, f.created_at,
     f.assigned_at, f.picked_up_at, f.delivered_at, f.cancelled_at, f.order_status, f.cancel_stage, f.cancel_reason, f.is_delivered,
     f.is_cancelled, f.items_amount, f.delivery_fee, f.discount_amount, f.gmv, f.commission_rate, f.commission_amount, f.payment_method,
     f.distance_km, f.promised_minutes, f.assign_latency_min, f.delivery_minutes, f.is_on_time, f.assignment_count, f.rating, f.source_updated_at)
  IS DISTINCT FROM (
     n.customer_key, n.merchant_key, n.courier_key, n.city_key, n.created_date_key, n.customer_id, n.merchant_id, n.created_at,
     n.assigned_at, n.picked_up_at, n.delivered_at, n.cancelled_at, n.order_status, n.cancel_stage, n.cancel_reason, n.is_delivered,
     n.is_cancelled, n.items_amount, n.delivery_fee, n.discount_amount, n.gmv, n.commission_rate, n.commission_amount, n.payment_method,
     n.distance_km, n.promised_minutes, n.assign_latency_min, n.delivery_minutes, n.is_on_time, n.assignment_count, n.rating, n.source_updated_at)
  -- last_run_id deliberately excluded: an unchanged order must not be rewritten (idempotency)
  THEN UPDATE SET
    customer_key = n.customer_key, merchant_key = n.merchant_key, courier_key = n.courier_key, city_key = n.city_key,
    created_date_key = n.created_date_key, customer_id = n.customer_id, merchant_id = n.merchant_id,
    created_at = n.created_at, assigned_at = n.assigned_at, picked_up_at = n.picked_up_at,
    delivered_at = n.delivered_at, cancelled_at = n.cancelled_at, order_status = n.order_status,
    cancel_stage = n.cancel_stage, cancel_reason = n.cancel_reason, is_delivered = n.is_delivered,
    is_cancelled = n.is_cancelled, items_amount = n.items_amount, delivery_fee = n.delivery_fee,
    discount_amount = n.discount_amount, gmv = n.gmv, commission_rate = n.commission_rate,
    commission_amount = n.commission_amount, payment_method = n.payment_method, distance_km = n.distance_km,
    promised_minutes = n.promised_minutes, assign_latency_min = n.assign_latency_min,
    delivery_minutes = n.delivery_minutes, is_on_time = n.is_on_time, assignment_count = n.assignment_count,
    rating = n.rating, source_updated_at = n.source_updated_at, last_run_id = n.last_run_id
WHEN NOT MATCHED THEN INSERT VALUES (
    n.order_id, n.customer_key, n.merchant_key, n.courier_key, n.city_key, n.created_date_key, n.customer_id,
    n.merchant_id, n.created_at, n.assigned_at, n.picked_up_at, n.delivered_at, n.cancelled_at, n.order_status,
    n.cancel_stage, n.cancel_reason, n.is_delivered, n.is_cancelled, n.items_amount, n.delivery_fee,
    n.discount_amount, n.gmv, n.commission_rate, n.commission_amount, n.payment_method, n.distance_km,
    n.promised_minutes, n.assign_latency_min, n.delivery_minutes, n.is_on_time, n.assignment_count, n.rating,
    n.source_updated_at, n.last_run_id);

INSERT INTO aff_dates SELECT DISTINCT created_date_key FROM new_fact;   -- post-image dates
