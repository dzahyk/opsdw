# Architecture

```
data/landing/<batch>/*.csv          deterministic synthetic generator (opsdw generate)
        │  opsdw ingest  — COPY, sha256 per file, idempotent, schema-drift check
        ▼
raw.*            append-only, all TEXT, + _ingest_id (identity) / _batch_id / _source_file / _ingested_at
        │  opsdw transform — ONE transaction; delta = _ingest_id in (watermark, max]
        ▼
staging.*        typed + validated (pg_input_is_valid), deduplicated current state;
                 merchant_versions keeps every version; rejected_rows = quarantine with reason
        ▼
core.*           star schema
                   dim_date, dim_city (static, conformed)
                   dim_customer, dim_courier       SCD1 + inferred members
                   dim_merchant                    SCD2 (EXCLUDE constraint: no overlapping versions)
                   fact_orders                     accumulating snapshot, 1 row / order
                   fact_order_events               transaction fact, monthly RANGE partitions
        ▼
mart.city_daily  periodic snapshot, ADDITIVE measures only (day × city)
        ▼
bi.*             Power BI-ready views (0/1 flags, no ±infinity dates)  → DAX measures (powerbi/)
        ▼
dashboard/dist/index.html   static dashboard, data embedded at build time (opsdw dashboard)
```

## Incremental strategy

- **Watermark = raw `_ingest_id`, not a business timestamp.** Late records carry old business
  timestamps but always get a new `_ingest_id`, so they cannot slip behind the watermark — *provided
  ids commit in order*. Identity values are assigned at insert, not commit, so two concurrent ingesters
  could break that; ingest therefore holds an advisory lock (one serialized ingester).
  `hi` is captured at the start of the run; rows landing during a run wait for the next one.
- **Change propagation, not full scans.** Each step outputs the keys it changed
  (`chg_customers`, `chg_merchants`, `chg_orders`, `chg_events`); the fact step rebuilds only
  `aff_orders` = changed headers ∪ orders with new events ∪ orders of merchants whose SCD2 history
  was rebuilt. The mart recomputes only the dates touched (pre- and post-image).
- **Out-of-order versions:** an upsert only applies if `updated_at` is strictly newer.
- **SCD2 by "rebuild affected keys":** a late, back-dated version re-derives the merchant's whole
  history from `staging.merchant_versions`; first version is back-dated to `-infinity` so no order
  falls before history; facts of that merchant are re-keyed in the same run.
- **Early-arriving facts:** customers/couriers get Kimball inferred members (stable surrogate
  key, attributes filled when the record arrives); unknown merchants map to `-1` and are re-keyed.
- **Exactly-once effect:** watermarks advance in the same transaction as the data. A crash
  rolls everything back; the next run re-processes the same delta. An advisory lock prevents
  concurrent transforms. `MERGE ... WHEN MATCHED AND (columns) IS DISTINCT FROM (...)` means a
  re-run rewrites nothing.
- **Full refresh** (`--full-refresh`) truncates and rebuilds through the same code path; a test
  proves 53 incremental runs over the dev data produce exactly the same tables as one full refresh.

## Why these modelling choices

| Choice | Reason |
|---|---|
| SCD2 only for merchants | Commission tier drives revenue; restating history with the current tier is wrong (Q13 measures the error). Customer/courier attribute changes are corrections → SCD1. |
| Accumulating snapshot for orders | Lifecycle milestones arrive as separate events, often late; one row per order makes funnels, latency and on-time KPIs simple and fast. |
| Events partitioned, orders not | Events are append-only, time-sliced and ~4.5× larger; partitioning gives pruning and cheap retention. `fact_orders` (800k rows at bench volume) is updated in place and needs a single-column PK on `order_id`, which partitioning would forbid. |
| Additive-only mart | Distinct counts and percentiles cannot be summed; they are computed from order rows (and the reconciliation proves the dashboard does so). |
| Natural keys kept in the fact | Needed for re-keying after SCD2 rebuilds and for grouping by merchant across versions (Q09). |

## Found at bench volume (not at dev volume)

The first bench-scale initial load (800k orders, 3.6M events) did not finish the event-fact step in
11 minutes and was cancelled. Cause: the step filtered with
`WHERE event_id IN (SELECT event_id FROM chg_events) OR order_id IN (SELECT order_id FROM chg_orders)`.
With 3.6M keys the hashed sub-plan no longer fit in `work_mem` (32 MB), so PostgreSQL fell back to
a plain per-row sub-plan — quadratic. At dev volume (110k events) the same SQL took 0.8 s, so no
test could have caught it. Fix: express the change-set filters as joins/`USING` (hash joins spill
to disk gracefully) and `ANALYZE` every change-set temp table so the planner sees real row counts.
Only tiny reference look-ups (`dim_city`, `ref_commission_tier`) still use `IN (SELECT …)`.
