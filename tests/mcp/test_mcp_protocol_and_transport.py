"""Automated protocol and transport tests for Table 2 Official FastMCP SDK integration."""

from __future__ import annotations

import inspect
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.mcp_bridge import McpBridgeFactory
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session
import seed_packs.t02_dynamic_storefronts.mcp_server as t02_mcp_module
from seed_packs.t02_dynamic_storefronts.mcp_server import MCP_TOOLS, mcp

EXPECTED_10_TOOL_NAMES = frozenset({
    "publish_storefront_layout",
    "queue_visual_asset_render",
    "update_promo_banner",
    "generate_hero_lifestyle_image",
    "render_storefront_preview",
    "sync_campaign_with_t01",
    "save_merchandising_memory",
    "recall_merchandising_memory",
    "route_merchandising_task",
    "register_gemini_enterprise_agent",
})


@pytest.mark.asyncio
async def test_fastmcp_instance_registration_and_tool_schemas() -> None:
    """Verify FastMCP server instance exposes all 10 tools with valid JSON Schema definitions."""
    assert isinstance(mcp, FastMCP)
    assert mcp.name == "t02_dynamic_storefronts_actions"

    tools = await mcp.list_tools()
    assert len(tools) == 10

    discovered_names = {t.name for t in tools}
    assert discovered_names == EXPECTED_10_TOOL_NAMES

    for tool_def in tools:
        assert tool_def.name in EXPECTED_10_TOOL_NAMES
        assert tool_def.description is not None
        assert len(tool_def.description.strip()) > 10, f"Description too short for {tool_def.name}"

        schema = tool_def.inputSchema
        assert isinstance(schema, dict)
        assert schema.get("type") == "object"
        assert "properties" in schema
        assert isinstance(schema["properties"], dict)

        # Confirm parameter schemas are typed
        for prop_name, prop_spec in schema["properties"].items():
            assert isinstance(prop_spec, dict)
            assert "type" in prop_spec, f"Missing type in property {prop_name} of {tool_def.name}"


def test_mcp_tools_export_list_parity() -> None:
    """Verify MCP_TOOLS exported list exactly matches FastMCP tools for Agent Runtime parity."""
    assert isinstance(MCP_TOOLS, list)
    assert len(MCP_TOOLS) == 10

    exported_names = {fn.__name__ for fn in MCP_TOOLS if callable(fn)}
    assert exported_names == EXPECTED_10_TOOL_NAMES

    # Ensure each function has Google-style docstrings and valid type signatures
    for fn in MCP_TOOLS:
        assert callable(fn)
        doc = inspect.getdoc(fn) or ""
        assert "Args:" in doc, f"Tool {fn.__name__} missing 'Args:' section in docstring"
        assert "Returns:" in doc, f"Tool {fn.__name__} missing 'Returns:' section in docstring"
        sig = inspect.signature(fn)
        assert len(sig.parameters) >= 1, f"Tool {fn.__name__} has no parameters"


@pytest.mark.asyncio
async def test_fastmcp_call_tool_all_10_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify executing all 10 tools through FastMCP `call_tool` returns valid TextContent JSON."""
    test_state_file = tmp_path / "test_mcp_state.json"
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(test_state_file))
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")

    # 1. publish_storefront_layout
    res_layout = await mcp.call_tool(
        "publish_storefront_layout",
        {
            "segment_id": "SEG-001",
            "featured_skus": "SKU-0001,SKU-0002",
            "hero_headline": "Nordic Living Refined",
            "theme_style": "Nordic_Minimal",
        },
    )
    assert isinstance(res_layout, tuple)
    payload_layout = json.loads(res_layout[0][0].text)
    assert payload_layout.get("status") == "SUCCESS"
    assert "LAYOUT-" in payload_layout.get("layout", {}).get("layout_id", "")

    # 2. queue_visual_asset_render
    res_queue = await mcp.call_tool(
        "queue_visual_asset_render",
        {
            "sku_id": "SKU-0002",
            "scene_prompt": "Minimalist wooden dining table in sunlit studio",
            "aspect_ratio": "16:9",
        },
    )
    payload_queue = json.loads(res_queue[0][0].text)
    assert payload_queue.get("status") == "SUCCESS"
    assert "RENDER-" in payload_queue.get("render_job", {}).get("render_job_id", "")

    # 3. update_promo_banner
    res_promo = await mcp.call_tool(
        "update_promo_banner",
        {
            "segment_id": "SEG-001",
            "discount_pct": 15,
            "banner_copy": "Mid-Season Curated Edit 15% Off",
            "sku_id": "SKU-0001",
        },
    )
    payload_promo = json.loads(res_promo[0][0].text)
    assert payload_promo.get("status") == "SUCCESS"
    assert payload_promo.get("promo_banner", {}).get("discount_pct") == 15

    # 4. generate_hero_lifestyle_image
    res_hero = await mcp.call_tool(
        "generate_hero_lifestyle_image",
        {
            "sku_id": "SKU-0001",
            "segment_id": "SEG-001",
            "style_theme": "Nordic_Minimal",
            "scene_description": "Clean Scandinavian interior with oak dining chair",
            "aspect_ratio": "16:9",
        },
    )
    payload_hero = json.loads(res_hero[0][0].text)
    assert payload_hero.get("status") == "SUCCESS"
    assert "hero_asset_url" in payload_hero

    # 5. render_storefront_preview
    res_preview = await mcp.call_tool(
        "render_storefront_preview",
        {
            "segment_id": "SEG-001",
            "featured_skus": "SKU-0001,SKU-0002",
            "hero_headline": "Preview Editorial Headline",
            "theme_style": "Nordic_Minimal",
            "discount_pct": 10,
            "banner_copy": "Preview Banner Headline",
        },
    )
    payload_preview = json.loads(res_preview[0][0].text)
    assert payload_preview.get("status") == "SUCCESS"
    assert "preview" in payload_preview

    # 6. sync_campaign_with_t01
    res_sync = await mcp.call_tool(
        "sync_campaign_with_t01",
        {
            "segment_id": "SEG-001",
            "featured_skus": "SKU-0001,SKU-0002",
            "hero_headline": "Sister Campaign Edit",
            "theme_style": "Nordic_Minimal",
            "target_cpm_bid_eur": 14.50,
        },
    )
    payload_sync = json.loads(res_sync[0][0].text)
    assert payload_sync.get("status") in {"SUCCESS", "STOREFRONT_TO_CAMPAIGN_SYNC"}

    # 7. save_merchandising_memory
    res_save_mem = await mcp.call_tool(
        "save_merchandising_memory",
        {
            "segment_id": "SEG-001",
            "memory_key": "hero_lighting_preference",
            "memory_note": "Prefer high contrast warm ambient lighting for London professionals",
            "author": "Marco Bellini",
        },
    )
    payload_save_mem = json.loads(res_save_mem[0][0].text)
    assert payload_save_mem.get("status") == "STORED"
    assert "MEM-" in payload_save_mem.get("memory", {}).get("memory_id", "")

    # 8. recall_merchandising_memory
    res_recall_mem = await mcp.call_tool(
        "recall_merchandising_memory",
        {
            "segment_id": "SEG-001",
            "query": "lighting",
        },
    )
    payload_recall_mem = json.loads(res_recall_mem[0][0].text)
    assert payload_recall_mem.get("status") == "SUCCESS"
    assert payload_recall_mem.get("count", 0) >= 1

    # 9. route_merchandising_task
    res_route = await mcp.call_tool(
        "route_merchandising_task",
        {
            "task_type": "fast_copy",
            "prompt_text": "Generate a concise 1-sentence tagline for Nordic dining room.",
            "segment_id": "SEG-001",
            "style_theme": "Nordic_Minimal",
        },
    )
    payload_route = json.loads(res_route[0][0].text)
    assert payload_route.get("status") == "SUCCESS"
    assert "routing_decision" in payload_route

    # 10. register_gemini_enterprise_agent
    res_reg = await mcp.call_tool(
        "register_gemini_enterprise_agent",
        {
            "app_id": "ateliernova-mcp-test",
            "agent_display_name": "AtelierNova FastMCP Agent",
            "app_location": "eu",
            "reasoning_engine_id": "112233445566",
        },
    )
    payload_reg = json.loads(res_reg[0][0].text)
    assert payload_reg.get("status") == "SUCCESS"
    assert "registration" in payload_reg


@pytest.mark.asyncio
async def test_in_memory_mcp_client_server_session_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify official MCP client-server JSON-RPC session over in-memory streams."""
    test_state_file = tmp_path / "test_session_state.json"
    monkeypatch.setenv("T02_LOCAL_STATE_FILE", str(test_state_file))
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")

    # Connect client session directly to FastMCP internal server
    server = mcp._mcp_server
    async with create_connected_server_and_client_session(server) as client:
        # 1. Test list_tools over client session
        tools_result = await client.list_tools()
        assert len(tools_result.tools) == 10
        tool_names = {t.name for t in tools_result.tools}
        assert tool_names == EXPECTED_10_TOOL_NAMES

        # 2. Test call_tool roundtrip over in-memory transport
        call_res = await client.call_tool(
            "publish_storefront_layout",
            {
                "segment_id": "SEG-002",
                "featured_skus": "SKU-0003,SKU-0004",
                "hero_headline": "Minimalist Session Headline",
                "theme_style": "Nordic_Minimal",
            },
        )
        assert len(call_res.content) >= 1
        text_content = call_res.content[0]
        assert getattr(text_content, "type", "") == "text"
        parsed = json.loads(text_content.text)
        assert parsed.get("status") == "SUCCESS"
        assert parsed.get("layout", {}).get("segment_id") == "SEG-002"

        # 3. Test policy rejection roundtrip through protocol
        cap_reject_res = await client.call_tool(
            "update_promo_banner",
            {
                "segment_id": "SEG-002",
                "discount_pct": 50,  # exceeds 30% cap
                "banner_copy": "Excessive 50% discount",
            },
        )
        parsed_reject = json.loads(cap_reject_res.content[0].text)
        assert parsed_reject.get("status") == "REJECTED_POLICY_CAP"


def test_mcp_bridge_factory_extract_module_functions() -> None:
    """Verify McpBridgeFactory extracts explicit MCP_TOOLS correctly."""
    factory = McpBridgeFactory()

    # 1. Valid pack module
    tools = factory.extract_module_functions("seed_packs.t02_dynamic_storefronts.mcp_server")
    assert len(tools) == 10
    names = {fn.__name__ for fn in tools}
    assert names == EXPECTED_10_TOOL_NAMES

    # 2. Unknown module raises ImportError
    with pytest.raises(ImportError, match="failed to import"):
        factory.extract_module_functions("nonexistent_mcp_module_xyz")

    # 3. Module without MCP_TOOLS logs warning and returns empty list
    mock_mod = MagicMock()
    del mock_mod.MCP_TOOLS
    import sys
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setitem(sys.modules, "mock_empty_mcp_module", mock_mod)
    res = factory.extract_module_functions("mock_empty_mcp_module")
    assert res == []
    monkeypatch.undo()


def test_mcp_bridge_factory_should_use_stdio_matrix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify McpBridgeFactory correctly determines stdio vs in-process function execution."""
    factory = McpBridgeFactory()

    # Explicit flag takes precedence
    assert factory.should_use_stdio(explicit_flag=True) is True
    assert factory.should_use_stdio(explicit_flag=False) is False

    # Env ENABLE_MCP_STDIO=0/false/no/off
    for val in ("0", "false", "no", "off"):
        monkeypatch.setenv("ENABLE_MCP_STDIO", val)
        assert factory.should_use_stdio() is False

    # Env ENABLE_MCP_STDIO=1/true/yes/on
    for val in ("1", "true", "yes", "on"):
        monkeypatch.setenv("ENABLE_MCP_STDIO", val)
        assert factory.should_use_stdio() is True

    monkeypatch.delenv("ENABLE_MCP_STDIO", raising=False)

    # Cloud container environments default to False
    monkeypatch.setenv("AGENT_RUNTIME_DEPLOY", "1")
    assert factory.should_use_stdio() is False
    monkeypatch.delenv("AGENT_RUNTIME_DEPLOY", raising=False)

    monkeypatch.setenv("K_SERVICE", "t02-mcp-gateway")
    assert factory.should_use_stdio() is False
    monkeypatch.delenv("K_SERVICE", raising=False)

    # Clean local workstation defaults to True
    assert factory.should_use_stdio() is True


def test_mcp_bridge_factory_build_stdio_toolset() -> None:
    """Verify McpBridgeFactory initializes McpToolset with stdio connection parameters."""
    factory = McpBridgeFactory()
    toolset = factory.build_stdio_toolset("seed_packs.t02_dynamic_storefronts.mcp_server")
    assert toolset is not None

    conn = getattr(toolset, "connection_params", None)
    assert conn is not None
    server_params = getattr(conn, "server_params", None)
    assert server_params is not None
    assert "-m" in server_params.args
    assert "seed_packs.t02_dynamic_storefronts.mcp_server" in server_params.args
    assert "PYTHONPATH" in server_params.env
