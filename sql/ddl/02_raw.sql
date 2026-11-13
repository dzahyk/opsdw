-- Raw layer: append-only, every column TEXT exactly as landed. Nothing is
-- rejected here, so bad records stay auditable. Each row gets a monotonic
-- _ingest_id used as the incremental watermark.
CREATE TABLE IF NOT EXISTS raw.customers (
    _ingest_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    _batch_id    text NOT NULL,
    _source_file text NOT NULL,
    _ingested_at timestamptz NOT NULL DEFAULT now(),
    customer_id text, signup_at text, city_code text, acquisition_channel text, updated_at text
);
CREATE TABLE IF NOT EXISTS raw.merchants (
    _ingest_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    _batch_id    text NOT NULL,
    _source_file text NOT NULL,
    _ingested_at timestamptz NOT NULL DEFAULT now(),
    merchant_id text, merchant_name text, category text, city_code text, commission_tier text, updated_at text
);
CREATE TABLE IF NOT EXISTS raw.couriers (
    _ingest_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    _batch_id    text NOT NULL,
    _source_file text NOT NULL,
    _ingested_at timestamptz NOT NULL DEFAULT now(),
    courier_id text, city_code text, vehicle_type text, joined_at text, updated_at text
);
CREATE TABLE IF NOT EXISTS raw.orders (
    _ingest_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    _batch_id    text NOT NULL,
    _source_file text NOT NULL,
    _ingested_at timestamptz NOT NULL DEFAULT now(),
    order_id text, customer_id text, merchant_id text, city_code text, created_at text,
    items_amount text, delivery_fee text, discount_amount text, payment_method text,
    distance_km text, promised_minutes text, updated_at text
);
CREATE TABLE IF NOT EXISTS raw.order_events (
    _ingest_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    _batch_id    text NOT NULL,
    _source_file text NOT NULL,
    _ingested_at timestamptz NOT NULL DEFAULT now(),
    event_id text, order_id text, event_type text, event_at text, courier_id text,
    cancel_reason text, rating text
);
