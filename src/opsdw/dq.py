"""Data-quality runner. Checks live in dq/checks.yml; each returns violating rows."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import psycopg
import yaml

from .config import ROOT

CHECKS_FILE = ROOT / "dq" / "checks.yml"


@dataclass
class Result:
    name: str
    type: str
    severity: str
    failures: int
    sample: list

    @property
    def status(self) -> str:
        if self.failures == 0:
            return "pass"
        return "fail" if self.severity == "error" else "warn"


def compile_check(c: dict) -> tuple[str, str, str]:
    """Return (name, type, sql) for a check definition."""
    t = c.get("type", "custom")
    tbl = c.get("table")
    where = f" AND ({c['where']})" if c.get("where") else ""
    if t == "unique":
        cols = ", ".join(c["columns"])
        name = c.get("name") or f"{tbl}.unique({cols})"
        q = f"SELECT {cols}, count(*) AS n FROM {tbl} WHERE true{where} GROUP BY {cols} HAVING count(*) > 1"
    elif t == "not_null":
        cond = " OR ".join(f"{col} IS NULL" for col in c["columns"])
        shown = ", ".join(c["columns"]) if len(c["columns"]) <= 3 else f"{len(c['columns'])} columns"
        name = c.get("name") or f"{tbl}.not_null({shown})"
        q = f"SELECT * FROM {tbl} WHERE ({cond}){where}"
    elif t == "relationships":
        col, to, field = c["column"], c["to"], c["field"]
        name = c.get("name") or f"{tbl}.{col} -> {to}.{field}"
        q = (f"SELECT s.{col} FROM {tbl} s WHERE s.{col} IS NOT NULL{where} "
             f"AND NOT EXISTS (SELECT 1 FROM {to} p WHERE p.{field} = s.{col})")
    elif t == "accepted_values":
        col = c["column"]
        vals = ", ".join("'" + v.replace("'", "''") + "'" for v in c["values"])
        name = c.get("name") or f"{tbl}.{col} in accepted values"
        q = f"SELECT {col}, count(*) FROM {tbl} WHERE {col} IS NOT NULL AND {col} NOT IN ({vals}){where} GROUP BY {col}"
    else:
        name, q = c["name"], c["sql"]
    return name, t, q


def load_checks(path: Path = CHECKS_FILE) -> list[dict]:
    return yaml.safe_load(path.read_text())["checks"]


def run_checks(conn: psycopg.Connection, checks: list[dict] | None = None, record: bool = True) -> list[Result]:
    results = []
    run_at = dt.datetime.now(dt.timezone.utc)
    for c in checks or load_checks():
        name, t, q = compile_check(c)
        sev = c.get("severity", "error")
        n = conn.execute(f"SELECT count(*) FROM ({q}) AS violations").fetchone()[0]
        sample = conn.execute(f"SELECT * FROM ({q}) AS violations LIMIT 3").fetchall() if n else []
        results.append(Result(name, t, sev, n, sample))
    if record:
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO meta.dq_results VALUES (%s, %s, %s, %s, %s, %s)",
                [(run_at, r.name, r.type, r.severity, r.status, r.failures) for r in results])
    conn.commit()
    return results


def main(conn: psycopg.Connection) -> int:
    results = run_checks(conn)
    width = max(len(r.name) for r in results)
    for r in results:
        mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[r.status]
        print(f"{mark}  {r.name:<{width}}  {r.failures:>8}" + (f"   e.g. {r.sample[:2]}" if r.failures else ""))
    failed = [r for r in results if r.status == "fail"]
    warned = [r for r in results if r.status == "warn"]
    print(f"\n{len(results)} checks: {len(results) - len(failed) - len(warned)} pass, {len(warned)} warn, {len(failed)} FAIL")
    if failed:
        print("DATA QUALITY FAILED: " + "; ".join(r.name for r in failed))
        return 1
    return 0
