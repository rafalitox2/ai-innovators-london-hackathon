"""Cloud Run ASGI server for Table 2 FastMCP Server + A2A Agent Card + Live Storefront UI Preview."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route
import uvicorn

from seed_packs.t02_dynamic_storefronts.mcp_server import (
    MCP_TOOLS,
    mcp,
    render_storefront_preview,
)
from seed_packs.t02_dynamic_storefronts.tools import TOOLS as ADK_TOOLS

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UI_DIR = _REPO_ROOT / "seed_packs" / "t02_dynamic_storefronts" / "ui"


def build_a2a_agent_card(base_url: str = "") -> dict[str, Any]:
    """Build the A2A Agent Discovery Card (/.well-known/agent.json) for Table 2."""
    clean_base = (
        base_url
        or os.environ.get("MCP_SERVER_URL", "")
        or "http://localhost:8080"
    ).rstrip("/")
    reasoning_engine = os.environ.get("AGENT_ENGINE_RESOURCE_NAME", "").strip()
    return {
        "name": "expedition_t02_dynamic_storefronts",
        "displayName": "Table 2 — Dynamic Storefront Engine (ADK + Cloud Run MCP)",
        "description": (
            "Real-time retail storefront optimization agent combining 3-table BigQuery analytics, "
            "Gemini multimodal hero lifestyle generation, interactive MCP App UI previews, "
            "deterministic 30% discount / 10% margin guardrails, and Table 1 A2A campaign sync."
        ),
        "version": "1.0.0",
        "tribe": "Creative AI & AdTech",
        "url": f"{clean_base}/a2a",
        "mcp_sse_endpoint": f"{clean_base}/sse",
        "storefront_preview_endpoint": f"{clean_base}/preview/SEG-001",
        "reasoning_engine_resource": reasoning_engine or "pending-agent-runtime-deploy",
        "capabilities": {
            "streaming": True,
            "mcp_sse": True,
            "multimodal_image_generation": True,
            "mcp_app_ui_preview": True,
            "a2a_tribe_handshake": True,
        },
        "skills": [
            {
                "id": "t02-adk-bigquery",
                "name": "BigQuery Multi-Table Storefront Optimization",
                "description": "Joins audience_segments, storefront_experiments, and products_catalog to rank high-margin SKUs and compute max safe discounts.",
                "tags": ["bigquery", "adk", "analytics", "retail"],
            },
            {
                "id": "t02-mcp-actions-a2a",
                "name": "FastMCP Storefront Actions & Table 1 Tribe A2A Sync",
                "description": "Publishes layouts, enforces <=30% discount and <=25 EUR CPM caps, and syncs creatives/bids with Table 1 (t01_campaign_orchestrator).",
                "tags": ["mcp", "a2a", "guardrails", "campaign-sync"],
            },
            {
                "id": "t02-storefront-ui-multimodal",
                "name": "Gemini Multimodal Hero Image & Interactive Storefront UI Preview",
                "description": "Generates lifestyle hero assets via GEMINI_IMAGE_MODEL and renders interactive HTML storefront preview cards.",
                "tags": ["multimodal", "gemini-image", "mcp-ui", "storefront"],
            },
            {
                "id": "t02-eval-and-deploy",
                "name": "Golden Evaluation & OpenTofu Cloud Run + Agent Registry CD",
                "description": "Validates golden trajectories and deploys MCP on Cloud Run + ADK Agent on Vertex AI Agent Runtime and Google Cloud Agent Registry.",
                "tags": ["eval", "opentofu", "cloud-run", "agent-registry"],
            },
        ],
    }


async def healthz_endpoint(request: Request) -> JSONResponse:
    """Return Cloud Run health status and registered ADK/MCP tool manifest."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        {
            "status": "ONLINE",
            "service": "t02-dynamic-storefronts-mcp",
            "seed_pack": os.environ.get("SEED_PACK", "t02"),
            "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT", "expedition-dn26lon-5922"),
            "gemini_model": os.environ.get("GEMINI_MODEL", "gemini-3.8-flash"),
            "gemini_image_model": os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image"),
            "mcp_tools": [fn.__name__ for fn in MCP_TOOLS],
            "adk_tools": [fn.__name__ for fn in ADK_TOOLS if hasattr(fn, "__name__")],
            "endpoints": {
                "healthz": f"{base_url}/healthz",
                "mcp_sse": f"{base_url}/sse",
                "mcp_messages": f"{base_url}/messages",
                "a2a_agent_card": f"{base_url}/.well-known/agent.json",
                "storefront_preview": f"{base_url}/preview/SEG-001",
            },
        }
    )


async def agent_card_endpoint(request: Request) -> JSONResponse:
    """Serve /.well-known/agent.json for A2A & Google Cloud Agent Registry discovery."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(build_a2a_agent_card(base_url=base_url))


async def storefront_preview_endpoint(request: Request) -> HTMLResponse:
    """Serve the interactive HTML storefront preview card for a given segment_id."""
    segment_id = request.path_params.get("segment_id", "SEG-001").strip() or "SEG-001"
    safe_seg = "".join(ch for ch in segment_id if ch.isalnum() or ch in ("-", "_")) or "SEG-001"

    preview_file = _UI_DIR / f"preview_{safe_seg}.html"
    tmp_file = Path(f"/tmp/t02_assets/preview_{safe_seg}.html")

    if not preview_file.exists() and not tmp_file.exists():
        raw = render_storefront_preview(
            segment_id=safe_seg,
            featured_skus="SKU-0001,SKU-0006",
            hero_headline=f"Nordic Minimal Collection — Tailored for {safe_seg}",
            theme_style="Nordic_Minimal",
            discount_pct=15,
            banner_copy="Cloud Run Live MCP Storefront Preview — 15% Off Featured Edit",
        )
        res = json.loads(raw)
        html_path = Path(res.get("preview", {}).get("html_path", ""))
        if html_path.exists():
            return HTMLResponse(html_path.read_text(encoding="utf-8"))

    target = preview_file if preview_file.exists() else tmp_file
    return HTMLResponse(target.read_text(encoding="utf-8"))


def build_mcp_cloudrun_app() -> Starlette:
    """Build the composite Starlette ASGI app combining FastMCP SSE routes and HTTP endpoints."""
    sse_starlette = mcp.sse_app()
    custom_routes = [
        Route("/", endpoint=healthz_endpoint, methods=["GET"]),
        Route("/healthz", endpoint=healthz_endpoint, methods=["GET"]),
        Route("/.well-known/agent.json", endpoint=agent_card_endpoint, methods=["GET"]),
        Route("/preview/{segment_id}", endpoint=storefront_preview_endpoint, methods=["GET"]),
    ]
    return Starlette(routes=[*custom_routes, *sse_starlette.routes])


app = build_mcp_cloudrun_app()


def main() -> None:
    """Run Uvicorn serving the Cloud Run FastMCP SSE + Storefront Preview app."""
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
