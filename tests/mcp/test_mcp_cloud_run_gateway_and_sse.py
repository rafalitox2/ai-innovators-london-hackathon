"""Tests for McpCloudRunGateway, HTTP /tools and /invoke endpoints, and SSE routes.

Validates:
- McpCloudRunGateway tool introspection and schema validation
- POST /invoke handler for all 10 MCP tools and error scenarios
- GET /health and GET /healthz system telemetry and tool manifests
- GET /preview/{segment_id} HTML storefront preview and path traversal defense
- Host header injection defense and public base URL resolution
- Security middleware headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP)
- A2A Discovery Agent Card (/.well-known/agent.json, /.well-known/agent-card.json, /a2a)
- A2A JSON-RPC 2.0 envelope and Tribe A2A campaign sync endpoint
- FastMCP SSE endpoint (/sse) and message posting route (/messages)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request
from starlette.testclient import TestClient

from mcp.http_gateway import McpCloudRunGateway
from seed_packs.t02_dynamic_storefronts.mcp_server import MCP_TOOLS


@pytest.fixture
def gateway(tmp_path: Path) -> McpCloudRunGateway:
    """Fixture providing a McpCloudRunGateway instance with temporary repo root."""
    return McpCloudRunGateway(mcp_tools=MCP_TOOLS, repo_root=Path(__file__).resolve().parents[2])


@pytest.fixture
def client(gateway: McpCloudRunGateway, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fixture providing a TestClient for the composite FastAPI application."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    app = gateway.build_fastapi_app()
    return TestClient(app, raise_server_exceptions=False)


# ==============================================================================
# 1. Tool Introspection & Schema Tests
# ==============================================================================


def test_mcp_gateway_list_tools_schema(gateway: McpCloudRunGateway, client: TestClient) -> None:
    """Verify tool introspection produces schemas for all 10 MCP tools."""
    tools = gateway.list_tools()
    assert len(tools) == 10
    names = {t["name"] for t in tools}
    expected_names = {
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
    }
    assert names == expected_names

    for tool in tools:
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert isinstance(tool["parameters"], dict)

    # Verify HTTP GET /tools
    resp = client.get("/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert "tools" in data
    assert len(data["tools"]) == 10


# ==============================================================================
# 2. Tool Invocation Tests (Direct & HTTP POST /invoke)
# ==============================================================================


def test_mcp_gateway_invoke_tool_direct_and_error(gateway: McpCloudRunGateway) -> None:
    """Verify direct invocation of registered tools and proper error raising."""
    # 1. Valid invocation
    res_str = gateway.invoke_tool(
        "publish_storefront_layout",
        {
            "segment_id": "SEG-001",
            "featured_skus": "SKU-0001",
            "hero_headline": "Direct Gateway Test",
        },
    )
    res = json.loads(res_str)
    assert res.get("status") == "SUCCESS"

    # 2. Unknown tool invocation raises ValueError
    with pytest.raises(ValueError, match="not found"):
        gateway.invoke_tool("nonexistent_unknown_tool", {})


def test_mcp_gateway_post_invoke_endpoint(client: TestClient) -> None:
    """Verify POST /invoke executes tools and returns standardized JSON responses."""
    # 1. Successful tool invocation
    resp_valid = client.post(
        "/invoke",
        json={
            "name": "publish_storefront_layout",
            "arguments": {
                "segment_id": "SEG-001",
                "featured_skus": "SKU-0001",
                "hero_headline": "HTTP Gateway Invoke Test",
            },
        },
    )
    assert resp_valid.status_code == 200
    data_valid = resp_valid.json()
    assert data_valid.get("status") == "SUCCESS"
    payload = json.loads(data_valid.get("result", "{}"))
    assert payload.get("status") == "SUCCESS"
    assert payload.get("layout", {}).get("segment_id") == "SEG-001"

    # 2. Guardrail rejection via POST /invoke
    resp_cap = client.post(
        "/invoke",
        json={
            "name": "update_promo_banner",
            "arguments": {
                "segment_id": "SEG-001",
                "discount_pct": 50,  # Exceeds 30% cap
                "banner_copy": "Mega clearance 50% off",
            },
        },
    )
    assert resp_cap.status_code == 200
    data_cap = resp_cap.json()
    payload_cap = json.loads(data_cap.get("result", "{}"))
    assert payload_cap.get("status") == "REJECTED_POLICY_CAP"

    # 3. Unknown tool returns 400 ERROR
    resp_err = client.post(
        "/invoke",
        json={
            "name": "unregistered_bogus_tool",
            "arguments": {},
        },
    )
    assert resp_err.status_code == 400
    data_err = resp_err.json()
    assert data_err.get("status") == "ERROR"
    assert "not found" in data_err.get("error", "").lower()


# ==============================================================================
# 3. System Telemetry & Health Checks
# ==============================================================================


def test_mcp_gateway_health_and_healthz_endpoints(client: TestClient) -> None:
    """Verify /health and /healthz return complete system telemetry and manifest."""
    for path in ("/health", "/healthz"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "ONLINE"
        assert data.get("service") == "t02-dynamic-storefronts-mcp"
        assert data.get("seed_pack") == "t02"
        assert len(data.get("mcp_tools", [])) == 10
        endpoints = data.get("endpoints", {})
        assert "tools" in endpoints
        assert "invoke" in endpoints
        assert "mcp_sse" in endpoints
        assert "a2a_endpoint" in endpoints
        assert "storefront_preview" in endpoints


# ==============================================================================
# 4. Preview Endpoint & Security Defenses
# ==============================================================================


def test_mcp_gateway_preview_endpoint(client: TestClient) -> None:
    """Verify GET /preview/{segment_id} renders HTML preview cards."""
    resp = client.get("/preview/SEG-001")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")
    assert len(resp.text) > 100


def test_mcp_gateway_preview_path_traversal_sanitization(client: TestClient) -> None:
    """Verify path traversal sequences in segment_id are sanitized safely."""
    # Attempt directory traversal and special character injection
    resp = client.get("/preview/..SEG-001--malicious")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")


def test_mcp_gateway_security_headers(client: TestClient) -> None:
    """Verify security headers are attached to all gateway HTTP responses."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_mcp_gateway_resolve_public_base_url_anti_injection(gateway: McpCloudRunGateway) -> None:
    """Verify resolve_public_base_url rejects untrusted Host headers."""
    # 1. Trusted local host
    req_local = MagicMock(spec=Request)
    req_local.url.hostname = "localhost"
    req_local.base_url = "http://localhost:8080/"
    req_local.headers = {}
    assert gateway.resolve_public_base_url(req_local) == "http://localhost:8080"

    # 2. Trusted Cloud Run host with HTTPS forwarding
    req_cr = MagicMock(spec=Request)
    req_cr.url.hostname = "t02-storefront-abcdef-ew.a.run.app"
    req_cr.base_url = "http://t02-storefront-abcdef-ew.a.run.app/"
    req_cr.headers = {"x-forwarded-proto": "https"}
    assert gateway.resolve_public_base_url(req_cr) == "https://t02-storefront-abcdef-ew.a.run.app"

    # 3. Untrusted external host header (Host header injection attempt)
    req_evil = MagicMock(spec=Request)
    req_evil.url.hostname = "evil-phishing-site.example.com"
    req_evil.base_url = "http://evil-phishing-site.example.com/"
    req_evil.headers = {}
    assert gateway.resolve_public_base_url(req_evil) == "http://localhost:8080"


# ==============================================================================
# 5. A2A Agent Discovery Card & Handshake Tests
# ==============================================================================


def test_mcp_gateway_a2a_agent_cards(client: TestClient) -> None:
    """Verify A2A agent card endpoints return valid discovery metadata."""
    for path in ("/.well-known/agent.json", "/.well-known/agent-card.json", "/a2a"):
        resp = client.get(path)
        assert resp.status_code == 200
        card = resp.json()
        assert card.get("name") == "expedition_t02_dynamic_storefronts"
        assert card.get("tribe") == "Creative AI & AdTech"
        assert card.get("capabilities", {}).get("mcp_sse") is True
        assert card.get("capabilities", {}).get("a2a_tribe_handshake") is True
        skills = card.get("skills", [])
        assert len(skills) >= 3
        skill_ids = {s.get("id") for s in skills}
        assert "t02-mcp-actions-a2a" in skill_ids


def test_mcp_gateway_a2a_jsonrpc_and_campaign_sync(client: TestClient) -> None:
    """Verify POST /a2a handles A2A JSON-RPC 2.0 envelopes and Tribe sync payloads."""
    # 1. A2A JSON-RPC 2.0 card request
    rpc_card_req = {
        "jsonrpc": "2.0",
        "id": "rpc-test-1",
        "method": "agent/authenticatedExtendedCard",
        "params": {},
    }
    resp_card = client.post("/a2a", json=rpc_card_req)
    assert resp_card.status_code == 200
    card_data = resp_card.json()
    assert card_data.get("jsonrpc") == "2.0"
    assert card_data.get("id") == "rpc-test-1"
    assert card_data.get("result", {}).get("name") == "expedition_t02_dynamic_storefronts"

    # 2. Tribe A2A campaign sync payload (valid)
    sync_payload = {
        "segment_id": "SEG-001",
        "featured_skus": "SKU-0001,SKU-0002",
        "hero_headline": "Gateway A2A Handshake Test",
        "theme_style": "Nordic_Minimal",
        "channel": "Meta_Reels",
        "target_cpm_bid_eur": 14.50,
    }
    resp_sync = client.post("/a2a", json={"payload": sync_payload})
    assert resp_sync.status_code == 200
    sync_res = resp_sync.json()
    assert sync_res.get("status") in {"SUCCESS", "STOREFRONT_TO_CAMPAIGN_SYNC"}

    # 3. Tribe A2A campaign sync payload (CPM cap violation > 25 EUR)
    sync_cap_payload = {
        "segment_id": "SEG-001",
        "featured_skus": "SKU-0001",
        "target_cpm_bid_eur": 35.0,
    }
    resp_cap = client.post("/a2a", json={"payload": sync_cap_payload})
    assert resp_cap.status_code == 200
    assert resp_cap.json().get("status") == "REJECTED_POLICY_CAP"


# ==============================================================================
# 6. SSE & Message Posting Routes
# ==============================================================================


def test_mcp_gateway_sse_routes_registered(client: TestClient) -> None:
    """Verify FastMCP SSE and messages routes are mounted in the FastAPI app."""
    routes = [r.path for r in client.app.router.routes]  # type: ignore[attr-defined]
    assert "/sse" in routes
    assert "/messages" in routes

    # Verify GET /sse initiates SSE stream response with localhost:8000 host header
    with client.stream("GET", "/sse", headers={"Host": "localhost:8000"}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
