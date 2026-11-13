"""Hand-built, fully synthetic fixture for the analytical-query tests.

19 orders, 2 cities, 4 merchants (MA changes bronze -> gold on 2025-01-15),
3 couriers, 9 customers. Every expected value in tests/test_analytics_queries.py
was derived by hand from the table below (see docs/ANALYTICS_QUERIES.md).
The fixture is loaded through the real pipeline (landing -> raw -> ... -> mart),
one landing batch per order date, so the tests also exercise incremental runs.

Outcome codes: D = delivered, CB = cancelled before assignment,
CA = cancelled after assignment, CP = cancelled after pickup, P = still pending.
All orders: delivery_fee 10,000, promised 40 minutes, created at 12:00 WIB unless noted.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from helpers.landing import courier, customer, event, merchant, order, write_batch

WIB = timezone(timedelta(hours=7))

#        id    cust  merch city  created            items   disc  outcome courier lat pick del/cancel reason  rating
ORDERS = [
    ("O01", "C1", "MA", "JKT", "2024-01-05 12:00", 100000, 0,     "D",  "R1", 2, 15, 30, None, 5),
    ("O02", "C2", "MB", "JKT", "2024-01-06 13:00", 200000, 10000, "D",  "R2", 4, 20, 45, None, 3),
    ("O03", "C4", "MC", "BDG", "2024-01-07 18:00", 50000,  0,     "D",  "R3", 1, 10, 35, None, None),
    ("O04", "C3", "MA", "JKT", "2024-01-08 19:00", 80000,  0,     "CB", None, None, None, 5, "customer_changed_mind", None),
    ("O05", "C1", "MB", "JKT", "2024-02-02 12:00", 150000, 0,     "D",  "R1", 3, 20, 40, None, None),
    ("O06", "C4", "MC", "BDG", "2024-02-03 12:00", 60000,  0,     "D",  "R3", 2, 15, 50, None, None),
    ("O07", "C5", "MC", "BDG", "2024-02-10 12:00", 40000,  0,     "CA", "R3", 5, None, 10, "merchant_closed", None),
    ("O08", "C1", "MA", "JKT", "2025-01-10 12:00", 100000, 0,     "D",  "R1", 2, 15, 35, None, None),
    ("O09", "C2", "MA", "JKT", "2025-01-20 12:00", 200000, 0,     "D",  "R1", 4, 20, 50, None, None),
    ("O10", "C6", "MD", "JKT", "2025-01-21 12:00", 300000, 20000, "D",  "R1", 1, 10, 30, None, None),
    ("O11", "C4", "MC", "BDG", "2025-01-22 12:00", 50000,  0,     "D",  "R3", 3, 12, 42, None, None),
    ("O12", "C5", "MC", "BDG", "2025-01-23 12:00", 70000,  0,     "D",  "R3", 2, 10, 30, None, None),
    ("O13", "C4", "MC", "BDG", "2025-01-24 12:00", 50000,  0,     "D",  "R3", 2, 10, 38, None, None),
    ("O14", "C1", "MB", "JKT", "2025-02-01 12:00", 100000, 0,     "D",  "R1", 2, 15, 35, None, None),
    ("O15", "C6", "MA", "JKT", "2025-02-05 12:00", 100000, 0,     "D",  "R2", 5, 20, 45, None, None),
    ("O16", "C7", "MB", "JKT", "2025-02-10 12:00", 50000,  0,     "CP", "R2", 2, 15, 30, "other", None),
    ("O17", "C1", "MA", "JKT", "2025-03-03 12:00", 100000, 0,     "D",  "R1", 2, 15, 36, None, None),
    ("O18", "C8", "MA", "JKT", "2025-03-04 12:00", 100000, 0,     "P",  None, None, None, None, None, None),
    ("O19", "C2", "MB", "JKT", "2025-03-05 12:00", 100000, 0,     "CB", None, None, None, 20, "no_courier_available", None),
]

CUSTOMERS = [
    customer("C1", "2024-01-01 09:00:00+07:00", "JKT", "organic"),
    customer("C2", "2024-01-02 09:00:00+07:00", "JKT", "referral"),
    customer("C3", "2024-01-03 09:00:00+07:00", "JKT", "paid_social"),
    customer("C4", "2024-01-04 09:00:00+07:00", "BDG", "organic"),
    customer("C5", "2024-02-01 09:00:00+07:00", "BDG", "search"),
    customer("C6", "2025-01-15 09:00:00+07:00", "JKT", "partner"),
    customer("C7", "2025-02-01 09:00:00+07:00", "JKT", "paid_social"),
    customer("C8", "2025-03-01 09:00:00+07:00", "JKT", "organic"),
    customer("C9", "2025-03-01 09:00:00+07:00", "BDG", "organic"),     # signs up, never orders
]
MERCHANTS = [
    merchant("MA", "bronze", "2023-12-01 00:00:00+07:00", "JKT", "food", "Warung Alpha"),
    merchant("MB", "silver", "2023-12-01 00:00:00+07:00", "JKT", "grocery", "Grocer Beta"),
    merchant("MC", "bronze", "2023-12-01 00:00:00+07:00", "BDG", "food", "Dapur Gamma"),
    merchant("MD", "gold", "2025-01-01 00:00:00+07:00", "JKT", "retail", "Retail Delta"),
]
MA_UPGRADE = merchant("MA", "gold", "2025-01-15 00:00:00+07:00", "JKT", "food", "Warung Alpha")
COURIERS = [
    courier("R1", "2023-12-01 00:00:00+07:00", "JKT", "motorbike"),
    courier("R2", "2023-12-01 00:00:00+07:00", "JKT", "car"),
    courier("R3", "2023-12-01 00:00:00+07:00", "BDG", "motorbike"),
]


def _t(base: datetime, minutes: float) -> str:
    return (base + timedelta(minutes=minutes)).isoformat(sep=" ")


def build(root: Path) -> None:
    write_batch(root, "2024-01-01", customers=CUSTOMERS, merchants=MERCHANTS, couriers=COURIERS)
    by_day: dict[str, dict[str, list]] = {}
    for (oid, cid, mid, city, created, items, disc, outcome, rid, lat, pick, end, reason, rating) in ORDERS:
        base = datetime.fromisoformat(created).replace(tzinfo=WIB)
        day = base.date().isoformat()
        b = by_day.setdefault(day, {"orders": [], "order_events": []})
        b["orders"].append(order(oid, cid, mid, base.isoformat(sep=" "), items=items, fee=10000, disc=disc,
                                 city=city, promised=40))
        ev = [event(f"{oid}-1", oid, "created", base.isoformat(sep=" "))]
        if outcome == "CB":
            ev.append(event(f"{oid}-2", oid, "cancelled", _t(base, end), reason=reason))
        elif outcome in ("D", "CA", "CP"):
            ev.append(event(f"{oid}-2", oid, "assigned", _t(base, lat), courier=rid))
            if outcome == "CA":
                ev.append(event(f"{oid}-3", oid, "cancelled", _t(base, end), reason=reason))
            else:
                ev.append(event(f"{oid}-3", oid, "picked_up", _t(base, pick)))
                if outcome == "CP":
                    ev.append(event(f"{oid}-4", oid, "cancelled", _t(base, end), reason=reason))
                else:
                    ev.append(event(f"{oid}-4", oid, "delivered", _t(base, end)))
                    if rating:
                        ev.append(event(f"{oid}-5", oid, "rated", _t(base, end + 60), rating=rating))
        b["order_events"].extend(ev)
    by_day.setdefault("2025-01-15", {"orders": [], "order_events": []})["merchants"] = [MA_UPGRADE]
    for day in sorted(by_day):
        write_batch(root, day, **by_day[day])
