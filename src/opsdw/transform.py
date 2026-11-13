"""Incremental transform: raw -> staging -> core -> mart in ONE transaction.

For each raw source the delta is (watermark, hi], where hi = max(_ingest_id)
captured at the start of the run. Every step consumes the delta temp tables
(d_*) and the change sets produced by earlier steps (chg_*, aff_*). Watermarks
advance in the same transaction, so a failed run leaves no partial state and
the next run re-processes the same delta (at-least-once input, exactly-once effect).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import psycopg
from psycopg import sql

from .config import ENTITIES, SQL_DIR

TRANSFORM_DIR = SQL_DIR / "transform"
LOCK_KEY = 482_100_017  # advisory lock: one transform at a time

TRUNCATE_FULL = """
TRUNCATE staging.customers, staging.merchant_versions, staging.couriers, staging.orders,
         staging.order_events, staging.rejected_rows,
         core.fact_orders, core.fact_order_events, core.dim_customer, core.dim_courier, core.dim_merchant,
         mart.city_daily RESTART IDENTITY;
UPDATE meta.watermarks SET last_ingest_id = 0, updated_at = now();
"""


class InjectedFailure(RuntimeError):
    """Raised by the test hook to simulate a crash mid-run."""


def steps() -> list[Path]:
    return sorted(TRANSFORM_DIR.glob("*.sql"))


def run(conn: psycopg.Connection, full_refresh: bool = False, fail_after: str | None = None,
        verbose: bool = False) -> dict:
    mode = "full_refresh" if full_refresh else "incremental"
    run_id = conn.execute("INSERT INTO meta.etl_runs (mode) VALUES (%s) RETURNING run_id", (mode,)).fetchone()[0]
    conn.commit()  # the run row survives even if the run fails
    t0 = time.perf_counter()
    stats: dict = {"run_id": run_id, "mode": mode, "steps": {}}
    try:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_KEY,))
        if full_refresh:
            conn.execute(TRUNCATE_FULL)
            conn.execute((SQL_DIR / "ddl" / "06_seed.sql").read_text())  # re-create unknown members
        conn.execute("CREATE TEMP TABLE ctx ON COMMIT DROP AS SELECT %s::bigint AS run_id", (run_id,))
        windows = {}
        for src in ENTITIES:
            lo = conn.execute("SELECT last_ingest_id FROM meta.watermarks WHERE source = %s FOR UPDATE", (src,)).fetchone()[0]
            hi = conn.execute(sql.SQL("SELECT coalesce(max(_ingest_id), 0) FROM raw.{}").format(sql.Identifier(src))).fetchone()[0]
            hi = max(hi, lo)
            conn.execute(sql.SQL(
                "CREATE TEMP TABLE {d} ON COMMIT DROP AS SELECT * FROM raw.{s} WHERE _ingest_id > %s AND _ingest_id <= %s"
            ).format(d=sql.Identifier(f"d_{src}"), s=sql.Identifier(src)), (lo, hi))
            conn.execute(sql.SQL("ANALYZE {}").format(sql.Identifier(f"d_{src}")))
            windows[src] = (lo, hi)
        stats["windows"] = windows
        for path in steps():
            ts = time.perf_counter()
            conn.execute(path.read_text())
            stats["steps"][path.stem] = round(time.perf_counter() - ts, 3)
            if verbose:
                print(f"  {path.stem:<28} {stats['steps'][path.stem]:>8.3f}s")
            if fail_after and path.stem.startswith(fail_after):
                raise InjectedFailure(f"injected failure after step {path.stem}")
        counts = conn.execute("""
            SELECT (SELECT count(*) FROM d_customers), (SELECT count(*) FROM d_merchants),
                   (SELECT count(*) FROM d_couriers), (SELECT count(*) FROM d_orders),
                   (SELECT count(*) FROM d_order_events),
                   (SELECT count(*) FROM chg_customers), (SELECT count(*) FROM chg_merchants),
                   (SELECT count(*) FROM chg_couriers), (SELECT count(*) FROM chg_orders),
                   (SELECT count(*) FROM chg_events), (SELECT count(*) FROM aff_orders),
                   (SELECT count(*) FROM new_fact),
                   (SELECT count(*) FROM core.fact_orders WHERE last_run_id = (SELECT run_id FROM ctx)),
                   (SELECT count(*) FROM staging.rejected_rows WHERE run_id = (SELECT run_id FROM ctx))
        """).fetchone()
        keys = ["raw_customers", "raw_merchants", "raw_couriers", "raw_orders", "raw_order_events",
                "changed_customers", "changed_merchants", "changed_couriers", "changed_orders", "new_events",
                "affected_orders", "orders_recomputed", "fact_orders_written", "rows_rejected"]
        stats["counts"] = dict(zip(keys, counts))
        for src, (_, hi) in windows.items():
            conn.execute("UPDATE meta.watermarks SET last_ingest_id = %s, updated_at = now() WHERE source = %s", (hi, src))
        stats["seconds"] = round(time.perf_counter() - t0, 3)
        conn.execute("UPDATE meta.etl_runs SET status = 'success', finished_at = clock_timestamp(), stats = %s WHERE run_id = %s",
                     (json.dumps(stats), run_id))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.execute("UPDATE meta.etl_runs SET status = 'failed', finished_at = clock_timestamp(), error = %s WHERE run_id = %s",
                     (repr(exc)[:2000], run_id))
        conn.commit()
        raise
    return stats
