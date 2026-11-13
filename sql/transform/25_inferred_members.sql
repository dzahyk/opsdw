-- Early-arriving facts: an order/event can land before its customer or courier
-- record. Kimball "inferred member": insert a placeholder row keyed by the
-- natural key now, so the fact gets a stable surrogate key; the SCD1 upsert
-- fills the attributes (and clears is_inferred) when the real record lands.
-- (Merchants are SCD2 and use the -1 unknown member + re-keying instead.)
CREATE TEMP TABLE aff_orders ON COMMIT DROP AS
SELECT order_id FROM chg_orders
UNION SELECT order_id FROM chg_events
UNION SELECT f.order_id FROM core.fact_orders f JOIN chg_merchants m USING (merchant_id);
ALTER TABLE aff_orders ADD PRIMARY KEY (order_id);
ANALYZE aff_orders;

INSERT INTO core.dim_customer (customer_id, is_inferred)
SELECT DISTINCT o.customer_id, true
FROM staging.orders o JOIN aff_orders a USING (order_id)
WHERE NOT EXISTS (SELECT 1 FROM core.dim_customer d WHERE d.customer_id = o.customer_id)
ON CONFLICT (customer_id) DO NOTHING;

INSERT INTO core.dim_courier (courier_id)
SELECT DISTINCT e.courier_id
FROM staging.order_events e JOIN chg_events c USING (event_id)
WHERE e.courier_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM core.dim_courier d WHERE d.courier_id = e.courier_id)
ON CONFLICT (courier_id) DO NOTHING;
