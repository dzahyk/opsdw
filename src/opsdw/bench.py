"""Query-performance benchmark: EXPLAIN (ANALYZE, BUFFERS) before vs after physical design.

BEFORE = perf.* copies of the same rows with NO indexes and NO partitioning.
AFTER  = the real core/mart tables (indexes from sql/ddl/07_indexes.sql, monthly partitions).
Each query: 1 warm-up run, then N measured runs; we report the MEDIAN execution time
and the buffers of the median run. Warm-cache numbers, single session, local Docker.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import subprocess
from pathlib import Path

import psycopg

from .config import ROOT

OUT = ROOT / "data" / "reports" / "perf"   # committed copy: --report-dir docs/perf

SETUP = """
CREATE SCHEMA IF NOT EXISTS perf;
DROP TABLE IF EXISTS perf.fact_orders_noidx, perf.fact_order_events_heap;
CREATE TABLE perf.fact_orders_noidx AS SELECT * FROM core.fact_orders;
CREATE TABLE perf.fact_order_events_heap AS SELECT * FROM core.fact_order_events;
VACUUM ANALYZE perf.fact_orders_noidx;
VACUUM ANALYZE perf.fact_order_events_heap;
VACUUM ANALYZE core.fact_orders;
VACUUM ANALYZE core.fact_order_events;
VACUUM ANALYZE mart.city_daily;
"""


def _params(conn) -> dict:
    cust = conn.execute("SELECT customer_key FROM core.fact_orders GROUP BY customer_key "
                        "ORDER BY count(*) DESC, customer_key LIMIT 1").fetchone()[0]
    courier = conn.execute("SELECT courier_key FROM core.fact_orders WHERE courier_key > 0 GROUP BY courier_key "
                           "ORDER BY count(*) DESC, courier_key LIMIT 1").fetchone()[0]
    return {"customer_key": cust, "courier_key": courier}


def benchmarks(p: dict) -> list[dict]:
    return [
        {
            "id": "B1", "title": "One month's GMV and orders by city (KPI / dashboard month filter)",
            "design": "B-tree index on fact_orders(created_date_key)",
            "sql": """SELECT city_key, count(*), sum(gmv) FROM {orders}
                      WHERE created_date_key BETWEEN 20251101 AND 20251130 GROUP BY city_key""",
            "before": {"orders": "perf.fact_orders_noidx"}, "after": {"orders": "core.fact_orders"},
        },
        {
            "id": "B2", "title": "Customer order history, latest 20 orders (customer 360 / support lookup)",
            "design": "Composite index on fact_orders(customer_key, created_at)",
            "sql": f"""SELECT order_id, created_at, order_status, gmv FROM {{orders}}
                      WHERE customer_key = {p['customer_key']} ORDER BY created_at DESC LIMIT 20""",
            "before": {"orders": "perf.fact_orders_noidx"}, "after": {"orders": "core.fact_orders"},
        },
        {
            "id": "B3", "title": "Hourly delivered events in a 7-day window (ops monitoring)",
            "design": "Monthly range partitions on event_at (pruning) + index (event_type, event_at)",
            "sql": """SELECT date_trunc('hour', event_at) AS h, count(*) FROM {events}
                      WHERE event_type = 'delivered' AND event_at >= '2025-06-01 00:00+07' AND event_at < '2025-06-08 00:00+07'
                      GROUP BY 1 ORDER BY 1""",
            "before": {"events": "perf.fact_order_events_heap"}, "after": {"events": "core.fact_order_events"},
        },
        {
            "id": "B4", "title": "One courier's active days in a quarter (gaps-and-islands input)",
            "design": "Partial index on fact_order_events(courier_key, event_date_key) WHERE courier_key IS NOT NULL",
            "sql": f"""SELECT DISTINCT event_date_key FROM {{events}}
                      WHERE courier_key = {p['courier_key']} AND event_date_key BETWEEN 20250701 AND 20250930""",
            "before": {"events": "perf.fact_order_events_heap"}, "after": {"events": "core.fact_order_events"},
        },
        {
            "id": "B5", "title": "24-month GMV / completion trend for all cities (dashboard landing view)",
            "design": "Pre-aggregated periodic snapshot mart.city_daily instead of scanning the fact",
            "sql_before": """SELECT d.year_month, count(*), count(*) FILTER (WHERE f.is_delivered), sum(f.gmv)
                             FROM perf.fact_orders_noidx f JOIN core.dim_date d ON d.date_key = f.created_date_key
                             GROUP BY d.year_month ORDER BY 1""",
            "sql_after": """SELECT d.year_month, sum(m.orders_created), sum(m.orders_delivered), sum(m.gmv)
                            FROM mart.city_daily m JOIN core.dim_date d ON d.date_key = m.date_key
                            GROUP BY d.year_month ORDER BY 1""",
        },
    ]


def _explain(conn, sql: str, repeats: int) -> dict:
    conn.execute(sql).fetchall()                                   # warm-up
    runs = []
    for _ in range(repeats):
        plan = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql).fetchone()[0][0]
        top = plan["Plan"]
        runs.append({"exec_ms": plan["Execution Time"], "plan_ms": plan["Planning Time"],
                     "hit": top.get("Shared Hit Blocks", 0), "read": top.get("Shared Read Blocks", 0)})
    med = sorted(runs, key=lambda r: r["exec_ms"])[len(runs) // 2]
    text = "\n".join(r[0] for r in conn.execute("EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, TIMING ON) " + sql).fetchall())
    return {**med, "median_exec_ms": statistics.median(r["exec_ms"] for r in runs),
            "all_exec_ms": [round(r["exec_ms"], 3) for r in runs], "plan_text": text}


def _env(conn) -> dict:
    q = lambda s: conn.execute(s).fetchone()[0]
    env = {
        "postgres": q("SELECT version()"),
        "shared_buffers": q("SHOW shared_buffers"), "work_mem": q("SHOW work_mem"), "jit": q("SHOW jit"),
        "max_parallel_workers_per_gather": q("SHOW max_parallel_workers_per_gather"),
        "rows": {t: q(f"SELECT count(*) FROM {t}") for t in
                 ("core.fact_orders", "core.fact_order_events", "core.dim_customer", "core.dim_merchant", "mart.city_daily")},
        "sizes": {t: q(f"SELECT pg_size_pretty(pg_total_relation_size('{t}'))") for t in
                  ("core.fact_orders", "perf.fact_orders_noidx", "perf.fact_order_events_heap", "mart.city_daily")},
        "events_partitioned_size": q("""SELECT pg_size_pretty(sum(pg_total_relation_size(inhrelid)))
                                        FROM pg_inherits WHERE inhparent = 'core.fact_order_events'::regclass"""),
        "index_sizes": [list(r) for r in conn.execute(r"""
            SELECT t.relname_parent AS table_name,
                   regexp_replace(i.relname, '^fact_order_events_(\d{6}|default)_', 'fact_order_events_<partition>_') AS index_name,
                   count(*) AS physical_indexes, sum(pg_relation_size(i.oid))::bigint AS bytes,
                   pg_size_pretty(sum(pg_relation_size(i.oid))) AS size
            FROM pg_class i
            JOIN pg_index x ON x.indexrelid = i.oid
            JOIN (SELECT c.oid, CASE WHEN c.relname LIKE 'fact_order_events%' THEN 'fact_order_events' ELSE c.relname END AS relname_parent
                  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'core') t ON t.oid = x.indrelid
            WHERE t.relname_parent IN ('fact_orders', 'fact_order_events') AND i.relkind = 'i'
            GROUP BY 1, 2 ORDER BY 1, 2""").fetchall()],
    }
    try:
        env["docker_host"] = subprocess.run(["docker", "info", "--format", "{{.NCPU}} CPUs, {{.MemTotal}} bytes RAM, {{.OperatingSystem}}"],
                                            capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as exc:  # docker CLI not available: record that rather than guess
        env["docker_host"] = f"unknown ({exc.__class__.__name__})"
    return env


def run(conn: psycopg.Connection, repeats: int = 5) -> dict:
    conn.autocommit = True
    for stmt in filter(None, (x.strip() for x in SETUP.split(";"))):
        conn.execute(stmt)            # one by one: VACUUM cannot run inside a multi-statement implicit transaction
    p = _params(conn)
    results = []
    for b in benchmarks(p):
        before_sql = b.get("sql_before") or b["sql"].format(**b["before"])
        after_sql = b.get("sql_after") or b["sql"].format(**b["after"])
        before, after = _explain(conn, before_sql, repeats), _explain(conn, after_sql, repeats)
        results.append({"id": b["id"], "title": b["title"], "design": b["design"], "before": before, "after": after,
                        "before_sql": " ".join(before_sql.split()), "after_sql": " ".join(after_sql.split())})
    conn.autocommit = False
    return {"measured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "repeats": repeats,
            "params": p, "env": _env(conn), "results": results}


def write(report: dict, out: Path = OUT) -> None:
    plans = out / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    slim = {**report, "results": []}
    for r in report["results"]:
        for side in ("before", "after"):
            (plans / f"{r['id']}_{side}.txt").write_text(f"-- {r['title']} ({side})\n-- {r[side + '_sql']}\n\n"
                                                          + r[side]["plan_text"] + "\n")
        slim["results"].append({k: (v if k not in ("before", "after") else {kk: vv for kk, vv in v.items() if kk != "plan_text"})
                                for k, v in r.items()})
    (out / "results.json").write_text(json.dumps(slim, indent=2) + "\n")


def main(conn: psycopg.Connection, repeats: int = 5, out: Path = OUT) -> int:
    report = run(conn, repeats)
    write(report, out)
    for r in report["results"]:
        b, a = r["before"]["median_exec_ms"], r["after"]["median_exec_ms"]
        print(f"{r['id']}  before {b:10.2f} ms  after {a:9.2f} ms  x{b / a:8.1f}   {r['title']}")
    print(f"wrote {out}/results.json and {out}/plans/*.txt")
    return 0


def etl_timings(conn: psycopg.Connection, landing: Path, initial_until: str = "2025-12-21", out_dir: Path = OUT) -> dict:
    """Initial build of every batch up to `initial_until`, then one incremental run per later batch
    (the last 10 regular days of the period, then the post-period stragglers that carry only late rows)."""
    import time
    from . import ingest, transform
    batches = ingest.batches(landing)
    cut = initial_until
    later = [b for b in batches if b > cut]
    t0 = time.perf_counter()
    r = ingest.ingest(conn, landing, until=cut)
    t_ing = time.perf_counter() - t0
    s = transform.run(conn)
    res = {"initial": {"batches": len(batches) - len(later), "ingest_s": round(t_ing, 1),
                       "raw_rows": sum(r.rows_loaded.values()), "transform_s": s["seconds"], "steps_s": s["steps"]},
           "incremental": []}
    for b in later:
        t0 = time.perf_counter()
        r = ingest.ingest(conn, landing, only=[b])
        t_ing = time.perf_counter() - t0
        s = transform.run(conn)
        res["incremental"].append({"batch": b, "raw_rows": sum(r.rows_loaded.values()), "ingest_s": round(t_ing, 2),
                                   "transform_s": s["seconds"], "affected_orders": s["counts"]["affected_orders"]})
    t0 = time.perf_counter()
    s = transform.run(conn)
    res["noop_rerun_s"] = round(time.perf_counter() - t0, 3)
    t0 = time.perf_counter()
    s = transform.run(conn, full_refresh=True)
    res["full_refresh_s"] = s["seconds"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "etl_timings.json").write_text(json.dumps(res, indent=2) + "\n")
    return res
