-- SCD1 upsert of changed customers. Also clears the inferred flag when the real record arrives.
INSERT INTO core.dim_customer (customer_id, signup_at, signup_date_key, city_code, acquisition_channel, source_updated_at, is_inferred)
SELECT s.customer_id, s.signup_at, to_char(s.signup_at AT TIME ZONE 'Asia/Jakarta', 'YYYYMMDD')::int,
       s.city_code, s.acquisition_channel, s.updated_at, false
FROM staging.customers s JOIN chg_customers c USING (customer_id)
ON CONFLICT (customer_id) DO UPDATE
   SET signup_at = EXCLUDED.signup_at, signup_date_key = EXCLUDED.signup_date_key, city_code = EXCLUDED.city_code,
       acquisition_channel = EXCLUDED.acquisition_channel, source_updated_at = EXCLUDED.source_updated_at,
       is_inferred = false;
