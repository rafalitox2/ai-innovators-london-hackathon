"""Multimodal hero lifestyle image generation service for Table 2 FastMCP."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import re
from typing import Any

from seed_packs.t02_dynamic_storefronts.guardrails import (
    contains_injection_marker,
    quarantine_action_args,
    sanitize_description,
    scan_args_for_injection,
)
from seed_packs.t02_dynamic_storefronts.mcp.state_store import (
    CatalogCsvRepository,
    McpStateStore,
)


def _sanitize_identifier(val: str | None, default: str) -> str:
    """Strictly restrict file/URI/JS identifiers to [A-Za-z0-9_-] to prevent path traversal and injection."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", (val or "").strip())
    return cleaned or default


class MultimodalHeroService:
    """Generates hero lifestyle visuals using GEMINI_IMAGE_MODEL or offline SVG fallbacks."""

    VALID_ASPECT_RATIOS = frozenset({"16:9", "1:1", "9:16", "4:3", "3:4"})

    def __init__(
        self,
        state_store: McpStateStore,
        pack_dir: Path | None = None,
        catalog_repo: CatalogCsvRepository | None = None,
    ) -> None:
        self.state_store = state_store
        self.pack_dir = pack_dir or Path(__file__).resolve().parent.parent
        self.catalog_repo = catalog_repo or CatalogCsvRepository(self.pack_dir / "data")

    def contains_injection(self, text: str | None) -> bool:
        """Return True if text contains any prompt-injection marker."""
        return contains_injection_marker(text)

    def _upload_bytes_to_gcs(self, data: bytes, destination_blob: str, content_type: str = "image/png") -> str:
        """Upload raw image bytes to GCS staging bucket if configured."""
        project, bucket_name = self.state_store.resolve_gcs_target()
        if not bucket_name:
            return ""
        try:
            from google.cloud import storage

            client = storage.Client(project=project or None)
            blob = client.bucket(bucket_name).blob(destination_blob)
            blob.upload_from_string(data, content_type=content_type)
            return f"gs://{bucket_name}/{destination_blob}"
        except Exception:
            return ""

    def generate_hero_lifestyle_image(
        self,
        sku_id: str,
        segment_id: str = "SEG-001",
        style_theme: str = "Nordic_Minimal",
        scene_description: str = "Sunlit modern European living space",
        aspect_ratio: str = "16:9",
    ) -> str:
        """Generate a tailored hero lifestyle visual asset using GEMINI_IMAGE_MODEL."""
        args = {k: v for k, v in locals().items() if k != "self"}
        flagged_key = scan_args_for_injection(args)
        if flagged_key is not None:
            return json.dumps({"status": "REJECTED", "error": f"Untrusted instruction marker in {flagged_key}."})
        rejection = quarantine_action_args(args)
        if rejection is not None:
            return json.dumps(rejection)
        try:
            sku_clean = _sanitize_identifier(sku_id, "SKU-0001")
            seg_clean = _sanitize_identifier(segment_id, "SEG-001")
            theme_clean = _sanitize_identifier(style_theme, "Nordic_Minimal")
            scene_clean = sanitize_description(scene_description or "Sunlit modern European living space")
            if self.contains_injection(scene_clean):
                return json.dumps({
                    "status": "REJECTED",
                    "error": "generate_hero_lifestyle_image rejected: scene_description contains an untrusted prompt-injection marker.",
                })
            raw_ratio = (aspect_ratio or "16:9").strip()
            if self.contains_injection(raw_ratio):
                return json.dumps({
                    "status": "REJECTED",
                    "error": "generate_hero_lifestyle_image rejected: aspect_ratio contains an untrusted prompt-injection marker.",
                })
            ratio_clean = raw_ratio if raw_ratio in self.VALID_ASPECT_RATIOS else "16:9"

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

            catalog_map = self.catalog_repo.load_catalog_by_sku()
            sku_row = catalog_map.get(
                sku_clean.upper(),
                {
                    "sku_id": sku_clean,
                    "product_name": f"AtelierNova {sku_clean}",
                    "category": "Design_Collection",
                    "base_price_eur": "490.00",
                },
            )
            product_name = sanitize_description(str(sku_row.get("product_name", sku_clean)))
            category = sanitize_description(str(sku_row.get("category", "Design_Collection")))

            seg_row = self.catalog_repo.load_segment_by_id(seg_clean)
            audience_segment_name = sanitize_description(str(seg_row.get("segment_name", seg_clean)))
            audience_region = sanitize_description(str(seg_row.get("region", "UK_London")))
            audience_preferred_style = sanitize_description(str(seg_row.get("preferred_style", theme_clean)))
            audience_device = sanitize_description(str(seg_row.get("device_type", "Desktop_Web")))
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

            ui_dir = self.pack_dir / "ui"
            ui_asset_path_str = str(asset_path)
            ui_sync_warning: str | None = None
            try:
                ui_dir.mkdir(parents=True, exist_ok=True)
                ui_sku_file = ui_dir / f"hero_{sku_clean}_{seg_clean}{asset_path.suffix}"
                ui_sku_file.write_bytes(asset_path.read_bytes())
                ui_asset_file = ui_dir / f"hero_{seg_clean}{asset_path.suffix}"
                ui_asset_file.write_bytes(asset_path.read_bytes())
                ui_asset_path_str = str(ui_asset_file)
            except OSError as exc:
                ui_sync_warning = f"Failed to sync hero image to ui/: {exc}"

            state = self.state_store.load_state()
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
            backend = self.state_store.save_state(state)
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
