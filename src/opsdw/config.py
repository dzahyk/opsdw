from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql"
DATA_DIR = ROOT / "data"
DEFAULT_LANDING = DATA_DIR / "landing"
ENTITIES = ("customers", "merchants", "couriers", "orders", "order_events")  # ingest order within a batch

ENTITY_COLUMNS: dict[str, tuple[str, ...]] = {
    "customers": ("customer_id", "signup_at", "city_code", "acquisition_channel", "updated_at"),
    "merchants": ("merchant_id", "merchant_name", "category", "city_code", "commission_tier", "updated_at"),
    "couriers": ("courier_id", "city_code", "vehicle_type", "joined_at", "updated_at"),
    "orders": ("order_id", "customer_id", "merchant_id", "city_code", "created_at", "items_amount",
               "delivery_fee", "discount_amount", "payment_method", "distance_km", "promised_minutes", "updated_at"),
    "order_events": ("event_id", "order_id", "event_type", "event_at", "courier_id", "cancel_reason", "rating"),
}


def conninfo(dbname: str | None = None) -> str:
    return (
        f"host={os.environ.get('OPSDW_PG_HOST', '127.0.0.1')} "
        f"port={os.environ.get('OPSDW_PG_PORT', '55462')} "
        f"user={os.environ.get('OPSDW_PG_USER', 'opsdw')} "
        f"password={os.environ.get('OPSDW_PG_PASSWORD', 'opsdw_local_only')} "
        f"dbname={dbname or os.environ.get('OPSDW_PG_DB', 'opsdw')}"
    )
