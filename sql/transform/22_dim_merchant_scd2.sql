-- SCD2 by "rebuild affected keys": for every merchant that received a new version
-- in this run (including a late, back-dated one), its whole history is rebuilt
-- from staging.merchant_versions. This is what makes out-of-order history safe.
-- Versions whose tracked attributes did not change are collapsed (no-op re-sends
-- with a new updated_at do not create a new SCD2 row).
DELETE FROM core.dim_merchant d USING chg_merchants c WHERE d.merchant_id = c.merchant_id;

INSERT INTO core.dim_merchant (merchant_id, version_no, merchant_name, category, city_code, commission_tier,
                               commission_rate, valid_from, valid_to, is_current)
WITH ordered AS (
    SELECT v.merchant_id, v.updated_at, v.merchant_name, v.category, v.city_code, v.commission_tier,
           lag(row(v.merchant_name, v.category, v.city_code, v.commission_tier)::text)
               OVER (PARTITION BY v.merchant_id ORDER BY v.updated_at) AS prev_attrs
    FROM staging.merchant_versions v
    JOIN chg_merchants cm ON cm.merchant_id = v.merchant_id
), changes AS (   -- keep only versions that actually change a tracked attribute
    SELECT * FROM ordered
    WHERE prev_attrs IS NULL OR prev_attrs IS DISTINCT FROM row(merchant_name, category, city_code, commission_tier)::text
)
SELECT c.merchant_id,
       row_number() OVER w,
       c.merchant_name, c.category, c.city_code, c.commission_tier, r.commission_rate,
       CASE WHEN row_number() OVER w = 1 THEN '-infinity'::timestamptz ELSE c.updated_at END,
       coalesce(lead(c.updated_at) OVER w, 'infinity'::timestamptz),
       lead(c.updated_at) OVER w IS NULL
FROM changes c JOIN core.ref_commission_tier r USING (commission_tier)
WINDOW w AS (PARTITION BY c.merchant_id ORDER BY c.updated_at);
