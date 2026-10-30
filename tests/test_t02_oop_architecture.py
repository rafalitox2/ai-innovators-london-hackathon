"""Unit tests for the Object-Oriented Architecture in `app/` and `mcp/`."""

from __future__ import annotations

import json
from pathlib import Path

from app import (
    AdkAgentBuilder,
    EnvironmentConfigResolver,
    GcpPreflightValidator,
    InstructionSanitizer,
    McpBridgeFactory,
    NocturneDashboardService,
    NocturneUiController,
    SeedPackLoader,
)
from mcp import (
    CatalogCsvRepository,
    EnterpriseOrchestrationService,
    McpCloudRunGateway,
    McpStateStore,
    MerchandisingMemoryService,
    MultimodalHeroService,
    StdioServerParameters,
    StorefrontActionService,
    T02McpController,
    TribeA2ASyncService,
)
from mcp.server.fastmcp import FastMCP


def test_mcp_package_coexists_with_official_mcp_sdk() -> None:
    """Verify top-level `mcp/` package bridges the official MCP SDK and OOP classes."""
    assert StdioServerParameters is not None
    assert FastMCP is not None
    assert T02McpController is not None
    assert McpStateStore is not None
    assert McpCloudRunGateway is not None


def test_t02_mcp_controller_and_domain_services(tmp_path: Path) -> None:
    """Verify `T02McpController` wires all 7 OOP MCP domain services cleanly."""
    state_file = tmp_path / "test_state.json"
    controller = T02McpController(
        default_state_path=state_file,
        fallback_state_path=state_file,
    )

    assert isinstance(controller.state_store, McpStateStore)
    assert isinstance(controller.catalog_repo, CatalogCsvRepository)
    assert isinstance(controller.storefront, StorefrontActionService)
    assert isinstance(controller.multimodal, MultimodalHeroService)
    assert isinstance(controller.a2a, TribeA2ASyncService)
    assert isinstance(controller.memory, MerchandisingMemoryService)
    assert isinstance(controller.enterprise, EnterpriseOrchestrationService)

    # 1. Publish layout via controller
    pub_res = json.loads(
        controller.publish_storefront_layout(
            segment_id="SEG-001",
            featured_skus="SKU-0001,SKU-0006",
            hero_headline="Nordic Autumn Edit",
            theme_style="Nordic_Minimal",
        )
    )
    assert pub_res["status"] == "SUCCESS"
    assert pub_res["layout"]["status"] == "LIVE"

    # 2. Policy guardrail via StorefrontActionService
    promo_reject = json.loads(
        controller.update_promo_banner(
            segment_id="SEG-001",
            discount_pct=45,
            banner_copy="Too high discount",
        )
    )
    assert promo_reject["status"] == "REJECTED_POLICY_CAP"

    # 3. Memory save & recall via MerchandisingMemoryService
    mem_save = json.loads(
        controller.save_merchandising_memory(
            segment_id="SEG-001",
            memory_key="layout_preference",
            memory_note="Prefer Editorial_Grid for high-basket Nordic shoppers.",
        )
    )
    assert mem_save["status"] == "STORED"

    mem_recall = json.loads(
        controller.recall_merchandising_memory(segment_id="SEG-001", query="Editorial_Grid")
    )
    assert mem_recall["status"] == "SUCCESS"
    assert mem_recall["count"] >= 1


def test_app_oop_classes_build_and_validate() -> None:
    """Verify `app/` OOP classes (`EnvironmentConfigResolver`, `SeedPackLoader`, `AdkAgentBuilder`)."""
    resolver = EnvironmentConfigResolver()
    assert resolver.is_placeholder("your-gcp-project-id") is True
    assert resolver.is_placeholder("valid-project-123") is False

    sanitizer = InstructionSanitizer()
    assert sanitizer.sanitize("Use {user_id} token") == "Use [user_id] token"

    bridge = McpBridgeFactory(repo_root=resolver.repo_root)
    funcs = bridge.extract_module_functions("seed_packs.t02_dynamic_storefronts.mcp_server")
    assert len(funcs) == 10

    loader = SeedPackLoader(
        repo_root=resolver.repo_root,
        config_resolver=resolver,
        mcp_bridge=bridge,
        sanitizer=sanitizer,
    )
    pack = loader.load("t02", enable_mcp_stdio=False)
    assert pack.pack_id == "t02"
    assert len(pack.tools) == 15

    builder = AdkAgentBuilder(
        repo_root=resolver.repo_root,
        pack_loader=loader,
        config_resolver=resolver,
        sanitizer=sanitizer,
    )
    agent, loaded_pack = builder.build("t02", enable_mcp_stdio=False)
    assert agent.name == "expedition_t02"
    assert loaded_pack.pack_id == "t02"

    validator = GcpPreflightValidator()
    err_msg = validator.format_error("Test Title", "Test Problem", ["make setup"])
    assert "Test Title" in err_msg

    dashboard_service = NocturneDashboardService()
    controller = NocturneUiController(service=dashboard_service)
    assert controller.service is dashboard_service

    dockerfile_mcp = (resolver.repo_root / "cd" / "Dockerfile.mcp").read_text(encoding="utf-8")
    assert "COPY mcp ./mcp" in dockerfile_mcp, (
        "cd/Dockerfile.mcp must copy top-level mcp/ package for Cloud Run MCP gateway startup"
    )
