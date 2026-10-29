# Dynamic Storefronts – synthetic dataset

Same seeded data shown in Dynamic Storefronts.dc.html. All values are synthetic. Currency EUR. Rates are fractions (0.0234 = 2.34%).

- summary.json – Overview tab KPIs
- products.csv – 100 SKUs (price, gross margin, stock)
- segments.csv – 80 audience segments (city × device × persona)
- experiments.csv – 120 SKU × segment baseline experiments; low_performance = CR below average
- opportunities.csv – Queue: low-performance pairs ranked by score_raw = views × price × margin × bounce_rate; rating indexed to top = 100; potential_* = uplift if CR reached average
- published.csv – Published tab: previous vs new per-visit metrics
- daily_results.csv – Results tab: daily and cumulative storefronts, site-wide CR, BR, revenue and margin per visit (2026-10-09 to 2026-10-29)

Join keys: sku → products.csv, segment_id → segments.csv, experiment_id → experiments.csv.
