"""The DQ suite must pass on clean data and FAIL LOUDLY (exit code 1) when each class of defect is introduced."""
from __future__ import annotations

import pytest

from opsdw import dq, ingest, transform

from fixtures.analytics_fixture import build


@pytest.fixture
def loaded(fresh_conn, tmp_path):
    build(tmp_path)
    ingest.ingest(fresh_conn, tmp_path)
    transform.run(fresh_conn)
    return fresh_conn


def _failed(conn):
    return {r.name for r in dq.run_checks(conn, record=False) if r.status == "fail"}


def test_clean_pipeline_passes_every_error_check(loaded):
    assert _failed(loaded) == set()
    assert dq.main(loaded) == 0


@pytest.mark.parametrize("sabotage, expected_failure", [
    # duplicate event_id in another partition: not blocked by the (event_id, event_at) PK
    ("INSERT INTO core.fact_order_events SELECT event_id, event_at + interval '40 days', event_date_key, order_id, "
     "event_type, courier_key, cancel_reason, rating FROM core.fact_order_events WHERE event_id = 'O01-1'",
     "core.fact_order_events.unique(event_id)"),
    ("UPDATE core.fact_orders SET customer_key = 999999 WHERE order_id = 'O01'",
     "core.fact_orders.customer_key -> core.dim_customer.customer_key"),
    ("UPDATE core.fact_orders SET order_status = 'lost' WHERE order_id = 'O18'",
     None),   # blocked by the CHECK constraint itself -> raises, see below
    ("UPDATE core.fact_orders SET gmv = gmv + 1 WHERE order_id = 'O01'", "fact_orders.gmv_formula"),
    ("UPDATE core.fact_orders SET commission_amount = items_amount * 0.15 WHERE order_id = 'O01'",
     "fact_orders.commission_uses_point_in_time_tier"),
    ("DELETE FROM core.fact_orders WHERE order_id = 'O19'", "reconcile.staging_orders_eq_fact_orders"),
    ("UPDATE mart.city_daily SET gmv = gmv - 1 WHERE date_key = 20240105", "reconcile.fact_orders_eq_mart"),
    ("UPDATE raw.orders SET _ingested_at = now() - interval '3 days'; "
     "UPDATE raw.order_events SET _ingested_at = now() - interval '3 days'", "freshness.source_landed_within_26h"),
    ("INSERT INTO raw.orders (_batch_id, _source_file, order_id) VALUES ('x', 'x', 'LATE')",
     "freshness.models_caught_up_with_raw"),
    ("UPDATE core.dim_merchant SET valid_to = valid_to - interval '1 day' WHERE merchant_id = 'MA' AND version_no = 1",
     "dim_merchant.scd2_contiguous_history"),
    ("UPDATE core.fact_orders SET delivered_at = created_at - interval '1 minute' WHERE order_id = 'O01'",
     "fact_orders.milestones_in_order"),
])
def test_each_defect_class_fails_the_run(loaded, sabotage, expected_failure):
    if expected_failure is None:
        with pytest.raises(Exception, match="check constraint"):
            loaded.execute(sabotage)
        loaded.rollback()
        return
    loaded.execute(sabotage)
    loaded.commit()
    assert expected_failure in _failed(loaded)
    assert dq.main(loaded) == 1


def test_dq_results_are_recorded(loaded):
    dq.run_checks(loaded)
    n = loaded.execute("SELECT count(*) FROM meta.dq_results").fetchone()[0]
    assert n == len(dq.load_checks())
