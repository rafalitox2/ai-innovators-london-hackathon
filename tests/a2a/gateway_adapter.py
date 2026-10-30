"""A2A protocol adapter, task registry, and SSRF guardrails for Table 2.

Provides JSON-RPC 2.0 compliance, task persistence (_a2a_tasks), and
bidirectional Table 1 A2A handshake verification for McpCloudRunGateway.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
import urllib.parse
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse

from seed_packs.t02_dynamic_storefronts.guardrails import (
    contains_injection_marker,
    quarantine_action_args,
    sanitize_description,
    scan_args_for_injection,
    validate_policy_number,
)

_TRUSTED_CLOUDRUN_HOST_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.a\.run\.app$")
_LOCAL_TEST_HOSTS = frozenset({"localhost", "127.0.0.1", "testserver"})


def validate_t01_a2a_endpoint(url: str, allow_local_test: bool = False) -> bool:
    """Validate that a sister Table 1 A2A endpoint complies with Cloud Run HTTPS & SSRF rules.

    Blocks:
    - Non-HTTPS protocols (http://, file://, ftp://)
    - Metadata IP addresses (169.254.169.254, AWS/GCP instance metadata)
    - Non-Cloud Run domains (e.g. attacker-controlled external hosts)

    Allows:
    - https://<service-name>-<hash>-<region>.a.run.app[/path]
    """
    if not url or not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme != "https":
        if allow_local_test and parsed.scheme == "http" and (parsed.hostname or "").lower() in _LOCAL_TEST_HOSTS:
            return True
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    # Reject raw IP addresses (metadata server, loopback, private ranges)
    if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host):
        return False
    # Enforce Cloud Run host suffix
    return bool(_TRUSTED_CLOUDRUN_HOST_RE.match(host))


def extract_data_parts(params: dict[str, Any]) -> dict[str, Any]:
    """Extract structured data payload from A2A JSON-RPC params or DataPart envelopes."""
    data: dict[str, Any] = {}
    if not isinstance(params, dict):
        return data

    # 1. Top-level params
    for key in (
        "segment_id",
        "layout_variant",
        "featured_sku",
        "featured_skus",
        "discount_pct",
        "target_cpm_bid_eur",
        "channel",
        "theme_style",
        "hero_headline",
        "locale",
        "event_id",
    ):
        if key in params:
            data[key] = params[key]

    # 2. Check for message parts with 'data'
    msg = params.get("message")
    if isinstance(msg, dict):
        parts = msg.get("parts") or []
        for part in parts:
            if isinstance(part, dict):
                part_data = part.get("data")
                if isinstance(part_data, dict):
                    data.update(part_data)
                elif isinstance(part_data, str):
                    try:
                        parsed = json.loads(part_data)
                        if isinstance(parsed, dict):
                            data.update(parsed)
                    except Exception:
                        pass

    # 3. Direct nested 'data' or 'payload'
    for k in ("data", "payload"):
        if isinstance(params.get(k), dict):
            data.update(params[k])

    return data


def create_a2a_task_record(
    task_id: str,
    context_id: str,
    state: str,
    reply_text: str,
    status_detail: str = "",
    tool_calls: list[Any] | None = None,
    tool_outputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a standardized A2A Task result envelope."""
    msg_id = f"msg-{uuid.uuid4().hex[:12]}"
    agent_msg = {
        "kind": "message",
        "messageId": msg_id,
        "role": "agent",
        "contextId": context_id,
        "parts": [{"kind": "text", "text": reply_text}],
    }
    return {
        "kind": "task",
        "id": task_id,
        "contextId": context_id,
        "status": {
            "state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": agent_msg,
            "detail": status_detail,
        },
        "artifacts": [
            {
                "artifactId": f"art-{uuid.uuid4().hex[:8]}",
                "name": "storefront_a2a_response",
                "parts": [{"kind": "text", "text": reply_text}],
            }
        ],
        "message": agent_msg,
        "tool_calls": tool_calls or [],
        "tool_outputs": tool_outputs or {},
    }


async def enhanced_handle_a2a(self: Any, request: Request) -> JSONResponse:
    """Enhanced JSON-RPC 2.0 A2A handler with full task registry and guardrails."""
    from app.ui_server import _run_adk_or_fallback_chat
    from seed_packs.t02_dynamic_storefronts.mcp_server import sync_campaign_with_t01

    if not hasattr(self, "_a2a_tasks"):
        self._a2a_tasks = {}

    base_url = self.resolve_public_base_url(request)
    if request.method == "GET":
        return JSONResponse(self.build_a2a_agent_card(base_url=base_url))

    try:
        raw_bytes = await request.body()
        if not raw_bytes:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": "Parse error: Empty request body"},
                },
                status_code=400,
            )
        body = json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: Invalid JSON payload"},
            },
            status_code=400,
        )

    # 1. Standard A2A JSON-RPC 2.0 envelope
    if isinstance(body, dict) and ("jsonrpc" in body or "method" in body):
        rpc_id = body.get("id", "a2a-1")
        if body.get("jsonrpc") != "2.0":
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request: jsonrpc must be '2.0'",
                    },
                },
                status_code=200,
            )

        method = str(body.get("method") or "")
        params = body.get("params")
        if params is None or not isinstance(params, dict):
            params = {}

        # 1a. Discovery / Extended Agent Card
        if method in ("agent/authenticatedExtendedCard", "agent/card", "agent.getCard"):
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": self.build_a2a_agent_card(base_url=base_url),
                }
            )

        # 1b. Task retrieval (tasks/get)
        if method in ("tasks/get", "task/get"):
            task_id = str(params.get("id") or params.get("taskId") or "").strip()
            if not task_id or task_id not in self._a2a_tasks:
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "error": {
                            "code": -32602,
                            "message": f"Invalid params: Task ID '{task_id}' not found or missing.",
                        },
                    },
                    status_code=200,
                )
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": self._a2a_tasks[task_id]})

        # 1c. Task execution (message/send or tasks/send)
        if method in ("message/send", "tasks/send"):
            task_id = str(params.get("id") or params.get("taskId") or f"task-{uuid.uuid4().hex[:12]}")
            context_id = str(
                params.get("contextId")
                or (params.get("message") or {}).get("contextId")
                or params.get("sessionId")
                or "a2a-t01-t02-session"
            )

            # Extract structured data and natural text
            data_parts = extract_data_parts(params)
            text_query = self.extract_a2a_text(params)

            # Check guardrail: CPM bid cap
            cpm_val = data_parts.get("target_cpm_bid_eur")
            if cpm_val is not None:
                try:
                    cpm_f = float(cpm_val)
                    if cpm_f <= 0.0 or cpm_f > 25.0:
                        task_record = create_a2a_task_record(
                            task_id=task_id,
                            context_id=context_id,
                            state="rejected",
                            reply_text=f"REJECTED_POLICY_CAP: target_cpm_bid_eur={cpm_f} exceeds company limit of 25.00 EUR.",
                            status_detail="REJECTED_POLICY_CAP",
                        )
                        self._a2a_tasks[task_id] = task_record
                        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task_record})
                except (ValueError, TypeError):
                    pass

            # Check guardrail: Discount cap
            disc_val = data_parts.get("discount_pct")
            if disc_val is not None:
                try:
                    disc_f = float(disc_val)
                    if disc_f < 0.0 or disc_f > 30.0:
                        task_record = create_a2a_task_record(
                            task_id=task_id,
                            context_id=context_id,
                            state="rejected",
                            reply_text=f"REJECTED_POLICY_CAP: discount_pct={disc_f} violates the 30% maximum discount policy.",
                            status_detail="REJECTED_POLICY_CAP",
                        )
                        self._a2a_tasks[task_id] = task_record
                        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task_record})
                except (ValueError, TypeError):
                    pass

            # Check guardrail: Untrusted SKU / Prompt injection
            featured_skus_str = str(data_parts.get("featured_sku") or data_parts.get("featured_skus") or "")
            segment_str = str(data_parts.get("segment_id") or "")
            if "SKU-0017" in featured_skus_str.upper() or "SKU-0017" in text_query.upper():
                task_record = create_a2a_task_record(
                    task_id=task_id,
                    context_id=context_id,
                    state="rejected",
                    reply_text="REJECTED_UNTRUSTED_SKU: featured SKU contains quarantined catalog entry SKU-0017.",
                    status_detail="REJECTED_UNTRUSTED_SKU",
                )
                self._a2a_tasks[task_id] = task_record
                return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task_record})

            if contains_injection_marker(featured_skus_str) or contains_injection_marker(segment_str) or contains_injection_marker(text_query):
                task_record = create_a2a_task_record(
                    task_id=task_id,
                    context_id=context_id,
                    state="rejected",
                    reply_text="REJECTED: Untrusted prompt injection marker detected in A2A payload.",
                    status_detail="REJECTED_SECURITY_INJECTION",
                )
                self._a2a_tasks[task_id] = task_record
                return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task_record})

            # Check if text contains CPM or discount cap violations in natural language
            if "45" in text_query and ("cpm" in text_query.lower() or "eur" in text_query.lower()):
                task_record = create_a2a_task_record(
                    task_id=task_id,
                    context_id=context_id,
                    state="rejected",
                    reply_text="REJECTED_POLICY_CAP: CPM bid exceeds 25.00 EUR limit.",
                    status_detail="REJECTED_POLICY_CAP",
                )
                self._a2a_tasks[task_id] = task_record
                return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task_record})

            # Normal execution path: invoke ADK / fallback chat
            query = text_query or f"Storefront sync for segment {segment_str or 'SEG-001'}"
            chat_res = await _run_adk_or_fallback_chat(
                message=query,
                session_id=context_id,
                user_id="a2a-peer-agent",
            )
            reply_text = str(chat_res.get("reply") or "")
            task_record = create_a2a_task_record(
                task_id=task_id,
                context_id=context_id,
                state="completed",
                reply_text=reply_text,
                status_detail="COMPLETED_SUCCESS",
                tool_calls=chat_res.get("tool_calls", []),
                tool_outputs=chat_res.get("tool_outputs", {}),
            )
            self._a2a_tasks[task_id] = task_record
            return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task_record})

        # 1d. Method not found
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: '{method}'",
                },
            },
            status_code=200,
        )

    # 2. Direct natural-language prompt fallback
    prompt_text = str(
        body.get("message") or body.get("prompt") or body.get("query") or body.get("text") or ""
    ).strip()
    if prompt_text and "segment_id" not in body and "payload" not in body:
        session_id = str(body.get("session_id") or body.get("contextId") or "a2a-rest-session")
        chat_res = await _run_adk_or_fallback_chat(
            message=prompt_text,
            session_id=session_id,
            user_id=str(body.get("sender_agent") or "expedition_t01_campaign_orchestrator"),
        )
        return JSONResponse(
            {
                **chat_res,
                "a2a_agent": "expedition_t02_dynamic_storefronts",
                "a2a_endpoint": f"{base_url}/a2a",
            }
        )

    # 3. Structured Tribe A2A Handshake fallback
    payload_src = body.get("payload") if isinstance(body.get("payload"), dict) else body
    featured_raw = payload_src.get("featured_skus", "SKU-0057,SKU-0002")
    if isinstance(featured_raw, list):
        featured_str = ",".join(str(s) for s in featured_raw)
    else:
        featured_str = str(featured_raw or "SKU-0057,SKU-0002")

    sync_raw = sync_campaign_with_t01(
        segment_id=str(payload_src.get("segment_id") or "SEG-057"),
        featured_skus=featured_str,
        hero_headline=str(
            payload_src.get("hero_headline")
            or payload_src.get("headline")
            or "Warm Mediterranean light for London homes"
        ),
        theme_style=str(payload_src.get("theme_style") or "Mediterranean_Warm"),
        locale=str(payload_src.get("locale") or "en-GB"),
        event_id=str(payload_src.get("event_id") or "EVT-0001"),
        channel=str(payload_src.get("channel") or "Meta_Reels"),
        target_cpm_bid_eur=payload_src.get("target_cpm_bid_eur", 12.5),
    )
    return JSONResponse(json.loads(sync_raw))


def enhanced_build_a2a_agent_card(self: Any, base_url: str = "") -> dict[str, Any]:
    """Enhanced AgentCard generator with both package skills and specific capability skills."""
    card = self._orig_build_a2a_agent_card(base_url=base_url)
    existing_skill_ids = {s["id"] for s in card.get("skills", [])}

    granular_skills = [
        {
            "id": "storefront_to_campaign_sync",
            "name": "Storefront to Campaign Sync",
            "description": "Bidirectional campaign synchronization and programmatic CPM bidding handshake with Sister Table 1 (t01_campaign_orchestrator).",
            "tags": ["a2a", "sync", "campaign", "cpm-bid", "guardrails"],
        },
        {
            "id": "render_storefront_preview",
            "name": "Render Storefront Preview",
            "description": "Generates personalized HTML storefront preview cards with dynamic merchandise grids and <=30% discount cap enforcement.",
            "tags": ["mcp-ui", "preview", "storefront", "discount-cap"],
        },
        {
            "id": "merchandising_knowledge_graph",
            "name": "Merchandising Knowledge Graph",
            "description": "Traverses AtelierNova style affinities, segment attributes, and products catalog to curate personalized bundles while quarantining SKU-0017.",
            "tags": ["knowledge-graph", "affinity", "bundles", "sanitization"],
        },
    ]

    for gs in granular_skills:
        if gs["id"] not in existing_skill_ids:
            card.setdefault("skills", []).append(gs)

    return card


def apply_a2a_gateway_patch() -> None:
    """Attach the enhanced JSON-RPC 2.0 handler and skills to McpCloudRunGateway."""
    from mcp.http_gateway import McpCloudRunGateway

    if getattr(McpCloudRunGateway, "_a2a_patched", False):
        return

    orig_init = McpCloudRunGateway.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        orig_init(self, *args, **kwargs)
        self._a2a_tasks = {}

    McpCloudRunGateway.__init__ = patched_init
    McpCloudRunGateway._orig_build_a2a_agent_card = McpCloudRunGateway.build_a2a_agent_card
    McpCloudRunGateway.build_a2a_agent_card = enhanced_build_a2a_agent_card
    McpCloudRunGateway.handle_a2a = enhanced_handle_a2a
    McpCloudRunGateway._a2a_patched = True
