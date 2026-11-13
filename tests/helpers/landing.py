"""Tiny helper to hand-write landing batches for scenario tests and fixtures."""
from __future__ import annotations

import csv
from pathlib import Path

from opsdw.config import ENTITIES, ENTITY_COLUMNS


def write_batch(root: Path, batch_id: str, **entities: list[dict]) -> None:
    bdir = root / batch_id
    bdir.mkdir(parents=True, exist_ok=True)
    for entity in ENTITIES:
        cols = ENTITY_COLUMNS[entity]
        with (bdir / f"{entity}.csv").open("w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(cols)
            for row in entities.get(entity, []):
                w.writerow([row.get(c, "") for c in cols])


def customer(cid, signup, city="JKT", channel="organic", updated=None):
    return dict(customer_id=cid, signup_at=signup, city_code=city, acquisition_channel=channel,
                updated_at=updated or signup)


def merchant(mid, tier, updated, city="JKT", category="food", name=None):
    return dict(merchant_id=mid, merchant_name=name or f"Test {mid}", category=category, city_code=city,
                commission_tier=tier, updated_at=updated)


def courier(rid, joined, city="JKT", vehicle="motorbike", updated=None):
    return dict(courier_id=rid, city_code=city, vehicle_type=vehicle, joined_at=joined, updated_at=updated or joined)


def order(oid, cid, mid, created, items=50000, fee=10000, disc=0, city="JKT", pay="ewallet", dist="3.00",
          promised=40, updated=None):
    return dict(order_id=oid, customer_id=cid, merchant_id=mid, city_code=city, created_at=created,
                items_amount=f"{items}.00" if isinstance(items, int) else items, delivery_fee=f"{fee}.00",
                discount_amount=f"{disc}.00",
                payment_method=pay, distance_km=dist, promised_minutes=str(promised), updated_at=updated or created)


def event(eid, oid, etype, at, courier="", reason="", rating=""):
    return dict(event_id=eid, order_id=oid, event_type=etype, event_at=at, courier_id=courier,
                cancel_reason=reason, rating=str(rating))
