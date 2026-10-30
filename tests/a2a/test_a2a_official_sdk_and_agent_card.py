"""Official A2A SDK and Google ADK RemoteA2aAgent integration tests for Table 2.

Validates:
1. Discovery endpoints (/.well-known/agent.json, /.well-known/agent-card.json) against official
   a2a.types.AgentCard and a2a.types.AgentSkill schemas.
2. Complete AgentCard contract: name, description, url, version, protocolVersion, capabilities,
   defaultInputModes, defaultOutputModes, and all registered skills.
3. Google ADK A2A converters (part_converter, event_converter) round-trip fidelity between
   genai.types.Part / Event and a2a.types.Part / Message / Task.
4. RemoteA2aAgent instantiation pointing to Table 2 and Sister Table 1 AgentCards.
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi.testclient import TestClient
from google.protobuf.json_format import ParseDict
import pytest

import a2a.types as a2a_types
from google.adk.a2a.agent._remote_a2a_agent import RemoteA2aAgent
from google.adk.a2a.converters import event_converter, part_converter
from google.adk.events.event import Event
from google.genai import types as genai_types
from mcp.http_gateway import McpCloudRunGateway


def _parse_agent_card(data: dict[str, Any]) -> a2a_types.AgentCard:
    """Parse and validate raw AgentCard dictionary using the official a2a SDK."""
    if hasattr(a2a_types.AgentCard, "model_validate"):
        return a2a_types.AgentCard.model_validate(data)
    card = a2a_types.AgentCard()
    ParseDict(data, card, ignore_unknown_fields=True)
    return card


def test_well_known_agent_discovery_card_schema_and_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """/.well-known/agent.json and /.well-known/agent-card.json strictly conform to the A2A spec."""
    monkeypatch.setenv("MCP_SERVER_URL", "https://t02-mcp-gateway-abc123-ew.a.run.app")
    gateway = McpCloudRunGateway()
    app = gateway.build_fastapi_app()
    client = TestClient(app)

    for path in ("/.well-known/agent.json", "/.well-known/agent-card.json", "/a2a"):
        resp = client.get(path)
        assert resp.status_code == 200, f"Failed on {path}: {resp.status_code}"
        card_data = resp.json()

        # Validate with official A2A SDK
        card_pb = _parse_agent_card(card_data)
        assert card_pb.name == "expedition_t02_dynamic_storefronts"
        assert "storefront" in card_pb.description.lower()
        assert card_pb.version == "1.0.0"

        # Check raw JSON contract fields
        assert card_data["protocolVersion"] == "0.2.5"
        assert card_data["url"] == "https://t02-mcp-gateway-abc123-ew.a.run.app/a2a"
        assert "application/json" in card_data["defaultInputModes"]
        assert "application/json" in card_data["defaultOutputModes"]

        # Capabilities verification
        caps = card_data["capabilities"]
        assert caps.get("streaming") is True
        assert caps.get("mcp_sse") is True
        assert caps.get("multimodal_image_generation") is True
        assert caps.get("mcp_app_ui_preview") is True
        assert caps.get("a2a_tribe_handshake") is True

        # Skills verification
        skill_ids = [s.get("id") or getattr(s, "id", "") for s in card_data.get("skills", [])]
        expected_skills = [
            "t02-adk-bigquery",
            "t02-mcp-actions-a2a",
            "t02-storefront-ui-multimodal",
            "t02-eval-and-deploy",
            "storefront_to_campaign_sync",
            "render_storefront_preview",
            "merchandising_knowledge_graph",
        ]
        for exp in expected_skills:
            assert exp in skill_ids, f"Expected skill {exp} not found in {skill_ids}"

        # Verify skills converted cleanly to protobuf
        assert len(card_pb.skills) >= len(expected_skills)
        pb_skill_ids = [s.id for s in card_pb.skills]
        for exp in expected_skills:
            assert exp in pb_skill_ids


def test_ui_server_and_gateway_a2a_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gateway mounts UI server routes and provides seamless A2A sync endpoints."""
    monkeypatch.setenv("SEED_OFFLINE_MODE", "1")
    gateway = McpCloudRunGateway()
    app = gateway.build_fastapi_app()
    client = TestClient(app)

    # UI server A2A sync endpoint
    sync_resp = client.post(
        "/api/a2a/sync",
        json={
            "segment_id": "SEG-001",
            "featured_skus": "SKU-0001,SKU-0006",
            "hero_headline": "Nordic Minimal Warm Autumn Edit",
            "theme_style": "Nordic_Minimal",
            "channel": "Meta_Reels",
            "target_cpm_bid_eur": 14.50,
        },
    )
    assert sync_resp.status_code == 200
    sync_data = sync_resp.json()
    assert sync_data["status"] == "SUCCESS"
    assert "a2a_handshake" in sync_data
    assert sync_data["a2a_handshake"]["handshake_type"] == "STOREFRONT_TO_CAMPAIGN_SYNC"


def test_adk_a2a_converters_part_conversion() -> None:
    """Test bi-directional part conversion between google.genai.types and a2a.types."""
    # 1. Text Part
    sample_text = "Personalize storefront for segment SEG-012 with Mediterranean Warm theme"
    genai_part = genai_types.Part.from_text(text=sample_text)
    a2a_part = part_converter.convert_genai_part_to_a2a_part(genai_part)

    assert a2a_part.text == sample_text
    round_trip_genai = part_converter.convert_a2a_part_to_genai_part(a2a_part)
    assert round_trip_genai.text == sample_text


def test_adk_a2a_converters_message_and_event() -> None:
    """Test bi-directional message conversion between google.adk Event and a2a.types.Message."""
    user_text = "Sync campaign creatives with Table 1 ad orchestrator"
    user_part = genai_types.Part.from_text(text=user_text)
    source_event = Event(
        content=genai_types.Content(parts=[user_part], role="model"),
        invocation_id="inv-t02-test-001",
    )

    a2a_msg = event_converter.convert_event_to_a2a_message(source_event)
    assert a2a_msg.role == a2a_types.Role.ROLE_AGENT
    assert len(a2a_msg.parts) == 1
    assert a2a_msg.parts[0].text == user_text

    reconstructed_event = event_converter.convert_a2a_message_to_event(a2a_msg)
    assert reconstructed_event.content.role == "model"
    assert reconstructed_event.content.parts[0].text == user_text

    # Test user message conversion
    a2a_user_part = a2a_types.Part(text="User instruction for storefront")
    user_msg = a2a_types.Message(
        message_id="msg-user-1",
        role=a2a_types.Role.ROLE_USER,
        parts=[a2a_user_part],
    )
    user_event = event_converter.convert_a2a_message_to_event(user_msg)
    assert user_event.content.role == "user"
    assert user_event.content.parts[0].text == "User instruction for storefront"


def test_adk_a2a_converters_task_conversion() -> None:
    """Test converting a2a.types.Task to google.adk Event."""
    task = a2a_types.Task(
        id="task-storefront-9001",
        context_id="ctx-tribe-handshake-55",
    )
    event = event_converter.convert_a2a_task_to_event(task)
    assert isinstance(event, Event)


def test_remote_a2a_agent_instantiation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test instantiating RemoteA2aAgent with Table 2 discovery card."""
    monkeypatch.setenv("MCP_SERVER_URL", "https://t02-storefront-prod.a.run.app")
    gateway = McpCloudRunGateway()
    card_dict = gateway.build_a2a_agent_card("https://t02-storefront-prod.a.run.app")

    card = _parse_agent_card(card_dict)

    remote_agent = RemoteA2aAgent(
        name="remote_t02_storefront_agent",
        agent_card=card,
        description="Remote ADK proxy agent representing Table 2 Storefront Engine",
    )

    assert remote_agent.name == "remote_t02_storefront_agent"
    assert "storefront" in remote_agent.description.lower()
    stored_card = getattr(remote_agent, "_agent_card", None) or getattr(remote_agent, "agent_card", None)
    assert stored_card is not None
    assert stored_card.name == "expedition_t02_dynamic_storefronts"
