"""Content fingerprints of every modelled table, expressed in NATURAL keys so
that two warehouses built along different paths (incremental vs full refresh)
can be compared even though their surrogate keys differ."""
from __future__ import annotations

QUERIES = {
    "staging.customers": "SELECT customer_id, signup_at, city_code, acquisition_channel, updated_at FROM staging.customers",
    "staging.merchant_versions": "SELECT merchant_id, updated_at, merchant_name, category, city_code, commission_tier FROM staging.merchant_versions",
    "staging.orders": "SELECT order_id, customer_id, merchant_id, created_at, items_amount, delivery_fee, discount_amount, updated_at FROM staging.orders",
    "staging.order_events": "SELECT event_id, order_id, event_type, event_at, courier_id, cancel_reason, rating FROM staging.order_events",
    "staging.rejected_rows": "SELECT source, _ingest_id, business_key, reason FROM staging.rejected_rows",
    "core.dim_customer": "SELECT customer_id, signup_at, signup_date_key, city_code, acquisition_channel, is_inferred FROM core.dim_customer",
    "core.dim_courier": "SELECT courier_id, city_code, vehicle_type, joined_at FROM core.dim_courier",
    "core.dim_merchant": "SELECT merchant_id, version_no, commission_tier, commission_rate, valid_from, valid_to, is_current FROM core.dim_merchant",
    "core.fact_orders": """
        SELECT f.order_id, c.customer_id, m.merchant_id, m.version_no, r.courier_id, f.city_key, f.created_date_key,
               f.created_at, f.assigned_at, f.picked_up_at, f.delivered_at, f.cancelled_at, f.order_status, f.cancel_stage,
               f.cancel_reason, f.gmv, f.commission_rate, f.commission_amount, f.delivery_minutes, f.is_on_time,
               f.assignment_count, f.rating, f.source_updated_at
        FROM core.fact_orders f
        JOIN core.dim_customer c USING (customer_key) JOIN core.dim_merchant m USING (merchant_key)
        JOIN core.dim_courier r USING (courier_key)""",
    "core.fact_order_events": """
        SELECT e.event_id, e.event_at, e.event_date_key, e.order_id, e.event_type, r.courier_id, e.cancel_reason, e.rating
        FROM core.fact_order_events e LEFT JOIN core.dim_courier r USING (courier_key)""",
    "mart.city_daily": "SELECT * FROM mart.city_daily",
}


def fingerprint(conn) -> dict[str, tuple[int, str]]:
    out = {}
    for name, q in QUERIES.items():
        out[name] = conn.execute(
            f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM ({q}) t").fetchone()
    return out
