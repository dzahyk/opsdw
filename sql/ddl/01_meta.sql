-- Pipeline bookkeeping.
CREATE TABLE IF NOT EXISTS meta.ingested_files (
    source_file  text PRIMARY KEY,           -- path relative to the landing root, e.g. 2024-01-03/orders.csv
    entity       text        NOT NULL,
    batch_id     text        NOT NULL,       -- landing batch = logical load date
    sha256       text        NOT NULL,
    row_count    integer     NOT NULL,
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

-- One watermark per raw source table. The watermark is the raw surrogate
-- _ingest_id (monotonic identity), NOT a business timestamp: late-arriving
-- records carry old business timestamps but always get a new _ingest_id,
-- so they can never fall behind the watermark.
CREATE TABLE IF NOT EXISTS meta.watermarks (
    source          text PRIMARY KEY,
    last_ingest_id  bigint      NOT NULL DEFAULT 0,
    updated_at      timestamptz NOT NULL DEFAULT now()
);
INSERT INTO meta.watermarks (source) VALUES
    ('customers'), ('merchants'), ('couriers'), ('orders'), ('order_events')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS meta.etl_runs (
    run_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mode         text        NOT NULL CHECK (mode IN ('incremental', 'full_refresh')),
    started_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at  timestamptz,
    status       text        NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'failed')),
    stats        jsonb       NOT NULL DEFAULT '{}'::jsonb,
    error        text
);

-- Data-quality results history (one row per check per dq run).
CREATE TABLE IF NOT EXISTS meta.dq_results (
    dq_run_at   timestamptz NOT NULL,
    check_name  text        NOT NULL,
    check_type  text        NOT NULL,
    severity    text        NOT NULL CHECK (severity IN ('error', 'warn')),
    status      text        NOT NULL CHECK (status IN ('pass', 'fail', 'warn')),
    failures    bigint      NOT NULL,
    PRIMARY KEY (dq_run_at, check_name)
);
