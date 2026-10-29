---
name: t02-mcp-actions-a2a
description: This skill should be used when creating, updating, or auditing FastMCP write/action tools, policy guardrails, MCP_TOOLS runtime parity, or the Tribe A2A campaign handshake (sync_campaign_with_t01) in seed_packs/t02_dynamic_storefronts/mcp_server.py.
---

# Table 2 FastMCP Actions, Guardrails & Tribe A2A Skill (`t02-mcp-actions-a2a`)

Guides implementation of operational write tools, deterministic policy guardrails, dual-mode MCP execution (`USE_MCP_STDIO=1` vs Vertex AI Agent Runtime in-process `MCP_TOOLS`), and cross-table A2A orchestration with **Table 1 (`t01_campaign_orchestrator`)**.

## Registered FastMCP Tools (`seed_packs/t02_dynamic_storefronts/mcp_server.py`)

| Tool | Purpose | Key Guardrails |
|---|---|---|
| `publish_storefront_layout` | Publishes a personalized layout (`Editorial_Grid`, `Single_Hero_Spotlight`, `Curated_Bundle_Carousel`) for a `segment_id` | Requires non-empty `featured_skus` and `hero_headline` |
| `queue_visual_asset_render` | Queues a lifestyle visual render job (`Nordic_Minimal`, `Warm_Mediterranean`, `Urban_Industrial`, `Bold_Editorial`) | Validates `aspect_ratio` (`16:9`, `4:5`, `1:1`) |
| `update_promo_banner` | Updates promotional banner copy and discount percentage for a segment | Enforces `0 <= discount_pct <= 30` (`REJECTED_POLICY_CAP`) |
| `generate_hero_lifestyle_image` | Generates an SVG/image hero lifestyle asset via `GEMINI_IMAGE_MODEL` | Reads model from env (`gemini-3.1-flash-image`), writes asset to `/tmp/t02_assets/` |
| `render_storefront_preview` | Renders interactive HTML preview card (`ui://storefront-preview/<segment_id>`) | Enforces `0 <= discount_pct <= 30` (`REJECTED_POLICY_CAP`) |
| `sync_campaign_with_t01` | Executes `STOREFRONT_TO_CAMPAIGN_SYNC` A2A handshake with Table 1 (`expedition_t01_campaign_orchestrator`) | Enforces `0 < target_cpm_bid_eur <= 25.0` (`REJECTED_POLICY_CAP`) |

## Dual-Mode Execution & `MCP_TOOLS` Parity

`app/loader.py` loads MCP tools in two ways:
1. **Local / CI Stdio Mode (`USE_MCP_STDIO=1`)**: Spawns `python -m seed_packs.t02_dynamic_storefronts.mcp_server` via `McpToolset` + `StdioConnectionParams`.
2. **Vertex AI Agent Runtime (`USE_MCP_STDIO=0`)**: Imports `MCP_TOOLS` directly from `seed_packs/t02_dynamic_storefronts/mcp_server.py` and deduplicates against `TOOLS`.

Whenever you add a new `@mcp.tool()` function in `mcp_server.py`, you **must** append it to `MCP_TOOLS`:

```python
MCP_TOOLS = [
    publish_storefront_layout,
    queue_visual_asset_render,
    update_promo_banner,
    generate_hero_lifestyle_image,
    render_storefront_preview,
    sync_campaign_with_t01,
]
```

## Tribe A2A Handshake Contract (`STOREFRONT_TO_CAMPAIGN_SYNC`)

`sync_campaign_with_t01` bridges **Table 2 (`expedition_t02_dynamic_storefronts`)** with **Table 1 (`expedition_t01_campaign_orchestrator`, Marketing & Customer Acquisition Tribe)**:
- Imports or invokes Table 1's `stage_creative_variant(segment_id, locale, headline, visual_theme, cta_text)` and `place_channel_bid(event_id, channel, segment_id, max_cpm_eur)` in `seed_packs/t01_campaign_orchestrator/mcp_server.py` (with graceful local state fallback if unavailable).
- Records the A2A envelope in `.state.json` under `a2a_handshakes` with `protocol: "A2A_TRIBE_HANDSHAKE_V1"` and `workflow: "STOREFRONT_TO_CAMPAIGN_SYNC"`.

## Verification Checklist
- [ ] Every `@mcp.tool()` is exported in `MCP_TOOLS`.
- [ ] Discounts `> 30%` and CPM bids `> 25.0 EUR` return `"status": "REJECTED_POLICY_CAP"`.
- [ ] Tested with `pytest tests/test_t02_phase2.py tests/test_t02_phase3.py -q`.
