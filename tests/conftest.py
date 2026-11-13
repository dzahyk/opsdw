from __future__ import annotations

import os
from pathlib import Path

import pytest

from opsdw import db

TEST_DB = os.environ.get("OPSDW_TEST_DB", "opsdw_test")
ROOT = Path(__file__).resolve().parents[1]
DEV_LANDING = ROOT / "data" / "landing" / "dev"


@pytest.fixture
def fresh_conn():
    """A brand-new, empty warehouse database for one test."""
    db.ensure_database(TEST_DB, drop=True)
    conn = db.connect(TEST_DB)
    db.apply_ddl(conn)
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def dev_landing() -> Path:
    if not (DEV_LANDING / "manifest.json").exists():
        from opsdw.generate import generate
        generate(DEV_LANDING, "dev", 42, force=True)
    return DEV_LANDING
