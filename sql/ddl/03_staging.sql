-- Staging: typed, validated, deduplicated current state per business key.
-- Merchants keep every version (needed to build SCD2 history).
CREATE TABLE IF NOT EXISTS staging.customers (
    customer_id         text PRIMARY KEY,
    signup_at           timestamptz NOT NULL,
    city_code           text        NOT NULL,
    acquisition_channel text        NOT NULL,
    updated_at          timestamptz NOT NULL,
    _ingest_id          bigint      NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.merchant_versions (
    merchant_id     text        NOT NULL,
    updated_at      timestamptz NOT NULL,   -- effective timestamp of this version
    merchant_name   text        NOT NULL,
    category        text        NOT NULL,
    city_code       text        NOT NULL,
    commission_tier text        NOT NULL,
    _ingest_id      bigint      NOT NULL,
    PRIMARY KEY (merchant_id, updated_at)
);
CREATE TABLE IF NOT EXISTS staging.couriers (
    courier_id   text PRIMARY KEY,
    city_code    text        NOT NULL,
    vehicle_type text        NOT NULL,
    joined_at    timestamptz NOT NULL,
    updated_at   timestamptz NOT NULL,
    _ingest_id   bigint      NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.orders (
    order_id         text PRIMARY KEY,
    customer_id      text          NOT NULL,
    merchant_id      text          NOT NULL,
    city_code        text          NOT NULL,
    created_at       timestamptz   NOT NULL,
    items_amount     numeric(14,2) NOT NULL,
    delivery_fee     numeric(14,2) NOT NULL,
    discount_amount  numeric(14,2) NOT NULL,
    payment_method   text          NOT NULL,
    distance_km      numeric(6,2)  NOT NULL,
    promised_minutes integer       NOT NULL,
    updated_at       timestamptz   NOT NULL,
    _ingest_id       bigint        NOT NULL
);
CREATE TABLE IF NOT EXISTS staging.order_events (
    event_id      text PRIMARY KEY,
    order_id      text        NOT NULL,
    event_type    text        NOT NULL,
    event_at      timestamptz NOT NULL,
    courier_id    text,
    cancel_reason text,
    rating        smallint,
    _ingest_id    bigint      NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_stg_events_order ON staging.order_events (order_id);

-- Quarantine: raw rows that failed validation, with the reason.
CREATE TABLE IF NOT EXISTS staging.rejected_rows (
    source       text   NOT NULL,
    _ingest_id   bigint NOT NULL,
    business_key text,
    reason       text   NOT NULL,
    raw_record   jsonb  NOT NULL,
    run_id       bigint NOT NULL,
    PRIMARY KEY (source, _ingest_id)
);

-- Strict validators. pg_input_is_valid() alone is too permissive: it accepts 'NaN' for
-- numeric and 'infinity' / 'now' / 'epoch' for timestamptz (found in review). CASE keeps the
-- evaluation order guaranteed, so a cast is only attempted on a string that already parsed.
CREATE OR REPLACE FUNCTION staging.is_valid_ts(x text) RETURNS boolean LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN x IS NULL OR x !~ '^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}(:?\d{2})?)?$' THEN false
        WHEN NOT pg_input_is_valid(x, 'timestamptz') THEN false
        ELSE x::timestamptz >= timestamptz '2023-01-01 00:00+07' AND x::timestamptz < timestamptz '2027-01-01 00:00+07'
    END   -- range = core.dim_date coverage, so every accepted timestamp has a date_key
$$;
CREATE OR REPLACE FUNCTION staging.is_valid_amount(x text) RETURNS boolean LANGUAGE sql IMMUTABLE AS $$
    SELECT x IS NOT NULL AND x ~ '^-?\d{1,12}(\.\d{1,2})?$'   -- fits numeric(14,2); rejects NaN / exponent forms
$$;
