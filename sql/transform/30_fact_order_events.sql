-- Transaction fact. Only events whose order header is known are loaded; events
-- that land before their order header wait in staging and are picked up in the
-- run where the header arrives (events of chg_orders).
-- Written as joins (not `IN (SELECT ...)` / OR): with millions of keys an IN-list
-- that does not fit work_mem degrades to a per-row subplan (quadratic) — found
-- at bench volume, see docs/perf/RESULTS.md.
WITH todo AS (
    SELECT event_id FROM chg_events
    UNION
    SELECT e.event_id FROM staging.order_events e JOIN chg_orders o USING (order_id)
)
INSERT INTO core.fact_order_events (event_id, event_at, event_date_key, order_id, event_type, courier_key, cancel_reason, rating)
SELECT e.event_id, e.event_at, to_char(e.event_at AT TIME ZONE 'Asia/Jakarta', 'YYYYMMDD')::int, e.order_id,
       e.event_type, dc.courier_key, e.cancel_reason, e.rating
FROM todo t
JOIN staging.order_events e USING (event_id)
JOIN staging.orders o ON o.order_id = e.order_id
LEFT JOIN core.dim_courier dc ON dc.courier_id = e.courier_id
ON CONFLICT DO NOTHING;
