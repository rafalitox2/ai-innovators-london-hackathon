# Phase 3 Technical Specification — Table T02 (`t02_dynamic_storefronts`)

**Issues**: `#6` (Phase 3 — Tribe A2A Handshake with Sister Table T01 `t01_campaign_orchestrator` + Editable Storefront UI Template + Judge Pitch Storyboard)

## 1. Tribe A2A Handshake (`sync_campaign_with_t01` — Bonus `+1 pt`)
- **Sister Table**: Table 1 (`t01_campaign_orchestrator` — *Autonomous Creative Campaign Orchestrator*, Tribe: *Creative AI & AdTech*).
- **Workflow**:
  1. When Table 2 publishes or optimizes a high-converting storefront layout for an audience segment (e.g., `SEG-002` in `ES_Madrid` or `SEG-001` in `UK_London`), it invokes `sync_campaign_with_t01`.
  2. `sync_campaign_with_t01` constructs a formal **A2A Protocol Envelope**:
     - `a2a_version`: `"1.0"`
     - `sender_agent`: `"expedition_t02_dynamic_storefronts"`
     - `recipient_agent`: `"expedition_t01_campaign_orchestrator"`
     - `tribe`: `"Creative AI & AdTech"`
     - `handshake_type`: `"STOREFRONT_TO_CAMPAIGN_SYNC"`
  3. Enforces Table 1's governance guardrail (`0.50 <= target_cpm_bid_eur <= 25.00 EUR`); if violated, returns `REJECTED_POLICY_CAP`.
  4. Calls Table 1's MCP action tools (`create_localized_variant` and `place_ad_bid` in `seed_packs.t01_campaign_orchestrator.mcp_server`, or posts to `T01_A2A_ENDPOINT` when set) so Table 1 stages the matching localized ad creative (`VAR-LOC-...`) and updates the programmatic CPM bid (`BID-...`).

## 2. Editable Storefront UI Directory (`seed_packs/t02_dynamic_storefronts/ui/`)
- Provides an editable HTML5/CSS template at `seed_packs/t02_dynamic_storefronts/ui/template.html` and writes rendered previews both to `seed_packs/t02_dynamic_storefronts/ui/preview_<segment_id>.html` (for local developer live-preview) and `/tmp/storefront_preview_<segment_id>.html` (for read-only cloud containers).
