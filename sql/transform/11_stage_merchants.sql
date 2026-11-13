-- Merchants: every distinct (merchant_id, updated_at) version is kept for SCD2.
CREATE TEMP TABLE v_merchants ON COMMIT DROP AS
SELECT d.*,
       CASE
         WHEN nullif(trim(d.merchant_id), '') IS NULL                          THEN 'missing merchant_id'
         WHEN nullif(trim(d.merchant_name), '') IS NULL                        THEN 'missing merchant_name'
         WHEN NOT staging.is_valid_ts(d.updated_at) THEN 'invalid updated_at'
         WHEN upper(trim(coalesce(d.city_code, ''))) NOT IN (SELECT city_code FROM core.dim_city WHERE city_key > 0)
                                                                              THEN 'unknown city_code'
         WHEN lower(trim(coalesce(d.category, ''))) NOT IN ('food','grocery','pharmacy','retail')
                                                                              THEN 'unknown category'
         WHEN lower(trim(coalesce(d.commission_tier, ''))) NOT IN (SELECT commission_tier FROM core.ref_commission_tier)
                                                                              THEN 'unknown commission_tier'
       END AS reject_reason
FROM d_merchants d;

INSERT INTO staging.rejected_rows (source, _ingest_id, business_key, reason, raw_record, run_id)
SELECT 'merchants', _ingest_id, merchant_id, reject_reason, to_jsonb(v) - 'reject_reason', (SELECT run_id FROM ctx)
FROM v_merchants v WHERE reject_reason IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TEMP TABLE chg_merchants (merchant_id text PRIMARY KEY) ON COMMIT DROP;
WITH latest AS (
    SELECT DISTINCT ON (trim(merchant_id), updated_at::timestamptz)
           trim(merchant_id) AS merchant_id, updated_at::timestamptz AS updated_at, trim(merchant_name) AS merchant_name,
           lower(trim(category)) AS category, upper(trim(city_code)) AS city_code,
           lower(trim(commission_tier)) AS commission_tier, _ingest_id
    FROM v_merchants WHERE reject_reason IS NULL
    ORDER BY trim(merchant_id), updated_at::timestamptz, _ingest_id DESC
), ins AS (
    INSERT INTO staging.merchant_versions SELECT * FROM latest
    ON CONFLICT (merchant_id, updated_at) DO UPDATE      -- same version landed again: last landing wins
       SET merchant_name = EXCLUDED.merchant_name, category = EXCLUDED.category, city_code = EXCLUDED.city_code,
           commission_tier = EXCLUDED.commission_tier, _ingest_id = EXCLUDED._ingest_id
       WHERE EXCLUDED._ingest_id > staging.merchant_versions._ingest_id
    RETURNING merchant_id
)
INSERT INTO chg_merchants SELECT DISTINCT merchant_id FROM ins;
ANALYZE chg_merchants;
