CREATE TEMP TABLE v_orders ON COMMIT DROP AS
SELECT d.*,
       CASE
         WHEN nullif(trim(d.order_id), '') IS NULL                              THEN 'missing order_id'
         WHEN nullif(trim(d.customer_id), '') IS NULL                           THEN 'missing customer_id'
         WHEN nullif(trim(d.merchant_id), '') IS NULL                           THEN 'missing merchant_id'
         WHEN NOT staging.is_valid_ts(d.created_at)  THEN 'invalid created_at'
         WHEN NOT staging.is_valid_ts(d.updated_at)  THEN 'invalid updated_at'
         WHEN NOT staging.is_valid_amount(d.items_amount) OR NOT staging.is_valid_amount(d.delivery_fee)
           OR NOT staging.is_valid_amount(d.discount_amount)                    THEN 'invalid amount'
         WHEN d.items_amount::numeric < 0 OR d.delivery_fee::numeric < 0 OR d.discount_amount::numeric < 0
                                                                               THEN 'negative amount'
         WHEN d.discount_amount::numeric > d.items_amount::numeric + d.delivery_fee::numeric
                                                                               THEN 'discount exceeds order value'
         WHEN coalesce(d.distance_km, '') !~ '^\d{1,4}(\.\d{1,2})?$'
                                                                               THEN 'invalid distance_km'
         WHEN coalesce(d.promised_minutes, '') !~ '^\d{1,4}$'                     THEN 'invalid promised_minutes'
         WHEN d.promised_minutes::int <= 0                                     THEN 'invalid promised_minutes'
         WHEN upper(trim(coalesce(d.city_code, ''))) NOT IN (SELECT city_code FROM core.dim_city WHERE city_key > 0)
                                                                               THEN 'unknown city_code'
         WHEN lower(trim(coalesce(d.payment_method, ''))) NOT IN ('cash','ewallet','card','paylater')
                                                                               THEN 'unknown payment_method'
       END AS reject_reason
FROM d_orders d;

INSERT INTO staging.rejected_rows (source, _ingest_id, business_key, reason, raw_record, run_id)
SELECT 'orders', _ingest_id, order_id, reject_reason, to_jsonb(v) - 'reject_reason', (SELECT run_id FROM ctx)
FROM v_orders v WHERE reject_reason IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TEMP TABLE chg_orders (order_id text PRIMARY KEY) ON COMMIT DROP;
WITH latest AS (
    SELECT DISTINCT ON (trim(order_id))
           trim(order_id) AS order_id, trim(customer_id) AS customer_id, trim(merchant_id) AS merchant_id,
           upper(trim(city_code)) AS city_code, created_at::timestamptz AS created_at,
           items_amount::numeric(14,2) AS items_amount, delivery_fee::numeric(14,2) AS delivery_fee,
           discount_amount::numeric(14,2) AS discount_amount, lower(trim(payment_method)) AS payment_method,
           distance_km::numeric(6,2) AS distance_km, promised_minutes::int AS promised_minutes,
           updated_at::timestamptz AS updated_at, _ingest_id
    FROM v_orders WHERE reject_reason IS NULL
    ORDER BY trim(order_id), updated_at::timestamptz DESC, _ingest_id DESC
), up AS (
    INSERT INTO staging.orders AS t SELECT * FROM latest
    ON CONFLICT (order_id) DO UPDATE
       SET customer_id = EXCLUDED.customer_id, merchant_id = EXCLUDED.merchant_id, city_code = EXCLUDED.city_code,
           created_at = EXCLUDED.created_at, items_amount = EXCLUDED.items_amount, delivery_fee = EXCLUDED.delivery_fee,
           discount_amount = EXCLUDED.discount_amount, payment_method = EXCLUDED.payment_method,
           distance_km = EXCLUDED.distance_km, promised_minutes = EXCLUDED.promised_minutes,
           updated_at = EXCLUDED.updated_at, _ingest_id = EXCLUDED._ingest_id
       WHERE (EXCLUDED.updated_at, EXCLUDED._ingest_id) > (t.updated_at, t._ingest_id)   -- newer version, or same version landed later (= full-refresh tie-break)
    RETURNING order_id
)
INSERT INTO chg_orders SELECT order_id FROM up;
ANALYZE chg_orders;
