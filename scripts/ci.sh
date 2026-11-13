#!/usr/bin/env bash
# CI-style gate: rebuild the dev warehouse from scratch and run every check.
# Any failing step exits non-zero (set -e), so this fails loudly.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n==> %s\n' "$*"; }

step "start PostgreSQL (docker compose, host port ${OPSDW_PG_PORT:-55462})"
if command -v docker-compose >/dev/null 2>&1; then DC=docker-compose; else DC="docker compose"; fi
$DC up -d --wait

step "python deps (uv, Python 3.12)"
uv sync --quiet

step "generate deterministic synthetic landing data (dev scale, seed 42)"
[ -f data/landing/dev/manifest.json ] || uv run opsdw generate --scale dev --seed 42

step "rebuild database objects"
uv run opsdw init --recreate

step "ingest landing batches -> raw"
uv run opsdw ingest --scale dev

step "transform raw -> staging -> core -> mart"
uv run opsdw transform

step "re-run is a no-op (idempotency smoke check)"
uv run opsdw transform | grep -q '"affected_orders": 0'

step "data-quality checks (exit 1 on any error-severity failure)"
uv run opsdw dq

step "KPI reconciliation: canonical SQL = semantic model = dashboard"
uv run opsdw reconcile

step "KPI dictionary and DAX file in sync"
uv run opsdw docs >/dev/null

step "test suite (ETL behaviour, analytics expected results, DQ negative tests, reconciliation)"
uv run pytest

printf '\nCI OK\n'
