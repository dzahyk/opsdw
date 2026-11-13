-- Events are immutable facts: the first valid copy of an event_id wins, re-sends are dropped.
CREATE TEMP TABLE v_order_events ON COMMIT DROP AS
SELECT d.*, lower(trim(coalesce(d.event_type, ''))) AS event_type_norm,
       CASE
         WHEN nullif(trim(d.event_id), '') IS NULL                             THEN 'missing event_id'
         WHEN nullif(trim(d.order_id), '') IS NULL                             THEN 'missing order_id'
         WHEN NOT staging.is_valid_ts(d.event_at)   THEN 'invalid event_at'
         WHEN lower(trim(coalesce(d.event_type, ''))) NOT IN ('created','assigned','picked_up','delivered','cancelled','rated')
                                                                              THEN 'unknown event_type'
         WHEN lower(trim(d.event_type)) = 'assigned' AND nullif(trim(d.courier_id), '') IS NULL
                                                                              THEN 'assigned event without courier'
         WHEN lower(trim(d.event_type)) = 'cancelled'
              AND lower(trim(coalesce(d.cancel_reason, ''))) NOT IN
                  ('customer_changed_mind','no_courier_available','merchant_closed','item_unavailable','payment_failed','other')
                                                                              THEN 'unknown cancel_reason'
         WHEN lower(trim(d.event_type)) = 'rated' AND coalesce(d.rating, '') !~ '^[1-5]$'
                                                                              THEN 'invalid rating'
       END AS reject_reason
FROM d_order_events d;

INSERT INTO staging.rejected_rows (source, _ingest_id, business_key, reason, raw_record, run_id)
SELECT 'order_events', _ingest_id, event_id, reject_reason, to_jsonb(v) - 'reject_reason' - 'event_type_norm', (SELECT run_id FROM ctx)
FROM v_order_events v WHERE reject_reason IS NOT NULL
ON CONFLICT DO NOTHING;

CREATE TEMP TABLE chg_events (event_id text PRIMARY KEY, order_id text NOT NULL) ON COMMIT DROP;
WITH firsts AS (
    SELECT DISTINCT ON (trim(event_id))
           trim(event_id) AS event_id, trim(order_id) AS order_id, event_type_norm AS event_type,
           event_at::timestamptz AS event_at, nullif(trim(courier_id), '') AS courier_id,
           CASE WHEN event_type_norm = 'cancelled' THEN lower(trim(cancel_reason)) END AS cancel_reason,
           CASE WHEN event_type_norm = 'rated' THEN rating::smallint END AS rating, _ingest_id
    FROM v_order_events WHERE reject_reason IS NULL
    ORDER BY trim(event_id), _ingest_id
), ins AS (
    INSERT INTO staging.order_events SELECT * FROM firsts
    ON CONFLICT (event_id) DO NOTHING
    RETURNING event_id, order_id
)
INSERT INTO chg_events SELECT event_id, order_id FROM ins;
ANALYZE chg_events;
