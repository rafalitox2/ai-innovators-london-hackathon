"""FastAPI HTTP Gateway for FastMCP, A2A Agent Card, and Storefront Preview."""

from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
import os
from pathlib import Path
import re
from typing import Any, Callable
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from app.loader import resolve_env_config

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TRUSTED_CLOUDRUN_HOST_RE = re.compile(r"^[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.a\.run\.app$")
_TRUSTED_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "testserver"})


class InvokeRequest(BaseModel):
    """Payload schema for invoking an MCP tool over HTTP."""

    name: str = Field(..., description="Tool function name to invoke")
    arguments: dict[str, Any] = Field(default_factory=dict, description="Named keyword arguments for the tool")


def _load_tools() -> dict[str, Callable[..., Any]]:
    """Return dictionary of tool names mapped to their callable functions."""
    from seed_packs.t02_dynamic_storefronts.mcp_server import MCP_TOOLS

    return {fn.__name__: fn for fn in MCP_TOOLS if hasattr(fn, "__name__")}


class McpCloudRunGateway:
    """Encapsulates the Cloud Run HTTP / SSE gateway, A2A discovery card, and UI preview."""

    def __init__(
        self,
        mcp_tools: list[Callable[..., Any]] | None = None,
        adk_tools: list[Any] | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self._mcp_tools = mcp_tools
        self._adk_tools = adk_tools
        self.repo_root = repo_root or _REPO_ROOT
        self.ui_dir = self.repo_root / "seed_packs" / "t02_dynamic_storefronts" / "ui"

    @property
    def mcp_tools(self) -> list[Callable[..., Any]]:
        if self._mcp_tools is not None:
            return self._mcp_tools
        from seed_packs.t02_dynamic_storefronts.mcp_server import MCP_TOOLS

        return MCP_TOOLS

    @property
    def adk_tools(self) -> list[Any]:
        if self._adk_tools is not None:
            return self._adk_tools
        from seed_packs.t02_dynamic_storefronts.tools import TOOLS

        return TOOLS

    def list_tools(self) -> list[dict[str, Any]]:
        """Return introspection schemas for all registered MCP tools."""
        manifest: list[dict[str, Any]] = []
        for fn in self.mcp_tools:
            name = getattr(fn, "__name__", str(fn))
            doc = inspect.getdoc(fn) or ""
            sig = inspect.signature(fn)
            params = {
                k: {
                    "type": str(v.annotation if v.annotation != inspect.Parameter.empty else "Any"),
                    "default": str(v.default if v.default != inspect.Parameter.empty else "REQUIRED"),
                }
                for k, v in sig.parameters.items()
            }
            manifest.append({
                "name": name,
                "description": doc.split("\n\n")[0] if doc else "",
                "parameters": params,
            })
        return manifest

    def invoke_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Invoke a registered MCP tool by name."""
        tools_map = {getattr(fn, "__name__", ""): fn for fn in self.mcp_tools}
        if tool_name not in tools_map:
            raise ValueError(f"Tool '{tool_name}' not found. Available: {list(tools_map.keys())}")
        fn = tools_map[tool_name]
        return fn(**(arguments or {}))

    def resolve_public_base_url(self, request: Request) -> str:
        """Resolve external HTTPS base URL behind Cloud Run GFE proxy."""
        env_url = os.environ.get("MCP_SERVER_URL", "").strip().rstrip("/")
        if env_url:
            return env_url
        hostname = (request.url.hostname or "").lower()
        if hostname not in _TRUSTED_LOCAL_HOSTS and not _TRUSTED_CLOUDRUN_HOST_RE.match(hostname):
            return "http://localhost:8080"
        base_url = str(request.base_url).rstrip("/")
        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        if (forwarded_proto == "https" or ".a.run.app" in base_url) and base_url.startswith("http://"):
            base_url = "https://" + base_url[len("http://") :]
        return base_url

    def resolve_reasoning_engine_resource(self) -> str:
        """Resolve the active Vertex AI ReasoningEngine resource name from env or state files."""
        from_env = os.environ.get("AGENT_ENGINE_RESOURCE_NAME", "").strip()
        if from_env:
            return from_env
        deployed_file = self.repo_root / ".deployed_agent.json"
        if deployed_file.exists():
            try:
                resource = str(json.loads(deployed_file.read_text(encoding="utf-8")).get("resource_name", "")).strip()
                if resource:
                    return resource
            except Exception:
                pass
        cd_state_file = self.repo_root / "cd" / "cd_deployment_state.json"
        if cd_state_file.exists():
            try:
                resource = str(
                    json.loads(cd_state_file.read_text(encoding="utf-8")).get("vertex_ai_reasoning_engine", "")
                ).strip()
                if resource:
                    return resource
            except Exception:
                pass
        return "projects/633924037012/locations/europe-west1/reasoningEngines/5876565294532526080"

    def build_a2a_agent_card(self, base_url: str = "") -> dict[str, Any]:
        """Build the A2A Agent Discovery Card (/.well-known/agent.json) for Table 2."""
        clean_base = (
            base_url
            or os.environ.get("MCP_SERVER_URL", "")
            or "http://localhost:8080"
        ).rstrip("/")
        if ".a.run.app" in clean_base and clean_base.startswith("http://"):
            clean_base = "https://" + clean_base[len("http://") :]
        reasoning_engine = self.resolve_reasoning_engine_resource()
        return {
            "name": "expedition_t02_dynamic_storefronts",
            "displayName": "Table 2 — Dynamic Storefront Engine (ADK + Cloud Run MCP)",
            "description": (
                "Real-time retail storefront optimization agent combining 3-table BigQuery analytics, "
                "Gemini multimodal hero lifestyle generation, interactive MCP App UI previews, "
                "deterministic 30% discount / 10% margin guardrails, and Table 1 A2A campaign sync."
            ),
            "version": "1.0.0",
            "protocolVersion": "0.2.5",
            "tribe": "Creative AI & AdTech",
            "url": f"{clean_base}/a2a",
            "supportedInterfaces": [
                {
                    "url": f"{clean_base}/a2a",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": "1.0",
                }
            ],
            "defaultInputModes": ["text", "text/plain", "application/json"],
            "defaultOutputModes": ["text", "text/plain", "application/json"],
            "mcp_sse_endpoint": f"{clean_base}/sse",
            "a2a_sync_endpoint": f"{clean_base}/api/a2a/sync",
            "storefront_preview_endpoint": f"{clean_base}/preview/SEG-001",
            "reasoning_engine_resource": reasoning_engine,
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
                    "tags": ["multimodal", "image-generation", "mcp-ui", "storefront"],
                },
                {
                    "id": "t02-eval-and-deploy",
                    "name": "Golden Evaluation & GitHub Actions Cloud Run + Agent Registry CD",
                    "description": "Validates golden trajectories and deploys MCP on Cloud Run + ADK Agent on Vertex AI Agent Runtime and Google Cloud Agent Registry.",
                    "tags": ["eval", "github-actions", "cloud-run", "agent-registry"],
                },
            ],
        }

    @staticmethod
    def extract_a2a_text(params: dict[str, Any]) -> str:
        """Extract plain text from an A2A JSON-RPC message/send or tasks/send params object."""
        msg = params.get("message") or {}
        if isinstance(msg, dict):
            parts = msg.get("parts") or []
            texts: list[str] = []
            for part in parts:
                if isinstance(part, dict):
                    if part.get("text"):
                        texts.append(str(part["text"]))
                    elif part.get("data"):
                        texts.append(json.dumps(part["data"]))
            if texts:
                return "\n".join(texts)
        for key in ("text", "prompt", "query", "input"):
            if params.get(key):
                return str(params[key])
        return ""

    async def handle_a2a(self, request: Request) -> JSONResponse:
        """Handle A2A Discovery (GET /a2a), A2A JSON-RPC 2.0 (POST /a2a), and Tribe A2A Handshake payloads."""
        from app.ui_server import _run_adk_or_fallback_chat
        from seed_packs.t02_dynamic_storefronts.mcp_server import sync_campaign_with_t01

        base_url = self.resolve_public_base_url(request)
        if request.method == "GET":
            return JSONResponse(self.build_a2a_agent_card(base_url=base_url))

        try:
            raw_bytes = await request.body()
            body: dict[str, Any] = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
        except Exception:
            return JSONResponse(
                {"status": "ERROR", "error": "Invalid JSON payload"},
                status_code=400,
            )

        # 1. Standard A2A JSON-RPC 2.0 envelope (e.g. google-adk RemoteA2aAgent / a2a-sdk)
        if isinstance(body, dict) and "jsonrpc" in body:
            rpc_id = body.get("id", "a2a-1")
            method = str(body.get("method") or "message/send")
            params = body.get("params") if isinstance(body.get("params"), dict) else {}

            if method in ("agent/authenticatedExtendedCard", "agent/card", "agent.getCard"):
                return JSONResponse(
                    {
                        "jsonrpc": "2.0",
                        "id": rpc_id,
                        "result": self.build_a2a_agent_card(base_url=base_url),
                    }
                )

            text_query = self.extract_a2a_text(params) or "Optimize storefront and synchronize campaign with Table 1"
            context_id = str(
                params.get("contextId")
                or (params.get("message") or {}).get("contextId")
                or params.get("sessionId")
                or "a2a-t01-t02-session"
            )
            chat_res = await _run_adk_or_fallback_chat(
                message=text_query,
                session_id=context_id,
                user_id="a2a-peer-agent",
            )
            reply_text = str(chat_res.get("reply") or "")
            msg_id = f"msg-{uuid.uuid4().hex[:12]}"
            task_id = str(params.get("id") or f"task-{uuid.uuid4().hex[:12]}")
            agent_msg = {
                "kind": "message",
                "messageId": msg_id,
                "role": "agent",
                "contextId": context_id,
                "parts": [{"kind": "text", "text": reply_text}],
            }
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "kind": "task",
                        "id": task_id,
                        "contextId": context_id,
                        "status": {
                            "state": "completed",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "message": agent_msg,
                        },
                        "artifacts": [
                            {
                                "artifactId": f"art-{uuid.uuid4().hex[:8]}",
                                "name": "storefront_a2a_response",
                                "parts": [{"kind": "text", "text": reply_text}],
                            }
                        ],
                        "message": agent_msg,
                        "tool_calls": chat_res.get("tool_calls", []),
                        "tool_outputs": chat_res.get("tool_outputs", {}),
                    },
                }
            )

        # 2. Direct prompt / natural-language A2A message
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

        # 3. Structured Tribe A2A Handshake (STOREFRONT_TO_CAMPAIGN_SYNC / CAMPAIGN_TO_STOREFRONT_SYNC)
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
        sync_res = json.loads(sync_raw)
        return JSONResponse(sync_res)

    def build_fastapi_app(self) -> FastAPI:
        """Build composite FastAPI/Starlette ASGI app combining Nocturne React UI, ADK APIs, and FastMCP SSE."""
        from app.ui_server import UI_DIST_DIR, register_ui_routes
        from seed_packs.t02_dynamic_storefronts.mcp_server import (
            mcp as fastmcp_server,
            render_storefront_preview,
        )

        cloud_app = FastAPI(
            title="AtelierNova Dynamic Storefronts — Cloud Run UI + FastMCP + ADK Server",
            version="1.0.0",
        )
        raw_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
        allowed_origins = (
            [o.strip() for o in raw_origins.split(",") if o.strip()]
            if raw_origins
            else [
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "http://localhost:8080",
                "http://127.0.0.1:8080",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ]
        )
        cloud_app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials="*" not in allowed_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )

        @cloud_app.middleware("http")
        async def _add_security_headers(request: Request, call_next: Any) -> Response:
            response = await call_next(request)
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
            response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
            content_type = response.headers.get("content-type", "").lower()
            if "image/svg+xml" in content_type:
                response.headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; sandbox",
                )
            return response
        register_ui_routes(cloud_app)

        gateway = self

        async def healthz_handler(request: Request) -> JSONResponse:
            base_url = gateway.resolve_public_base_url(request)
            return JSONResponse({
                "status": "ONLINE",
                "service": "t02-dynamic-storefronts-mcp",
                "seed_pack": resolve_env_config("SEED_PACK", default="t02"),
                "project_id": resolve_env_config("GOOGLE_CLOUD_PROJECT", default="expedition-dn26lon-5922"),
                "gemini_model": resolve_env_config("GEMINI_MODEL"),
                "gemini_image_model": resolve_env_config("GEMINI_IMAGE_MODEL"),
                "reasoning_engine_resource": gateway.resolve_reasoning_engine_resource(),
                "mcp_tools": [fn.__name__ for fn in gateway.mcp_tools],
                "adk_tools": [fn.__name__ for fn in gateway.adk_tools if hasattr(fn, "__name__")],
                "endpoints": {
                    "nocturne_ui": f"{base_url}/ui",
                    "health": f"{base_url}/health",
                    "healthz": f"{base_url}/healthz",
                    "api_health": f"{base_url}/api/health",
                    "api_dashboard": f"{base_url}/api/dashboard",
                    "mcp_sse": f"{base_url}/sse",
                    "mcp_messages": f"{base_url}/messages",
                    "a2a_endpoint": f"{base_url}/a2a",
                    "a2a_sync": f"{base_url}/api/a2a/sync",
                    "a2a_agent_card": f"{base_url}/.well-known/agent.json",
                    "a2a_agent_card_v2": f"{base_url}/.well-known/agent-card.json",
                    "storefront_preview": f"{base_url}/preview/SEG-001",
                    "tools": f"{base_url}/tools",
                    "invoke": f"{base_url}/invoke",
                },
            })

        async def root_ui_or_health_handler(request: Request) -> Response:
            index_file = UI_DIST_DIR / "index.html"
            if index_file.exists():
                return HTMLResponse(index_file.read_text(encoding="utf-8"))
            return await healthz_handler(request)

        async def agent_card_handler(request: Request) -> JSONResponse:
            base_url = gateway.resolve_public_base_url(request)
            return JSONResponse(gateway.build_a2a_agent_card(base_url=base_url))

        async def preview_handler(request: Request) -> HTMLResponse:
            segment_id = request.path_params.get("segment_id", "SEG-001").strip() or "SEG-001"
            safe_seg = "".join(ch for ch in segment_id if ch.isalnum() or ch in ("-", "_")) or "SEG-001"

            preview_file = gateway.ui_dir / f"preview_{safe_seg}.html"
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

        async def list_tools_handler(request: Request) -> JSONResponse:
            return JSONResponse({"tools": gateway.list_tools()})

        async def invoke_tool_handler(req: InvokeRequest) -> JSONResponse:
            try:
                res = gateway.invoke_tool(req.name, req.arguments)
                return JSONResponse({"status": "SUCCESS", "result": res})
            except Exception as exc:
                return JSONResponse({"status": "ERROR", "error": str(exc)}, status_code=400)

        cloud_app.add_route("/", root_ui_or_health_handler, methods=["GET"])
        cloud_app.add_route("/health", healthz_handler, methods=["GET"])
        cloud_app.add_route("/healthz", healthz_handler, methods=["GET"])
        cloud_app.add_route("/.well-known/agent.json", agent_card_handler, methods=["GET"])
        cloud_app.add_route("/.well-known/agent-card.json", agent_card_handler, methods=["GET"])
        cloud_app.add_route("/a2a/.well-known/agent.json", agent_card_handler, methods=["GET"])
        cloud_app.add_route("/a2a/.well-known/agent-card.json", agent_card_handler, methods=["GET"])
        cloud_app.add_route("/a2a", gateway.handle_a2a, methods=["GET", "POST"])
        cloud_app.add_route("/a2a/", gateway.handle_a2a, methods=["GET", "POST"])
        cloud_app.add_route("/preview/{segment_id}", preview_handler, methods=["GET"])
        cloud_app.add_route("/tools", list_tools_handler, methods=["GET"])
        cloud_app.add_api_route("/invoke", invoke_tool_handler, methods=["POST"])

        sse_starlette = fastmcp_server.sse_app()
        for route in sse_starlette.routes:
            cloud_app.router.routes.append(route)

        return cloud_app
