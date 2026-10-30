"""Storefront layout, banner, queue, and preview actions for Table 2 FastMCP."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
from typing import Any

from seed_packs.t02_dynamic_storefronts.guardrails import (
    MARGIN_SAFETY_BUFFER_PCT,
    MAX_DISCOUNT_PCT,
    compute_max_safe_discount_pct,
    contains_injection_marker,
    quarantine_action_args,
    sanitize_description,
    scan_args_for_injection,
    validate_policy_number,
)
from seed_packs.t02_dynamic_storefronts.mcp.state_store import (
    CatalogCsvRepository,
    McpStateStore,
)


def _sanitize_identifier(val: str | None, default: str) -> str:
    """Strictly restrict file/URI/JS identifiers to [A-Za-z0-9_-] to prevent path traversal and injection."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", (val or "").strip())
    return cleaned or default


class StorefrontActionService:
    """Manages storefront layouts, promo banners, asset render queueing, and HTML preview generation."""

    def __init__(
        self,
        state_store: McpStateStore,
        catalog_repo: CatalogCsvRepository,
        pack_dir: Path | None = None,
    ) -> None:
        self.state_store = state_store
        self.catalog_repo = catalog_repo
        self.pack_dir = pack_dir or Path(__file__).resolve().parent.parent

    def resolve_featured_skus(self, segment_id: str, featured_skus_csv: str) -> list[str]:
        """Parse, clean, and resolve list of featured SKU identifiers."""
        if not featured_skus_csv:
            return []
        return [
            _sanitize_identifier(s, "SKU-0001")
            for s in featured_skus_csv.split(",")
            if s.strip()
        ]

    def publish_storefront_layout(
        self,
        segment_id: str,
        featured_skus: str,
        hero_headline: str,
        theme_style: str = "Nordic_Minimal",
    ) -> str:
        """Publish a personalized dynamic storefront layout for an audience segment."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        rejection = quarantine_action_args(args)
        if rejection is not None:
            return json.dumps(rejection)
        headline_clean = sanitize_description(hero_headline)
        if contains_injection_marker(headline_clean):
            return json.dumps({
                "status": "REJECTED",
                "error": "publish_storefront_layout rejected: hero_headline contains an untrusted prompt-injection marker.",
            })

        state = self.state_store.load_state()
        layouts = state.setdefault("published_layouts", [])
        layout_id = f"LAYOUT-{1001 + len(layouts)}"
        record = {
            "layout_id": layout_id,
            "segment_id": _sanitize_identifier(segment_id, "SEG-001"),
            "featured_skus": self.resolve_featured_skus(segment_id, featured_skus),
            "hero_headline": headline_clean,
            "theme_style": _sanitize_identifier(theme_style, "Nordic_Minimal"),
            "published_at": datetime.now(timezone.utc).isoformat(),
            "status": "LIVE",
        }
        layouts.append(record)
        backend = self.state_store.save_state(state)
        return json.dumps({"status": "SUCCESS", "layout": record, "state_backend": backend})

    def queue_visual_asset_render(
        self,
        sku_id: str,
        scene_prompt: str,
        aspect_ratio: str = "16:9",
    ) -> str:
        """Queue a generative visual asset render job for a catalog SKU."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        rejection = quarantine_action_args(args)
        if rejection is not None:
            return json.dumps(rejection)
        scene_clean = sanitize_description(scene_prompt)
        if contains_injection_marker(scene_clean):
            return json.dumps({
                "status": "REJECTED",
                "error": "queue_visual_asset_render rejected: scene_prompt contains an untrusted prompt-injection marker.",
            })

        state = self.state_store.load_state()
        queue = state.setdefault("render_queue", [])
        job_id = f"RENDER-{2001 + len(queue)}"
        record = {
            "render_job_id": job_id,
            "sku_id": _sanitize_identifier(sku_id, "SKU-0001"),
            "scene_prompt": scene_clean,
            "aspect_ratio": aspect_ratio.strip(),
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "status": "QUEUED",
        }
        queue.append(record)
        backend = self.state_store.save_state(state)
        return json.dumps({"status": "SUCCESS", "render_job": record, "state_backend": backend})

    def update_promo_banner(
        self,
        segment_id: str,
        discount_pct: int,
        banner_copy: str,
        sku_id: str = "",
    ) -> str:
        """Update promotional discount banner enforcing <= 30% cap and margin buffer floors."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        rejection = quarantine_action_args(args)
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
            catalog = self.catalog_repo.load_catalog_by_sku()
            sku_row = catalog.get(sku_clean.upper())
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

        banner_clean = sanitize_description(banner_copy)
        if contains_injection_marker(banner_clean):
            return json.dumps({
                "status": "REJECTED",
                "error": "update_promo_banner rejected: banner_copy contains an untrusted prompt-injection marker.",
            })

        state = self.state_store.load_state()
        banners = state.setdefault("promo_banners", [])
        banner_id = f"PROMO-{3001 + len(banners)}"
        record = {
            "banner_id": banner_id,
            "segment_id": _sanitize_identifier(segment_id, "SEG-001"),
            "sku_id": _sanitize_identifier(sku_clean, "") if sku_clean else "",
            "discount_pct": disc,
            "banner_copy": banner_clean,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "ACTIVE",
        }
        banners.append(record)
        backend = self.state_store.save_state(state)
        return json.dumps({"status": "SUCCESS", "promo_banner": record, "state_backend": backend})

    def render_storefront_preview(
        self,
        segment_id: str,
        featured_skus: str,
        hero_headline: str,
        theme_style: str = "Nordic_Minimal",
        discount_pct: int = 15,
        banner_copy: str = "AtelierNova Exclusive Edit",
    ) -> str:
        """Render an interactive MCP App HTML preview card for an audience segment."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        rejection = quarantine_action_args(args)
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

            seg_clean = _sanitize_identifier(segment_id, "SEG-001")
            headline_clean = sanitize_description(hero_headline or "AtelierNova Curated Living")
            theme_clean = _sanitize_identifier(theme_style, "Nordic_Minimal")
            banner_clean = sanitize_description(banner_copy or "AtelierNova Exclusive Edit")
            sku_list = self.resolve_featured_skus(seg_clean, featured_skus)

            catalog_map = self.catalog_repo.load_catalog_by_sku()
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

            seg_row = self.catalog_repo.load_segment_by_id(seg_clean)

            cards_html: list[str] = []
            featured_details: list[dict[str, Any]] = []
            for sku in sku_list:
                row = catalog_map.get(sku.upper(), {})
                name = sanitize_description(str(row.get("product_name", f"AtelierNova {sku}")))
                cat = sanitize_description(str(row.get("category", "Design")))
                base_price = float(row.get("base_price_eur", 350.0) or 350.0)
                margin_pct = float(row.get("margin_pct", 52.0) or 52.0)
                promo_price = round(base_price * (1.0 - disc / 100.0), 2)
                net_margin_pct = round(margin_pct - disc, 1)
                desc = sanitize_description(str(row.get("description", "Curated European design piece.")))
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
            ui_dir = self.pack_dir / "ui"
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

            state = self.state_store.load_state()
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
            backend = self.state_store.save_state(state)
            return json.dumps({"status": "SUCCESS", "preview": record, "state_backend": backend})
        except Exception as exc:
            return json.dumps({"status": "ERROR", "error": str(exc)})
