# Convenience wrappers. Everything is also runnable directly with `uv run opsdw <cmd>`.
.PHONY: up down ci dev bench docs dashboard test

up:            ## start PostgreSQL on 127.0.0.1:55462
	docker-compose up -d --wait

down:
	docker-compose down

ci:            ## full CI-style gate on the dev dataset
	./scripts/ci.sh

dev:           ## build the dev warehouse (database opsdw)
	uv run opsdw generate --scale dev || true
	uv run opsdw init --recreate && uv run opsdw ingest --scale dev && uv run opsdw transform && uv run opsdw dq

bench:         ## rebuild the documented benchmark volume and regenerate docs/perf + docs/RECONCILIATION.md
	uv run opsdw generate --scale bench || true
	OPSDW_PG_DB=opsdw_bench uv run opsdw init --recreate
	OPSDW_PG_DB=opsdw_bench uv run opsdw bench-etl --report-dir docs/perf
	OPSDW_PG_DB=opsdw_bench uv run opsdw dq
	OPSDW_PG_DB=opsdw_bench uv run opsdw bench --repeats 7 --report-dir docs/perf
	OPSDW_PG_DB=opsdw_bench uv run opsdw reconcile --report-dir docs
	uv run python scripts/render_perf_md.py

docs:
	uv run opsdw docs

dashboard:
	uv run opsdw dashboard

test:
	uv run pytest
