"""Expected-result tests for every analytical query in sql/analytics on the hand-built fixture.
Expected values were computed by hand from tests/fixtures/analytics_fixture.py (not copied from query output)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from opsdw import db, ingest, transform
from opsdw.config import SQL_DIR

from fixtures.analytics_fixture import build

FIXTURE_DB = "opsdw_fixture"
Q = SQL_DIR / "analytics"
N = None


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    root = tmp_path_factory.mktemp("fixture_landing")
    build(root)
    db.ensure_database(FIXTURE_DB, drop=True)
    c = db.connect(FIXTURE_DB)
    db.apply_ddl(c)
    for b in ingest.batches(root):              # one incremental run per landing batch
        ingest.ingest(c, root, only=[b])
        transform.run(c)
    yield c
    c.close()


def _norm(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


def run(conn, name):
    path = next(Q.glob(f"{name}_*.sql"))
    return [tuple(_norm(v) for v in row) for row in conn.execute(path.read_text()).fetchall()]


def test_every_query_file_has_a_test():
    tested = {f.split("_")[1] for f in globals() if f.startswith("test_q")}
    files = {p.name.split("_")[0] for p in Q.glob("q*.sql")}
    assert len(files) == 18 and files == tested, files ^ tested


def test_q01(conn):
    zeros = [(f"2024-{m:02d}-01", 0, 0.0, 0.0, N) for m in range(4, 13)]   # prev = 0 -> growth undefined
    assert run(conn, "q01") == [
        ("2024-01-01", 3, 370000.0, N, N),
        ("2024-02-01", 2, 230000.0, 370000.0, -37.84),
        ("2024-03-01", 0, 0.0, 230000.0, -100.0),
        *zeros,
        ("2025-01-01", 6, 810000.0, 0.0, N),
        ("2025-02-01", 2, 220000.0, 810000.0, -72.84),
        ("2025-03-01", 1, 110000.0, 220000.0, -50.0),
    ]


def test_q02(conn):
    assert run(conn, "q02") == [
        ("2025-01-01", 810000.0, 370000.0, 118.92),
        ("2025-02-01", 220000.0, 230000.0, -4.35),
        ("2025-03-01", 110000.0, 0.0, N),
    ]


def test_q03(conn):
    assert run(conn, "q03") == [
        ("Bandung", 6, 6, 5, 5, 100.0, 83.33, 100.0, 83.33),
        ("Jakarta", 13, 10, 10, 9, 76.92, 100.0, 90.0, 69.23),
        ("All cities", 19, 16, 15, 14, 84.21, 93.75, 93.33, 73.68),
    ]


def test_q04(conn):
    y24 = [("2024-01-01", 3, k, 0, 0.0) for k in range(2, 12)]
    assert run(conn, "q04") == [
        ("2024-01-01", 3, 0, 3, 100.0),
        ("2024-01-01", 3, 1, 2, 66.67),
        *y24,
        ("2024-01-01", 3, 12, 3, 100.0),
        ("2024-01-01", 3, 13, 1, 33.33),
        ("2024-01-01", 3, 14, 1, 33.33),
        ("2025-01-01", 2, 0, 2, 100.0),
        ("2025-01-01", 2, 1, 1, 50.0),
        ("2025-01-01", 2, 2, 0, 0.0),
    ]


def test_q05(conn):
    def days(start, n, value):
        s = dt.date.fromisoformat(start)
        return [((s + dt.timedelta(d)).isoformat(), value) for d in range(n)]
    expected = (days("2025-02-04", 13, 5) + days("2025-02-17", 3, 4) + [("2025-02-20", 3)]
                + days("2025-02-21", 8, 2) + days("2025-03-01", 2, 1) + days("2025-03-03", 2, 2) + [("2025-03-05", 1)])
    assert len(expected) == 30
    assert run(conn, "q05") == expected


def test_q06(conn):
    assert run(conn, "q06") == [
        ("Bandung", 5, 38.0, 46.8, 48.4),
        ("Jakarta", 9, 36.0, 46.0, 48.0),
        ("All cities", 14, 37.0, 48.5, 50.0),
    ]


def test_q07(conn):
    assert run(conn, "q07") == [
        ("2024-01-01", "Bandung", 1, 1, 100.0),
        ("2024-01-01", "Jakarta", 2, 1, 50.0),
        ("2024-02-01", "Bandung", 1, 0, 0.0),
        ("2024-02-01", "Jakarta", 1, 1, 100.0),
        ("2025-01-01", "Bandung", 3, 2, 66.67),
        ("2025-01-01", "Jakarta", 3, 2, 66.67),
        ("2025-02-01", "Jakarta", 2, 1, 50.0),
        ("2025-03-01", "Jakarta", 1, 1, 100.0),
    ]


def test_q08(conn):
    assert run(conn, "q08") == [
        ("R3", 5, 3, "2025-01-22", "2025-01-24"),
        ("R1", 7, 2, "2025-01-20", "2025-01-21"),
        ("R2", 2, 1, "2024-01-06", "2024-01-06"),
    ]


def test_q09(conn):
    assert run(conn, "q09") == [
        ("2024-01-01", "Bandung", 1, "MC", "Dapur Gamma", 60000.0),
        ("2024-01-01", "Jakarta", 1, "MB", "Grocer Beta", 200000.0),
        ("2024-01-01", "Jakarta", 2, "MA", "Warung Alpha", 110000.0),
        ("2024-02-01", "Bandung", 1, "MC", "Dapur Gamma", 70000.0),
        ("2024-02-01", "Jakarta", 1, "MB", "Grocer Beta", 160000.0),
        ("2025-01-01", "Bandung", 1, "MC", "Dapur Gamma", 200000.0),
        ("2025-01-01", "Jakarta", 1, "MA", "Warung Alpha", 320000.0),   # spans both SCD2 versions of MA
        ("2025-01-01", "Jakarta", 2, "MD", "Retail Delta", 290000.0),
        ("2025-02-01", "Jakarta", 1, "MA", "Warung Alpha", 110000.0),   # tie -> same dense rank
        ("2025-02-01", "Jakarta", 1, "MB", "Grocer Beta", 110000.0),
        ("2025-03-01", "Jakarta", 1, "MA", "Warung Alpha", 110000.0),
    ]


def test_q10(conn):
    assert run(conn, "q10") == [
        ("after_assignment", "merchant_closed", 1, 25.0, 5.26),
        ("after_assignment", "ALL", 1, 25.0, 5.26),
        ("after_pickup", "other", 1, 25.0, 5.26),
        ("after_pickup", "ALL", 1, 25.0, 5.26),
        ("before_assignment", "customer_changed_mind", 1, 25.0, 5.26),
        ("before_assignment", "no_courier_available", 1, 25.0, 5.26),
        ("before_assignment", "ALL", 2, 50.0, 10.53),
        ("ALL", "ALL", 4, 100.0, 21.05),
    ]


def test_q11(conn):
    # R (recency desc): C2 44 ->1, C5 41 ->2, C4 40 ->3, C6 28 ->4, C1 2 ->4  (ceil(4 x cume_dist))
    # F (freq asc):      C5 1 ->1, C2 2 & C6 2 tie ->3 (both), C4 4 ->4, C1 5 ->4
    # M (gmv asc):       C5 ->1, C4 ->2, C6 ->3, C2 ->4, C1 ->4
    # C1 r4 f4 champions; C6 r4 f3 champions; C4 r3 f4 loyal; C2 r1 m4 at_risk; C5 hibernating
    assert run(conn, "q11") == [
        ("at_risk", 1, 44.0, 2.0, 410000.0),
        ("champions", 2, 15.0, 3.5, 1000000.0),
        ("hibernating", 1, 41.0, 1.0, 80000.0),
        ("loyal", 1, 40.0, 4.0, 250000.0),
    ]


def test_q12(conn):
    assert run(conn, "q12") == [
        ("2024-01-01", 3, 2, 66.67, True),
        ("2025-01-01", 2, 1, 50.0, True),
    ]


def test_q13(conn):
    assert run(conn, "q13") == [
        ("bronze", 7, 96000.0, 86000.0, -10000.0),
        ("silver", 3, 76500.0, 76500.0, 0.0),
        ("gold", 4, 105000.0, 105000.0, 0.0),
        ("ALL", 14, 277500.0, 267500.0, -10000.0),
    ]


def test_q14(conn):
    assert run(conn, "q14") == [
        ("Bandung", "2024-01-01", 60000.0, 60000.0),
        ("Bandung", "2024-02-01", 70000.0, 130000.0),
        ("Bandung", "2025-01-01", 200000.0, 200000.0),
        ("Jakarta", "2024-01-01", 310000.0, 310000.0),
        ("Jakarta", "2024-02-01", 160000.0, 470000.0),
        ("Jakarta", "2025-01-01", 610000.0, 610000.0),
        ("Jakarta", "2025-02-01", 220000.0, 830000.0),
        ("Jakarta", "2025-03-01", 110000.0, 940000.0),
    ]


def test_q15(conn):
    assert run(conn, "q15") == [
        ("motorbike", 2, 12, 12, 1.0, 37.58),
        ("car", 1, 2, 2, 1.0, 45.0),
    ]


def test_q16(conn):
    assert run(conn, "q16") == [
        ("organic", 2, 1, 50.0, 250000.0),
        ("partner", 1, 0, 0.0, 0.0),
        ("referral", 1, 1, 100.0, 410000.0),
    ]


def test_q17(conn):
    assert run(conn, "q17") == [(4, 3, 75.0, 1, 37.36)]


def test_q18(conn):
    assert run(conn, "q18") == [
        ("2024-01-05", 1, 2.0, 2.0), ("2024-01-06", 1, 4.0, 3.0), ("2024-01-07", 1, 1.0, 2.33),
        ("2024-02-02", 1, 3.0, 3.0), ("2024-02-03", 1, 2.0, 2.5), ("2024-02-10", 1, 5.0, 5.0),
        ("2025-01-10", 1, 2.0, 2.0), ("2025-01-20", 1, 4.0, 4.0), ("2025-01-21", 1, 1.0, 2.5),
        ("2025-01-22", 1, 3.0, 2.67), ("2025-01-23", 1, 2.0, 2.5), ("2025-01-24", 1, 2.0, 2.4),
        ("2025-02-01", 1, 2.0, 2.0), ("2025-02-05", 1, 5.0, 3.5), ("2025-02-10", 1, 2.0, 3.5),
        ("2025-03-03", 1, 2.0, 2.0),
    ]
