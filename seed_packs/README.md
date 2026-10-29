# AI Innovators Expedition — Creative AI & AdTech Seed Packs (`t02` & Sister `t01`)

Welcome to the **Seed Packs** catalog for **Table 2 — Dynamic Storefront Engine** (`t02_dynamic_storefronts`) and its **Creative AI & AdTech** Tribe Sister Table (`t01_campaign_orchestrator`).

Each active Seed Pack pairs a real-world enterprise scenario with:

1. **`pack.yaml`** — Declarative metadata, ADK system `instruction`, BigQuery dataset (`seed_t02` / `seed_t01`), GCS prefix (`seed/t02/` / `seed/t01/`), and MCP server module path.
2. **`data/*.csv` + `generate.py`** — 3 realistic, deterministic synthetic CSV datasets (80–120 rows per table) with realistic edge cases and an embedded adversarial / policy-trap row (`SKU-0017`) for the **Security & Guardrails Test Vector (+1 Bonus)**.
3. **`load.py`** — Idempotent loader (`make seed PACK=t02`) that creates the BigQuery dataset in **your** `GOOGLE_CLOUD_PROJECT` (`BQ_LOCATION`, default `EU`, `WRITE_TRUNCATE`) from the bundled `data/*.csv` files.
4. **`tools.py`** — ADK-ready BigQuery Function Tools (`TOOLS`) with full type annotations, docstrings, and parameterized SQL (`@params`) against `GOOGLE_CLOUD_PROJECT`, with automatic local CSV fallback when offline (`SEED_OFFLINE_MODE=1`).
5. **`mcp_server.py`** — FastMCP (`from mcp.server.fastmcp import FastMCP`) stdio server with Mock Action APIs (`MCP_TOOLS`, re-exported as `ACTION_TOOLS`), policy guardrails, multimodal image generation (`GEMINI_IMAGE_MODEL`), MCP App UI preview (`ui://storefront-preview/<segment_id>`), and Tribe A2A campaign handshake (`sync_campaign_with_t01`).
6. **`eval/golden.test.json`** — Golden evaluation test cases in the official ADK `EvalSet` schema (`make eval PACK=t02`).
7. **`CHALLENGE_CARD.md`** — Printable one-page table brief with persona, minimum playable scope, Must-Haves, Bonus capabilities, and Security & Guardrails test vectors.

---

## Index of Active Seed Packs

| Table | Seed Pack Directory | Challenge Title | Tribe | BigQuery Dataset & Tables (`EU`) | BigQuery `TOOLS` (Read) | FastMCP `MCP_TOOLS` (Write/Action) | Sister Table (A2A) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | [`t01_campaign_orchestrator`](./t01_campaign_orchestrator/CHALLENGE_CARD.md) | **Autonomous Creative Campaign Orchestrator** | Creative AI & AdTech | `seed_t01` (`events_catalog`, `ad_variants`, `campaign_telemetry`) | `query_underperforming_campaigns`, `get_event_ad_variants`, `get_channel_roi_summary` | `place_ad_bid`, `create_localized_variant`, `pause_ad_variant` | `t02_dynamic_storefronts` |
| **2** | [`t02_dynamic_storefronts`](./t02_dynamic_storefronts/CHALLENGE_CARD.md) | **Visual Content Creator & Dynamic Storefronts** | Creative AI & AdTech | `seed_t02` (`products_catalog`, `audience_segments`, `storefront_experiments`) | `find_catalog_products`, `get_storefront_performance`, `get_audience_segments`, `recommend_storefront_optimization` | `publish_storefront_layout`, `queue_visual_asset_render`, `update_promo_banner`, `generate_hero_lifestyle_image`, `render_storefront_preview`, `sync_campaign_with_t01` | `t01_campaign_orchestrator` |

*(Plus [`t00_example`](./t00_example/) as the baseline reference implementation used by offline starter unit tests.)*

---

## Quickstart: Running Table 2 (`t02_dynamic_storefronts`)

### 1. Select Table 2 via `SEED_PACK`

```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GOOGLE_CLOUD_LOCATION="global"
export GEMINI_MODEL="gemini-3.8-flash"
export GEMINI_IMAGE_MODEL="gemini-3.1-flash-image"
export SEED_PACK="t02"
```

### 2. Seed Your GCP Project

```bash
make seed PACK=t02            # reads GOOGLE_CLOUD_PROJECT from .env
# Or directly, from the repo root:
GOOGLE_CLOUD_PROJECT=<your-project-id> .venv/bin/python -m seed_packs.t02_dynamic_storefronts.load
```

### 3. Run Locally, Evaluate, and Validate Packs

```bash
# Validate active seed packs (YAML, CSV row counts, TOOLS signatures, MCP_TOOLS, EvalSet JSON, Challenge Cards)
.venv/bin/python -m seed_packs.check_packs

# Run the ADK evaluation suite against Table 2's 9 golden cases
make eval PACK=t02
```
