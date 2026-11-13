CREATE TEMP TABLE v_couriers ON COMMIT DROP AS
SELECT d.*,
       CASE
         WHEN nullif(trim(d.courier_id), '') IS NULL                           THEN 'missing courier_id'
         WHEN NOT staging.is_valid_ts(d.joined_at)  THEN 'invalid joined_at'
         WHEN NOT staging.is_valid_ts(d.updated_at) THEN 'invalid updated_at'
         WHEN upper(trim(coalesce(d.city_code, ''))) NOT IN (SELECT city_code FROM core.dim_city WHERE city_key > 0)
                                                                              THEN 'unknown city_code'
         WHEN lower(trim(coalesce(d.vehicle_type, ''))) NOT IN ('motorbike','car','bicycle')
                                                                              THEN 'unknown vehicle_type'
       END AS reject_reason
FROM d_couriers d;

INSERT INTO staging.rejected_rows (source, _ingest_id, business_key, reason, raw_record, run_id)
SELECT 'couriers', _ingest_id, courier_id, reject_reason, to_jsonb(v) - 'reject_reason', (SELECT run_id FROM ctx)
FROM v_couriers v WHERE reject_reason IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TEMP TABLE chg_couriers (courier_id text PRIMARY KEY) ON COMMIT DROP;
WITH latest AS (
    SELECT DISTINCT ON (trim(courier_id))
           trim(courier_id) AS courier_id, upper(trim(city_code)) AS city_code, lower(trim(vehicle_type)) AS vehicle_type,
           joined_at::timestamptz AS joined_at, updated_at::timestamptz AS updated_at, _ingest_id
    FROM v_couriers WHERE reject_reason IS NULL
    ORDER BY trim(courier_id), updated_at::timestamptz DESC, _ingest_id DESC
), up AS (
    INSERT INTO staging.couriers AS t SELECT * FROM latest
    ON CONFLICT (courier_id) DO UPDATE
       SET city_code = EXCLUDED.city_code, vehicle_type = EXCLUDED.vehicle_type, joined_at = EXCLUDED.joined_at,
           updated_at = EXCLUDED.updated_at, _ingest_id = EXCLUDED._ingest_id
       WHERE (EXCLUDED.updated_at, EXCLUDED._ingest_id) > (t.updated_at, t._ingest_id)   -- newer version, or same version landed later (= full-refresh tie-break)
    RETURNING courier_id
)
INSERT INTO chg_couriers SELECT courier_id FROM up;
ANALYZE chg_couriers;
