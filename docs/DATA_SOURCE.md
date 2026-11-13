# Data source: deterministic synthetic generator

**All data in this project is synthetic.** There are no real customers, merchants, couriers,
transactions or business outcomes. Nothing here describes any real company's performance.

## Why synthetic and not a public dataset

| Need of this project | Synthetic generator | Typical public e-commerce / delivery dataset |
|---|---|---|
| Incremental, late-arriving and out-of-order records to test the ETL | Injected on purpose, with exact counts | Usually a single static dump |
| SCD2 history (merchant commission tier changes, incl. back-dated) | Generated | Rarely present |
| Order lifecycle events (created → assigned → picked up → delivered / cancelled) | Generated | Often only final status |
| Ground truth to test the pipeline against | `manifest.json` lists every injected defect | Unknown |
| Licence / redistribution | Own code, no licence question | Varies; some forbid redistribution |
| Scalable volume for performance work | `--scale dev` / `--scale bench` | Fixed |

The trade-off is realism: distributions are plausible but invented, so **no business conclusion
should be drawn from any number in this repository**. They exist to prove the engineering.

## What is generated

`opsdw.generate` (`src/opsdw/generate.py`) simulates a fictional on-demand delivery platform in six
Indonesian cities (real city names, geography only) from **2024-01-01 to 2025-12-31** and writes one
landing batch per day: `data/landing/<scale>/<YYYY-MM-DD>/{customers,merchants,couriers,orders,order_events}.csv`.

- Same `(scale, seed)` → byte-identical files (single seeded `random.Random`, no wall-clock input).
- Customers sign up (growing over time, weekend uplift) and order following a per-customer Poisson rate
  with a finite active lifetime that depends on the acquisition channel; 18% never order.
- Merchants (Pareto popularity), 60% present at launch; 20% get 1–2 commission-tier changes.
- Couriers are recruited when daily demand exceeds capacity and work in on/off streaks (Markov chain).
- Lifecycle timings: assignment latency (slower at lunch/dinner peaks), prep time, travel time by
  distance with a city traffic factor; ratings depend on lateness.

| Scale | Customers | Merchants | Couriers | Orders | Unique events | Raw rows landed |
|---|---:|---:|---:|---:|---:|---:|
| `dev` (seed 42) | 2,664 | 120 | 58 | 24,484 | 109,643 | 137,948 |
| `bench` (seed 42) | 87,652 | 3,000 | 413 | 800,100 | 3,583,406 | 4,507,273 |

## Injected defects (and where the pipeline handles them)

| Defect | Rate | Handled by |
|---|---|---|
| Event lands 1–5 days after it happened | 2% of events | watermark on `_ingest_id`, accumulating-snapshot rebuild of affected orders |
| Exact duplicate event re-sent 0–2 days later | 0.5% | `DISTINCT ON` + `ON CONFLICT DO NOTHING` on `event_id` |
| `event_type` casing/whitespace noise | 1% | normalised in staging (`lower(trim())`) |
| Corrupted event re-send (unknown type) | 0.05% | quarantined in `staging.rejected_rows` |
| Order correction (discount changed, later `updated_at`) | 1% of orders | newest `updated_at` wins |
| Stale re-send of the original after a correction | 20% of corrections | ignored (`updated_at` must increase) |
| Corrupted order re-send (negative amount) | 0.1% | quarantined |
| Order header only ever arrives corrupted | 0.02% | quarantined; its events wait in staging (`warn.orphan_events_*`) |
| Customer record lands 1–3 days after their first order | 1% | inferred member, filled later (stable key) |
| Courier record lands after first shift | 2% | inferred member |
| Merchant's first version lands 1–3 days late | 5% of in-period joiners | unknown member (-1), re-keyed on arrival |
| Merchant tier change lands 3–20 days late (back-dated) | 10% of tier changes | SCD2 history rebuilt for that merchant, facts re-keyed |
| Merchant re-send with identical attributes | 3% | collapsed (no new SCD2 version) |
| Corrupted customer / courier / merchant re-sends | 0.1% / 1% / 1% | quarantined |

The exact injected counts are in `data/landing/<scale>/manifest.json`;
`tests/test_etl_incremental.py::test_pipeline_matches_generator_ground_truth` asserts the pipeline
quarantines, deduplicates and versions exactly that many records.
