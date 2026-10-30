"""FastMCP stdio server with Mock Action APIs for Table 2 (t02_dynamic_storefronts)."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
from typing import Any

from mcp.server.fastmcp import FastMCP

from seed_packs.t02_dynamic_storefronts.guardrails import (
    MARGIN_SAFETY_BUFFER_PCT,
    MAX_DISCOUNT_PCT,
    compute_max_safe_discount_pct,
    contains_injection_marker,
    sanitize_description,
    scan_args_for_injection,
    quarantine_action_args,
    validate_policy_number,
)

mcp = FastMCP("t02_dynamic_storefronts_actions")

_PACK_DIR = Path(__file__).resolve().parent
_DATA_DIR = _PACK_DIR / "data"
_DEFAULT_STATE_PATH = _PACK_DIR / ".state.json"
_FALLBACK_STATE_PATH = Path("/tmp/t02_dynamic_storefronts_state.json")
_GCS_STATE_BLOB_PATH = "t02_dynamic_storefronts/state.json"
_sanitize_text = sanitize_description


def _read_csv_rows(name: str) -> list[dict[str, Any]]:
    path = _DATA_DIR / f"{name}.csv"
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fp:
        return list(csv.DictReader(fp))


def _resolve_gcs_bucket_name() -> tuple[str, str]:
    """Return `(project_id, bucket_name)` when GCS state sync is active, or `('', '')`."""
    use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
    sync_enabled = (
        os.environ.get("AGENT_RUNTIME_DEPLOY") == "1"
        or os.environ.get("T02_ENABLE_GCS_STATE") == "1"
    )
    if use_offline or not sync_enabled:
        return "", ""
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("AGENT_ENGINE_PROJECT")
        or ""
    ).strip()
    raw_bucket = (os.environ.get("STAGING_BUCKET") or "").strip()
    if not raw_bucket and project:
        raw_bucket = f"{project}-hackathon-staging"
    bucket_name = raw_bucket.removeprefix("gs://").strip("/")
    return project, bucket_name


def _load_state() -> dict[str, Any]:
    for path in (_DEFAULT_STATE_PATH, _FALLBACK_STATE_PATH):
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    project, bucket_name = _resolve_gcs_bucket_name()
    if bucket_name:
        try:
            from google.cloud import storage

            client = storage.Client(project=project or None)
            blob = client.bucket(bucket_name).blob(_GCS_STATE_BLOB_PATH)
            if blob.exists():
                return json.loads(blob.download_as_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "published_layouts": [],
        "render_queue": [],
        "promo_banners": [],
        "storefront_previews": [],
    }


def _save_state(state: dict[str, Any]) -> str:
    payload = json.dumps(state, indent=2)
    local_written = ""
    for path in (_DEFAULT_STATE_PATH, _FALLBACK_STATE_PATH):
        try:
            path.write_text(payload, encoding="utf-8")
            local_written = str(path)
            break
        except OSError:
            continue
    project, bucket_name = _resolve_gcs_bucket_name()
    if bucket_name:
        try:
            from google.cloud import storage

            client = storage.Client(project=project or None)
            blob = client.bucket(bucket_name).blob(_GCS_STATE_BLOB_PATH)
            blob.upload_from_string(payload, content_type="application/json")
            gcs_uri = f"gs://{bucket_name}/{_GCS_STATE_BLOB_PATH}"
            return f"{gcs_uri}+{local_written}" if local_written else gcs_uri
        except Exception:
            pass
    return local_written or "memory-only"


@mcp.tool()
def publish_storefront_layout(
    segment_id: str,
    featured_skus: str,
    hero_headline: str,
    theme_style: str = "Nordic_Minimal",
) -> str:
    """Publish a personalized dynamic storefront layout for an audience segment.

    Args:
        segment_id: Target audience segment ID (e.g. 'SEG-001').
        featured_skus: Comma-separated list of SKU IDs to feature (e.g. 'SKU-0001,SKU-0006').
        hero_headline: Headline displayed in the storefront hero banner.
        theme_style: Visual style theme (e.g. 'Nordic_Minimal', 'Mediterranean_Warm').

    Returns:
        JSON string confirming the published layout ID and live status.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    rejection = quarantine_action_args(locals())
    if rejection is not None:
        return json.dumps(rejection)
    headline_clean = _sanitize_text(hero_headline)
    if contains_injection_marker(headline_clean):
        return json.dumps({
            "status": "REJECTED",
            "error": "publish_storefront_layout rejected: hero_headline contains an untrusted prompt-injection marker.",
        })
    state = _load_state()
    layouts = state.setdefault("published_layouts", [])
    layout_id = f"LAYOUT-{1001 + len(layouts)}"
    record = {
        "layout_id": layout_id,
        "segment_id": segment_id.strip(),
        "featured_skus": [s.strip() for s in featured_skus.split(",") if s.strip()],
        "hero_headline": headline_clean,
        "theme_style": theme_style.strip(),
        "published_at": datetime.now(timezone.utc).isoformat(),
        "status": "LIVE",
    }
    layouts.append(record)
    backend = _save_state(state)
    return json.dumps({"status": "SUCCESS", "layout": record, "state_backend": backend})


@mcp.tool()
def queue_visual_asset_render(
    sku_id: str,
    scene_prompt: str,
    aspect_ratio: str = "16:9",
) -> str:
    """Queue a generative visual asset render job for a catalog SKU.

    Args:
        sku_id: Catalog SKU ID (e.g. 'SKU-0003').
        scene_prompt: Descriptive scene prompt for lifestyle rendering.
        aspect_ratio: Target aspect ratio ('16:9', '1:1', or '9:16').

    Returns:
        JSON string with render job ID and queue status.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    rejection = quarantine_action_args(locals())
    if rejection is not None:
        return json.dumps(rejection)
    scene_clean = _sanitize_text(scene_prompt)
    if contains_injection_marker(scene_clean):
        return json.dumps({
            "status": "REJECTED",
            "error": "queue_visual_asset_render rejected: scene_prompt contains an untrusted prompt-injection marker.",
        })
    state = _load_state()
    queue = state.setdefault("render_queue", [])
    job_id = f"RENDER-{2001 + len(queue)}"
    record = {
        "render_job_id": job_id,
        "sku_id": sku_id.strip(),
        "scene_prompt": scene_clean,
        "aspect_ratio": aspect_ratio.strip(),
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "status": "QUEUED",
    }
    queue.append(record)
    backend = _save_state(state)
    return json.dumps({"status": "SUCCESS", "render_job": record, "state_backend": backend})


@mcp.tool()
def update_promo_banner(
    segment_id: str,
    discount_pct: int,
    banner_copy: str,
    sku_id: str = "",
) -> str:
    """Update the promotional discount banner for an audience segment (max 30% discount policy, margin-protected).

    Args:
        segment_id: Target audience segment ID (e.g. 'SEG-002').
        discount_pct: Promotional discount percentage (must be between 0 and 30).
        banner_copy: Promotional banner text shown to shoppers.
        sku_id: Optional catalog SKU ID (e.g. 'SKU-0017') to cross-check the discount
            against that SKU's real gross margin. When provided, a discount within the
            30% policy cap can still be rejected if it would undercut the SKU's margin.

    Returns:
        JSON string confirming the banner activation, or a policy/margin rejection.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    rejection = quarantine_action_args(locals())
    if rejection is not None:
        return json.dumps(rejection)
    disc = validate_policy_number(discount_pct, cap=MAX_DISCOUNT_PCT, integral=True)
    if disc is None:
        return json.dumps({
            "status": "REJECTED_POLICY_CAP",
            "error": f"discount_pct must be a finite whole number between 0 and {MAX_DISCOUNT_PCT}; booleans are not allowed.",
        })

    disc = int(disc)
    sku_clean = sku_id.strip()
    if sku_clean:
        sku_row = next(
            (r for r in _read_csv_rows("products_catalog") if r.get("sku_id", "").strip().upper() == sku_clean.upper()),
            None,
        )
        if sku_row is not None:
            margin_pct = float(sku_row.get("margin_pct", 0.0) or 0.0)
            safe_cap = compute_max_safe_discount_pct(margin_pct)
            if disc > safe_cap:
                return json.dumps({
                    "status": "REJECTED_MARGIN_POLICY",
                    "error": (
                        f"discount_pct={disc}% would undercut {sku_clean}'s real gross margin "
                        f"({margin_pct}%); the maximum safe discount at a {MARGIN_SAFETY_BUFFER_PCT}pt "
                        f"margin buffer is {safe_cap}%."
                    ),
                })

    banner_clean = _sanitize_text(banner_copy)
    if contains_injection_marker(banner_clean):
        return json.dumps({
            "status": "REJECTED",
            "error": "update_promo_banner rejected: banner_copy contains an untrusted prompt-injection marker.",
        })

    state = _load_state()
    banners = state.setdefault("promo_banners", [])
    banner_id = f"PROMO-{3001 + len(banners)}"
    record = {
        "banner_id": banner_id,
        "segment_id": segment_id.strip(),
        "sku_id": sku_clean,
        "discount_pct": disc,
        "banner_copy": banner_clean,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": "ACTIVE",
    }
    banners.append(record)
    backend = _save_state(state)
    return json.dumps({"status": "SUCCESS", "promo_banner": record, "state_backend": backend})


@mcp.tool()
def generate_hero_lifestyle_image(
    sku_id: str,
    segment_id: str = "SEG-001",
    style_theme: str = "Nordic_Minimal",
    scene_description: str = "Sunlit modern European living space",
    aspect_ratio: str = "16:9",
) -> str:
    """Generate a tailored hero lifestyle visual asset for a catalog SKU and audience segment using GEMINI_IMAGE_MODEL.

    Args:
        sku_id: Catalog SKU ID (e.g. 'SKU-0006').
        segment_id: Target audience segment ID (e.g. 'SEG-001').
        style_theme: Visual style theme (e.g. 'Nordic_Minimal', 'Mediterranean_Warm').
        scene_description: Architectural and lighting scene prompt for the lifestyle hero shot.
        aspect_ratio: Target aspect ratio ('16:9', '1:1', or '9:16').

    Returns:
        JSON string containing the generated asset file path, model metadata, and render job status.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    rejection = quarantine_action_args(locals())
    if rejection is not None:
        return json.dumps(rejection)
    try:
        sku_clean = (sku_id or "SKU-0001").strip()
        seg_clean = (segment_id or "SEG-001").strip()
        theme_clean = (style_theme or "Nordic_Minimal").strip()
        scene_clean = _sanitize_text(scene_description or "Sunlit modern European living space")
        ratio_clean = (aspect_ratio or "16:9").strip()

        from app.loader import resolve_env_config

        image_model = (
            os.environ.get("GEMINI_IMAGE_MODEL", "").strip()
            or resolve_env_config("GEMINI_IMAGE_MODEL")
        )
        if not image_model:
            return json.dumps({
                "status": "CONFIG_ERROR",
                "error": "GEMINI_IMAGE_MODEL is not set in environment or .env.",
            })

        sku_row = next(
            (r for r in _read_csv_rows("products_catalog") if r.get("sku_id", "").lower() == sku_clean.lower()),
            {"sku_id": sku_clean, "product_name": f"AtelierNova {sku_clean}", "category": "Design_Collection", "base_price_eur": "490.00"},
        )
        product_name = _sanitize_text(str(sku_row.get("product_name", sku_clean)))
        category = _sanitize_text(str(sku_row.get("category", "Design_Collection")))

        seg_row = next(
            (r for r in _read_csv_rows("audience_segments") if r.get("segment_id", "").lower() == seg_clean.lower()),
            {
                "segment_id": seg_clean,
                "segment_name": f"{seg_clean}_Default",
                "region": "UK_London",
                "preferred_style": theme_clean,
                "device_type": "Desktop_Web",
                "avg_order_value_eur": "450.00",
                "conversion_rate_pct": "3.50",
            },
        )
        audience_segment_name = _sanitize_text(str(seg_row.get("segment_name", seg_clean)))
        audience_region = _sanitize_text(str(seg_row.get("region", "UK_London")))
        audience_preferred_style = _sanitize_text(str(seg_row.get("preferred_style", theme_clean)))
        audience_device = _sanitize_text(str(seg_row.get("device_type", "Desktop_Web")))
        audience_aov_eur = float(seg_row.get("avg_order_value_eur", 450.0) or 450.0)
        audience_cr_pct = float(seg_row.get("conversion_rate_pct", 3.5) or 3.5)
        audience_context: dict[str, Any] = {
            "segment_id": seg_clean,
            "segment_name": audience_segment_name,
            "region": audience_region,
            "preferred_style": audience_preferred_style,
            "device_type": audience_device,
            "avg_order_value_eur": audience_aov_eur,
            "conversion_rate_pct": audience_cr_pct,
        }

        prompt_text = (
            f"AtelierNova editorial hero photograph ({ratio_clean}): {product_name} ({sku_clean}, {category}) "
            f"styled in {theme_clean} aesthetic for segment {seg_clean} ({audience_segment_name}, "
            f"region={audience_region}, preferred_style={audience_preferred_style}, device={audience_device}, "
            f"AOV=€{audience_aov_eur:.2f}). Scene: {scene_clean}."
        )

        use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
        project = (os.environ.get("GOOGLE_CLOUD_PROJECT") or resolve_env_config("GOOGLE_CLOUD_PROJECT")).strip()
        location = (os.environ.get("GOOGLE_CLOUD_LOCATION") or resolve_env_config("GOOGLE_CLOUD_LOCATION", default="global")).strip()

        asset_path: Path | None = None
        generation_mode = "svg_editorial_card"

        if project and not use_offline:
            try:
                from google import genai
                from google.genai import types

                client = genai.Client(vertexai=True, project=project, location=location)
                resp = client.models.generate_content(
                    model=image_model,
                    contents=prompt_text,
                    config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
                )
                for cand in getattr(resp, "candidates", []) or []:
                    for part in getattr(getattr(cand, "content", None), "parts", []) or []:
                        inline = getattr(part, "inline_data", None)
                        if inline and getattr(inline, "data", None):
                            out_png = Path(f"/tmp/t02_hero_{sku_clean}_{seg_clean}.png")
                            out_png.write_bytes(inline.data)
                            asset_path = out_png
                            generation_mode = "vertex_ai_multimodal_image"
                            break
                    if asset_path is not None:
                        break
            except Exception:
                asset_path = None

        if asset_path is None:
            svg_path = Path(f"/tmp/t02_hero_{sku_clean}_{seg_clean}.svg")
            svg_markup = (
                f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" width="1280" height="720">'
                f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
                f'<stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#334155"/>'
                f'</linearGradient></defs>'
                f'<rect width="1280" height="720" fill="url(#bg)"/>'
                f'<rect x="60" y="60" width="1160" height="600" rx="24" fill="none" stroke="#94a3b8" stroke-width="2"/>'
                f'<text x="110" y="160" fill="#f8fafc" font-family="sans-serif" font-size="22" letter-spacing="3">'
                f'ATELIERNOVA HOME &amp; LIFESTYLE • {html.escape(theme_clean.upper())} • {html.escape(seg_clean)}</text>'
                f'<text x="110" y="270" fill="#ffffff" font-family="serif" font-size="54" font-weight="bold">'
                f'{html.escape(product_name)} ({html.escape(sku_clean)})</text>'
                f'<text x="110" y="340" fill="#cbd5e1" font-family="sans-serif" font-size="26">'
                f'{html.escape(scene_clean[:95])}</text>'
                f'<text x="110" y="600" fill="#38bdf8" font-family="monospace" font-size="20">'
                f'Rendered via {html.escape(image_model)} • Aspect {html.escape(ratio_clean)}</text>'
                f'</svg>'
            )
            svg_path.write_text(svg_markup, encoding="utf-8")
            asset_path = svg_path

        ui_dir = _PACK_DIR / "ui"
        ui_asset_path_str = str(asset_path)
        ui_sync_warning: str | None = None
        try:
            ui_dir.mkdir(parents=True, exist_ok=True)
            ui_asset_file = ui_dir / f"hero_{seg_clean}{asset_path.suffix}"
            ui_asset_file.write_bytes(asset_path.read_bytes())
            ui_asset_path_str = str(ui_asset_file)
        except OSError as exc:
            ui_sync_warning = f"Failed to sync hero image to ui/: {exc}"

        state = _load_state()
        queue = state.setdefault("render_queue", [])
        job_id = f"HERO-{2501 + len(queue)}"
        record: dict[str, Any] = {
            "render_job_id": job_id,
            "sku_id": sku_clean,
            "product_name": product_name,
            "segment_id": seg_clean,
            "style_theme": theme_clean,
            "scene_description": scene_clean,
            "aspect_ratio": ratio_clean,
            "image_model": image_model,
            "generation_mode": generation_mode,
            "prompt_text": prompt_text,
            "audience_context": audience_context,
            "asset_path": str(asset_path),
            "ui_asset_path": ui_asset_path_str,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
            "status": "RENDERED",
        }
        if ui_sync_warning:
            record["ui_sync_warning"] = ui_sync_warning
        queue.append(record)
        backend = _save_state(state)
        ui_filename = f"hero_{seg_clean}{asset_path.suffix}"
        return json.dumps({
            "status": "SUCCESS",
            "ui_filename": ui_filename,
            "hero_asset_url": f"/api/assets/hero/{seg_clean}?sku_id={sku_clean}&style_theme={theme_clean}",
            "render_job": record,
            "state_backend": backend,
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@mcp.tool()
def render_storefront_preview(
    segment_id: str,
    featured_skus: str,
    hero_headline: str,
    theme_style: str = "Nordic_Minimal",
    discount_pct: int = 15,
    banner_copy: str = "AtelierNova Exclusive Edit",
) -> str:
    """Render an interactive MCP App / Generative UI HTML storefront preview card for an audience segment.

    Args:
        segment_id: Target audience segment ID (e.g. 'SEG-001').
        featured_skus: Comma-separated list of SKU IDs to feature (e.g. 'SKU-0001,SKU-0006').
        hero_headline: Headline displayed in the storefront hero banner.
        theme_style: Visual style theme (e.g. 'Nordic_Minimal', 'Mediterranean_Warm').
        discount_pct: Promotional discount percentage (must be between 0 and 30).
        banner_copy: Promotional banner text shown at the top of the storefront preview.

    Returns:
        JSON string with MCP UI resource URI (`ui://storefront-preview/<segment_id>`), HTML file path, and preview metadata.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    rejection = quarantine_action_args(locals())
    if rejection is not None:
        return json.dumps(rejection)
    try:
        disc = validate_policy_number(discount_pct, cap=MAX_DISCOUNT_PCT, integral=True)
        if disc is None:
            return json.dumps({
                "status": "REJECTED_POLICY_CAP",
                "error": f"discount_pct must be a finite whole number between 0 and {MAX_DISCOUNT_PCT}; booleans are not allowed.",
            })

        disc = int(disc)
        seg_clean = (segment_id or "SEG-001").strip()
        headline_clean = _sanitize_text(hero_headline or "AtelierNova Curated Living")
        theme_clean = (theme_style or "Nordic_Minimal").strip()
        banner_clean = _sanitize_text(banner_copy or "AtelierNova Exclusive Edit")
        sku_list = [s.strip() for s in (featured_skus or "").split(",") if s.strip()]

        catalog_map = {
            r.get("sku_id", "").strip().upper(): r for r in _read_csv_rows("products_catalog")
        }
        for sku in sku_list:
            cat_row = catalog_map.get(sku.upper())
            if cat_row is not None:
                row_margin = float(cat_row.get("margin_pct", 0.0) or 0.0)
                safe_cap = compute_max_safe_discount_pct(row_margin)
                if disc > safe_cap:
                    return json.dumps({
                        "status": "REJECTED_MARGIN_POLICY",
                        "error": (
                            f"discount_pct={disc}% would undercut {sku}'s real gross margin "
                            f"({row_margin}%); the maximum safe discount at a {MARGIN_SAFETY_BUFFER_PCT}pt "
                            f"margin buffer is {safe_cap}%."
                        ),
                    })
        seg_row = next(
            (r for r in _read_csv_rows("audience_segments") if r.get("segment_id", "").strip().upper() == seg_clean.upper()),
            {"segment_id": seg_clean, "segment_name": seg_clean, "region": "EU", "device_type": "all"},
        )

        cards_html: list[str] = []
        featured_details: list[dict[str, Any]] = []
        for sku in sku_list:
            row = catalog_map.get(sku.upper(), {})
            name = _sanitize_text(str(row.get("product_name", f"AtelierNova {sku}")))
            cat = _sanitize_text(str(row.get("category", "Design")))
            base_price = float(row.get("base_price_eur", 350.0) or 350.0)
            margin_pct = float(row.get("margin_pct", 52.0) or 52.0)
            promo_price = round(base_price * (1.0 - disc / 100.0), 2)
            net_margin_pct = round(margin_pct - disc, 1)
            desc = _sanitize_text(str(row.get("description", "Curated European design piece.")))
            featured_details.append({
                "sku_id": sku,
                "product_name": name,
                "category": cat,
                "base_price_eur": base_price,
                "promo_price_eur": promo_price,
                "net_margin_pct": net_margin_pct,
            })
            cards_html.append(
                f'<div class="sku-card">'
                f'<div class="sku-badge">{html.escape(sku)} • {html.escape(cat)}</div>'
                f'<h3>{html.escape(name)}</h3>'
                f'<p>{html.escape(desc)}</p>'
                f'<div class="price-row">'
                f'<span class="price-promo">€{promo_price:.2f}</span>'
                f'<span class="price-base">€{base_price:.2f}</span>'
                f'<span class="margin-pill">Net Margin {net_margin_pct:.1f}%</span>'
                f'</div></div>'
            )

        out_html = Path(f"/tmp/storefront_preview_{seg_clean}.html")
        ui_dir = _PACK_DIR / "ui"
        template_path = ui_dir / "template.html"
        region_str = str(seg_row.get("region", "EU"))
        segment_name_str = str(seg_row.get("segment_name", seg_clean))
        preferred_style_str = str(seg_row.get("preferred_style", theme_clean))
        device_type_str = str(seg_row.get("device_type", "Desktop_Web"))
        aov_eur_str = str(seg_row.get("avg_order_value_eur", "450.00"))
        primary_sku_str = sku_list[0] if sku_list else "SKU-0001"
        hero_image_html = ""
        existing_heroes = [
            ui_dir / f"hero_{seg_clean}{ext}"
            for ext in (".png", ".svg")
            if (ui_dir / f"hero_{seg_clean}{ext}").exists()
        ]
        if existing_heroes:
            newest_hero = max(existing_heroes, key=lambda p: p.stat().st_mtime)
            hero_image_html = (
                f'<img src="/ui/{html.escape(newest_hero.name)}" alt="{html.escape(headline_clean)}" />'
            )
        if template_path.exists():
            tpl = template_path.read_text(encoding="utf-8")
            doc = (
                tpl.replace("{{SEGMENT_ID}}", html.escape(seg_clean))
                .replace("{{SEGMENT_NAME}}", html.escape(segment_name_str))
                .replace("{{REGION}}", html.escape(region_str))
                .replace("{{PREFERRED_STYLE}}", html.escape(preferred_style_str))
                .replace("{{DEVICE_TYPE}}", html.escape(device_type_str))
                .replace("{{AOV_EUR}}", html.escape(aov_eur_str))
                .replace("{{PRIMARY_SKU}}", html.escape(primary_sku_str))
                .replace("{{THEME_STYLE}}", html.escape(theme_clean))
                .replace("{{HERO_HEADLINE}}", html.escape(headline_clean))
                .replace("{{HERO_IMAGE_HTML}}", hero_image_html)
                .replace("{{BANNER_COPY}}", html.escape(banner_clean))
                .replace("{{DISCOUNT_PCT}}", str(disc))
                .replace("{{CARDS_HTML}}", "".join(cards_html))
            )
        else:
            doc = (
                "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'/>"
                f"<title>AtelierNova Storefront Preview — {html.escape(seg_clean)}</title>"
                "<style>"
                "body{font-family:system-ui,-apple-system,sans-serif;margin:0;background:#0f172a;color:#f8fafc;padding:24px;}"
                ".promo{background:#38bdf8;color:#0f172a;padding:10px 18px;border-radius:8px;font-weight:700;margin-bottom:18px;}"
                ".hero{background:linear-gradient(135deg,#1e293b,#334155);padding:36px;border-radius:16px;margin-bottom:24px;border:1px solid #475569;}"
                ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px;}"
                ".sku-card{background:#1e293b;padding:20px;border-radius:12px;border:1px solid #334155;}"
                ".sku-badge{font-size:12px;color:#94a3b8;text-transform:uppercase;letter-spacing:1px;}"
                ".price-row{display:flex;align-items:center;gap:12px;margin-top:12px;}"
                ".price-promo{font-size:20px;font-weight:700;color:#38bdf8;}"
                ".price-base{text-decoration:line-through;color:#64748b;font-size:14px;}"
                ".margin-pill{margin-left:auto;background:#064e3b;color:#6ee7b7;padding:4px 8px;border-radius:6px;font-size:12px;}"
                "</style></head><body>"
                f"<div class='promo'>{html.escape(banner_clean)} ({disc}% OFF • Policy Guardrail Verified &le;30%)</div>"
                f"<div class='hero'><small>{html.escape(seg_clean)} • {html.escape(region_str)} • Theme: {html.escape(theme_clean)}</small>"
                f"<h1>{html.escape(headline_clean)}</h1></div>"
                f"<div class='grid'>{''.join(cards_html)}</div>"
                "</body></html>"
            )
        out_html.write_text(doc, encoding="utf-8")
        ui_repo_file = ui_dir / f"preview_{seg_clean}.html"
        ui_repo_path_str = str(out_html)
        try:
            ui_dir.mkdir(parents=True, exist_ok=True)
            ui_repo_file.write_text(doc, encoding="utf-8")
            ui_repo_path_str = str(ui_repo_file)
        except OSError:
            pass

        state = _load_state()
        previews = state.setdefault("storefront_previews", [])
        preview_id = f"PREVIEW-{4001 + len(previews)}"
        record = {
            "preview_id": preview_id,
            "ui_uri": f"ui://storefront-preview/{seg_clean}",
            "html_path": str(out_html),
            "ui_repo_path": ui_repo_path_str,
            "segment_id": seg_clean,
            "theme_style": theme_clean,
            "hero_headline": headline_clean,
            "discount_pct": disc,
            "banner_copy": banner_clean,
            "featured_skus": featured_details,
            "rendered_at": datetime.now(timezone.utc).isoformat(),
            "status": "READY",
        }
        previews.append(record)
        backend = _save_state(state)
        return json.dumps({"status": "SUCCESS", "preview": record, "state_backend": backend})
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@mcp.tool()
def sync_campaign_with_t01(
    segment_id: str,
    featured_skus: str,
    hero_headline: str,
    theme_style: str = "Nordic_Minimal",
    locale: str = "en-GB",
    event_id: str = "EVT-0001",
    channel: str = "Meta_Reels",
    target_cpm_bid_eur: float = 12.5,
) -> str:
    """Execute a Tribe A2A Handshake with Sister Table 1 (t01_campaign_orchestrator) to synchronize ad variants and CPM bids with a storefront layout.

    Args:
        segment_id: Target audience segment ID (e.g. 'SEG-001').
        featured_skus: Comma-separated list of featured SKU IDs (e.g. 'SKU-0001,SKU-0006').
        hero_headline: Storefront hero headline to align ad creative copy.
        theme_style: Visual style theme (e.g. 'Nordic_Minimal', 'Mediterranean_Warm').
        locale: Target locale code for Table 1 ad variant (e.g. 'en-GB', 'es-ES').
        event_id: Partner event identifier in Table 1's catalog (e.g. 'EVT-0001').
        channel: Ad network channel for Table 1 bid activation (e.g. 'Meta_Reels', 'TikTok_Pulse').
        target_cpm_bid_eur: Target CPM bid in EUR (must obey Table 1's 0.50 to 25.00 EUR cap).

    Returns:
        JSON string containing the A2A protocol envelope and Table 1's staged variant and active bid confirmations.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    rejection = quarantine_action_args(locals())
    if rejection is not None:
        return json.dumps(rejection)
    try:
        cpm = validate_policy_number(target_cpm_bid_eur, cap=25.0, positive=True)
        if cpm is None:
            return json.dumps({
                "status": "REJECTED_POLICY_CAP",
                "error": "target_cpm_bid_eur must be finite and greater than 0, at most 25.00 EUR; booleans are not allowed.",
            })

        seg_clean = (segment_id or "SEG-001").strip()
        skus_clean = [s.strip() for s in (featured_skus or "").split(",") if s.strip()]
        headline_clean = _sanitize_text(hero_headline or "AtelierNova Curated Living")
        theme_clean = (theme_style or "Nordic_Minimal").strip()
        loc_clean = (locale or "en-GB").strip()
        evt_clean = (event_id or "EVT-0001").strip()
        ch_clean = (channel or "Meta_Reels").strip()

        from seed_packs.t01_campaign_orchestrator.mcp_server import (
            create_localized_variant,
            place_ad_bid,
        )

        visual_prompt = (
            f"AtelierNova x PulseStage cross-promo ({theme_clean}) featuring {', '.join(skus_clean)} "
            f"for segment {seg_clean}"
        )
        var_resp = json.loads(
            create_localized_variant(
                event_id=evt_clean,
                locale=loc_clean,
                headline=headline_clean,
                visual_prompt=visual_prompt,
                cta_text=f"Shop {theme_clean} Edit",
            )
        )
        variant_obj = var_resp.get("variant", {})
        variant_id = str(variant_obj.get("variant_id", "VAR-LOC-2001"))

        bid_resp = json.loads(
            place_ad_bid(
                variant_id=variant_id,
                channel=ch_clean,
                new_cpm_bid_eur=cpm,
                daily_budget_eur=600.0,
            )
        )
        bid_obj = bid_resp.get("bid", {})

        state = _load_state()
        handshakes = state.setdefault("a2a_handshakes", [])
        handshake_id = f"A2A-T02-T01-{5001 + len(handshakes)}"
        record = {
            "handshake_id": handshake_id,
            "a2a_version": "1.0",
            "tribe": "Creative AI & AdTech",
            "sender_agent": "expedition_t02_dynamic_storefronts",
            "recipient_agent": "expedition_t01_campaign_orchestrator",
            "handshake_type": "STOREFRONT_TO_CAMPAIGN_SYNC",
            "payload": {
                "segment_id": seg_clean,
                "featured_skus": skus_clean,
                "hero_headline": headline_clean,
                "theme_style": theme_clean,
                "locale": loc_clean,
                "event_id": evt_clean,
                "channel": ch_clean,
                "target_cpm_bid_eur": round(cpm, 2),
            },
            "t01_response": {
                "variant": variant_obj,
                "bid": bid_obj,
            },
            "synced_at": datetime.now(timezone.utc).isoformat(),
            "status": "SYNCED",
        }
        handshakes.append(record)
        backend = _save_state(state)
        return json.dumps({"status": "SUCCESS", "a2a_handshake": record, "state_backend": backend})
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@mcp.tool()
def save_merchandising_memory(
    segment_id: str,
    memory_key: str,
    memory_note: str,
    author: str = "Marco Bellini",
) -> str:
    """Persist a cross-session merchandising memory note for an audience segment.

    Args:
        segment_id: Target audience segment ID (e.g. 'SEG-001').
        memory_key: Short identifier key for the memory (e.g. 'preferred_hero_sku', 'promo_policy').
        memory_note: Merchandising decision, rule, or preference to remember across sessions.
        author: Merchandising author recording the note (default 'Marco Bellini').

    Returns:
        JSON string confirming the sanitized memory record (`MEM-6001+`) and storage backend.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    try:
        seg_clean = _sanitize_text(segment_id or "").strip()
        key_clean = _sanitize_text(memory_key or "").strip()
        note_clean = _sanitize_text(memory_note or "").strip()
        author_clean = _sanitize_text(author or "Marco Bellini").strip() or "Marco Bellini"

        if not seg_clean or not key_clean or not note_clean:
            return json.dumps({
                "status": "REJECTED",
                "error": "segment_id, memory_key, and memory_note must all be non-empty.",
            })

        if any(contains_injection_marker(v) for v in (seg_clean, key_clean, note_clean, author_clean)):
            return json.dumps({
                "status": "REJECTED",
                "error": "Memory rejected: input contains an untrusted prompt-injection marker.",
            })

        state = _load_state()
        memories: list[dict[str, Any]] = state.setdefault("memories", [])
        now_iso = datetime.now(timezone.utc).isoformat()

        existing = next(
            (
                m
                for m in memories
                if str(m.get("segment_id", "")).upper() == seg_clean.upper()
                and str(m.get("memory_key", "")).lower() == key_clean.lower()
            ),
            None,
        )
        if existing is not None:
            existing["memory_note"] = note_clean
            existing["author"] = author_clean
            existing["revision"] = int(existing.get("revision", 1)) + 1
            existing["saved_at"] = now_iso
            existing["status"] = "STORED"
            record = existing
        else:
            record = {
                "memory_id": f"MEM-{6001 + len(memories)}",
                "segment_id": seg_clean,
                "memory_key": key_clean,
                "memory_note": note_clean,
                "author": author_clean,
                "revision": 1,
                "saved_at": now_iso,
                "status": "STORED",
            }
            memories.append(record)

        backend = _save_state(state)
        return json.dumps({
            "status": "STORED",
            "memory": record,
            "state_backend": backend,
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@mcp.tool()
def recall_merchandising_memory(
    segment_id: str = "all",
    query: str = "",
) -> str:
    """Recall persisted cross-session merchandising memory notes filtered by segment and keyword.

    Args:
        segment_id: Segment ID to filter by (e.g. 'SEG-001'), or 'all' for all segments.
        query: Optional case-insensitive keyword filter across memory keys and notes.

    Returns:
        JSON string containing matching merchandising memories sorted most-recent first.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    try:
        seg_clean = (segment_id or "all").strip()
        query_clean = (query or "").strip().lower()

        state = _load_state()
        memories: list[dict[str, Any]] = list(state.get("memories", []))

        filtered: list[dict[str, Any]] = []
        for item in memories:
            if seg_clean and seg_clean.lower() != "all":
                if str(item.get("segment_id", "")).upper() != seg_clean.upper():
                    continue
            if query_clean:
                haystack = " ".join([
                    str(item.get("memory_id", "")),
                    str(item.get("segment_id", "")),
                    str(item.get("memory_key", "")),
                    str(item.get("memory_note", "")),
                    str(item.get("author", "")),
                ]).lower()
                if query_clean not in haystack:
                    continue
            filtered.append(item)

        filtered.sort(key=lambda r: str(r.get("saved_at", "")), reverse=True)
        return json.dumps({
            "status": "SUCCESS",
            "segment_id": seg_clean or "all",
            "query": query_clean,
            "count": len(filtered),
            "memories": filtered,
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@mcp.tool()
def route_merchandising_task(
    task_type: str,
    prompt_text: str,
    segment_id: str = "SEG-001",
    style_theme: str = "Nordic_Minimal",
) -> str:
    """Dynamically route a merchandising task to Gemma or Gemini based on task complexity and latency tier.

    Args:
        task_type: Task category ('fast_copy', 'tag_classification', 'banner_tagline', 'multi_table_reasoning', 'campaign_strategy', 'a2a_orchestration', 'hero_image_generation', or 'visual_render').
        prompt_text: Merchandising prompt or instruction to execute on the selected model tier.
        segment_id: Target audience segment ID (default 'SEG-001').
        style_theme: Target visual style theme (default 'Nordic_Minimal').

    Returns:
        JSON string containing the model routing decision, latency/cost tier metadata, and generated output.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    try:
        from seed_packs.t02_dynamic_storefronts.model_router import (
            SUPPORTED_TASK_TYPES,
            execute_routed_task,
            select_model_for_task,
        )

        clean_prompt = _sanitize_text(prompt_text or "").strip()
        if not clean_prompt:
            return json.dumps({
                "status": "REJECTED",
                "error": "prompt_text must be non-empty.",
                "supported_task_types": SUPPORTED_TASK_TYPES,
            })

        if contains_injection_marker(clean_prompt):
            return json.dumps({
                "status": "REJECTED",
                "error": "Routing rejected: prompt_text contains an untrusted prompt-injection marker.",
                "supported_task_types": SUPPORTED_TASK_TYPES,
            })

        decision = select_model_for_task(task_type)
        if decision is None:
            return json.dumps({
                "status": "REJECTED",
                "error": f"Unsupported task_type '{task_type}'.",
                "supported_task_types": SUPPORTED_TASK_TYPES,
            })

        seg_clean = _sanitize_text(segment_id or "SEG-001").strip() or "SEG-001"
        theme_clean = _sanitize_text(style_theme or "Nordic_Minimal").strip() or "Nordic_Minimal"
        output_text, exec_mode, fallback_reason = execute_routed_task(
            decision=decision,
            prompt_text=clean_prompt,
            segment_id=seg_clean,
            style_theme=theme_clean,
        )

        state = _load_state()
        routings = state.setdefault("model_routings", [])
        routing_id = f"RTE-{7001 + len(routings)}"
        routing_record: dict[str, Any] = {
            "routing_id": routing_id,
            **decision,
            "segment_id": seg_clean,
            "style_theme": theme_clean,
            "execution_mode": exec_mode,
            "routed_at": datetime.now(timezone.utc).isoformat(),
        }
        if fallback_reason:
            routing_record["fallback_reason"] = fallback_reason
        routings.append(routing_record)
        backend = _save_state(state)

        return json.dumps({
            "status": "SUCCESS",
            "routing_decision": routing_record,
            "output_text": output_text,
            "state_backend": backend,
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@mcp.tool()
def register_gemini_enterprise_agent(
    app_id: str = "ateliernova-enterprise-search",
    agent_display_name: str = "AtelierNova Dynamic Storefront Agent",
    app_location: str = "eu",
    reasoning_engine_id: str = "",
) -> str:
    """Register the deployed Table 2 Vertex AI ReasoningEngine as an ADK Agent inside a Gemini Enterprise App (Discovery Engine v1alpha).

    Args:
        app_id: Target Gemini Enterprise / Agentspace engine identifier (e.g. 'ateliernova-enterprise-search').
        agent_display_name: Human-readable display name shown inside the Gemini Enterprise workspace.
        app_location: Discovery Engine multi-region location ('eu', 'us', or 'global'; default 'eu').
        reasoning_engine_id: Vertex AI ReasoningEngine ID or full resource name (defaults to `.deployed_agent.json` or live engine `3204215998593531904`).

    Returns:
        JSON string containing the Gemini Enterprise registration record (`GEM-ENT-8001+`), Discovery Engine endpoint URL, and `adkAgentDefinition` payload.
    """
    flagged_key = scan_args_for_injection(locals())
    if flagged_key is not None:
        return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
    try:
        from seed_packs.t02_dynamic_storefronts.gemini_enterprise import (
            execute_gemini_enterprise_registration,
        )

        for val in (app_id, agent_display_name, app_location, reasoning_engine_id):
            if contains_injection_marker(str(val or "")):
                return json.dumps({
                    "status": "REJECTED",
                    "error": "Gemini Enterprise registration rejected: input contains an untrusted prompt-injection marker.",
                })

        app_clean = _sanitize_text(app_id or "ateliernova-enterprise-search").strip()
        display_clean = _sanitize_text(
            agent_display_name or "AtelierNova Dynamic Storefront Agent"
        ).strip()
        loc_clean = _sanitize_text(app_location or "eu").strip().lower() or "eu"
        re_clean = _sanitize_text(reasoning_engine_id or "").strip()

        reg_data = execute_gemini_enterprise_registration(
            app_id=app_clean,
            agent_display_name=display_clean,
            app_location=loc_clean,
            reasoning_engine_id=re_clean,
        )

        state = _load_state()
        registrations = state.setdefault("gemini_enterprise_registrations", [])
        reg_id = f"GEM-ENT-{8001 + len(registrations)}"
        record: dict[str, Any] = {
            "registration_id": reg_id,
            **reg_data,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        registrations.append(record)
        backend = _save_state(state)

        return json.dumps({
            "status": "SUCCESS",
            "registration": record,
            "state_backend": backend,
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


ACTION_TOOLS = [
    publish_storefront_layout,
    queue_visual_asset_render,
    update_promo_banner,
    generate_hero_lifestyle_image,
    render_storefront_preview,
    sync_campaign_with_t01,
    save_merchandising_memory,
    recall_merchandising_memory,
    route_merchandising_task,
    register_gemini_enterprise_agent,
]
MCP_TOOLS = ACTION_TOOLS

if __name__ == "__main__":
    mcp.run(transport="stdio")
