# Phase 2 Specification — Table T02 (`t02_dynamic_storefronts`)

## 1. Scope & Targeted Hackathon Bonuses
- **BigQuery Multi-Table Analytics (`+1 pt`)**: `recommend_storefront_optimization` joins `seed_t02.audience_segments`, `seed_t02.storefront_experiments`, and `seed_t02.products_catalog` to diagnose high-bounce storefront experiments and recommend the highest-margin in-stock SKUs matching each segment's `preferred_style`.
- **Multimodality (`+1 pt` — Stretch Goal)**: `generate_hero_lifestyle_image` reads `GEMINI_IMAGE_MODEL` (`gemini-3.1-flash-image`) from environment variables to generate live lifestyle hero visuals for featured SKUs (especially those with `hero_asset_status = 'NEEDS_RENDER'`).
- **MCP App / Generative UI Storefront Preview (`+1 pt`) & Memory (`+1 pt`)**: `render_storefront_preview` builds an interactive `ui://storefront-preview/<segment_id>` HTML5 storefront card adapted to the segment's region, device type, and style theme, while persisting storefront state across sessions.

## 2. BigQuery Data Size & Summary of Optimizations
- **Dataset Size Check**:
  - `seed_t02.audience_segments`: 80 rows (~6 KB)
  - `seed_t02.products_catalog`: 100 rows (~12 KB)
  - `seed_t02.storefront_experiments`: 120 rows (~10 KB)
  - Total size < 30 KB; queried via parameterized `google-cloud-bigquery` SQL for full compatibility with Vertex AI Agent Runtime Python 3.12 containers.
- **Summary of Optimizations Applied**:
  1. **Column Pruning**: Only required analytical fields are projected in each CTE (`filtered_segments`, `high_bounce_experiments`, `ranked_skus`).
  2. **Predicate Pushdown**: Filters on `region`, `bounce_rate_pct >= @min_bounce`, and `stock_qty >= @min_stock` are pushed into base CTEs prior to joining.
  3. **Window Ranking via `QUALIFY`**: Uses `ROW_NUMBER() OVER (PARTITION BY LOWER(style_theme) ORDER BY margin_pct DESC, stock_qty DESC)` to select the top-margin SKU per style theme in a single pass.
