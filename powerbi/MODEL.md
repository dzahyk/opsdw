# Power BI semantic model (Power BI-ready, .pbix NOT built)

**Gap, stated plainly:** Power BI Desktop is Windows-only and this project was built on macOS.
No `.pbix` / `.pbip` file was created or opened, and **the DAX in `measures.dax` has not been
executed by a DAX engine**. What *is* delivered and verified:

1. A star-schema view layer (`sql/semantic/bi_views.sql`, schema `bi`) shaped for Power BI.
2. The relationships below.
3. DAX measures (`powerbi/measures.dax`) matching `kpis/kpis.yml` one-to-one (checked by a test).
4. For every measure, an SQL translation evaluated in the same filter context (month × city)
   and reconciled against the canonical KPI SQL and the dashboard: `docs/RECONCILIATION.md`.

## Tables (connect with the PostgreSQL connector to `bi.*`)

| Table | Type | Key | Notes |
|---|---|---|---|
| `fact_orders` | fact (accumulating snapshot) | `order_id` | flags are 0/1 integers; `gmv` and `commission_amount` are 0 for undelivered orders |
| `dim_date` | dimension | `date_key` (yyyymmdd) | mark as date table using `date` |
| `dim_city` | dimension | `city_key` | `-1` = Unknown |
| `dim_customer` | dimension (SCD1) | `customer_key` | `is_inferred = 1` while the customer record has not arrived |
| `dim_merchant` | dimension (SCD2) | `merchant_key` (one row per version) | `valid_from_date` 1900-01-01 / `valid_to_date` 9999-12-31 replace ±infinity |
| `dim_courier` | dimension (SCD1) | `courier_key` | `-1` = not assigned |
| `fact_order_events` | fact (transaction) | `event_id` | optional; for event-level analysis |

## Relationships

| From (many) | To (one) | Cardinality | Cross-filter | Active |
|---|---|---|---|---|
| `fact_orders[created_date_key]` | `dim_date[date_key]` | many-to-one | single | yes |
| `fact_orders[city_key]` | `dim_city[city_key]` | many-to-one | single | yes |
| `fact_orders[customer_key]` | `dim_customer[customer_key]` | many-to-one | single | yes |
| `fact_orders[merchant_key]` | `dim_merchant[merchant_key]` | many-to-one | single | yes |
| `fact_orders[courier_key]` | `dim_courier[courier_key]` | many-to-one | single | yes |
| `fact_order_events[event_date_key]` | `dim_date[date_key]` | many-to-one | single | yes |
| `fact_order_events[courier_key]` | `dim_courier[courier_key]` | many-to-one | single | yes |

Slicing merchants: filtering `dim_merchant[commission_tier]` slices by the tier **at order time**
(point-in-time). To slice by the merchant's *current* attributes, filter on
`dim_merchant[merchant_id]` together with `dim_merchant[is_current] = 1` in a separate
"current merchant" table (not built here).

## Measures

See `measures.dax` (generated alongside `docs/KPI_DICTIONARY.md`). Non-additive measures
(`P90 Delivery Minutes`, `Monthly Active Customers`) must never be summed in a visual total;
Power BI evaluates them in the total's own filter context, which is what the reconciliation's
`ALL` city rows verify.

DAX vs SQL differences to know (found in review):

- `GMV` / `Commission Revenue` return **BLANK** (not 0) for an empty filter context; the SQL
  translation returns 0. Visuals then hide empty cells; use `+ 0` if zeros must show.
- `Monthly Active Customers` is a distinct count over *whatever period is in context*; it is only a
  monthly figure with month on the axis (at year level it is yearly actives).
- The SQL path inner-joins `dim_date`; Power BI would show a fact row with an unknown date key under
  a blank date. The staging validator now rejects any timestamp outside `dim_date`, so none exist.

## Reconciliation sheet

`docs/RECONCILIATION.md` (summary) and `docs/reconciliation.csv` (every month × city × KPI cell):
canonical SQL vs DAX-equivalent SQL on `bi.*` vs the built dashboard, 0 mismatches required.
