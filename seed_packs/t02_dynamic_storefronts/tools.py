"""ADK Function Tools for Seed Pack t02_dynamic_storefronts (BigQuery + Mock Actions)."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from seed_packs.t02_dynamic_storefronts.guardrails import (
    INJECTION_REGEX_PATTERN,
    before_tool_security_callback,
    compute_max_safe_discount_pct,
    contains_injection_marker,
    sanitize_description,
)
from seed_packs.t02_dynamic_storefronts.mcp_server import (
    ACTION_TOOLS,
    generate_hero_lifestyle_image,
    publish_storefront_layout,
    queue_visual_asset_render,
    recall_merchandising_memory,
    render_storefront_preview,
    route_merchandising_task,
    save_merchandising_memory,
    sync_campaign_with_t01,
    update_promo_banner,
)

_DATA_DIR = Path(__file__).resolve().parent / "data"
_DEFAULT_DATASET = "seed_t02"


def _resolve_project_and_dataset() -> tuple[str, str]:
    """Resolve project and dataset at call time; '' project means "not configured"."""
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("AGENT_ENGINE_PROJECT")
        or ""
    ).strip()
    if "your-gcp-project-id" in project.lower() or "your-project-id" in project.lower():
        project = ""
    dataset = os.environ.get("SEED_BQ_DATASET", _DEFAULT_DATASET).strip() or _DEFAULT_DATASET
    return project, dataset


def _offline_reason(project: str) -> str:
    """Explain why BigQuery was skipped and what to do about it."""
    if not project:
        return (
            "GOOGLE_CLOUD_PROJECT (or AGENT_ENGINE_PROJECT) is not set, so these rows come "
            "from the bundled CSV copy. Set GOOGLE_CLOUD_PROJECT in .env and run "
            "`make seed PACK=t02` to query BigQuery."
        )
    return "SEED_OFFLINE_MODE enabled: rows come from the bundled CSV copy."


def _bq_error_hint(exc: Exception) -> str:
    """Turn a BigQuery failure into an actionable fallback reason."""
    return (
        f"BigQuery query failed ({type(exc).__name__}: {exc}). These rows come from the "
        "bundled CSV copy. If the dataset is missing run `make seed PACK=t02`; if "
        "credentials are missing run `gcloud auth application-default login`."
    )


def _read_local_csv(name: str) -> list[dict[str, Any]]:
    path = _DATA_DIR / f"{name}.csv"
    with path.open("r", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def find_catalog_products(
    category: str = "all",
    style_theme: str = "all",
    min_stock: int = 10,
) -> str:
    """Search catalog products in BigQuery by category, style theme, and minimum stock level.

    Args:
        category: Product category (e.g. 'Modular_Sofas', 'Smart_Lighting', 'Ergonomic_Desks', or 'all').
        style_theme: Style theme (e.g. 'Nordic_Minimal', 'Mediterranean_Warm', or 'all').
        min_stock: Minimum stock quantity required (default 10).

    Returns:
        JSON string with matching products sorted by highest margin percentage.
    """
    project, dataset = _resolve_project_and_dataset()
    cat_clean = (category or "all").strip()
    style_clean = (style_theme or "all").strip()
    use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
    if project and not use_offline:
        try:
            client = bigquery.Client(project=project)
            table_ref = f"`{project}.{dataset}.products_catalog`"
            clauses = ["stock_qty >= @min_stock"]
            params: list[Any] = [bigquery.ScalarQueryParameter("min_stock", "INT64", int(min_stock))]
            if cat_clean.lower() != "all":
                clauses.append("LOWER(category) = LOWER(@cat)")
                params.append(bigquery.ScalarQueryParameter("cat", "STRING", cat_clean))
            if style_clean.lower() != "all":
                clauses.append("LOWER(style_theme) = LOWER(@style)")
                params.append(bigquery.ScalarQueryParameter("style", "STRING", style_clean))
            where_sql = " AND ".join(clauses)
            sql = (
                f"SELECT sku_id, product_name, category, style_theme, base_price_eur, "
                f"stock_qty, margin_pct, hero_asset_status, description "
                f"FROM {table_ref} WHERE {where_sql} ORDER BY margin_pct DESC LIMIT 15"
            )
            cfg = bigquery.QueryJobConfig(query_parameters=params)
            rows = [dict(r.items()) for r in client.query(sql, job_config=cfg).result()]
            for row in rows:
                row["description"] = sanitize_description(row.get("description"))
            return json.dumps({
                "status": "SUCCESS",
                "source": f"bigquery:{project}.{dataset}.products_catalog",
                "count": len(rows),
                "products": rows,
            }, default=str)
        except Exception as exc:
            fallback_error = _bq_error_hint(exc)
    else:
        fallback_error = _offline_reason(project)

    rows = [
        r for r in _read_local_csv("products_catalog")
        if int(r["stock_qty"]) >= int(min_stock)
        and (cat_clean.lower() == "all" or r["category"].lower() == cat_clean.lower())
        and (style_clean.lower() == "all" or r["style_theme"].lower() == style_clean.lower())
    ]
    rows.sort(key=lambda r: float(r["margin_pct"]), reverse=True)
    top_rows = rows[:15]
    for row in top_rows:
        row["description"] = sanitize_description(row.get("description"))
    return json.dumps({
        "status": "SUCCESS",
        "source": "local_csv_fallback",
        "fallback_reason": fallback_error,
        "count": len(top_rows),
        "products": top_rows,
    })


def get_storefront_performance(segment_id: str = "SEG-001", limit: int = 10) -> str:
    """Query storefront experiment performance (views, add-to-cart, purchases, bounce rate) from BigQuery.

    Args:
        segment_id: Audience segment ID (e.g. 'SEG-001' or 'all').
        limit: Max rows to return (default 10).

    Returns:
        JSON string with storefront experiment metrics for the requested segment.
    """
    project, dataset = _resolve_project_and_dataset()
    seg_clean = (segment_id or "all").strip()
    use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
    if project and not use_offline:
        try:
            client = bigquery.Client(project=project)
            table_ref = f"`{project}.{dataset}.storefront_experiments`"
            params: list[Any] = [bigquery.ScalarQueryParameter("lim", "INT64", int(limit))]
            where_sql = ""
            if seg_clean.lower() != "all":
                where_sql = "WHERE LOWER(segment_id) = LOWER(@seg) "
                params.append(bigquery.ScalarQueryParameter("seg", "STRING", seg_clean))
            sql = (
                f"SELECT experiment_id, segment_id, sku_id, layout_variant, hero_headline, "
                f"views, add_to_cart_count, purchases, bounce_rate_pct "
                f"FROM {table_ref} {where_sql}ORDER BY purchases DESC LIMIT @lim"
            )
            cfg = bigquery.QueryJobConfig(query_parameters=params)
            rows = [dict(r.items()) for r in client.query(sql, job_config=cfg).result()]
            return json.dumps({
                "status": "SUCCESS",
                "source": f"bigquery:{project}.{dataset}.storefront_experiments",
                "segment_id": seg_clean,
                "count": len(rows),
                "experiments": rows,
            }, default=str)
        except Exception as exc:
            fallback_error = _bq_error_hint(exc)
    else:
        fallback_error = _offline_reason(project)

    rows = [
        r for r in _read_local_csv("storefront_experiments")
        if seg_clean.lower() == "all" or r["segment_id"].lower() == seg_clean.lower()
    ][: int(limit)]
    return json.dumps({
        "status": "SUCCESS",
        "source": "local_csv_fallback",
        "fallback_reason": fallback_error,
        "count": len(rows),
        "experiments": rows,
    })


def get_audience_segments(region: str = "all") -> str:
    """Query audience segments, preferred style themes, AOV, and conversion rates from BigQuery.

    Args:
        region: Region filter (e.g. 'UK_London', 'ES_Madrid', 'ES_Barcelona', or 'all').

    Returns:
        JSON string listing audience segments ordered by conversion rate.
    """
    project, dataset = _resolve_project_and_dataset()
    reg_clean = (region or "all").strip()
    use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
    if project and not use_offline:
        try:
            client = bigquery.Client(project=project)
            table_ref = f"`{project}.{dataset}.audience_segments`"
            params: list[Any] = []
            where_sql = ""
            if reg_clean.lower() != "all":
                where_sql = "WHERE LOWER(region) = LOWER(@reg) "
                params.append(bigquery.ScalarQueryParameter("reg", "STRING", reg_clean))
            sql = (
                f"SELECT segment_id, segment_name, region, preferred_style, device_type, "
                f"avg_order_value_eur, conversion_rate_pct "
                f"FROM {table_ref} {where_sql}ORDER BY conversion_rate_pct DESC LIMIT 20"
            )
            cfg = bigquery.QueryJobConfig(query_parameters=params)
            rows = [dict(r.items()) for r in client.query(sql, job_config=cfg).result()]
            return json.dumps({
                "status": "SUCCESS",
                "source": f"bigquery:{project}.{dataset}.audience_segments",
                "region": reg_clean,
                "count": len(rows),
                "segments": rows,
            }, default=str)
        except Exception as exc:
            fallback_error = _bq_error_hint(exc)
    else:
        fallback_error = _offline_reason(project)

    rows = [
        r for r in _read_local_csv("audience_segments")
        if reg_clean.lower() == "all" or r["region"].lower() == reg_clean.lower()
    ][:20]
    return json.dumps({
        "status": "SUCCESS",
        "source": "local_csv_fallback",
        "fallback_reason": fallback_error,
        "count": len(rows),
        "segments": rows,
    })


def recommend_storefront_optimization(
    region: str = "all",
    min_bounce_rate_pct: float = 55.0,
    min_stock: int = 20,
    limit: int = 5,
) -> str:
    """Recommend end-to-end storefront optimizations by joining audience_segments, storefront_experiments, and products_catalog in BigQuery.

    Args:
        region: Region filter (e.g. 'ES_Madrid', 'UK_London', 'ES_Barcelona', or 'all').
        min_bounce_rate_pct: Minimum experiment bounce rate percentage to flag for optimization (default 55.0).
        min_stock: Minimum required stock quantity for recommended replacement SKUs (default 20).
        limit: Max recommendations to return (default 5).

    Returns:
        JSON string with joined segment-experiment-SKU recommendations, margin headroom, and max safe discount cap (<=30%).
    """
    try:
        project, dataset = _resolve_project_and_dataset()
        reg_clean = (region or "all").strip()
        min_bounce = float(min_bounce_rate_pct)
        min_stk = int(min_stock)
        lim = int(limit)
        use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}

        if project and not use_offline:
            try:
                client = bigquery.Client(project=project)
                seg_tbl = f"`{project}.{dataset}.audience_segments`"
                exp_tbl = f"`{project}.{dataset}.storefront_experiments`"
                cat_tbl = f"`{project}.{dataset}.products_catalog`"

                reg_clause = ""
                params: list[Any] = [
                    bigquery.ScalarQueryParameter("min_bounce", "FLOAT64", min_bounce),
                    bigquery.ScalarQueryParameter("min_stock", "INT64", min_stk),
                    bigquery.ScalarQueryParameter("lim", "INT64", lim),
                ]
                if reg_clean.lower() != "all":
                    reg_clause = "WHERE LOWER(region) = LOWER(@reg)"
                    params.append(bigquery.ScalarQueryParameter("reg", "STRING", reg_clean))

                sql = f"""
                WITH filtered_segments AS (
                    SELECT segment_id, segment_name, region, preferred_style, device_type,
                           avg_order_value_eur, conversion_rate_pct
                    FROM {seg_tbl}
                    {reg_clause}
                ),
                high_bounce_experiments AS (
                    SELECT experiment_id, segment_id, sku_id AS current_sku_id,
                           layout_variant, bounce_rate_pct, purchases, views
                    FROM {exp_tbl}
                    WHERE bounce_rate_pct >= @min_bounce
                ),
                top_style_skus AS (
                    SELECT sku_id AS recommended_sku_id,
                           product_name AS recommended_product_name,
                           category AS recommended_category,
                           style_theme,
                           base_price_eur AS recommended_price_eur,
                           stock_qty AS recommended_stock_qty,
                           margin_pct AS recommended_margin_pct,
                           GREATEST(0, LEAST(30, CAST(FLOOR(margin_pct - 15.0) AS INT64))) AS max_safe_discount_pct,
                           ROW_NUMBER() OVER (
                               PARTITION BY LOWER(style_theme)
                               ORDER BY margin_pct DESC, stock_qty DESC
                           ) AS rn
                    FROM {cat_tbl}
                    WHERE stock_qty >= @min_stock
                      AND UPPER(sku_id) != 'SKU-0017'
                      AND NOT REGEXP_CONTAINS(
                          LOWER(IFNULL(description, '')),
                          r'{INJECTION_REGEX_PATTERN}'
                      )
                )
                SELECT
                    s.segment_id,
                    s.segment_name,
                    s.region,
                    s.preferred_style,
                    s.device_type,
                    s.conversion_rate_pct,
                    e.experiment_id,
                    e.current_sku_id,
                    e.layout_variant,
                    e.bounce_rate_pct,
                    e.purchases,
                    k.recommended_sku_id,
                    k.recommended_product_name,
                    k.recommended_category,
                    k.recommended_price_eur,
                    k.recommended_stock_qty,
                    k.recommended_margin_pct,
                    k.max_safe_discount_pct
                FROM filtered_segments AS s
                INNER JOIN high_bounce_experiments AS e
                    ON s.segment_id = e.segment_id
                INNER JOIN top_style_skus AS k
                    ON LOWER(s.preferred_style) = LOWER(k.style_theme) AND k.rn = 1
                ORDER BY e.bounce_rate_pct DESC, k.recommended_margin_pct DESC
                LIMIT @lim
                """
                cfg = bigquery.QueryJobConfig(query_parameters=params)
                rows = [dict(r.items()) for r in client.query(sql, job_config=cfg).result()]
                for row in rows:
                    row["recommended_product_name"] = sanitize_description(
                        str(row.get("recommended_product_name", ""))
                    )
                    row["recommended_category"] = sanitize_description(
                        str(row.get("recommended_category", ""))
                    )
                return json.dumps({
                    "status": "SUCCESS",
                    "source": f"bigquery_join:{project}.{dataset}.(audience_segments+storefront_experiments+products_catalog)",
                    "region": reg_clean,
                    "count": len(rows),
                    "recommendations": rows,
                }, default=str)
            except Exception as exc:
                fallback_error = _bq_error_hint(exc)
        else:
            fallback_error = _offline_reason(project)

        segments = [
            s for s in _read_local_csv("audience_segments")
            if reg_clean.lower() == "all" or s["region"].lower() == reg_clean.lower()
        ]
        seg_map = {s["segment_id"]: s for s in segments}

        experiments = [
            e for e in _read_local_csv("storefront_experiments")
            if e["segment_id"] in seg_map and float(e["bounce_rate_pct"]) >= min_bounce
        ]

        catalog = [
            p for p in _read_local_csv("products_catalog")
            if int(p["stock_qty"]) >= min_stk
            and p.get("sku_id", "").strip().upper() != "SKU-0017"
            and not contains_injection_marker(p.get("description"))
        ]
        catalog.sort(key=lambda p: (float(p["margin_pct"]), int(p["stock_qty"])), reverse=True)
        top_by_style: dict[str, dict[str, Any]] = {}
        for p in catalog:
            st = p["style_theme"].lower()
            if st not in top_by_style:
                top_by_style[st] = p

        joined: list[dict[str, Any]] = []
        for e in experiments:
            s = seg_map[e["segment_id"]]
            k = top_by_style.get(s["preferred_style"].lower())
            if not k:
                continue
            margin_val = float(k["margin_pct"])
            max_disc = compute_max_safe_discount_pct(margin_val)
            joined.append({
                "segment_id": s["segment_id"],
                "segment_name": s["segment_name"],
                "region": s["region"],
                "preferred_style": s["preferred_style"],
                "device_type": s["device_type"],
                "conversion_rate_pct": float(s["conversion_rate_pct"]),
                "experiment_id": e["experiment_id"],
                "current_sku_id": e["sku_id"],
                "layout_variant": e["layout_variant"],
                "bounce_rate_pct": float(e["bounce_rate_pct"]),
                "purchases": int(e["purchases"]),
                "recommended_sku_id": k["sku_id"],
                "recommended_product_name": sanitize_description(k["product_name"]),
                "recommended_category": sanitize_description(k["category"]),
                "recommended_price_eur": float(k["base_price_eur"]),
                "recommended_stock_qty": int(k["stock_qty"]),
                "recommended_margin_pct": margin_val,
                "max_safe_discount_pct": max_disc,
            })

        joined.sort(
            key=lambda r: (float(r["bounce_rate_pct"]), float(r["recommended_margin_pct"])),
            reverse=True,
        )
        sliced = joined[:lim]
        return json.dumps({
            "status": "SUCCESS",
            "source": "local_csv_fallback",
            "fallback_reason": fallback_error,
            "region": reg_clean,
            "count": len(sliced),
            "recommendations": sliced,
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


TOOLS = [
    find_catalog_products,
    get_storefront_performance,
    get_audience_segments,
    recommend_storefront_optimization,
]

BEFORE_TOOL_CALLBACK = before_tool_security_callback

__all__ = [
    "TOOLS",
    "ACTION_TOOLS",
    "BEFORE_TOOL_CALLBACK",
    "find_catalog_products",
    "get_storefront_performance",
    "get_audience_segments",
    "recommend_storefront_optimization",
    "publish_storefront_layout",
    "queue_visual_asset_render",
    "update_promo_banner",
    "generate_hero_lifestyle_image",
    "render_storefront_preview",
    "sync_campaign_with_t01",
    "save_merchandising_memory",
    "recall_merchandising_memory",
    "route_merchandising_task",
]
