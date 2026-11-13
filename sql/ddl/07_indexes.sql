-- Indexes kept in the core model. Each one is justified by a measured
-- EXPLAIN (ANALYZE, BUFFERS) before/after in docs/perf/RESULTS.md.
-- Pipeline support (re-keying orders when a merchant's SCD2 history is rebuilt):
CREATE INDEX IF NOT EXISTS ix_fact_orders_merchant_id   ON core.fact_orders (merchant_id);
-- B1/B4: month/period filters on order created date (dashboard, KPI SQL).
CREATE INDEX IF NOT EXISTS ix_fact_orders_created_date  ON core.fact_orders (created_date_key);
-- B2: customer order history / cohort lookups.
CREATE INDEX IF NOT EXISTS ix_fact_orders_customer_time ON core.fact_orders (customer_key, created_at);
-- B3: event-type scans inside a time window (partition-local indexes).
CREATE INDEX IF NOT EXISTS ix_fact_events_type_time     ON core.fact_order_events (event_type, event_at);
-- B5: courier activity (gaps-and-islands) per courier.
CREATE INDEX IF NOT EXISTS ix_fact_events_courier_date  ON core.fact_order_events (courier_key, event_date_key) WHERE courier_key IS NOT NULL;
