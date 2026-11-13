"""Incremental ETL behaviour: idempotency, re-runs, late / out-of-order data, rollback."""
from __future__ import annotations

import json
import shutil

import pytest

from opsdw import ingest, transform
from opsdw.ingest import IngestError, batches

from helpers.landing import courier, customer, event, merchant, order, write_batch
from helpers.snapshot import fingerprint


def _counts(conn, *tables):
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}


# --------------------------------------------------------------------------- dev dataset
def test_incremental_batches_equal_full_refresh(fresh_conn, dev_landing):
    """Process the 2-year dev dataset in 14-day increments (53 runs), then rebuild
    everything in one full refresh: every modelled table must be identical."""
    all_batches = batches(dev_landing)
    for i in range(0, len(all_batches), 14):
        ingest.ingest(fresh_conn, dev_landing, until=all_batches[min(i + 13, len(all_batches) - 1)])
        transform.run(fresh_conn)
    incremental = fingerprint(fresh_conn)
    transform.run(fresh_conn, full_refresh=True)
    full = fingerprint(fresh_conn)
    assert incremental == full
    assert incremental["core.fact_orders"][0] > 20_000


def test_pipeline_matches_generator_ground_truth(fresh_conn, dev_landing):
    """The generator records every defect it injected; the pipeline must catch exactly those."""
    manifest = json.loads((dev_landing / "manifest.json").read_text())
    inj, ent = manifest["injected"], manifest["entities"]
    ingest.ingest(fresh_conn, dev_landing)
    transform.run(fresh_conn)
    rejected = dict(fresh_conn.execute("SELECT source, count(*) FROM staging.rejected_rows GROUP BY source").fetchall())
    for src in ("customers", "merchants", "couriers", "orders", "order_events"):
        assert rejected.get(src, 0) == inj.get(f"rejected_{src}", 0), src
    c = _counts(fresh_conn, "staging.orders", "staging.order_events", "core.fact_orders", "core.dim_merchant",
                "staging.customers", "core.dim_courier")
    assert c["staging.orders"] == ent["orders"] - inj["orders_only_corrupt"]
    assert c["core.fact_orders"] == c["staging.orders"]
    assert c["staging.order_events"] == ent["events"]           # duplicates and noise removed
    assert c["staging.customers"] == ent["customers"]
    assert c["core.dim_courier"] == ent["couriers"] + 1          # + unassigned member
    # SCD2: one row per merchant + one per real tier change; no-op re-sends are collapsed.
    assert c["core.dim_merchant"] == ent["merchants"] + inj["merchant_tier_changes"] + 1   # + unknown member
    corrections = fresh_conn.execute(
        "SELECT count(*) FROM staging.orders WHERE updated_at > created_at").fetchone()[0]
    assert corrections == inj["order_corrections"]               # stale re-sends did not win


def test_rerun_without_new_data_is_a_noop(fresh_conn, dev_landing):
    ingest.ingest(fresh_conn, dev_landing, until="2024-03-31")
    transform.run(fresh_conn)
    before = fingerprint(fresh_conn)
    stats = transform.run(fresh_conn)
    assert stats["counts"]["affected_orders"] == 0
    assert stats["counts"]["fact_orders_written"] == 0
    assert fingerprint(fresh_conn) == before


def test_reingest_same_files_is_skipped(fresh_conn, dev_landing):
    first = ingest.ingest(fresh_conn, dev_landing, until="2024-01-31")
    raw_before = _counts(fresh_conn, "raw.orders", "raw.order_events")
    second = ingest.ingest(fresh_conn, dev_landing, until="2024-01-31")
    assert first.files_loaded > 0 and second.files_loaded == 0
    assert second.files_skipped == first.files_loaded
    assert _counts(fresh_conn, "raw.orders", "raw.order_events") == raw_before


def test_changed_landing_file_is_rejected_loudly(fresh_conn, dev_landing, tmp_path):
    shutil.copytree(dev_landing / "2024-01-02", tmp_path / "2024-01-02")
    ingest.ingest(fresh_conn, tmp_path)
    with (tmp_path / "2024-01-02" / "orders.csv").open("a") as fh:
        fh.write("O999,C1,M1,JKT,2024-01-02 10:00:00+07:00,1.00,1.00,0.00,cash,1.00,30,2024-01-02 10:00:00+07:00\n")
    with pytest.raises(IngestError, match="changed after it was ingested"):
        ingest.ingest(fresh_conn, tmp_path)


def test_schema_drift_is_rejected_loudly(fresh_conn, tmp_path):
    write_batch(tmp_path, "2024-01-01")
    p = tmp_path / "2024-01-01" / "orders.csv"
    p.write_text(p.read_text().replace("promised_minutes", "promised_mins"))
    with pytest.raises(IngestError, match="schema drift"):
        ingest.ingest(fresh_conn, tmp_path)


def test_failed_run_rolls_back_and_retry_succeeds(fresh_conn, dev_landing):
    ingest.ingest(fresh_conn, dev_landing, until="2024-02-29")
    with pytest.raises(transform.InjectedFailure):
        transform.run(fresh_conn, fail_after="31")          # crash after the fact build, before commit
    assert _counts(fresh_conn, "core.fact_orders", "staging.orders", "core.fact_order_events") == \
        {"core.fact_orders": 0, "staging.orders": 0, "core.fact_order_events": 0}
    assert fresh_conn.execute("SELECT max(last_ingest_id) FROM meta.watermarks").fetchone()[0] == 0
    assert fresh_conn.execute("SELECT status FROM meta.etl_runs ORDER BY run_id DESC LIMIT 1").fetchone()[0] == "failed"
    stats = transform.run(fresh_conn)                       # same delta is re-processed
    assert stats["counts"]["fact_orders_written"] > 0
    assert fresh_conn.execute("SELECT status FROM meta.etl_runs ORDER BY run_id DESC LIMIT 1").fetchone()[0] == "success"


# --------------------------------------------------------------------------- hand-written scenarios
T = "2024-03-04"   # a Monday


def _base(root):
    write_batch(root, "2024-03-04",
                customers=[customer("C1", f"{T} 08:00:00+07:00")],
                merchants=[merchant("M1", "bronze", "2024-02-01 00:00:00+07:00")],
                couriers=[courier("R1", f"{T} 00:00:00+07:00")])


def _run(conn, root):
    ingest.ingest(conn, root)
    return transform.run(conn)


def _fact(conn, oid):
    cur = conn.execute("SELECT * FROM core.fact_orders WHERE order_id = %s", (oid,))
    row = cur.fetchone()
    return dict(zip([d.name for d in cur.description], row)) if row else None


def test_late_arriving_delivery_event_updates_snapshot_and_mart(fresh_conn, tmp_path):
    _base(tmp_path)
    write_batch(tmp_path, "2024-03-04b",
                orders=[order("O1", "C1", "M1", f"{T} 12:00:00+07:00", items=50000, fee=10000, promised=40)],
                order_events=[event("O1-1", "O1", "created", f"{T} 12:00:00+07:00"),
                              event("O1-2", "O1", "assigned", f"{T} 12:02:00+07:00", courier="R1"),
                              event("O1-3", "O1", "picked_up", f"{T} 12:15:00+07:00")])
    _run(fresh_conn, tmp_path)
    f = _fact(fresh_conn, "O1")
    assert f["order_status"] == "picked_up" and f["gmv"] == 0
    # the delivery event happened on 2024-03-04 but lands two days later
    write_batch(tmp_path, "2024-03-06", order_events=[event("O1-4", "O1", "delivered", f"{T} 12:35:00+07:00")])
    _run(fresh_conn, tmp_path)
    f = _fact(fresh_conn, "O1")
    assert f["order_status"] == "delivered"
    assert float(f["delivery_minutes"]) == 35.0 and f["is_on_time"] is True
    assert float(f["gmv"]) == 60000.0 and float(f["commission_amount"]) == 10000.0   # 50,000 * 20% bronze
    mart = fresh_conn.execute("SELECT orders_delivered, gmv FROM mart.city_daily WHERE date_key = 20240304").fetchone()
    assert mart[0] == 1 and float(mart[1]) == 60000.0


def test_out_of_order_order_versions_keep_the_newest(fresh_conn, tmp_path):
    _base(tmp_path)
    v1 = order("O1", "C1", "M1", f"{T} 12:00:00+07:00", disc=0)
    v2 = order("O1", "C1", "M1", f"{T} 12:00:00+07:00", disc=5000, updated="2024-03-05 09:00:00+07:00")
    write_batch(tmp_path, "2024-03-05", orders=[v2])
    _run(fresh_conn, tmp_path)
    write_batch(tmp_path, "2024-03-06", orders=[v1])         # stale re-send arrives after the correction
    stats = _run(fresh_conn, tmp_path)
    assert stats["counts"]["changed_orders"] == 0
    assert float(fresh_conn.execute("SELECT discount_amount FROM staging.orders").fetchone()[0]) == 5000.0


def test_early_arriving_fact_gets_inferred_customer_then_filled(fresh_conn, tmp_path):
    _base(tmp_path)
    write_batch(tmp_path, "2024-03-05",
                orders=[order("O9", "C9", "M1", "2024-03-05 10:00:00+07:00")],
                order_events=[event("O9-1", "O9", "created", "2024-03-05 10:00:00+07:00")])
    _run(fresh_conn, tmp_path)
    key1, inferred = fresh_conn.execute(
        "SELECT customer_key, is_inferred FROM core.dim_customer WHERE customer_id = 'C9'").fetchone()
    assert inferred is True and _fact(fresh_conn, "O9")["customer_key"] == key1
    write_batch(tmp_path, "2024-03-06", customers=[customer("C9", "2024-03-05 09:00:00+07:00", channel="referral")])
    _run(fresh_conn, tmp_path)
    key2, inferred, channel = fresh_conn.execute(
        "SELECT customer_key, is_inferred, acquisition_channel FROM core.dim_customer WHERE customer_id = 'C9'").fetchone()
    assert (key2, inferred, channel) == (key1, False, "referral")   # surrogate key is stable


def _delivered(oid, cid, mid, created_at, delivered_at):
    return [event(f"{oid}-1", oid, "created", created_at),
            event(f"{oid}-2", oid, "assigned", created_at, courier="R1"),
            event(f"{oid}-3", oid, "picked_up", created_at),
            event(f"{oid}-4", oid, "delivered", delivered_at)]


def test_late_scd2_version_rebuilds_history_and_rekeys_facts(fresh_conn, tmp_path):
    _base(tmp_path)   # M1 bronze since 2024-02-01
    write_batch(tmp_path, "2024-03-10",
                merchants=[merchant("M1", "gold", "2024-03-09 00:00:00+07:00")],
                orders=[order("OA", "C1", "M1", "2024-03-05 10:00:00+07:00", items=100000),
                        order("OB", "C1", "M1", "2024-03-08 10:00:00+07:00", items=100000),
                        order("OC", "C1", "M1", "2024-03-10 10:00:00+07:00", items=100000)],
                order_events=_delivered("OA", "C1", "M1", "2024-03-05 10:00:00+07:00", "2024-03-05 10:30:00+07:00")
                + _delivered("OB", "C1", "M1", "2024-03-08 10:00:00+07:00", "2024-03-08 10:30:00+07:00")
                + _delivered("OC", "C1", "M1", "2024-03-10 10:00:00+07:00", "2024-03-10 10:30:00+07:00"))
    _run(fresh_conn, tmp_path)
    assert float(_fact(fresh_conn, "OB")["commission_amount"]) == 20000.0   # bronze 20%
    # a silver period effective 2024-03-07 arrives LATE, after the gold version was already loaded
    write_batch(tmp_path, "2024-03-12", merchants=[merchant("M1", "silver", "2024-03-07 00:00:00+07:00")])
    _run(fresh_conn, tmp_path)
    tiers = fresh_conn.execute(
        "SELECT version_no, commission_tier, valid_from::text, valid_to::text, is_current FROM core.dim_merchant "
        "WHERE merchant_id = 'M1' ORDER BY version_no").fetchall()
    assert [t[1] for t in tiers] == ["bronze", "silver", "gold"]
    assert tiers[0][3] == tiers[1][2] and tiers[1][3] == tiers[2][2] and tiers[2][4] is True
    assert float(_fact(fresh_conn, "OA")["commission_amount"]) == 20000.0   # bronze
    assert float(_fact(fresh_conn, "OB")["commission_amount"]) == 17000.0   # re-keyed to silver
    assert float(_fact(fresh_conn, "OC")["commission_amount"]) == 15000.0   # gold
    assert fresh_conn.execute("SELECT sum(commission_amount) FROM mart.city_daily").fetchone()[0] == 52000


def test_order_before_merchant_uses_unknown_member_then_rekeys(fresh_conn, tmp_path):
    _base(tmp_path)
    write_batch(tmp_path, "2024-03-05", orders=[order("OX", "C1", "M7", "2024-03-05 10:00:00+07:00")],
                order_events=_delivered("OX", "C1", "M7", "2024-03-05 10:00:00+07:00", "2024-03-05 10:30:00+07:00"))
    _run(fresh_conn, tmp_path)
    f = _fact(fresh_conn, "OX")
    assert f["merchant_key"] == -1 and float(f["commission_amount"]) == 0.0
    write_batch(tmp_path, "2024-03-06", merchants=[merchant("M7", "silver", "2024-03-06 00:00:00+07:00")])
    _run(fresh_conn, tmp_path)
    f = _fact(fresh_conn, "OX")
    assert f["merchant_key"] > 0 and float(f["commission_amount"]) == 8500.0  # first version back-dated to -infinity


def test_duplicates_noise_and_invalid_rows(fresh_conn, tmp_path):
    _base(tmp_path)
    created = event("O1-1", "O1", "created", f"{T} 12:00:00+07:00")
    write_batch(tmp_path, "2024-03-05",
                orders=[order("O1", "C1", "M1", f"{T} 12:00:00+07:00"),
                        order("O2", "C1", "M1", f"{T} 12:00:00+07:00", items=-5),
                        order("O3", "C1", "M1", "not-a-date")],
                order_events=[created, created, event("O1-2", "O1", " Assigned ", f"{T} 12:01:00+07:00", courier="R1"),
                              event("O1-3", "O1", "teleported", f"{T} 12:02:00+07:00")])
    write_batch(tmp_path, "2024-03-06", order_events=[created])        # re-sent again a day later
    _run(fresh_conn, tmp_path)
    assert fresh_conn.execute("SELECT count(*) FROM core.fact_order_events").fetchone()[0] == 2
    assert _fact(fresh_conn, "O1")["order_status"] == "assigned"           # ' Assigned ' normalised
    reasons = dict(fresh_conn.execute("SELECT business_key, reason FROM staging.rejected_rows").fetchall())
    assert reasons == {"O2": "negative amount", "O3": "invalid created_at", "O1-3": "unknown event_type"}


def test_values_pg_accepts_but_we_must_reject(fresh_conn, tmp_path):
    """pg_input_is_valid() accepts 'NaN', 'infinity', 'now', 'epoch'; staging must quarantine them
    instead of poisoning sums or aborting the whole run (found in review)."""
    _base(tmp_path)
    write_batch(tmp_path, "2024-03-05",
                orders=[order("N1", "C1", "M1", f"{T} 12:00:00+07:00", items="NaN"),
                        order("N2", "C1", "M1", "infinity"),
                        order("N3", "C1", "M1", "now"),
                        order("N4", "C1", "M1", "1970-01-01 00:00:00+07:00"),
                        order("N5", "C1", "M1", f"{T} 12:00:00+07:00", dist="NaN"),
                        order("OK", "C1", "M1", f"{T} 12:00:00+07:00")],
                order_events=[event("N6-1", "OK", "created", "infinity"),
                              event("N7-1", "OK", "rated", f"{T} 13:00:00+07:00", rating="NaN"),
                              event("OK-1", "OK", "created", f"{T} 12:00:00+07:00")])
    _run(fresh_conn, tmp_path)
    reasons = dict(fresh_conn.execute("SELECT business_key, reason FROM staging.rejected_rows").fetchall())
    assert reasons == {"N1": "invalid amount", "N2": "invalid created_at", "N3": "invalid created_at",
                       "N4": "invalid created_at", "N5": "invalid distance_km", "N6-1": "invalid event_at",
                       "N7-1": "invalid rating"}
    assert [r[0] for r in fresh_conn.execute("SELECT order_id FROM core.fact_orders").fetchall()] == ["OK"]


def test_same_updated_at_different_content_matches_full_refresh(fresh_conn, tmp_path):
    """Two versions with an identical updated_at: the last LANDED wins, incrementally and on rebuild."""
    _base(tmp_path)
    write_batch(tmp_path, "2024-03-05", orders=[order("O1", "C1", "M1", f"{T} 12:00:00+07:00", items=100)],
                merchants=[merchant("M1", "silver", "2024-03-01 00:00:00+07:00")])
    _run(fresh_conn, tmp_path)
    write_batch(tmp_path, "2024-03-06", orders=[order("O1", "C1", "M1", f"{T} 12:00:00+07:00", items=120)],
                merchants=[merchant("M1", "gold", "2024-03-01 00:00:00+07:00")])
    _run(fresh_conn, tmp_path)
    q = ("SELECT (SELECT items_amount FROM staging.orders WHERE order_id = 'O1'), "
         "(SELECT commission_tier FROM core.dim_merchant WHERE merchant_id = 'M1' AND is_current)")
    incremental = fresh_conn.execute(q).fetchone()
    transform.run(fresh_conn, full_refresh=True)
    assert fresh_conn.execute(q).fetchone() == incremental == (120, "gold")


def test_concurrent_ingest_is_refused(fresh_conn, tmp_path):
    from opsdw import db as dbmod
    from opsdw.ingest import INGEST_LOCK_KEY
    _base(tmp_path)
    other = dbmod.connect(fresh_conn.info.dbname, autocommit=True)
    other.execute("SELECT pg_advisory_lock(%s)", (INGEST_LOCK_KEY,))
    try:
        with pytest.raises(IngestError, match="serialized"):
            ingest.ingest(fresh_conn, tmp_path)
    finally:
        other.close()
