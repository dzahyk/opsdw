"""Builds dashboard/dist/index.html: a static, self-contained page with the data embedded.

The dashboard computes its numbers along a path deliberately independent of the
canonical KPI SQL: additive measures come from mart.city_daily, roll-ups to
"All cities" and every ratio are done here in Python (sum numerators and
denominators, divide last). `opsdw reconcile` then proves these equal the SQL.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from decimal import Decimal
from pathlib import Path

import psycopg

from .config import ROOT
from . import kpis as kpi_mod

DASH = ROOT / "dashboard"
DIST = DASH / "dist" / "index.html"
ADDITIVE = ("orders_created", "delivered_orders", "cancelled_orders", "on_time_orders", "gmv", "commission_revenue")


def _div(a, b):
    return None if not b else Decimal(a) / Decimal(b)


def build_dataset(conn: psycopg.Connection) -> dict:
    rows = conn.execute((DASH / "dataset_additive.sql").read_text()).fetchall()
    base: dict[tuple[str, str], dict] = {}
    for ym, city, *vals in rows:
        base[(ym, city)] = dict(zip(ADDITIVE, vals))
        tot = base.setdefault((ym, "ALL"), {k: 0 for k in ADDITIVE})   # roll up: SUM the additive parts
        for k, v in zip(ADDITIVE, vals):
            tot[k] += v
    na = {(ym, city): (p90, mac) for ym, city, p90, mac in
          conn.execute((DASH / "dataset_non_additive.sql").read_text()).fetchall()}
    months = sorted({ym for ym, _ in base})
    cities = [("ALL", "All cities")] + [tuple(r) for r in conn.execute(
        "SELECT city_code, city_name FROM core.dim_city WHERE city_key > 0 ORDER BY city_name").fetchall()]
    values: dict[str, dict[str, list]] = {}
    for code, _ in cities:
        series = {k["key"]: [] for k in kpi_mod.kpis()}
        for ym in months:
            b = base.get((ym, code))
            p90, mac = na.get((ym, code), (None, None))
            v = {} if b is None else {
                "orders_created": b["orders_created"], "delivered_orders": b["delivered_orders"], "gmv": b["gmv"],
                "completion_rate": _div(b["delivered_orders"], b["orders_created"]),
                "cancellation_rate": _div(b["cancelled_orders"], b["orders_created"]),
                "on_time_rate": _div(b["on_time_orders"], b["delivered_orders"]),
                "aov": _div(b["gmv"], b["delivered_orders"]),
                "commission_revenue": b["commission_revenue"],
                "take_rate": _div(b["commission_revenue"], b["gmv"]),
            }
            v["p90_delivery_minutes"] = p90
            v["monthly_active_customers"] = mac
            for key in series:
                x = v.get(key)
                series[key].append(None if x is None else (float(x) if isinstance(x, Decimal) else x))
        values[code] = series
    meta = conn.execute("""SELECT (SELECT count(*) FROM core.fact_orders), (SELECT count(*) FROM core.fact_order_events),
                                  (SELECT max(run_id) FROM meta.etl_runs WHERE status = 'success'),
                                  current_database()""").fetchone()
    return {
        "title": "Delivery operations KPIs",
        "synthetic": True,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": {"database": meta[3], "fact_orders": meta[0], "fact_order_events": meta[1], "etl_run_id": meta[2]},
        "months": months,
        "cities": [{"code": c, "name": n} for c, n in cities],
        "kpis": [{"key": k["key"], "id": k["id"], "name": k["name"], "unit": k["unit"]} for k in kpi_mod.kpis()],
        "values": values,
    }


def render(dataset: dict, out: Path = DIST) -> Path:
    html = (DASH / "template.html").read_text()
    payload = json.dumps(dataset, separators=(",", ":")).replace("</", "<\\/")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html.replace("/*__DATASET__*/null", payload))
    return out


def read_embedded(path: Path = DIST) -> dict:
    """Parse the dataset back out of the BUILT artifact (used by the reconciliation)."""
    m = re.search(r'<script id="dataset" type="application/json">(.*?)</script>', path.read_text(), re.S)
    if not m:
        raise RuntimeError(f"no embedded dataset in {path}")
    return json.loads(m.group(1).replace("<\\/", "</"))


def main(conn: psycopg.Connection) -> int:
    path = render(build_dataset(conn))
    print(f"wrote {path.relative_to(ROOT)}")
    return 0
