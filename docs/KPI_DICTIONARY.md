# KPI dictionary

> Generated from `kpis/kpis.yml` by `uv run opsdw docs`. Do not edit by hand.
> All data is **synthetic** (see `docs/DATA_SOURCE.md`); values describe a fictional platform.

Defaults for every KPI unless a row overrides them:

- **Grain:** order (one row of core.fact_orders = one order)
- **Time window:** calendar month of order creation, Asia/Jakarta (WIB); orders are attributed to their CREATED date, not delivery date
- **Filters:** all cities unless sliced; includes every order whose header passed validation
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)

| ID | KPI | Business question | Numerator | Denominator | Unit | Additive |
|---|---|---|---|---|---|---|
| K01 | Orders Created | How much demand did the platform receive? | COUNT of orders | — | count | yes |
| K02 | Delivered Orders | How many orders were fulfilled? | COUNT of orders with is_delivered = true | — | count | yes |
| K03 | GMV | What value did customers pay for fulfilled orders? | SUM(items_amount + delivery_fee - discount_amount) over delivered orders | — | IDR | yes |
| K04 | Order Completion Rate | What share of demand turns into a delivery? | Delivered Orders (K02) | Orders Created (K01) | ratio | no |
| K05 | Cancellation Rate | What share of demand is lost to cancellation? | COUNT of orders with is_cancelled = true | Orders Created (K01) | ratio | no |
| K06 | On-time Delivery Rate | Do we keep the delivery-time promise? | COUNT of delivered orders with delivered_at <= created_at + promised_minutes | Delivered Orders (K02) | ratio | no |
| K07 | Average Order Value | How much is a typical fulfilled order worth? | GMV (K03) | Delivered Orders (K02) | IDR | no |
| K08 | Commission Revenue | How much did the platform earn from merchants? | SUM(items_amount x commission_rate of the merchant's SCD2 version valid at created_at) over delivered orders | — | IDR | yes |
| K09 | Take Rate | What share of GMV does the platform keep as commission? | Commission Revenue (K08) | GMV (K03) | ratio | no |
| K10 | P90 Delivery Time | How slow are our slowest 10% of deliveries? | 90th percentile (linear interpolation) of delivered_at - created_at in minutes, delivered orders | — | minutes | no |
| K11 | Monthly Active Customers | How many distinct customers received at least one delivery? | COUNT DISTINCT customer_key over delivered orders | — | count | no |

## Definitions, DAX and caveats

### K01 Orders Created

- **Business question:** How much demand did the platform receive?
- **Numerator:** COUNT of orders
- **Denominator:** — (not a ratio)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k01_orders_created.sql`](../sql/kpi/k01_orders_created.sql)
- **DAX:** `Orders Created = COUNTROWS ( fact_orders )`
- **DAX-equivalent SQL (executed in reconciliation):** `count(*)`
- **Caveats:** Counts every order regardless of outcome, including orders still in progress at month end.

### K02 Delivered Orders

- **Business question:** How many orders were fulfilled?
- **Numerator:** COUNT of orders with is_delivered = true
- **Denominator:** — (not a ratio)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k02_delivered_orders.sql`](../sql/kpi/k02_delivered_orders.sql)
- **DAX:** `Delivered Orders = CALCULATE ( COUNTROWS ( fact_orders ), fact_orders[is_delivered] = 1 )`
- **DAX-equivalent SQL (executed in reconciliation):** `count(*) FILTER (WHERE f.is_delivered = 1)`
- **Caveats:** Attributed to creation month; an order created 31 Jan 23:50 and delivered 1 Feb counts in January.

### K03 GMV

- **Business question:** What value did customers pay for fulfilled orders?
- **Numerator:** SUM(items_amount + delivery_fee - discount_amount) over delivered orders
- **Denominator:** — (not a ratio)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k03_gmv.sql`](../sql/kpi/k03_gmv.sql)
- **DAX:** `GMV = SUM ( fact_orders[gmv] )`
- **DAX-equivalent SQL (executed in reconciliation):** `coalesce(sum(f.gmv), 0)`
- **Caveats:** fact_orders.gmv is 0 for non-delivered orders, so a plain SUM is correct. Discounts are platform-funded in this synthetic model; refunds are not modelled.

### K04 Order Completion Rate

- **Business question:** What share of demand turns into a delivery?
- **Numerator:** Delivered Orders (K02)
- **Denominator:** Orders Created (K01)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k04_completion_rate.sql`](../sql/kpi/k04_completion_rate.sql)
- **DAX:** `Completion Rate = DIVIDE ( [Delivered Orders], [Orders Created] )`
- **DAX-equivalent SQL (executed in reconciliation):** `count(*) FILTER (WHERE f.is_delivered = 1)::numeric / nullif(count(*), 0)`
- **Caveats:** The latest month is understated while orders are still in progress; recompute after the month closes.

### K05 Cancellation Rate

- **Business question:** What share of demand is lost to cancellation?
- **Numerator:** COUNT of orders with is_cancelled = true
- **Denominator:** Orders Created (K01)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k05_cancellation_rate.sql`](../sql/kpi/k05_cancellation_rate.sql)
- **DAX:** `Cancellation Rate = DIVIDE ( CALCULATE ( COUNTROWS ( fact_orders ), fact_orders[is_cancelled] = 1 ), [Orders Created] )`
- **DAX-equivalent SQL (executed in reconciliation):** `count(*) FILTER (WHERE f.is_cancelled = 1)::numeric / nullif(count(*), 0)`
- **Caveats:** Completion + cancellation < 100% when orders are still in progress. Use Q10 for the stage/reason split.

### K06 On-time Delivery Rate

- **Business question:** Do we keep the delivery-time promise?
- **Numerator:** COUNT of delivered orders with delivered_at <= created_at + promised_minutes
- **Denominator:** Delivered Orders (K02)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k06_on_time_rate.sql`](../sql/kpi/k06_on_time_rate.sql)
- **DAX:** `On-time Rate = DIVIDE ( CALCULATE ( COUNTROWS ( fact_orders ), fact_orders[is_on_time] = 1 ), [Delivered Orders] )`
- **DAX-equivalent SQL (executed in reconciliation):** `count(*) FILTER (WHERE f.is_on_time = 1)::numeric / nullif(count(*) FILTER (WHERE f.is_delivered = 1), 0)`
- **Caveats:** Arriving exactly at the promised minute counts as on time. Promise = 25 + 4 min/km rounded up to 5 (synthetic rule).

### K07 Average Order Value

- **Business question:** How much is a typical fulfilled order worth?
- **Numerator:** GMV (K03)
- **Denominator:** Delivered Orders (K02)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k07_average_order_value.sql`](../sql/kpi/k07_average_order_value.sql)
- **DAX:** `AOV = DIVIDE ( [GMV], [Delivered Orders] )`
- **DAX-equivalent SQL (executed in reconciliation):** `coalesce(sum(f.gmv), 0) / nullif(count(*) FILTER (WHERE f.is_delivered = 1), 0)`
- **Caveats:** Mean, sensitive to large retail baskets; use Q06-style percentiles for a robust view.

### K08 Commission Revenue

- **Business question:** How much did the platform earn from merchants?
- **Numerator:** SUM(items_amount x commission_rate of the merchant's SCD2 version valid at created_at) over delivered orders
- **Denominator:** — (not a ratio)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k08_commission_revenue.sql`](../sql/kpi/k08_commission_revenue.sql)
- **DAX:** `Commission Revenue = SUM ( fact_orders[commission_amount] )`
- **DAX-equivalent SQL (executed in reconciliation):** `coalesce(sum(f.commission_amount), 0)`
- **Caveats:** Point-in-time tier (SCD2). Orders whose merchant record had not arrived yet carry 0 until re-keyed (see warn.orders_on_unknown_merchant). Delivery fees are not counted as revenue here.

### K09 Take Rate

- **Business question:** What share of GMV does the platform keep as commission?
- **Numerator:** Commission Revenue (K08)
- **Denominator:** GMV (K03)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k09_take_rate.sql`](../sql/kpi/k09_take_rate.sql)
- **DAX:** `Take Rate = DIVIDE ( [Commission Revenue], [GMV] )`
- **DAX-equivalent SQL (executed in reconciliation):** `coalesce(sum(f.commission_amount), 0) / nullif(sum(f.gmv), 0)`
- **Caveats:** Commission is charged on items only, while GMV = items + delivery fee - discount, so take rate is not the tier rate: it is lower when delivery fees exceed discounts and can be higher on heavily discounted orders (per-order maximum in the bench data: 0.235 vs a 0.20 top rate).

### K10 P90 Delivery Time

- **Business question:** How slow are our slowest 10% of deliveries?
- **Numerator:** 90th percentile (linear interpolation) of delivered_at - created_at in minutes, delivered orders
- **Denominator:** — (not a ratio)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k10_p90_delivery_minutes.sql`](../sql/kpi/k10_p90_delivery_minutes.sql)
- **DAX:** `P90 Delivery Minutes = CALCULATE ( PERCENTILE.INC ( fact_orders[delivery_minutes], 0.9 ), fact_orders[is_delivered] = 1 )`
- **DAX-equivalent SQL (executed in reconciliation):** `percentile_cont(0.9) WITHIN GROUP (ORDER BY f.delivery_minutes) FILTER (WHERE f.is_delivered = 1)`
- **Caveats:** NON-ADDITIVE: the all-city or quarterly value must be recomputed from order rows, never averaged from city/month values. PERCENTILE.INC and percentile_cont use the same interpolation.

### K11 Monthly Active Customers

- **Business question:** How many distinct customers received at least one delivery?
- **Numerator:** COUNT DISTINCT customer_key over delivered orders
- **Denominator:** — (not a ratio)
- **Grain / time window / filters:** per defaults above
- **Owner:** Operations BI (illustrative role — synthetic project, no real team)
- **Canonical SQL:** [`sql/kpi/k11_monthly_active_customers.sql`](../sql/kpi/k11_monthly_active_customers.sql)
- **DAX:** `Monthly Active Customers = CALCULATE ( DISTINCTCOUNT ( fact_orders[customer_key] ), fact_orders[is_delivered] = 1 )`
- **DAX-equivalent SQL (executed in reconciliation):** `count(DISTINCT f.customer_key) FILTER (WHERE f.is_delivered = 1)`
- **Caveats:** NON-ADDITIVE: a customer ordering in two cities counts once in 'ALL'. At year level the DAX measure returns yearly distinct customers, not a sum of months.

