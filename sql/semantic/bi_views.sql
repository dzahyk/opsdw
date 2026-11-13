-- Power BI-ready semantic layer (import or DirectQuery against these views only).
-- Conventions for the BI tool: integer surrogate keys, 0/1 integer flags (DAX-friendly),
-- no +/-infinity timestamps (Power BI cannot represent them), friendly column names.
CREATE OR REPLACE VIEW bi.dim_date AS
SELECT date_key, date, year, quarter, month, month_start, year_month, iso_week, day_of_week, day_name,
       is_weekend::int AS is_weekend
FROM core.dim_date;

CREATE OR REPLACE VIEW bi.dim_city AS
SELECT city_key, city_code, city_name, province, island FROM core.dim_city;

CREATE OR REPLACE VIEW bi.dim_customer AS
SELECT customer_key, customer_id, signup_date_key, city_code AS home_city_code, acquisition_channel,
       is_inferred::int AS is_inferred
FROM core.dim_customer;

CREATE OR REPLACE VIEW bi.dim_courier AS
SELECT courier_key, courier_id, city_code AS home_city_code, vehicle_type, (joined_at AT TIME ZONE 'Asia/Jakarta')::date AS joined_date
FROM core.dim_courier;

-- SCD2: one row per merchant VERSION. Facts point at the version valid when the order was placed.
CREATE OR REPLACE VIEW bi.dim_merchant AS
SELECT merchant_key, merchant_id, version_no, merchant_name, category, city_code, commission_tier, commission_rate,
       CASE WHEN valid_from = '-infinity' THEN date '1900-01-01' ELSE (valid_from AT TIME ZONE 'Asia/Jakarta')::date END AS valid_from_date,
       CASE WHEN valid_to = 'infinity' THEN date '9999-12-31' ELSE (valid_to AT TIME ZONE 'Asia/Jakarta')::date END AS valid_to_date,
       is_current::int AS is_current
FROM core.dim_merchant;

CREATE OR REPLACE VIEW bi.fact_orders AS
SELECT order_id, created_date_key, city_key, customer_key, merchant_key, courier_key,
       order_status, cancel_stage, cancel_reason, payment_method,
       is_delivered::int AS is_delivered,
       is_cancelled::int AS is_cancelled,
       coalesce(is_on_time, false)::int AS is_on_time,       -- 0 for undelivered orders; KPIs divide by delivered
       items_amount, delivery_fee, discount_amount, gmv, commission_amount,
       distance_km, promised_minutes, assign_latency_min, delivery_minutes, rating
FROM core.fact_orders;

CREATE OR REPLACE VIEW bi.fact_order_events AS
SELECT event_id, order_id, event_date_key, event_type, coalesce(courier_key, -1) AS courier_key, cancel_reason, rating
FROM core.fact_order_events;
