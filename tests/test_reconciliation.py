"""Dashboard/semantic-model/SQL reconciliation, including proof that it catches a wrong dashboard."""
from __future__ import annotations

import json

import pytest

from opsdw import dashboard, db, ingest, kpis, reconcile, transform

from fixtures.analytics_fixture import build

RECON_DB = "opsdw_recon"


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    root = tmp_path_factory.mktemp("recon_landing")
    build(root)
    db.ensure_database(RECON_DB, drop=True)
    c = db.connect(RECON_DB)
    db.apply_ddl(c)
    ingest.ingest(c, root)
    transform.run(c)
    yield c
    c.close()


def test_all_kpis_reconcile_on_fixture(conn, tmp_path):
    rows = reconcile.reconcile(conn, dist=tmp_path / "index.html")
    assert rows and all(r["status"] == "OK" for r in rows), [r for r in rows if r["status"] != "OK"][:5]
    assert {r["kpi"] for r in rows} == {k["id"] for k in kpis.kpis()}


def test_fixture_kpi_values_match_hand_calculation(conn, tmp_path):
    rows = reconcile.reconcile(conn, dist=tmp_path / "index.html")
    v = {(r["key"], r["year_month"], r["city"]): r["canonical_sql"] for r in rows}
    jan = lambda k, city="ALL": v[(k, "2025-01", city)]
    assert jan("orders_created") == 6 and jan("delivered_orders") == 6
    assert jan("gmv") == 810000.0 and jan("aov") == 135000.0
    assert jan("on_time_rate") == pytest.approx(4 / 6)
    assert jan("commission_revenue") == 129000.0                 # O08 bronze 20,000 + O09 gold 30,000 + ...
    assert jan("take_rate") == pytest.approx(129000 / 810000)
    assert jan("p90_delivery_minutes") == pytest.approx(46.0)    # 30,30,35,38,42,50 -> 42 + 0.5*8
    assert jan("monthly_active_customers") == 5
    assert jan("p90_delivery_minutes", "BDG") == pytest.approx(41.2)   # 30,38,42 -> 38 + 0.8*4
    assert v[("cancellation_rate", "2025-03", "ALL")] == pytest.approx(1 / 3)
    assert v[("completion_rate", "2025-03", "ALL")] == pytest.approx(1 / 3)   # O18 still in progress


def test_reconciliation_catches_naively_averaged_ratios(conn, tmp_path):
    """Classic BI bug: 'All cities' rate = average of the city rates. The reconciliation must flag it."""
    dist = tmp_path / "index.html"
    ds = dashboard.build_dataset(conn)
    ji = ds["months"].index("2025-01")
    city_rates = [ds["values"][c["code"]]["on_time_rate"][ji] for c in ds["cities"] if c["code"] != "ALL"]
    city_rates = [r for r in city_rates if r is not None]
    ds["values"]["ALL"]["on_time_rate"][ji] = sum(city_rates) / len(city_rates)   # JKT 2/3, BDG 2/3 -> same here
    ds["values"]["ALL"]["p90_delivery_minutes"][ji] = sum(
        x for c in ("JKT", "BDG") if (x := ds["values"][c]["p90_delivery_minutes"][ji]) is not None) / 2
    dashboard.render(ds, dist)
    rows = reconcile.reconcile(conn, build=False, dist=dist)
    bad = {(r["key"], r["year_month"], r["city"]) for r in rows if r["status"] != "OK"}
    assert ("p90_delivery_minutes", "2025-01", "ALL") in bad       # averaged percentiles are wrong
    assert ("on_time_rate", "2025-01", "ALL") not in bad          # equal city rates: averaging happens to be right


def test_reconciliation_catches_a_dropped_city(conn, tmp_path):
    dist = tmp_path / "index.html"
    ds = dashboard.build_dataset(conn)
    ds["values"]["ALL"]["gmv"] = ds["values"]["JKT"]["gmv"]        # forgot Bandung in the roll-up
    dashboard.render(ds, dist)
    bad = [r for r in reconcile.reconcile(conn, build=False, dist=dist) if r["status"] != "OK"]
    assert {r["key"] for r in bad} == {"gmv"} and len(bad) == 3     # Jan-24, Feb-24, Jan-25 had BDG GMV


def test_dashboard_embeds_parseable_dataset(conn, tmp_path):
    path = dashboard.render(dashboard.build_dataset(conn), tmp_path / "index.html")
    ds = dashboard.read_embedded(path)
    assert ds["synthetic"] is True and ds["months"][0] == "2024-01" and ds["months"][-1] == "2025-03"
    json.dumps(ds)


def test_dax_measures_file_matches_kpi_dictionary():
    assert kpis.check_dax_file() == []
