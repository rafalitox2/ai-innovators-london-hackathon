"""ADK Function Tools for Seed Pack t02_dynamic_storefronts (BigQuery + Mock Actions)."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from google.cloud import bigquery
from seed_packs.t02_dynamic_storefronts.mcp_server import (
    ACTION_TOOLS,
    generate_hero_lifestyle_image,
    publish_storefront_layout,
    queue_visual_asset_render,
    render_storefront_preview,
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
    return json.dumps({
        "status": "SUCCESS",
        "source": "local_csv_fallback",
        "fallback_reason": fallback_error,
        "count": len(rows[:15]),
        "products": rows[:15],
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
            max_disc = max(0, min(30, int(margin_val - 15.0)))
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
                "recommended_product_name": k["product_name"],
                "recommended_category": k["category"],
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


def _min_max_norm(val: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 100.0
    return round(((val - lo) / (hi - lo)) * 100.0, 2)


def rank_skus_by_combined_metrics(
    category: str = "all",
    style_theme: str = "all",
    min_stock: int = 10,
    views_mode: str = "total",
    limit: int = 10,
) -> str:
    """Rank SKUs by a combined 0-100 composite score across views, margin_pct, base_price_eur, and stock_qty.

    Joins `products_catalog` with `storefront_experiments` and min-max normalizes (0-100) each of the
    four metrics (`views`, `margin_pct`, `base_price_eur`, `stock_qty`) with equal 25% weight.

    Args:
        category: Product category filter (e.g. 'Ergonomic_Desks', 'Modular_Sofas', or 'all').
        style_theme: Style theme filter (e.g. 'Biophilic_Zen', 'Nordic_Minimal', or 'all').
        min_stock: Minimum stock quantity required (default 10).
        views_mode: 'total' to sum views across all experiments for a SKU, or 'max_experiment' to use peak single-experiment views.
        limit: Max ranked SKUs to return (default 10).

    Returns:
        JSON string with top-ranked SKUs, raw metrics, 0-100 normalized sub-scores, and combined composite score.
    """
    try:
        project, dataset = _resolve_project_and_dataset()
        cat_clean = (category or "all").strip()
        style_clean = (style_theme or "all").strip()
        mode_clean = (views_mode or "total").strip().lower()
        use_max_exp = mode_clean in {"max", "max_experiment", "single", "single_experiment"}
        lim = max(1, int(limit))
        min_stk = int(min_stock)

        raw_records: list[dict[str, Any]] = []
        source_label = "local_csv_fallback"
        fallback_error = ""

        use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
        if project and not use_offline:
            try:
                client = bigquery.Client(project=project)
                cat_table = f"`{project}.{dataset}.products_catalog`"
                exp_table = f"`{project}.{dataset}.storefront_experiments`"
                clauses = ["p.stock_qty >= @min_stock"]
                params: list[Any] = [bigquery.ScalarQueryParameter("min_stock", "INT64", min_stk)]
                if cat_clean.lower() != "all":
                    clauses.append("LOWER(p.category) = LOWER(@cat)")
                    params.append(bigquery.ScalarQueryParameter("cat", "STRING", cat_clean))
                if style_clean.lower() != "all":
                    clauses.append("LOWER(p.style_theme) = LOWER(@style)")
                    params.append(bigquery.ScalarQueryParameter("style", "STRING", style_clean))
                where_sql = " AND ".join(clauses)
                sql = (
                    f"SELECT p.sku_id, p.product_name, p.category, p.style_theme, "
                    f"p.base_price_eur, p.stock_qty, p.margin_pct, p.hero_asset_status, "
                    f"COALESCE(SUM(e.views), 0) AS total_views, "
                    f"COALESCE(MAX(e.views), 0) AS max_exp_views, "
                    f"COALESCE(SUM(e.purchases), 0) AS total_purchases, "
                    f"COUNT(e.experiment_id) AS experiment_count "
                    f"FROM {cat_table} p "
                    f"LEFT JOIN {exp_table} e ON p.sku_id = e.sku_id "
                    f"WHERE {where_sql} "
                    f"GROUP BY p.sku_id, p.product_name, p.category, p.style_theme, "
                    f"p.base_price_eur, p.stock_qty, p.margin_pct, p.hero_asset_status"
                )
                cfg = bigquery.QueryJobConfig(query_parameters=params)
                raw_records = [dict(r.items()) for r in client.query(sql, job_config=cfg).result()]
                source_label = f"bigquery:{project}.{dataset}.products_catalog+storefront_experiments"
            except Exception as exc:
                fallback_error = _bq_error_hint(exc)
        else:
            fallback_error = _offline_reason(project)

        if not raw_records and source_label == "local_csv_fallback":
            exp_by_sku: dict[str, list[dict[str, Any]]] = {}
            for exp in _read_local_csv("storefront_experiments"):
                exp_by_sku.setdefault(exp["sku_id"], []).append(exp)

            for p in _read_local_csv("products_catalog"):
                if int(p["stock_qty"]) < min_stk:
                    continue
                if cat_clean.lower() != "all" and p["category"].lower() != cat_clean.lower():
                    continue
                if style_clean.lower() != "all" and p["style_theme"].lower() != style_clean.lower():
                    continue
                exps = exp_by_sku.get(p["sku_id"], [])
                raw_records.append({
                    "sku_id": p["sku_id"],
                    "product_name": p["product_name"],
                    "category": p["category"],
                    "style_theme": p["style_theme"],
                    "base_price_eur": float(p["base_price_eur"]),
                    "stock_qty": int(p["stock_qty"]),
                    "margin_pct": float(p["margin_pct"]),
                    "hero_asset_status": p["hero_asset_status"],
                    "total_views": sum(int(x["views"]) for x in exps),
                    "max_exp_views": max((int(x["views"]) for x in exps), default=0),
                    "total_purchases": sum(int(x["purchases"]) for x in exps),
                    "experiment_count": len(exps),
                })

        if not raw_records:
            return json.dumps({
                "status": "SUCCESS",
                "source": source_label,
                "count": 0,
                "ranked_skus": [],
            })

        tot_v_vals = [float(r["total_views"]) for r in raw_records]
        max_v_vals = [float(r["max_exp_views"]) for r in raw_records]
        margin_vals = [float(r["margin_pct"]) for r in raw_records]
        price_vals = [float(r["base_price_eur"]) for r in raw_records]
        stock_vals = [float(r["stock_qty"]) for r in raw_records]

        v_tot_lo, v_tot_hi = min(tot_v_vals), max(tot_v_vals)
        v_max_lo, v_max_hi = min(max_v_vals), max(max_v_vals)
        m_lo, m_hi = min(margin_vals), max(margin_vals)
        p_lo, p_hi = min(price_vals), max(price_vals)
        s_lo, s_hi = min(stock_vals), max(stock_vals)

        scored: list[dict[str, Any]] = []
        for r in raw_records:
            v_tot_score = _min_max_norm(float(r["total_views"]), v_tot_lo, v_tot_hi)
            v_max_score = _min_max_norm(float(r["max_exp_views"]), v_max_lo, v_max_hi)
            m_score = _min_max_norm(float(r["margin_pct"]), m_lo, m_hi)
            p_score = _min_max_norm(float(r["base_price_eur"]), p_lo, p_hi)
            s_score = _min_max_norm(float(r["stock_qty"]), s_lo, s_hi)

            comp_tot = round((v_tot_score + m_score + p_score + s_score) / 4.0, 2)
            comp_max = round((v_max_score + m_score + p_score + s_score) / 4.0, 2)
            active_views_score = v_max_score if use_max_exp else v_tot_score
            active_combined = comp_max if use_max_exp else comp_tot

            scored.append({
                **r,
                "views_score": active_views_score,
                "margin_score": m_score,
                "price_score": p_score,
                "stock_score": s_score,
                "combined_score": active_combined,
                "combined_score_total_views": comp_tot,
                "combined_score_max_exp_views": comp_max,
            })

        scored.sort(key=lambda x: float(x["combined_score"]), reverse=True)
        top_rows = scored[:lim]
        for idx, item in enumerate(top_rows, start=1):
            item["rank"] = idx

        payload: dict[str, Any] = {
            "status": "SUCCESS",
            "source": source_label,
            "views_mode": "max_experiment" if use_max_exp else "total",
            "weights": {
                "views": 0.25,
                "margin_pct": 0.25,
                "base_price_eur": 0.25,
                "stock_qty": 0.25,
            },
            "count": len(top_rows),
            "ranked_skus": top_rows,
        }
        if fallback_error:
            payload["fallback_reason"] = fallback_error
        return json.dumps(payload, default=str)
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


TOOLS = [
    find_catalog_products,
    get_storefront_performance,
    get_audience_segments,
    recommend_storefront_optimization,
    rank_skus_by_combined_metrics,
]

__all__ = [
    "TOOLS",
    "ACTION_TOOLS",
    "find_catalog_products",
    "get_storefront_performance",
    "get_audience_segments",
    "recommend_storefront_optimization",
    "rank_skus_by_combined_metrics",
    "publish_storefront_layout",
    "queue_visual_asset_render",
    "update_promo_banner",
    "generate_hero_lifestyle_image",
    "render_storefront_preview",
    "sync_campaign_with_t01",
]
