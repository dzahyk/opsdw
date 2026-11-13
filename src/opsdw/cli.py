"""Command line entry point: `uv run opsdw <command>`."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import db, ingest as ingest_mod, transform
from .config import DATA_DIR


def _landing(args) -> Path:
    return Path(args.landing) if args.landing else DATA_DIR / "landing" / args.scale


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="opsdw")
    p.add_argument("--db", default=None, help="database name (default: $OPSDW_PG_DB or opsdw)")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="write deterministic synthetic landing files")
    g.add_argument("--scale", default="dev", choices=["dev", "bench"])
    g.add_argument("--seed", type=int, default=42)
    g.add_argument("--landing", default=None)
    g.add_argument("--force", action="store_true")

    i = sub.add_parser("init", help="create database objects (idempotent)")
    i.add_argument("--recreate", action="store_true", help="drop and recreate the database first")

    ing = sub.add_parser("ingest", help="load landing CSV batches into raw.*")
    ing.add_argument("--scale", default="dev", choices=["dev", "bench"])
    ing.add_argument("--landing", default=None)
    ing.add_argument("--until", default=None, help="last batch id (YYYY-MM-DD) to ingest")

    t = sub.add_parser("transform", help="incremental raw->staging->core->mart run")
    t.add_argument("--full-refresh", action="store_true")
    t.add_argument("-v", "--verbose", action="store_true")

    sub.add_parser("dq", help="run data-quality checks (exit 1 on any error-severity failure)")
    rc = sub.add_parser("reconcile", help="KPI reconciliation: canonical SQL vs semantic model vs dashboard")
    rc.add_argument("--report-dir", default=None, help="default data/reports; the committed copy uses docs")
    b = sub.add_parser("bench", help="EXPLAIN (ANALYZE, BUFFERS) before/after benchmark")
    b.add_argument("--repeats", type=int, default=5)
    b.add_argument("--report-dir", default=None, help="default data/reports/perf; the committed copy uses docs/perf")
    be = sub.add_parser("bench-etl", help="time initial load, per-batch incremental runs and a full refresh")
    be.add_argument("--scale", default="bench", choices=["dev", "bench"])
    be.add_argument("--landing", default=None)
    be.add_argument("--report-dir", default=None, help="default data/reports/perf")
    sub.add_parser("dashboard", help="build the static dashboard from the warehouse")
    sub.add_parser("docs", help="regenerate docs/KPI_DICTIONARY.md from kpis/kpis.yml")

    args = p.parse_args(argv)
    if args.cmd == "generate":
        from .generate import generate
        t0 = time.perf_counter()
        m = generate(_landing(args), args.scale, args.seed, args.force)
        print(json.dumps(m, indent=2))
        print(f"generated in {time.perf_counter() - t0:.1f}s")
        return 0
    if args.cmd == "init":
        name = args.db or __import__("os").environ.get("OPSDW_PG_DB", "opsdw")
        db.ensure_database(name, drop=args.recreate)
        with db.connect(args.db) as conn:
            print("applied:", ", ".join(db.apply_ddl(conn)))
        return 0
    with db.connect(args.db) as conn:
        if args.cmd == "ingest":
            t0 = time.perf_counter()
            r = ingest_mod.ingest(conn, _landing(args), until=args.until)
            print(f"files loaded={r.files_loaded} skipped={r.files_skipped} rows={r.rows_loaded} "
                  f"in {time.perf_counter() - t0:.1f}s")
            return 0
        if args.cmd == "transform":
            s = transform.run(conn, full_refresh=args.full_refresh, verbose=args.verbose)
            print(json.dumps({k: s[k] for k in ("run_id", "mode", "counts", "seconds")}, indent=2))
            return 0
        if args.cmd == "dq":
            from . import dq
            return dq.main(conn)
        if args.cmd == "reconcile":
            from . import reconcile
            return reconcile.main(conn, *( [Path(args.report_dir)] if args.report_dir else []))
        if args.cmd == "bench":
            from . import bench
            return bench.main(conn, repeats=args.repeats, **({"out": Path(args.report_dir)} if args.report_dir else {}))
        if args.cmd == "bench-etl":
            from . import bench
            kw = {"out_dir": Path(args.report_dir)} if args.report_dir else {}
            print(json.dumps(bench.etl_timings(conn, _landing(args), **kw), indent=2))
            return 0
        if args.cmd == "dashboard":
            from . import dashboard
            return dashboard.main(conn)
        if args.cmd == "docs":
            from . import kpis
            return kpis.write_dictionary()
    return 1


if __name__ == "__main__":
    sys.exit(main())
