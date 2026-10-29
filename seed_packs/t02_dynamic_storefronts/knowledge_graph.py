"""Merchandising Knowledge Graph & Cross-Sell Bundle Engine for Table 2 (`t02_dynamic_storefronts`).

Models a property graph connecting:
- `SEGMENT` (`audience_segments`) -> `LOCATED_IN` -> `REGION`
- `SEGMENT` -> `PREFERS_STYLE` -> `STYLE_THEME`
- `SEGMENT` -> `OBSERVED_IN_EXPERIMENT` -> `EXPERIMENT` (`storefront_experiments`)
- `STYLE_THEME` -> `ANCHORED_BY_HERO` -> `HERO_SKU` (`products_catalog`)
- `STYLE_THEME` -> `STYLE_AFFINITY` -> `STYLE_THEME` (complementary interior styles)
- `HERO_SKU` -> `COMPLEMENTS_CATEGORY` -> `COMPLEMENTARY_SKU` (distinct product categories)
- `HERO_SKU` -> `GUARDED_BY_MARGIN` -> `POLICY` (`<= 30%` max automated discount cap)
- `SEGMENT` -> `SYNCS_WITH_A2A` -> `SISTER_CAMPAIGN` (`expedition_t01_campaign_orchestrator`)
"""

from __future__ import annotations

from typing import Any

from seed_packs.t02_dynamic_storefronts.guardrails import (
    MAX_DISCOUNT_PCT,
    compute_max_safe_discount_pct,
    contains_injection_marker,
    sanitize_description,
)

QUARANTINED_SKU_IDS = ("SKU-0017",)

STYLE_AFFINITY_GRAPH: dict[str, list[tuple[str, float, str]]] = {
    "Nordic_Minimal": [
        ("Mediterranean_Warm", 0.92, "Warm ambient lighting softens clean Nordic upholstery lines."),
        ("Biophilic_Zen", 0.89, "Natural timber ergonomic desks pair with minimalist living zones."),
        ("Neo_Bauhaus", 0.85, "Geometric ceramic accents elevate Nordic modular layouts."),
        ("Industrial_Loft", 0.78, "Architectural acoustic panels frame open-plan Nordic rooms."),
    ],
    "Mediterranean_Warm": [
        ("Nordic_Minimal", 0.93, "Tactile modular sofas anchor warm Mediterranean lighting scenes."),
        ("Neo_Bauhaus", 0.90, "Sculptural ceramic decor complements warm terracotta illumination."),
        ("Biophilic_Zen", 0.86, "Organic workspace surfaces harmonize with warm ambient lighting."),
        ("Industrial_Loft", 0.79, "Textured acoustic panels balance warm Mediterranean interiors."),
    ],
    "Industrial_Loft": [
        ("Biophilic_Zen", 0.91, "Biophilic ergonomic desks soften raw architectural loft acoustics."),
        ("Mediterranean_Warm", 0.88, "Warm smart lighting adds hospitality to industrial studio layouts."),
        ("Nordic_Minimal", 0.84, "Modular sofas create lounge zones inside acoustic loft spaces."),
        ("Neo_Bauhaus", 0.81, "Bold Bauhaus ceramics punctuate industrial shelving."),
    ],
    "Biophilic_Zen": [
        ("Nordic_Minimal", 0.92, "Minimalist modular seating extends biophilic home-office serenity."),
        ("Mediterranean_Warm", 0.89, "Circadian warm smart lighting reinforces biophilic wellbeing."),
        ("Neo_Bauhaus", 0.85, "Artisanal ceramic vessels ground natural workspace aesthetics."),
        ("Industrial_Loft", 0.83, "Acoustic absorption panels improve focus in biophilic studios."),
    ],
    "Neo_Bauhaus": [
        ("Nordic_Minimal", 0.91, "Clean modular sofas provide a neutral canvas for Bauhaus ceramics."),
        ("Mediterranean_Warm", 0.89, "Directional smart lighting highlights sculptural Bauhaus forms."),
        ("Industrial_Loft", 0.85, "Geometric acoustic panels echo Bauhaus structural proportions."),
        ("Biophilic_Zen", 0.82, "Ergonomic timber desks balance bold modernist objects."),
    ],
}


def _is_poisoned_product(row: dict[str, Any]) -> bool:
    sku_id = str(row.get("sku_id", "")).strip().upper()
    if sku_id in QUARANTINED_SKU_IDS:
        return True
    for field in ("sku_id", "product_name", "category", "style_theme", "description"):
        if contains_injection_marker(str(row.get(field, ""))):
            return True
    return False


def build_segment_knowledge_graph(
    segment_id: str,
    segments: list[dict[str, Any]],
    products: list[dict[str, Any]],
    experiments: list[dict[str, Any]],
    max_bundle_size: int = 3,
    min_stock: int = 15,
    source: str = "local_csv_knowledge_graph",
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    """Construct a deterministic merchandising knowledge graph and cross-sell bundle for a segment."""
    seg_clean = (segment_id or "SEG-001").strip().upper()
    bundle_cap = max(1, min(int(max_bundle_size), 5))
    stock_floor = max(0, int(min_stock))

    seg_row = next(
        (s for s in segments if str(s.get("segment_id", "")).strip().upper() == seg_clean),
        None,
    )
    if seg_row is None:
        return {
            "status": "NOT_FOUND",
            "segment_id": seg_clean,
            "error": f"Segment '{seg_clean}' was not found in audience_segments.",
        }

    preferred_style = str(seg_row.get("preferred_style", "Nordic_Minimal")).strip()
    region = str(seg_row.get("region", "EU")).strip()
    segment_name = sanitize_description(str(seg_row.get("segment_name", seg_clean)))
    device_type = str(seg_row.get("device_type", "Desktop_Web")).strip()
    aov_eur = float(seg_row.get("avg_order_value_eur", 0.0) or 0.0)
    conv_rate = float(seg_row.get("conversion_rate_pct", 0.0) or 0.0)

    quarantined_skus: list[str] = []
    safe_products: list[dict[str, Any]] = []
    for p in products:
        sku_id = str(p.get("sku_id", "")).strip().upper()
        if _is_poisoned_product(p):
            if sku_id and sku_id not in quarantined_skus:
                quarantined_skus.append(sku_id)
            continue
        if int(p.get("stock_qty", 0) or 0) < stock_floor:
            continue
        safe_products.append(p)

    for q_sku in sorted(QUARANTINED_SKU_IDS):
        if q_sku not in quarantined_skus:
            quarantined_skus.append(q_sku)

    by_style: dict[str, list[dict[str, Any]]] = {}
    for p in safe_products:
        style_key = str(p.get("style_theme", "")).strip()
        by_style.setdefault(style_key, []).append(p)

    for style_key, items in by_style.items():
        items.sort(
            key=lambda r: (float(r.get("margin_pct", 0.0) or 0.0), int(r.get("stock_qty", 0) or 0)),
            reverse=True,
        )

    hero_candidates = by_style.get(preferred_style, [])
    if not hero_candidates and safe_products:
        hero_candidates = sorted(
            safe_products,
            key=lambda r: (float(r.get("margin_pct", 0.0) or 0.0), int(r.get("stock_qty", 0) or 0)),
            reverse=True,
        )
    if not hero_candidates:
        return {
            "status": "NOT_FOUND",
            "segment_id": seg_clean,
            "error": f"No safe in-stock SKUs (min_stock={stock_floor}) found for segment '{seg_clean}'.",
        }

    hero_raw = hero_candidates[0]
    hero_margin = float(hero_raw.get("margin_pct", 0.0) or 0.0)
    hero_node_data = {
        "sku_id": str(hero_raw["sku_id"]).strip(),
        "product_name": sanitize_description(str(hero_raw.get("product_name", ""))),
        "category": sanitize_description(str(hero_raw.get("category", ""))),
        "style_theme": str(hero_raw.get("style_theme", preferred_style)).strip(),
        "base_price_eur": round(float(hero_raw.get("base_price_eur", 0.0) or 0.0), 2),
        "margin_pct": round(hero_margin, 2),
        "stock_qty": int(hero_raw.get("stock_qty", 0) or 0),
        "max_safe_discount_pct": compute_max_safe_discount_pct(hero_margin),
    }

    nodes: list[dict[str, Any]] = [
        {
            "id": seg_clean,
            "type": "SEGMENT",
            "label": segment_name,
            "properties": {
                "region": region,
                "preferred_style": preferred_style,
                "device_type": device_type,
                "avg_order_value_eur": aov_eur,
                "conversion_rate_pct": conv_rate,
            },
        },
        {
            "id": f"REGION:{region}",
            "type": "REGION",
            "label": region,
            "properties": {"market": region},
        },
        {
            "id": f"STYLE:{preferred_style}",
            "type": "STYLE_THEME",
            "label": preferred_style,
            "properties": {"role": "primary_segment_style"},
        },
        {
            "id": hero_node_data["sku_id"],
            "type": "HERO_SKU",
            "label": hero_node_data["product_name"],
            "properties": hero_node_data,
        },
        {
            "id": f"POLICY:MAX_DISCOUNT_{MAX_DISCOUNT_PCT}_PCT",
            "type": "POLICY",
            "label": f"Max Automated Discount <= {MAX_DISCOUNT_PCT}%",
            "properties": {"max_discount_pct": MAX_DISCOUNT_PCT},
        },
        {
            "id": "AGENT:expedition_t01_campaign_orchestrator",
            "type": "SISTER_CAMPAIGN",
            "label": "Table 1 Autonomous Creative Campaign Orchestrator",
            "properties": {
                "tribe": "Creative AI & AdTech",
                "a2a_handshake": "STOREFRONT_TO_CAMPAIGN_SYNC",
            },
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "source": seg_clean,
            "target": f"REGION:{region}",
            "relation": "LOCATED_IN",
            "weight": 1.0,
            "metadata": {"device_type": device_type},
        },
        {
            "source": seg_clean,
            "target": f"STYLE:{preferred_style}",
            "relation": "PREFERS_STYLE",
            "weight": 1.0,
            "metadata": {"conversion_rate_pct": conv_rate},
        },
        {
            "source": f"STYLE:{preferred_style}",
            "target": hero_node_data["sku_id"],
            "relation": "ANCHORED_BY_HERO",
            "weight": round(hero_margin / 100.0, 3),
            "metadata": {"category": hero_node_data["category"]},
        },
        {
            "source": hero_node_data["sku_id"],
            "target": f"POLICY:MAX_DISCOUNT_{MAX_DISCOUNT_PCT}_PCT",
            "relation": "GUARDED_BY_MARGIN",
            "weight": 1.0,
            "metadata": {"max_safe_discount_pct": hero_node_data["max_safe_discount_pct"]},
        },
        {
            "source": seg_clean,
            "target": "AGENT:expedition_t01_campaign_orchestrator",
            "relation": "SYNCS_WITH_A2A",
            "weight": 0.95,
            "metadata": {"protocol": "A2A/1.0", "tribe": "Creative AI & AdTech"},
        },
    ]

    for exp in experiments:
        if str(exp.get("segment_id", "")).strip().upper() != seg_clean:
            continue
        exp_id = str(exp.get("experiment_id", "")).strip()
        if not exp_id:
            continue
        bounce_val = float(exp.get("bounce_rate_pct", 0.0) or 0.0)
        nodes.append({
            "id": exp_id,
            "type": "EXPERIMENT",
            "label": f"{exp_id} ({exp.get('layout_variant', 'Grid')})",
            "properties": {
                "tested_sku_id": str(exp.get("sku_id", "")),
                "layout_variant": str(exp.get("layout_variant", "")),
                "bounce_rate_pct": bounce_val,
                "purchases": int(exp.get("purchases", 0) or 0),
            },
        })
        edges.append({
            "source": seg_clean,
            "target": exp_id,
            "relation": "OBSERVED_IN_EXPERIMENT",
            "weight": round(bounce_val / 100.0, 3),
            "metadata": {"bounce_rate_pct": bounce_val},
        })

    complementary_skus: list[dict[str, Any]] = []
    seen_categories: set[str] = {hero_node_data["category"].lower()}
    seen_skus: set[str] = {hero_node_data["sku_id"].upper()}

    affinities = STYLE_AFFINITY_GRAPH.get(preferred_style, [])
    for comp_style, affinity_score, rationale in affinities:
        if len(complementary_skus) + 1 >= bundle_cap:
            break
        candidates = by_style.get(comp_style, [])
        chosen = next(
            (
                c
                for c in candidates
                if str(c.get("sku_id", "")).strip().upper() not in seen_skus
                and str(c.get("category", "")).strip().lower() not in seen_categories
            ),
            None,
        )
        if chosen is None:
            continue
        c_margin = float(chosen.get("margin_pct", 0.0) or 0.0)
        comp_item = {
            "sku_id": str(chosen["sku_id"]).strip(),
            "product_name": sanitize_description(str(chosen.get("product_name", ""))),
            "category": sanitize_description(str(chosen.get("category", ""))),
            "style_theme": comp_style,
            "base_price_eur": round(float(chosen.get("base_price_eur", 0.0) or 0.0), 2),
            "margin_pct": round(c_margin, 2),
            "stock_qty": int(chosen.get("stock_qty", 0) or 0),
            "affinity_score": affinity_score,
            "pairing_rationale": rationale,
            "max_safe_discount_pct": compute_max_safe_discount_pct(c_margin),
        }
        complementary_skus.append(comp_item)
        seen_skus.add(comp_item["sku_id"].upper())
        seen_categories.add(comp_item["category"].lower())

        nodes.append({
            "id": f"STYLE:{comp_style}",
            "type": "STYLE_THEME",
            "label": comp_style,
            "properties": {"role": "complementary_style", "affinity_score": affinity_score},
        })
        nodes.append({
            "id": comp_item["sku_id"],
            "type": "COMPLEMENTARY_SKU",
            "label": comp_item["product_name"],
            "properties": comp_item,
        })
        edges.append({
            "source": f"STYLE:{preferred_style}",
            "target": f"STYLE:{comp_style}",
            "relation": "STYLE_AFFINITY",
            "weight": affinity_score,
            "metadata": {"rationale": rationale},
        })
        edges.append({
            "source": hero_node_data["sku_id"],
            "target": comp_item["sku_id"],
            "relation": "COMPLEMENTS_CATEGORY",
            "weight": affinity_score,
            "metadata": {
                "from_category": hero_node_data["category"],
                "to_category": comp_item["category"],
                "rationale": rationale,
            },
        })

    all_bundle_items = [hero_node_data, *complementary_skus]
    bundle_sku_ids = [item["sku_id"] for item in all_bundle_items]
    categories_covered = [item["category"] for item in all_bundle_items]
    combined_price = round(sum(float(item["base_price_eur"]) for item in all_bundle_items), 2)
    avg_margin = round(
        sum(float(item["margin_pct"]) for item in all_bundle_items) / len(all_bundle_items),
        2,
    )
    min_margin = round(min(float(item["margin_pct"]) for item in all_bundle_items), 2)
    max_safe_bundle_disc = compute_max_safe_discount_pct(min_margin)

    result: dict[str, Any] = {
        "status": "SUCCESS",
        "source": source,
        "segment_id": seg_clean,
        "knowledge_graph": {
            "graph_schema_version": "1.0",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "quarantined_skus": quarantined_skus,
            "nodes": nodes,
            "edges": edges,
        },
        "cross_sell_bundle": {
            "bundle_id": f"BUNDLE-{seg_clean}-{preferred_style.upper()}",
            "hero_sku": hero_node_data,
            "complementary_skus": complementary_skus,
            "bundle_sku_ids": bundle_sku_ids,
            "categories_covered": categories_covered,
            "combined_base_price_eur": combined_price,
            "average_margin_pct": avg_margin,
            "min_item_margin_pct": min_margin,
            "max_safe_bundle_discount_pct": max_safe_bundle_disc,
            "recommended_layout_variant": "Curated_Bundle_Carousel",
        },
    }
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result
