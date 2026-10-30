"""ADK InMemoryRunner end-to-end execution and guardrail verification for all 15 Table 2 tools."""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from app.agent import build_agent
from google.adk.evaluation.request_intercepter_plugin import _RequestIntercepterPlugin
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
import google.genai.types as types

MODEL_ID_FROM_ENV = os.environ.get("GEMINI_MODEL", "mock-agent-model")


class SingleToolMockLlm(BaseLlm):
    """Deterministic mock LLM yielding a target tool call on turn 1, then completion text."""

    model: str = MODEL_ID_FROM_ENV
    tool_name: str
    tool_args: dict[str, Any]
    call_count: int = 0

    async def generate_content_async(self, req: Any, stream: bool = False):  # type: ignore[override]
        self.call_count += 1
        if self.call_count == 1:
            yield LlmResponse(
                content=types.Content(
                    parts=[types.Part.from_function_call(name=self.tool_name, args=self.tool_args)]
                )
            )
        else:
            yield LlmResponse(
                content=types.Content(
                    parts=[types.Part.from_text(text=f"Executed {self.tool_name} successfully.")]
                )
            )


def _execute_runner_tool(tool_name: str, tool_args: dict[str, Any]) -> tuple[dict[str, Any], list[Any], _RequestIntercepterPlugin]:
    """Helper to run an in-memory agent turn invoking tool_name and return the tool output."""
    agent, pack = build_agent("t02", enable_mcp_stdio=False)
    mock_llm = SingleToolMockLlm(tool_name=tool_name, tool_args=tool_args)
    agent.model = mock_llm

    intercepter = _RequestIntercepterPlugin(name=f"intercepter_{tool_name}")
    runner = InMemoryRunner(agent, plugins=[intercepter])

    session_id = f"sess_{tool_name}"
    runner.session_service.create_session_sync(
        app_name=runner.app_name, user_id="test_user", session_id=session_id
    )

    events = list(
        runner.run(
            user_id="test_user",
            session_id=session_id,
            new_message=types.Content(parts=[types.Part.from_text(text=f"Run {tool_name}")]),
        )
    )

    # Find the function response
    response_payload: dict[str, Any] = {}
    for ev in events:
        for part in (ev.content.parts if ev.content else []):
            if part.function_response and part.function_response.name == tool_name:
                raw_res = part.function_response.response.get("result")
                if isinstance(raw_res, str):
                    response_payload = json.loads(raw_res)
                elif isinstance(raw_res, dict):
                    response_payload = raw_res
                elif isinstance(part.function_response.response, dict):
                    response_payload = part.function_response.response

    return response_payload, events, intercepter


def test_agent_registers_all_15_tools() -> None:
    """Verify that build_agent('t02') binds all 15 expected Table 2 tools."""
    agent, pack = build_agent("t02", enable_mcp_stdio=False)
    registered = [t.__name__ for t in agent.tools if callable(t)]
    assert len(registered) == 15

    expected_15 = [
        "find_catalog_products",
        "get_storefront_performance",
        "get_audience_segments",
        "recommend_storefront_optimization",
        "query_merchandising_knowledge_graph",
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
    ]
    for exp in expected_15:
        assert exp in registered, f"Missing tool in ADK agent: {exp}"


@pytest.mark.parametrize(
    "tool_name,tool_args",
    [
        ("find_catalog_products", {"category": "Modular_Sofas", "min_stock": 5}),
        ("get_storefront_performance", {"segment_id": "SEG-001", "limit": 3}),
        ("get_audience_segments", {"region": "ES_Madrid"}),
        ("recommend_storefront_optimization", {"region": "all", "min_bounce_rate_pct": 50.0, "limit": 2}),
        ("query_merchandising_knowledge_graph", {"segment_id": "SEG-001", "max_bundle_size": 3, "min_stock": 10}),
        ("publish_storefront_layout", {"segment_id": "SEG-001", "featured_skus": "SKU-0001,SKU-0002", "hero_headline": "Nordic Edit"}),
        ("queue_visual_asset_render", {"sku_id": "SKU-0001", "scene_prompt": "loft render", "aspect_ratio": "16:9"}),
        ("update_promo_banner", {"segment_id": "SEG-001", "discount_pct": 20, "banner_copy": "Autumn Edit"}),
        ("generate_hero_lifestyle_image", {"sku_id": "SKU-0001", "scene_description": "Minimalist living room"}),
        ("render_storefront_preview", {"segment_id": "SEG-001", "featured_skus": "SKU-0001", "hero_headline": "Nordic Living", "discount_pct": 5}),
        ("sync_campaign_with_t01", {"segment_id": "SEG-001", "featured_skus": "SKU-0001", "hero_headline": "Autumn Edit", "target_cpm_bid_eur": 18.0}),
        ("save_merchandising_memory", {"segment_id": "SEG-001", "memory_key": "style_notes", "memory_note": "Minimalist wood focus"}),
        ("recall_merchandising_memory", {"segment_id": "SEG-001", "query": "Minimalist"}),
        ("route_merchandising_task", {"task_type": "fast_copy", "prompt_text": "Craft high CTR tagline"}),
        ("register_gemini_enterprise_agent", {"app_id": "atelier-app", "reasoning_engine_id": "engine-42"}),
    ],
)
def test_in_memory_runner_executes_each_of_all_15_tools(
    tool_name: str, tool_args: dict[str, Any]
) -> None:
    """End-to-end execution of every tool in InMemoryRunner via FunctionCall -> FunctionResponse flow."""
    payload, events, intercepter = _execute_runner_tool(tool_name, tool_args)

    assert payload, f"No tool response captured for {tool_name}"
    assert payload.get("status") in {"SUCCESS", "STORED", "NEEDS_IMAGE_GENERATION"}, (
        f"Tool {tool_name} returned non-success payload: {payload}"
    )

    # Verify event structure: FC -> FR -> Text
    fc_events = [
        e for e in events
        if any(p.function_call and p.function_call.name == tool_name for p in (e.content.parts if e.content else []))
    ]
    fr_events = [
        e for e in events
        if any(p.function_response and p.function_response.name == tool_name for p in (e.content.parts if e.content else []))
    ]
    assert len(fc_events) == 1, f"Missing FunctionCall event for {tool_name}"
    assert len(fr_events) == 1, f"Missing FunctionResponse event for {tool_name}"

    # Verify RequestIntercepterPlugin intercepted the request
    assert len(intercepter._llm_requests_cache) >= 1


def test_guardrail_promo_discount_policy_cap_rejected() -> None:
    """Discounts exceeding 30% are deterministically rejected with REJECTED_POLICY_CAP or REJECTED_SECURITY_CALLBACK."""
    # 1. update_promo_banner
    payload_banner, _, _ = _execute_runner_tool(
        "update_promo_banner",
        {"segment_id": "SEG-001", "discount_pct": 45, "banner_copy": "Super Sale"},
    )
    assert payload_banner.get("status") in {"REJECTED_POLICY_CAP", "REJECTED_SECURITY_CALLBACK"}
    assert "discount_pct" in str(payload_banner.get("error", "")) or "30" in str(payload_banner.get("error", ""))

    # 2. render_storefront_preview
    payload_preview, _, _ = _execute_runner_tool(
        "render_storefront_preview",
        {"segment_id": "SEG-001", "featured_skus": "SKU-0001", "hero_headline": "Nordic Living", "discount_pct": 35},
    )
    assert payload_preview.get("status") in {"REJECTED_POLICY_CAP", "REJECTED_SECURITY_CALLBACK"}
    assert "discount_pct" in str(payload_preview.get("error", "")) or "30" in str(payload_preview.get("error", ""))


def test_guardrail_a2a_cpm_bid_cap_rejected() -> None:
    """CPM bids exceeding 25.0 EUR in sync_campaign_with_t01 are rejected with REJECTED_POLICY_CAP or REJECTED_SECURITY_CALLBACK."""
    payload, _, _ = _execute_runner_tool(
        "sync_campaign_with_t01",
        {
            "segment_id": "SEG-001",
            "featured_skus": "SKU-0001",
            "hero_headline": "High Bid Test",
            "target_cpm_bid_eur": 35.5,
        },
    )
    assert payload.get("status") in {"REJECTED_POLICY_CAP", "REJECTED_SECURITY_CALLBACK"}
    assert "target_cpm_bid_eur" in str(payload.get("error", "")) or "25.0" in str(payload.get("error", ""))


def test_guardrail_prompt_injection_sku0017_quarantined() -> None:
    """Prompt injection strings and SKU-0017 attack vectors are quarantined or rejected."""
    # 1. Action tools reject quarantined SKU-0017
    payload_queue, _, _ = _execute_runner_tool(
        "queue_visual_asset_render",
        {"sku_id": "SKU-0017", "scene_prompt": "loft scene"},
    )
    assert payload_queue.get("status") == "REJECTED_QUARANTINED_SKU"
    assert "quarantined" in str(payload_queue.get("error", "")).lower()

    # 2. Recommender filters out SKU-0017
    payload_rec, _, _ = _execute_runner_tool(
        "recommend_storefront_optimization",
        {"region": "all", "min_bounce_rate_pct": 50.0, "limit": 10},
    )
    assert payload_rec.get("status") == "SUCCESS"
    for rec in payload_rec.get("recommendations", []):
        assert rec.get("recommended_sku_id") != "SKU-0017"
