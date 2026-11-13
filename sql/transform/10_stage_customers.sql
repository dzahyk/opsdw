-- Input: temp table d_customers (raw delta: _ingest_id in (watermark, hi]).
-- Output: staging.customers upserted; temp chg_customers(customer_id) = keys whose state changed.
CREATE TEMP TABLE v_customers ON COMMIT DROP AS
SELECT d.*,
       CASE
         WHEN nullif(trim(d.customer_id), '') IS NULL                          THEN 'missing customer_id'
         WHEN NOT staging.is_valid_ts(d.signup_at)  THEN 'invalid signup_at'
         WHEN NOT staging.is_valid_ts(d.updated_at) THEN 'invalid updated_at'
         WHEN upper(trim(coalesce(d.city_code, ''))) NOT IN (SELECT city_code FROM core.dim_city WHERE city_key > 0)
                                                                              THEN 'unknown city_code'
         WHEN lower(trim(coalesce(d.acquisition_channel, ''))) NOT IN ('organic','referral','paid_social','search','partner')
                                                                              THEN 'unknown acquisition_channel'
       END AS reject_reason
FROM d_customers d;

INSERT INTO staging.rejected_rows (source, _ingest_id, business_key, reason, raw_record, run_id)
SELECT 'customers', _ingest_id, customer_id, reject_reason, to_jsonb(v) - 'reject_reason', (SELECT run_id FROM ctx)
FROM v_customers v WHERE reject_reason IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TEMP TABLE chg_customers (customer_id text PRIMARY KEY) ON COMMIT DROP;
WITH latest AS (   -- one candidate per key inside the delta: newest business version, then newest landing
    SELECT DISTINCT ON (trim(customer_id))
           trim(customer_id) AS customer_id, signup_at::timestamptz AS signup_at, upper(trim(city_code)) AS city_code,
           lower(trim(acquisition_channel)) AS acquisition_channel, updated_at::timestamptz AS updated_at, _ingest_id
    FROM v_customers WHERE reject_reason IS NULL
    ORDER BY trim(customer_id), updated_at::timestamptz DESC, _ingest_id DESC
), up AS (
    INSERT INTO staging.customers AS t
    SELECT * FROM latest
    ON CONFLICT (customer_id) DO UPDATE
       SET signup_at = EXCLUDED.signup_at, city_code = EXCLUDED.city_code,
           acquisition_channel = EXCLUDED.acquisition_channel, updated_at = EXCLUDED.updated_at,
           _ingest_id = EXCLUDED._ingest_id
       WHERE (EXCLUDED.updated_at, EXCLUDED._ingest_id) > (t.updated_at, t._ingest_id)   -- newer version, or same version landed later (= full-refresh tie-break)
    RETURNING customer_id
)
INSERT INTO chg_customers SELECT customer_id FROM up;
ANALYZE chg_customers;
