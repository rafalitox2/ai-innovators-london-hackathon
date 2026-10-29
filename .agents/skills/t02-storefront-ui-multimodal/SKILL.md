---
name: t02-storefront-ui-multimodal
description: This skill should be used when modifying multimodal hero lifestyle image generation (generate_hero_lifestyle_image with GEMINI_IMAGE_MODEL) or customizing the MCP App UI storefront preview template (render_storefront_preview, ui://storefront-preview/, template.html) for Table 2.
---

# Table 2 Multimodal Image & Storefront UI Preview Skill (`t02-storefront-ui-multimodal`)

Guides customization of Table 2's multimodal image pipeline (`generate_hero_lifestyle_image`) and interactive MCP App UI preview (`render_storefront_preview` and `seed_packs/t02_dynamic_storefronts/ui/template.html`).

## 1. Multimodal Hero Lifestyle Image (`generate_hero_lifestyle_image`)

Located in `seed_packs/t02_dynamic_storefronts/mcp_server.py`:
- **Environment Variable**: Always read the image model via `os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")` — never hardcode the model name.
- **Asset Output**: Writes self-contained SVG/image preview files to `/tmp/t02_assets/hero_<segment_id>_<sku_id>.svg` and records the render job in `.state.json["render_queue"]` with `status: "RENDERED_READY"`.
- **Style Palette Mapping**:
  - `Nordic_Minimal`: `#0f172a` / `#334155` / `#38bdf8`
  - `Warm_Mediterranean`: `#431407` / `#9a3412` / `#fb923c`
  - `Urban_Industrial`: `#18181b` / `#3f3f46` / `#a1a1aa`
  - `Bold_Editorial`: `#3b0764` / `#6b21a8` / `#f472b6`

## 2. Interactive Storefront UI Preview (`render_storefront_preview`)

Located in `seed_packs/t02_dynamic_storefronts/mcp_server.py` and `seed_packs/t02_dynamic_storefronts/ui/`:
- **MCP Resource URI**: Exposes `@mcp.resource("ui://storefront-preview/{segment_id}")` via `get_storefront_preview_resource(segment_id: str) -> str`.
- **Editable HTML Template**: `seed_packs/t02_dynamic_storefronts/ui/template.html` uses safe `{{PLACEHOLDER}}` tokens replaced by `render_storefront_preview`:
  - `{{SEGMENT_ID}}` — Target segment ID (e.g., `SEG-001`)
  - `{{THEME_STYLE}}` — Active visual theme (e.g., `Nordic_Minimal`)
  - `{{HERO_HEADLINE}}` — HTML-escaped hero headline
  - `{{BANNER_COPY}}` — HTML-escaped promotional banner copy
  - `{{DISCOUNT_PCT}}` — Validated discount percentage (`0..30`)
  - `{{PRIMARY_BG}}`, `{{SECONDARY_BG}}`, `{{ACCENT_COLOR}}` — Theme palette colors
  - `{{SKU_CARDS_HTML}}` — Rendered product cards enriched from `seed_packs/t02_dynamic_storefronts/data/products_catalog.csv` (`sku_id`, `title`, `category`, `price_eur`, `margin_pct`, `stock_available`).
- **Generated Preview Files**:
  - Repo UI preview: `seed_packs/t02_dynamic_storefronts/ui/preview_<segment_id>.html` (open directly in browser during live demo).
  - Runtime artifact copy: `/tmp/t02_assets/preview_<segment_id>.html`.

## Verification Checklist
- [ ] `GEMINI_IMAGE_MODEL` is read dynamically from `os.environ`.
- [ ] All placeholders in `seed_packs/t02_dynamic_storefronts/ui/template.html` match the replacements in `render_storefront_preview`.
- [ ] User/catalog strings interpolated into HTML use `html.escape(...)` to prevent XSS or broken markup.
- [ ] Tested with `pytest tests/test_t02_phase2.py tests/test_t02_phase3.py -q`.
