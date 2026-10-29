---
name: t02-adk-bigquery
description: This skill should be used when adding, modifying, or debugging ADK LlmAgent instructions and BigQuery analytics tools (find_catalog_products, get_storefront_performance, get_audience_segments, recommend_storefront_optimization) for Table 2 (t02_dynamic_storefronts).
---

# Table 2 ADK & BigQuery Analytics Skill (`t02-adk-bigquery`)

Guides development and maintenance of the ADK `LlmAgent` (`app/agent.py`, `seed_packs/t02_dynamic_storefronts/pack.yaml`) and the BigQuery read/analytics tools in `seed_packs/t02_dynamic_storefronts/tools.py`.

## BigQuery Dataset & Schema (`seed_t02`, `BQ_LOCATION=EU`)

| Table | Primary Key | Key Columns | Rows |
|---|---|---|---|
| `audience_segments` | `segment_id` (`SEG-001`..`SEG-080`) | `segment_name`, `dominant_style`, `avg_basket_eur`, `return_sensitivity`, `region` | 80 |
| `products_catalog` | `sku_id` (`SKU-0001`..`SKU-0100`) | `title`, `category`, `style_theme`, `price_eur`, `margin_pct`, `stock_available`, `visual_tags` | 100 |
| `storefront_experiments` | `experiment_id` (`EXP-0001`..`EXP-0120`) | `segment_id`, `layout_variant`, `hero_sku_id`, `conversion_rate_pct`, `bounce_rate_pct`, `sample_sessions` | 120 |

## Existing ADK BigQuery Tools (`seed_packs/t02_dynamic_storefronts/tools.py`)

1. `find_catalog_products(style_theme: str = "", category: str = "", min_stock: int = 10, limit: int = 8) -> str`
   - Queries `products_catalog` ordered by `margin_pct DESC, stock_available DESC`.
2. `get_storefront_performance(segment_id: str = "", layout_variant: str = "", limit: int = 10) -> str`
   - Queries `storefront_experiments` ordered by `conversion_rate_pct DESC`.
3. `get_audience_segments(region: str = "", dominant_style: str = "", limit: int = 10) -> str`
   - Queries `audience_segments` ordered by `avg_basket_eur DESC`.
4. `recommend_storefront_optimization(region: str = "", segment_id: str = "", min_bounce_rate_pct: float = 45.0, min_stock: int = 15, limit: int = 5) -> str`
   - Performs a 3-table BigQuery JOIN across `audience_segments`, `storefront_experiments`, and `products_catalog` (matching `p.style_theme = s.dominant_style` and excluding `SKU-0017` injection payloads) to rank high-margin replacement SKUs and compute `max_safe_discount_pct` (`min(30, floor(margin_pct - 10.0))`).

## Implementation Pattern for New or Updated BigQuery Tools

Always follow this dual-mode (offline CSV fallback + parameterized BigQuery) pattern:

```python
from google.cloud import bigquery

def my_analytics_tool(region: str = "", min_stock: int = 10, limit: int = 5) -> str:
    """One-line description of what this tool queries and returns.

    Args:
        region: Optional region filter (e.g. ES_Madrid, UK_London).
        min_stock: Minimum stock threshold.
        limit: Maximum rows returned (1 to 25).
    """
    limit = max(1, min(int(limit), 25))
    try:
        if _offline_mode():
            # Deterministic offline fallback using _read_csv("...")
            return json.dumps({"status": "SUCCESS", "source": "local_csv_fallback", "rows": []}, indent=2)

        client = _bq_client()
        params = [
            bigquery.ScalarQueryParameter("min_stock", "INT64", int(min_stock)),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
        sql = f"""
            SELECT sku_id, title, style_theme, margin_pct
            FROM `{_table("products_catalog")}`
            WHERE stock_available >= @min_stock
            LIMIT @limit
        """
        job_config = bigquery.QueryJobConfig(query_parameters=params)
        rows = [dict(r.items()) for r in client.query(sql, job_config=job_config, location=_bq_location()).result()]
        return json.dumps({"status": "SUCCESS", "source": "bigquery", "count": len(rows), "rows": rows}, default=str, indent=2)
    except Exception as exc:
        # Always fall back to CSV or return structured ERROR JSON — never raise
        return json.dumps({"status": "ERROR", "error": str(exc)}, indent=2)
```

## Verification Checklist
- [ ] All SQL parameters use `bigquery.ScalarQueryParameter(...)` inside `bigquery.QueryJobConfig`.
- [ ] Offline mode (`SEED_OFFLINE_MODE=1`) returns deterministic results from `seed_packs/t02_dynamic_storefronts/data/*.csv`.
- [ ] Registered in `TOOLS` list at the bottom of `seed_packs/t02_dynamic_storefronts/tools.py`.
- [ ] Tested with `make test` and `make eval-validate PACK=t02`.
