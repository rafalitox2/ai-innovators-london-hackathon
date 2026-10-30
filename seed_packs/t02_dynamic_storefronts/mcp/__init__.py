"""Table 2 (t02_dynamic_storefronts) OOP MCP Architecture Package."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from seed_packs.t02_dynamic_storefronts.mcp.a2a_service import TribeA2ASyncService
from seed_packs.t02_dynamic_storefronts.mcp.enterprise_service import (
    EnterpriseOrchestrationService,
)
from seed_packs.t02_dynamic_storefronts.mcp.memory_service import (
    MerchandisingMemoryService,
)
from seed_packs.t02_dynamic_storefronts.mcp.multimodal_service import (
    MultimodalHeroService,
)
from seed_packs.t02_dynamic_storefronts.mcp.state_store import (
    CatalogCsvRepository,
    McpStateStore,
)
from seed_packs.t02_dynamic_storefronts.mcp.storefront_service import (
    StorefrontActionService,
)

_PACK_DIR = Path(__file__).resolve().parent.parent


class T02McpController:
    """Unified OOP facade controller coordinating all Table 2 FastMCP services."""

    def __init__(
        self,
        default_state_path: Path | None = None,
        fallback_state_path: Path | None = None,
        pack_dir: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self.pack_dir = pack_dir or _PACK_DIR
        self.data_dir = data_dir or (self.pack_dir / "data")
        self.catalog_repo = CatalogCsvRepository(data_dir=self.data_dir)
        self.state_store = McpStateStore(
            default_state_path=default_state_path or (self.pack_dir / ".state.json"),
            fallback_state_path=fallback_state_path or Path("/tmp/t02_dynamic_storefronts_state.json"),
        )
        self.storefront = StorefrontActionService(
            state_store=self.state_store,
            catalog_repo=self.catalog_repo,
            pack_dir=self.pack_dir,
        )
        self.multimodal = MultimodalHeroService(
            state_store=self.state_store,
            pack_dir=self.pack_dir,
            catalog_repo=self.catalog_repo,
        )
        self.a2a = TribeA2ASyncService(state_store=self.state_store)
        self.memory = MerchandisingMemoryService(state_store=self.state_store)
        self.enterprise = EnterpriseOrchestrationService(state_store=self.state_store)

    # 1. Storefront Layout
    def publish_storefront_layout(
        self,
        segment_id: str,
        featured_skus: str,
        hero_headline: str,
        theme_style: str = "Nordic_Minimal",
    ) -> str:
        return self.storefront.publish_storefront_layout(
            segment_id=segment_id,
            featured_skus=featured_skus,
            hero_headline=hero_headline,
            theme_style=theme_style,
        )

    # 2. Render Queue
    def queue_visual_asset_render(
        self,
        sku_id: str,
        scene_prompt: str,
        aspect_ratio: str = "16:9",
    ) -> str:
        return self.storefront.queue_visual_asset_render(
            sku_id=sku_id,
            scene_prompt=scene_prompt,
            aspect_ratio=aspect_ratio,
        )

    # 3. Promo Banner
    def update_promo_banner(
        self,
        segment_id: str,
        discount_pct: int,
        banner_copy: str,
        sku_id: str = "",
    ) -> str:
        return self.storefront.update_promo_banner(
            segment_id=segment_id,
            discount_pct=discount_pct,
            banner_copy=banner_copy,
            sku_id=sku_id,
        )

    # 4. Multimodal Hero Lifestyle Image
    def generate_hero_lifestyle_image(
        self,
        sku_id: str,
        segment_id: str = "SEG-001",
        style_theme: str = "Nordic_Minimal",
        scene_description: str = "Sunlit modern European living space",
        aspect_ratio: str = "16:9",
    ) -> str:
        return self.multimodal.generate_hero_lifestyle_image(
            sku_id=sku_id,
            segment_id=segment_id,
            style_theme=style_theme,
            scene_description=scene_description,
            aspect_ratio=aspect_ratio,
        )

    # 5. Interactive Storefront Preview
    def render_storefront_preview(
        self,
        segment_id: str,
        featured_skus: str,
        hero_headline: str,
        theme_style: str = "Nordic_Minimal",
        discount_pct: int = 15,
        banner_copy: str = "AtelierNova Exclusive Edit",
    ) -> str:
        return self.storefront.render_storefront_preview(
            segment_id=segment_id,
            featured_skus=featured_skus,
            hero_headline=hero_headline,
            theme_style=theme_style,
            discount_pct=discount_pct,
            banner_copy=banner_copy,
        )

    # 6. Tribe A2A Handshake
    def sync_campaign_with_t01(
        self,
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
        return self.a2a.sync_campaign_with_t01(
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

    # 7. Cross-Session Memory Save
    def save_merchandising_memory(
        self,
        segment_id: str,
        memory_key: str,
        memory_note: str,
        author: str = "Marco Bellini",
        author_agent: str = "expedition_t02",
    ) -> str:
        return self.memory.save_merchandising_memory(
            segment_id=segment_id,
            memory_key=memory_key,
            memory_note=memory_note,
            author=author,
            author_agent=author_agent,
        )

    # 8. Cross-Session Memory Recall
    def recall_merchandising_memory(
        self,
        segment_id: str = "ALL",
        query: str = "",
    ) -> str:
        return self.memory.recall_merchandising_memory(
            segment_id=segment_id,
            query=query,
        )

    # 9. Dynamic Model Router
    def route_merchandising_task(
        self,
        task_type: str,
        prompt_text: str = "",
        segment_id: str = "SEG-001",
        style_theme: str = "Nordic_Minimal",
        prompt_preview: str = "",
        latency_budget_ms: int = 1500,
        require_visual_output: bool = False,
    ) -> str:
        return self.enterprise.route_merchandising_task(
            task_type=task_type,
            prompt_text=prompt_text,
            segment_id=segment_id,
            style_theme=style_theme,
            prompt_preview=prompt_preview,
            latency_budget_ms=latency_budget_ms,
            require_visual_output=require_visual_output,
        )

    # 10. Gemini Enterprise Registration
    def register_gemini_enterprise_agent(
        self,
        app_id: str = "ateliernova-enterprise-search",
        agent_display_name: str = "AtelierNova Dynamic Storefront Agent",
        app_location: str = "eu",
        reasoning_engine_id: str = "",
    ) -> str:
        return self.enterprise.register_gemini_enterprise_agent(
            app_id=app_id,
            agent_display_name=agent_display_name,
            app_location=app_location,
            reasoning_engine_id=reasoning_engine_id,
        )


__all__ = [
    "CatalogCsvRepository",
    "McpStateStore",
    "StorefrontActionService",
    "MultimodalHeroService",
    "TribeA2ASyncService",
    "MerchandisingMemoryService",
    "EnterpriseOrchestrationService",
    "T02McpController",
]
