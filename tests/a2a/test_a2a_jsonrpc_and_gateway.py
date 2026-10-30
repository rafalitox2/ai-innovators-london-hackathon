"""Tests for JSON-RPC 2.0 /a2a gateway endpoint, task registry, and error compliance.

Covers:
1. message/send and tasks/send with structured DataPart and natural-language TextPart.
2. tasks/get retrieval from in-memory task registry (_a2a_tasks) and -32602 error handling.
3. agent/authenticatedExtendedCard returning full A2A discovery card via JSON-RPC.
4. JSON-RPC 2.0 error specification compliance (-32700, -32600, -32601, -32602).
5. Async HTTP client execution and state sync between /api/a2a/sync and /api/dashboard.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
import pytest

from mcp.http_gateway import McpCloudRunGateway


@pytest.fixture
def gateway_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Fixture providing an initialized McpCloudRunGateway app in offline mode."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    monkeypatch.setenv("MCP_SERVER_URL", "https://t02-mcp-gateway-abc123-ew.a.run.app")
    gateway = McpCloudRunGateway()
    return gateway.build_fastapi_app()


def test_jsonrpc_message_send_and_tasks_send_with_structured_data_parts(gateway_app: Any) -> None:
    """Validate message/send and tasks/send with structured DataParts."""
    client = TestClient(gateway_app)

    # 1. message/send with nested DataPart
    req_body = {
        "jsonrpc": "2.0",
        "id": "req-msg-001",
        "method": "message/send",
        "params": {
            "id": "task-data-001",
            "contextId": "ctx-storefront-t01-t02",
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "data",
                        "data": {
                            "segment_id": "SEG-002",
                            "layout_variant": "Editorial_Grid",
                            "featured_sku": "SKU-0008",
                            "discount_pct": 15,
                            "target_cpm_bid_eur": 18.5,
                            "channel": "Meta_Reels",
                        },
                    }
                ],
            },
        },
    }
    resp = client.post("/a2a", json=req_body)
    assert resp.status_code == 200
    res = resp.json()
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == "req-msg-001"
    task = res["result"]
    assert task["id"] == "task-data-001"
    assert task["status"]["state"] == "completed"
    assert len(task["artifacts"]) >= 1

    # 2. tasks/send with top-level params data
    req_tasks = {
        "jsonrpc": "2.0",
        "id": "req-task-send-002",
        "method": "tasks/send",
        "params": {
            "id": "task-data-002",
            "segment_id": "SEG-005",
            "layout_variant": "Single_Hero_Spotlight",
            "featured_sku": "SKU-0005",
            "discount_pct": 20,
            "target_cpm_bid_eur": 14.0,
            "channel": "TikTok_Spark",
        },
    }
    resp2 = client.post("/a2a", json=req_tasks)
    assert resp2.status_code == 200
    res2 = resp2.json()
    assert res2["result"]["id"] == "task-data-002"
    assert res2["result"]["status"]["state"] == "completed"


def test_jsonrpc_message_send_with_natural_language_text_parts(gateway_app: Any) -> None:
    """Validate message/send with natural-language TextParts."""
    client = TestClient(gateway_app)

    req_body = {
        "jsonrpc": "2.0",
        "id": "req-text-003",
        "method": "message/send",
        "params": {
            "contextId": "ctx-nl-session-77",
            "message": {
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": "Please optimize storefront layout for segment SEG-002, feature SKU-0008 at 15% discount and bid 18.5 EUR CPM.",
                    }
                ],
            },
        },
    }
    resp = client.post("/a2a", json=req_body)
    assert resp.status_code == 200
    res = resp.json()
    assert res["jsonrpc"] == "2.0"
    assert res["id"] == "req-text-003"
    task = res["result"]
    assert task["status"]["state"] == "completed"
    assert task["contextId"] == "ctx-nl-session-77"
    assert task["message"]["parts"][0]["text"]


def test_jsonrpc_tasks_get_retrieval_and_unknown_id(gateway_app: Any) -> None:
    """Validate tasks/get retrieves saved tasks from _a2a_tasks and handles unknown IDs."""
    client = TestClient(gateway_app)

    # 1. First stage a task via message/send
    known_task_id = "task-persisted-999"
    stage_resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "stage-req-1",
            "method": "message/send",
            "params": {
                "id": known_task_id,
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Sync segment SEG-010 with Table 1"}],
                },
            },
        },
    )
    assert stage_resp.status_code == 200

    # 2. Retrieve existing task by ID
    get_resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "get-req-1",
            "method": "tasks/get",
            "params": {"id": known_task_id},
        },
    )
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["jsonrpc"] == "2.0"
    assert get_data["id"] == "get-req-1"
    assert get_data["result"]["id"] == known_task_id
    assert get_data["result"]["status"]["state"] == "completed"

    # 3. Retrieve non-existent task ID -> -32602 error
    bad_resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "get-req-2",
            "method": "tasks/get",
            "params": {"id": "non-existent-task-id-12345"},
        },
    )
    assert bad_resp.status_code == 200
    bad_data = bad_resp.json()
    assert bad_data["jsonrpc"] == "2.0"
    assert "error" in bad_data
    assert bad_data["error"]["code"] == -32602
    assert "not found" in bad_data["error"]["message"].lower()

    # 4. Missing ID parameter -> -32602 error
    missing_id_resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "get-req-3",
            "method": "tasks/get",
            "params": {},
        },
    )
    assert missing_id_resp.status_code == 200
    assert missing_id_resp.json()["error"]["code"] == -32602


def test_jsonrpc_authenticated_extended_card(gateway_app: Any) -> None:
    """Validate agent/authenticatedExtendedCard returns full AgentCard over JSON-RPC."""
    client = TestClient(gateway_app)

    for method in ("agent/authenticatedExtendedCard", "agent/card", "agent.getCard"):
        resp = client.post(
            "/a2a",
            json={
                "jsonrpc": "2.0",
                "id": f"card-{method}",
                "method": method,
            },
        )
        assert resp.status_code == 200
        res = resp.json()
        assert res["jsonrpc"] == "2.0"
        assert res["id"] == f"card-{method}"
        card = res["result"]
        assert card["name"] == "expedition_t02_dynamic_storefronts"
        assert card["protocolVersion"] == "0.2.5"
        assert card["capabilities"]["a2a_tribe_handshake"] is True
        assert len(card["skills"]) >= 5


def test_jsonrpc_error_compliance_standards(gateway_app: Any) -> None:
    """Validate JSON-RPC 2.0 error codes (-32700, -32600, -32601, -32602)."""
    client = TestClient(gateway_app)

    # 1. Malformed JSON -> -32700 Parse error
    malformed_resp = client.post(
        "/a2a",
        content=b"INVALID-JSON-PAYLOAD{{{",
        headers={"Content-Type": "application/json"},
    )
    assert malformed_resp.status_code in (200, 400)
    err1 = malformed_resp.json()
    assert err1.get("error", {}).get("code") == -32700

    # 2. Invalid jsonrpc version -> -32600 Invalid Request
    bad_rpc_resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "1.0",
            "id": "err-rpc-ver",
            "method": "message/send",
            "params": {},
        },
    )
    assert bad_rpc_resp.status_code == 200
    err2 = bad_rpc_resp.json()
    assert err2.get("error", {}).get("code") == -32600

    # 3. Unknown method -> -32601 Method not found
    unknown_method_resp = client.post(
        "/a2a",
        json={
            "jsonrpc": "2.0",
            "id": "err-unknown-fn",
            "method": "unsupported/custom_action",
            "params": {},
        },
    )
    assert unknown_method_resp.status_code == 200
    err3 = unknown_method_resp.json()
    assert err3.get("error", {}).get("code") == -32601


@pytest.mark.asyncio
async def test_async_client_jsonrpc_and_state_synchronization(gateway_app: Any) -> None:
    """Test full async execution and dashboard state sync via httpx.AsyncClient."""
    transport = ASGITransport(app=gateway_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        # 1. Execute A2A sync
        sync_resp = await async_client.post(
            "/api/a2a/sync",
            json={
                "segment_id": "SEG-015",
                "featured_skus": "SKU-0015",
                "hero_headline": "Warm Lighting for City Apartments",
                "theme_style": "Mediterranean_Warm",
                "channel": "Meta_Reels",
                "target_cpm_bid_eur": 16.0,
            },
        )
        assert sync_resp.status_code == 200
        sync_data = sync_resp.json()
        assert sync_data["status"] == "SUCCESS"
        handshake = sync_data["a2a_handshake"]
        assert handshake["handshake_type"] == "STOREFRONT_TO_CAMPAIGN_SYNC"
        assert handshake["payload"]["target_cpm_bid_eur"] == 16.0

        # 2. Query Dashboard
        dash_resp = await async_client.get("/api/dashboard")
        assert dash_resp.status_code == 200
        dash_data = dash_resp.json()
        assert dash_data["status"] == "SUCCESS"
        assert "products" in dash_data
        assert "segments" in dash_data
