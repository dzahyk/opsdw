"""Landing-zone loader: CSV batch files -> raw.* (append-only).

Landing layout: <landing>/<batch_id>/<entity>.csv, batch_id = YYYY-MM-DD.
Idempotency: every file is recorded in meta.ingested_files with its sha256.
Re-ingesting the same file is a no-op; a file whose content changed after it
was ingested is an error (landing files are immutable), never a silent reload.
"""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import psycopg
from psycopg import sql

from .config import ENTITIES, ENTITY_COLUMNS


INGEST_LOCK_KEY = 482_100_018  # session advisory lock: one ingester at a time


class IngestError(RuntimeError):
    pass


@dataclass
class IngestReport:
    files_loaded: int = 0
    files_skipped: int = 0
    rows_loaded: dict[str, int] = field(default_factory=lambda: {e: 0 for e in ENTITIES})


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def batches(landing: Path) -> list[str]:
    return sorted(p.name for p in landing.iterdir() if p.is_dir())


def ingest(conn: psycopg.Connection, landing: Path, until: str | None = None,
           only: list[str] | None = None) -> IngestReport:
    report = IngestReport()
    # Identity values are assigned at INSERT but become visible at COMMIT. Two concurrent
    # ingesters could commit out of id order and a transform in between would skip the lower
    # ids forever. A single serialized ingester commits ids in order, so the watermark is safe.
    if not conn.execute("SELECT pg_try_advisory_lock(%s)", (INGEST_LOCK_KEY,)).fetchone()[0]:
        raise IngestError("another ingest is running (advisory lock held); ingesters must be serialized")
    conn.commit()
    try:
        return _ingest(conn, landing, until, only, report)
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (INGEST_LOCK_KEY,))
        conn.commit()


def _ingest(conn, landing, until, only, report) -> IngestReport:
    for batch_id in batches(landing):
        if until is not None and batch_id > until:
            break
        if only is not None and batch_id not in only:
            continue
        for entity in ENTITIES:
            path = landing / batch_id / f"{entity}.csv"
            if not path.exists():
                continue
            rel = f"{batch_id}/{entity}.csv"
            digest = _sha256(path)
            seen = conn.execute("SELECT sha256 FROM meta.ingested_files WHERE source_file = %s", (rel,)).fetchone()
            if seen:
                if seen[0] != digest:
                    raise IngestError(f"{rel} changed after it was ingested (sha256 mismatch); landing files are immutable")
                report.files_skipped += 1
                continue
            n = _load_file(conn, path, entity, batch_id, rel, digest)
            conn.commit()                      # one transaction per file: file row + its bookkeeping
            report.files_loaded += 1
            report.rows_loaded[entity] += n
    return report


def _load_file(conn: psycopg.Connection, path: Path, entity: str, batch_id: str, rel: str, digest: str) -> int:
    cols = ENTITY_COLUMNS[entity]
    with path.open(newline="") as fh:
        header = next(csv.reader(fh))
    if tuple(header) != cols:
        raise IngestError(f"{rel}: header {header} does not match contract {list(cols)} (schema drift)")
    col_list = sql.SQL(", ").join(map(sql.Identifier, cols))
    conn.execute(sql.SQL("CREATE TEMP TABLE IF NOT EXISTS _load_{e} AS SELECT {c} FROM raw.{e} WITH NO DATA").format(
        e=sql.SQL(entity), c=col_list))
    conn.execute(sql.SQL("TRUNCATE _load_{e}").format(e=sql.SQL(entity)))
    with conn.cursor() as cur:
        with cur.copy(sql.SQL("COPY _load_{e} ({c}) FROM STDIN WITH (FORMAT csv, HEADER true)").format(
                e=sql.SQL(entity), c=col_list)) as cp:
            with path.open("rb") as fh:
                while chunk := fh.read(1 << 20):
                    cp.write(chunk)
        cur.execute(sql.SQL(
            "INSERT INTO raw.{e} (_batch_id, _source_file, {c}) SELECT %s, %s, {c} FROM _load_{e} ORDER BY ctid"
        ).format(e=sql.SQL(entity), c=col_list), (batch_id, rel))
        n = cur.rowcount
        cur.execute(
            "INSERT INTO meta.ingested_files (source_file, entity, batch_id, sha256, row_count) VALUES (%s,%s,%s,%s,%s)",
            (rel, entity, batch_id, digest, n))
    return n
