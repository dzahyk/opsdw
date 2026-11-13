"""Deterministic synthetic data generator for a FICTIONAL on-demand delivery platform.

Everything produced here is synthetic: no real customers, merchants, couriers or
business outcomes. City names are real Indonesian cities (geography only).
The same (seed, scale) always yields byte-identical landing files.

Data-quality defects are injected ON PURPOSE (rates below) so the pipeline's
dedup / quarantine / late-data handling has something real to do. The exact
number of injected defects is written to manifest.json as ground truth, and the
test-suite checks the pipeline against it.
"""
from __future__ import annotations

import csv
import json
import math
import random
import shutil
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .config import ENTITIES, ENTITY_COLUMNS

START = date(2024, 1, 1)
END = date(2025, 12, 31)
D = (END - START).days + 1                       # 731 simulated days
END_T = D * 1440.0                               # minutes since START 00:00 WIB
OFFSET = 400                                     # day offset so pre-launch timestamps format correctly

SCALES = {
    # signups/day is the main volume knob; orders/customer is ~ 10-12 on average.
    "dev":   {"signups_per_day": 3.5, "merchants": 120},
    "bench": {"signups_per_day": 115.0, "merchants": 3000},
}

CITIES = [("JKT", .35), ("SBY", .18), ("BDG", .15), ("MDN", .12), ("SMG", .10), ("YOG", .10)]
CITY_TRAVEL = {"JKT": 1.20, "SBY": 1.05, "BDG": 1.10, "MDN": 1.05, "SMG": 0.95, "YOG": 0.95}
# channel: (weight, mean orders/day while active, mean active lifetime in days)
CHANNELS = {"organic": (.35, .080, 240), "referral": (.15, .090, 300), "paid_social": (.25, .050, 150),
            "search": (.15, .070, 220), "partner": (.10, .060, 200)}
CATEGORIES = [("food", .60, 55_000), ("grocery", .20, 120_000), ("pharmacy", .08, 80_000), ("retail", .12, 150_000)]
TIERS = [("bronze", .50), ("silver", .35), ("gold", .15)]
PAYMENTS = [("ewallet", .55), ("cash", .20), ("card", .10), ("paylater", .15)]
VEHICLES = [("motorbike", .85), ("car", .10), ("bicycle", .05)]
HOUR_W = [0.2, 0.1, 0.05, 0.05, 0.05, 0.2, 0.6, 1.2, 1.6, 1.4, 1.6, 3.0,
          3.4, 2.2, 1.4, 1.3, 1.6, 2.4, 3.2, 3.0, 2.2, 1.4, 0.8, 0.4]
PEAK_HOURS = {11, 12, 13, 18, 19, 20}
COURIER_CAPACITY = 14                            # orders per working courier-day before recruiting

# Injected defect rates (documented in docs/DATA_SOURCE.md)
P_EVENT_LATE = 0.02          # event lands 1-5 days after it happened
P_EVENT_DUP = 0.005          # exact duplicate re-sent 0-2 days later
P_EVENT_NOISE = 0.01         # event_type casing / whitespace noise (valid after normalisation)
P_EVENT_CORRUPT = 0.0005     # corrupted re-send (unknown event_type) -> quarantine
P_ORDER_CORRECTION = 0.01    # later corrected version (discount changed)
P_STALE_RESEND = 0.20        # of corrections: the ORIGINAL is re-sent after the correction
P_ORDER_CORRUPT = 0.001      # corrupted re-send (negative amount) -> quarantine
P_ORDER_ONLY_CORRUPT = 0.0002  # order header only ever arrives corrupted -> its events stay orphaned
P_CUSTOMER_LATE = 0.01       # customer record lands 1-3 days after signup (early-arriving facts)
P_CUSTOMER_FIX = 0.02        # later SCD1 correction of acquisition_channel
P_CUSTOMER_CORRUPT = 0.001   # corrupted re-send (unknown city) -> quarantine
P_COURIER_LATE = 0.02        # courier record lands 1-2 days after first shift
P_COURIER_CORRUPT = 0.01
P_MERCHANT_LATE = 0.05       # of in-period joiners: first version lands 1-3 days late
P_TIER_CHANGE = 0.20         # merchant gets 1-2 commission tier changes
P_TIER_CHANGE_LATE = 0.10    # of tier changes: lands 3-20 days late (back-dated SCD2 version)
P_MERCHANT_NOOP = 0.03       # re-send with new updated_at but identical attributes
P_MERCHANT_CORRUPT = 0.01


def _wchoice(rng: random.Random, items):
    r = rng.random() * sum(w for _, w, *_ in items)
    acc = 0.0
    for it in items:
        acc += it[1]
        if r <= acc:
            return it
    return items[-1]


_DAY = [(START + timedelta(days=d - OFFSET)).isoformat() for d in range(D + OFFSET + 60)]


def ts(t: float) -> str:
    sec = int(t * 60)
    d, rem = divmod(sec, 86400)
    h, rem = divmod(rem, 3600)
    m, s = divmod(rem, 60)
    return f"{_DAY[d + OFFSET]} {h:02d}:{m:02d}:{s:02d}+07:00"


def day_of(t: float) -> int:
    return int(t // 1440)


def r500(x: float) -> int:
    return int(round(x / 500.0)) * 500


@dataclass
class Merchant:
    merchant_id: str
    city: str
    category: str
    median: int
    join_t: float
    weight: float


class Landing:
    """Buffers rows by landing day and flushes one batch directory per day."""

    def __init__(self, out: Path):
        self.out = out
        self.buf: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
        self.rows = {e: 0 for e in ENTITIES}
        self.batches = 0

    def put(self, day: int, entity: str, row: tuple) -> None:
        self.buf[max(day, 0)][entity].append(row)
        self.rows[entity] += 1

    def flush(self, day: int) -> None:
        data = self.buf.pop(day, None)
        if data is None:
            return
        bdir = self.out / _DAY[day + OFFSET]
        bdir.mkdir(parents=True, exist_ok=True)
        for entity in ENTITIES:
            with (bdir / f"{entity}.csv").open("w", newline="") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(ENTITY_COLUMNS[entity])
                w.writerows(data.get(entity, ()))
        self.batches += 1


def generate(out: Path, scale: str = "dev", seed: int = 42, force: bool = False) -> dict:
    cfg = SCALES[scale]
    if out.exists() and any(out.iterdir()):
        if not force:
            raise SystemExit(f"{out} is not empty; pass --force to regenerate")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    land = Landing(out)
    gt = defaultdict(int)          # ground truth counters for manifest.json

    # ---------------- merchants (SCD2 source) ----------------
    by_city: dict[str, list[Merchant]] = defaultdict(list)
    for i in range(cfg["merchants"]):
        mid = f"M{i + 1:05d}"
        city = _wchoice(rng, CITIES)[0]
        cat, _, median = _wchoice(rng, CATEGORIES)
        tier = _wchoice(rng, TIERS)[0]
        weight = min(rng.paretovariate(1.3), 50.0)
        if rng.random() < 0.6:
            join_t, land_day = -rng.uniform(1, 300) * 1440, 0           # pre-launch merchants land in batch 1
        else:
            join_t = rng.uniform(0, D - 1) * 1440
            land_day = day_of(join_t)
            if rng.random() < P_MERCHANT_LATE:
                land_day += rng.randint(1, 3)
                gt["merchants_first_version_late"] += 1
        name = f"{cat.title()} Merchant {i + 1:05d}"
        attrs = [name, cat, city, tier]
        land.put(land_day, "merchants", (mid, *attrs[:2], city, tier, ts(join_t)))
        last_t = max(join_t, 0.0)
        if rng.random() < P_TIER_CHANGE:
            for _ in range(rng.randint(1, 2)):
                ct = rng.uniform(last_t + 30 * 1440, END_T) if last_t + 30 * 1440 < END_T else None
                if ct is None:
                    break
                attrs[3] = rng.choice([t for t, _ in TIERS if t != attrs[3]])
                lday = day_of(ct)
                if rng.random() < P_TIER_CHANGE_LATE:
                    lday += rng.randint(3, 20)
                    gt["merchant_tier_changes_late"] += 1
                land.put(lday, "merchants", (mid, attrs[0], attrs[1], attrs[2], attrs[3], ts(ct)))
                gt["merchant_tier_changes"] += 1
                last_t = ct
        if rng.random() < P_MERCHANT_NOOP and last_t + 1440 < END_T:
            nt = rng.uniform(last_t + 1440, END_T)
            land.put(day_of(nt), "merchants", (mid, attrs[0], attrs[1], attrs[2], attrs[3], ts(nt)))
            gt["merchant_noop_resends"] += 1
        if rng.random() < P_MERCHANT_CORRUPT:
            land.put(land_day + 1, "merchants", (mid, attrs[0], attrs[1], attrs[2], "platinum", ts(max(join_t, 0) + 61)))
            gt["rejected_merchants"] += 1
        by_city[city].append(Merchant(mid, city, cat, median, join_t, weight))
    pick = {}
    for city, ms in by_city.items():
        ms.sort(key=lambda m: m.join_t)
        cum, acc = [], 0.0
        for m in ms:
            acc += m.weight
            cum.append(acc)
        pick[city] = ([m.join_t for m in ms], cum, ms)

    def pick_merchant(city: str, t: float) -> Merchant:
        joins, cum, ms = pick[city]
        k = bisect_right(joins, t)
        r = rng.random() * cum[k - 1]
        return ms[min(bisect_right(cum, r), k - 1)]

    # ---------------- customers + their order timelines ----------------
    customers: list[tuple[str, str]] = []           # (customer_id, city)
    order_times: list[tuple[float, int]] = []
    ch_items = [(c, w) for c, (w, _, _) in CHANNELS.items()]
    for d in range(D):
        g = 0.6 + 0.8 * d / (D - 1)
        wk = 1.15 if (START + timedelta(days=d)).isoweekday() >= 6 else 1.0
        lam = cfg["signups_per_day"] * g * wk
        n = int(lam) + (1 if rng.random() < lam - int(lam) else 0)
        for _ in range(n):
            idx = len(customers)
            cid = f"C{idx + 1:07d}"
            city = _wchoice(rng, CITIES)[0]
            channel = _wchoice(rng, ch_items)[0]
            hour = _wchoice(rng, list(enumerate(HOUR_W)))[0]
            st = d * 1440 + hour * 60 + rng.random() * 60
            lday = d
            if rng.random() < P_CUSTOMER_LATE:
                lday += rng.randint(1, 3)
                gt["customers_late"] += 1
            land.put(lday, "customers", (cid, ts(st), city, channel, ts(st)))
            if rng.random() < P_CUSTOMER_FIX:
                ft = st + rng.uniform(5, 120) * 1440
                if ft < END_T:
                    newch = rng.choice([c for c in CHANNELS if c != channel])
                    land.put(day_of(ft), "customers", (cid, ts(st), city, newch, ts(ft)))
                    gt["customer_corrections"] += 1
            if rng.random() < P_CUSTOMER_CORRUPT:
                land.put(lday + 1, "customers", (cid, ts(st), "XXX", channel, ts(st + 1)))
                gt["rejected_customers"] += 1
            customers.append((cid, city))
            _, rate_mean, life_mean = CHANNELS[channel]
            if rng.random() < 0.82:                                   # 18% never order (activation gap)
                rate = rng.gammavariate(1.5, rate_mean / 1.5)
                stop = min(st + rng.expovariate(1 / life_mean) * 1440, END_T)
                t = st + rng.expovariate(1 / 1.5) * 1440
                while t < stop:
                    od = day_of(t)
                    h = _wchoice(rng, list(enumerate(HOUR_W)))[0]
                    ot = od * 1440 + h * 60 + rng.random() * 60
                    if ot <= st:
                        ot = st + rng.uniform(5, 60)
                    if ot < END_T:
                        order_times.append((ot, idx))
                    t += rng.expovariate(max(rate, 0.002)) * 1440
    order_times.sort()
    need: dict[tuple[int, str], int] = defaultdict(int)
    for ot, idx in order_times:
        need[(day_of(ot), customers[idx][1])] += 1

    # ---------------- day loop: couriers, orders, events ----------------
    couriers: dict[str, list[list]] = {c: [] for c, _ in CITIES}      # [courier_id, working, active]
    n_couriers = 0
    oi = 0
    order_seq = 0
    for d in range(D):
        working: dict[str, list[str]] = {}
        for city, _ in CITIES:
            pool = couriers[city]
            for c in pool:
                if not c[2]:
                    continue
                if rng.random() < 0.0015:
                    c[2] = False                                      # courier churns for good
                    continue
                c[1] = (rng.random() < 0.80) if c[1] else (rng.random() < 0.45)
            wl = [c[0] for c in pool if c[2] and c[1]]
            req = math.ceil(need.get((d, city), 0) / COURIER_CAPACITY)
            while len(wl) < req:
                n_couriers += 1
                rid = f"R{n_couriers:05d}"
                pool.append([rid, True, True])
                wl.append(rid)
                lday = d
                if rng.random() < P_COURIER_LATE:
                    lday += rng.randint(1, 2)
                    gt["couriers_late"] += 1
                veh = _wchoice(rng, VEHICLES)[0]
                land.put(lday, "couriers", (rid, city, veh, ts(d * 1440), ts(d * 1440)))
                if rng.random() < P_COURIER_CORRUPT:
                    land.put(lday + 1, "couriers", (rid, city, "truck", ts(d * 1440), ts(d * 1440 + 1)))
                    gt["rejected_couriers"] += 1
            working[city] = wl

        while oi < len(order_times) and day_of(order_times[oi][0]) == d:
            ot, idx = order_times[oi]
            oi += 1
            order_seq += 1
            _emit_order(rng, land, gt, f"O{order_seq:09d}", ot, customers[idx], pick_merchant, working)
        land.flush(d)
    for d in sorted(list(land.buf)):
        land.flush(d)

    manifest = {
        "generator": "opsdw.generate", "synthetic": True, "scale": scale, "seed": seed,
        "period": [START.isoformat(), END.isoformat()], "batches": land.batches,
        "rows_landed": land.rows,
        "entities": {"customers": len(customers), "merchants": cfg["merchants"], "couriers": n_couriers,
                     "orders": order_seq, "events": gt.pop("events_unique")},
        "injected": dict(sorted(gt.items())),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _emit_order(rng, land: Landing, gt, oid: str, ot: float, cust, pick_merchant, working) -> None:
    cid, city = cust
    m = pick_merchant(city, ot)
    items = max(5_000, r500(rng.lognormvariate(math.log(m.median), 0.5)))
    dist = round(min(20.0, max(0.3, rng.lognormvariate(math.log(3.5), 0.55))), 2)
    fee = r500(5_000 + 2_500 * dist)
    disc = r500(min(items * 0.2, 25_000)) if rng.random() < 0.30 else 0
    pay = _wchoice(rng, PAYMENTS)[0]
    promised = 25 + 5 * math.ceil(4 * dist / 5)
    oday = day_of(ot)
    header = [oid, cid, m.merchant_id, city, ts(ot), f"{items}.00", f"{fee}.00", f"{disc}.00", pay,
              f"{dist:.2f}", str(promised), ts(ot)]
    if rng.random() < P_ORDER_ONLY_CORRUPT:
        bad = header.copy()
        bad[4] = "N/A"
        land.put(oday, "orders", tuple(bad))
        gt["rejected_orders"] += 1
        gt["orders_only_corrupt"] += 1
    else:
        land.put(oday, "orders", tuple(header))
        if rng.random() < P_ORDER_CORRECTION:
            ct = ot + rng.uniform(1, 10) * 1440
            fixed = header.copy()
            fixed[7] = f"{r500(items * 0.1)}.00" if disc == 0 else "0.00"
            fixed[11] = ts(ct)
            land.put(day_of(ct), "orders", tuple(fixed))
            gt["order_corrections"] += 1
            if rng.random() < P_STALE_RESEND:
                land.put(day_of(ct) + rng.randint(1, 3), "orders", tuple(header))
                gt["order_stale_resends"] += 1
        if rng.random() < P_ORDER_CORRUPT:
            bad = header.copy()
            bad[5] = "-15000.00"
            bad[11] = ts(ot + 2)
            land.put(oday + rng.randint(1, 2), "orders", tuple(bad))
            gt["rejected_orders"] += 1

    hour = int((ot % 1440) // 60)
    peak = hour in PEAK_HOURS
    ev: list[tuple] = [("created", ot, None, None, None)]
    wl = working.get(city) or []
    r = rng.random()
    if r < 0.025:
        ev.append(("cancelled", ot + rng.uniform(1, 10), None,
                   "customer_changed_mind" if rng.random() < 0.7 else "payment_failed", None))
    elif not wl or rng.random() < (0.02 if peak else 0.008):
        ev.append(("cancelled", ot + rng.uniform(10, 25), None, "no_courier_available", None))
    else:
        at = ot + 0.3 + rng.expovariate(1 / (3.0 * (1.8 if peak else 1.0)))
        c1 = rng.choice(wl)
        ev.append(("assigned", at, c1, None, None))
        if rng.random() < 0.03 and len(wl) > 1:
            at = at + rng.uniform(2, 6)
            ev.append(("assigned", at, rng.choice([c for c in wl[:50] if c != c1] or [c1]), None, None))
        if rng.random() < 0.03:
            ev.append(("cancelled", at + rng.uniform(3, 15), None,
                       rng.choice(["merchant_closed", "item_unavailable", "customer_changed_mind"]), None))
        else:
            pt = at + rng.lognormvariate(math.log(12), 0.4)
            ev.append(("picked_up", pt, None, None, None))
            if rng.random() < 0.005:
                ev.append(("cancelled", pt + rng.uniform(5, 20), None, "other", None))
            else:
                travel = 3 + dist * 3.2 * rng.lognormvariate(0, 0.25) * (1.25 if peak else 1.0) * CITY_TRAVEL[city]
                dt = pt + travel
                ev.append(("delivered", dt, None, None, None))
                if rng.random() < 0.6:
                    late = dt > ot + promised
                    w = [.15, .20, .30, .20, .15] if late else [.02, .03, .10, .30, .55]
                    rating = _wchoice(rng, [(i + 1, x) for i, x in enumerate(w)])[0]
                    ev.append(("rated", dt + rng.uniform(10, 600), None, None, str(rating)))
    for n, (etype, et, courier, reason, rating) in enumerate(ev, start=1):
        gt["events_unique"] += 1
        eid = f"{oid}-{n:02d}"
        shown = etype
        if rng.random() < P_EVENT_NOISE:
            shown = rng.choice([etype.upper(), f" {etype}", f"{etype.title()} "])
            gt["event_type_noise"] += 1
        row = (eid, oid, shown, ts(et), courier or "", reason or "", rating or "")
        lday = day_of(et)
        if rng.random() < P_EVENT_LATE:
            lday += rng.randint(1, 5)
            gt["events_late"] += 1
        land.put(lday, "order_events", row)
        if rng.random() < P_EVENT_DUP:
            land.put(lday + rng.randint(0, 2), "order_events", row)
            gt["event_duplicates"] += 1
        if rng.random() < P_EVENT_CORRUPT:
            land.put(lday + rng.randint(1, 3), "order_events", (eid, oid, "status_unknown", ts(et), "", "", ""))
            gt["rejected_order_events"] += 1
