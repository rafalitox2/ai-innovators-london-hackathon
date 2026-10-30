"""Cloud Run ASGI server for Table 2 FastMCP Server + A2A Agent Card + Live Storefront UI Preview."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
import uvicorn

from app.loader import resolve_env_config
from mcp.http_gateway import (
    InvokeRequest,
    McpCloudRunGateway,
    _load_tools,
)

_gateway = McpCloudRunGateway()


def _resolve_public_base_url(request: Request) -> str:
    """Resolve external HTTPS base URL behind Cloud Run GFE proxy."""
    return _gateway.resolve_public_base_url(request)


def _resolve_reasoning_engine_resource() -> str:
    """Resolve the active Vertex AI ReasoningEngine resource name from env or state files."""
    return _gateway.resolve_reasoning_engine_resource()


def build_a2a_agent_card(base_url: str = "") -> dict[str, Any]:
    """Build the A2A Agent Discovery Card (/.well-known/agent.json) for Table 2."""
    return _gateway.build_a2a_agent_card(base_url=base_url)


async def healthz_endpoint(request: Request) -> JSONResponse:
    """Return Cloud Run health status and registered ADK/MCP tool manifest."""
    base_url = _gateway.resolve_public_base_url(request)
    return JSONResponse(
        {
            "status": "ONLINE",
            "service": "t02-dynamic-storefronts-mcp",
            "seed_pack": resolve_env_config("SEED_PACK", default="t02"),
            "project_id": resolve_env_config("GOOGLE_CLOUD_PROJECT", default="expedition-dn26lon-5922"),
            "gemini_model": resolve_env_config("GEMINI_MODEL"),
            "gemini_image_model": resolve_env_config("GEMINI_IMAGE_MODEL"),
            "reasoning_engine_resource": _gateway.resolve_reasoning_engine_resource(),
            "mcp_tools": [fn.__name__ for fn in _gateway.mcp_tools],
            "adk_tools": [fn.__name__ for fn in _gateway.adk_tools if hasattr(fn, "__name__")],
            "endpoints": {
                "nocturne_ui": f"{base_url}/ui",
                "executive_slides": f"{base_url}/slides",
                "health": f"{base_url}/health",
                "healthz": f"{base_url}/healthz",
                "api_health": f"{base_url}/api/health",
                "api_dashboard": f"{base_url}/api/dashboard",
                "mcp_sse": f"{base_url}/sse",
                "mcp_messages": f"{base_url}/messages",
                "a2a_agent_card": f"{base_url}/.well-known/agent.json",
                "storefront_preview": f"{base_url}/preview/SEG-001",
                "tools": f"{base_url}/tools",
                "invoke": f"{base_url}/invoke",
            },
        }
    )


async def root_ui_or_health_endpoint(request: Request) -> Response:
    """Serve the compiled Nocturne React SPA at / when ui/dist/index.html is present."""
    from app.ui_server import UI_DIST_DIR

    index_file = UI_DIST_DIR / "index.html"
    if index_file.exists():
        return HTMLResponse(index_file.read_text(encoding="utf-8"))
    return await healthz_endpoint(request)


async def agent_card_endpoint(request: Request) -> JSONResponse:
    """Serve /.well-known/agent.json and /.well-known/agent-card.json for A2A & Google Cloud Agent Registry discovery."""
    base_url = _gateway.resolve_public_base_url(request)
    return JSONResponse(_gateway.build_a2a_agent_card(base_url=base_url))


async def a2a_endpoint(request: Request) -> JSONResponse:
    """Handle A2A Discovery (GET /a2a), A2A JSON-RPC 2.0 (POST /a2a), and Tribe A2A Handshake payloads."""
    return await _gateway.handle_a2a(request)


async def storefront_preview_endpoint(request: Request) -> HTMLResponse:
    """Serve the interactive HTML storefront preview card for a given segment_id."""
    import json
    from seed_packs.t02_dynamic_storefronts.mcp_server import render_storefront_preview

    segment_id = request.path_params.get("segment_id", "SEG-001").strip() or "SEG-001"
    safe_seg = "".join(ch for ch in segment_id if ch.isalnum() or ch in ("-", "_")) or "SEG-001"

    preview_file = _gateway.ui_dir / f"preview_{safe_seg}.html"
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


def build_mcp_cloudrun_app() -> FastAPI:
    """Build composite FastAPI/Starlette ASGI app using McpCloudRunGateway."""
    return _gateway.build_fastapi_app()


app = build_mcp_cloudrun_app()


def main() -> None:
    """Run Uvicorn serving the Cloud Run FastMCP SSE + Storefront Preview app."""
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
