"""FastMCP stdio server with Mock Action APIs for Table 2 (t02_dynamic_storefronts)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from seed_packs.t02_dynamic_storefronts.guardrails import (
    sanitize_description,
)
from seed_packs.t02_dynamic_storefronts.mcp import (
    CatalogCsvRepository,
    EnterpriseOrchestrationService,
    McpStateStore,
    MerchandisingMemoryService,
    MultimodalHeroService,
    StorefrontActionService,
    T02McpController,
    TribeA2ASyncService,
)

mcp = FastMCP("t02_dynamic_storefronts_actions")

_PACK_DIR = Path(__file__).resolve().parent
_DATA_DIR = _PACK_DIR / "data"
_DEFAULT_STATE_PATH = _PACK_DIR / ".state.json"
_FALLBACK_STATE_PATH = Path("/tmp/t02_dynamic_storefronts_state.json")
_GCS_STATE_BLOB_PATH = "t02_dynamic_storefronts/state.json"
_sanitize_text = sanitize_description


def _get_controller() -> T02McpController:
    """Instantiate the facade controller dynamically using current module state paths."""
    return T02McpController(
        default_state_path=_DEFAULT_STATE_PATH,
        fallback_state_path=_FALLBACK_STATE_PATH,
        pack_dir=_PACK_DIR,
        data_dir=_DATA_DIR,
    )


def _read_csv_rows(name: str) -> list[dict[str, Any]]:
    return _get_controller().catalog_repo.read_csv_rows(name)


def _resolve_gcs_bucket_name() -> tuple[str, str]:
    return _get_controller().state_store.resolve_gcs_target()


def _load_state() -> dict[str, Any]:
    return _get_controller().state_store.load_state()


def _save_state(state: dict[str, Any]) -> str:
    return _get_controller().state_store.save_state(state)


def _load_catalog_by_sku() -> dict[str, dict[str, Any]]:
    return _get_controller().catalog_repo.load_catalog_by_sku()


def _load_segment_by_id(segment_id: str) -> dict[str, Any]:
    return _get_controller().catalog_repo.load_segment_by_id(segment_id)


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
    return _get_controller().publish_storefront_layout(
        segment_id=segment_id,
        featured_skus=featured_skus,
        hero_headline=hero_headline,
        theme_style=theme_style,
    )


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
    return _get_controller().queue_visual_asset_render(
        sku_id=sku_id,
        scene_prompt=scene_prompt,
        aspect_ratio=aspect_ratio,
    )


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
    return _get_controller().update_promo_banner(
        segment_id=segment_id,
        discount_pct=discount_pct,
        banner_copy=banner_copy,
        sku_id=sku_id,
    )


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
    return _get_controller().generate_hero_lifestyle_image(
        sku_id=sku_id,
        segment_id=segment_id,
        style_theme=style_theme,
        scene_description=scene_description,
        aspect_ratio=aspect_ratio,
    )


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
    return _get_controller().render_storefront_preview(
        segment_id=segment_id,
        featured_skus=featured_skus,
        hero_headline=hero_headline,
        theme_style=theme_style,
        discount_pct=discount_pct,
        banner_copy=banner_copy,
    )


@mcp.tool()
def sync_campaign_with_t01(
    segment_id: str,
    featured_skus: str = "",
    hero_headline: str = "",
    theme_style: str = "Nordic_Minimal",
    locale: str = "en-GB",
    event_id: str = "EVT-0001",
    channel: str = "Meta_Reels",
    target_cpm_bid_eur: float = 12.5,
    layout_variant: str = "",
    featured_sku: str = "",
    campaign_channel: str = "",
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
        layout_variant: Optional layout variant name for creative alignment.
        featured_sku: Optional single featured SKU ID (alias for featured_skus).
        campaign_channel: Optional campaign channel override.

    Returns:
        JSON string containing the A2A protocol envelope and Table 1's staged variant and active bid confirmations.
    """
    return _get_controller().sync_campaign_with_t01(
        segment_id=segment_id,
        featured_skus=featured_skus,
        hero_headline=hero_headline,
        theme_style=theme_style,
        locale=locale,
        event_id=event_id,
        channel=channel,
        target_cpm_bid_eur=target_cpm_bid_eur,
        layout_variant=layout_variant,
        featured_sku=featured_sku,
        campaign_channel=campaign_channel,
    )


@mcp.tool()
def save_merchandising_memory(
    segment_id: str,
    memory_key: str,
    memory_note: str,
    author: str = "Marco Bellini",
    author_agent: str = "expedition_t02",
) -> str:
    """Persist a cross-session merchandising memory note for an audience segment.

    Args:
        segment_id: Target audience segment ID (e.g. 'SEG-001').
        memory_key: Short identifier key for the memory (e.g. 'preferred_hero_sku', 'promo_policy').
        memory_note: Merchandising decision, rule, or preference to remember across sessions.
        author: Merchandising author recording the note (default 'Marco Bellini').
        author_agent: Originating agent identifier (default 'expedition_t02').

    Returns:
        JSON string confirming the sanitized memory record (`MEM-6001+`) and storage backend.
    """
    return _get_controller().save_merchandising_memory(
        segment_id=segment_id,
        memory_key=memory_key,
        memory_note=memory_note,
        author=author,
        author_agent=author_agent,
    )


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
    return _get_controller().recall_merchandising_memory(
        segment_id=segment_id,
        query=query,
    )


@mcp.tool()
def route_merchandising_task(
    task_type: str,
    prompt_text: str = "",
    segment_id: str = "SEG-001",
    style_theme: str = "Nordic_Minimal",
    prompt_preview: str = "",
    latency_budget_ms: int = 1500,
    require_visual_output: bool = False,
) -> str:
    """Dynamically route a merchandising task to Gemma or Gemini based on task complexity and latency tier.

    Args:
        task_type: Task category ('fast_copy', 'tag_classification', 'banner_tagline', 'multi_table_reasoning', 'campaign_strategy', 'a2a_orchestration', 'hero_image_generation', or 'visual_render').
        prompt_text: Merchandising prompt or instruction to execute on the selected model tier.
        segment_id: Target audience segment ID (default 'SEG-001').
        style_theme: Target visual style theme (default 'Nordic_Minimal').
        prompt_preview: Preview snippet or instruction prompt.
        latency_budget_ms: Target latency budget in milliseconds.
        require_visual_output: Whether the task demands visual render output.

    Returns:
        JSON string containing the model routing decision, latency/cost tier metadata, and generated output.
    """
    return _get_controller().route_merchandising_task(
        task_type=task_type,
        prompt_text=prompt_text,
        segment_id=segment_id,
        style_theme=style_theme,
        prompt_preview=prompt_preview,
        latency_budget_ms=latency_budget_ms,
        require_visual_output=require_visual_output,
    )


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
    return _get_controller().register_gemini_enterprise_agent(
        app_id=app_id,
        agent_display_name=agent_display_name,
        app_location=app_location,
        reasoning_engine_id=reasoning_engine_id,
    )


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
