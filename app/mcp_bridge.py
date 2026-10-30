"""MCP bridge factory for connecting ADK agents to Seed Pack FastMCP servers."""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path
import sys
from typing import Any, Callable

logger = logging.getLogger(__name__)


class McpBridgeFactory:
    """Factory for inspecting Seed Pack MCP modules and building ADK McpToolset bridges."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parent.parent

    def extract_module_functions(
        self,
        mcp_module_path: str | Path,
        pack_name: str = "",
    ) -> list[Callable[..., Any]]:
        """Import the pack's `mcp_server` module and return its explicit `MCP_TOOLS` list.

        Seed Pack contract: every `mcp_server.py` exports `MCP_TOOLS = [fn, ...]`
        (the same functions decorated with `@mcp.tool()`). Only this public list is
        used; FastMCP internals are never inspected, so MCP SDK upgrades cannot
        silently drop tools.

        Raises:
            ImportError: if the module declared in `pack.yaml` cannot be imported.
        """
        mod_str = str(mcp_module_path)
        try:
            mod = importlib.import_module(mod_str)
        except Exception as exc:
            pack_ctx = f" for '{pack_name}'" if pack_name else ""
            raise ImportError(
                f"pack.yaml declares mcp_server '{mod_str}'{pack_ctx} but it failed to import "
                f"({type(exc).__name__}: {exc}). Fix the module or remove `mcp_server` from pack.yaml."
            ) from exc

        explicit = vars(mod).get("MCP_TOOLS")
        if isinstance(explicit, (list, tuple)) and explicit:
            return [fn for fn in explicit if callable(fn)]

        logger.warning(
            "mcp_server '%s' does not export a non-empty MCP_TOOLS list; its mock actions "
            "will NOT be available in Agent Runtime or `make eval`. Add "
            "`MCP_TOOLS = [your_tool, ...]` at the bottom of mcp_server.py.",
            mod_str,
        )
        return []

    def build_stdio_toolset(self, mcp_module_path: str | Path) -> Any | None:
        """Create an ADK McpToolset connected to `python -m <mcp_module_path>` over stdio."""
        mod_str = str(mcp_module_path)
        try:
            from google.adk.tools.mcp_tool import McpToolset
            from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
            from mcp import StdioServerParameters

            env = dict(os.environ)
            python_path = str(self.repo_root)
            if env.get("PYTHONPATH"):
                python_path = f"{python_path}{os.pathsep}{env['PYTHONPATH']}"
            env["PYTHONPATH"] = python_path

            return McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command=sys.executable,
                        args=["-m", mod_str],
                        env=env,
                    ),
                    timeout=30.0,
                )
            )
        except Exception as exc:
            logger.warning(
                "Optional MCP stdio toolset for '%s' could not be initialized (%s); "
                "falling back to plain Python function tools.",
                mod_str,
                exc,
            )
            return None

    def should_use_stdio(self, explicit_flag: bool | None = None) -> bool:
        """Determine whether to attach McpToolset (stdio) vs plain Python function tools.

        Inside Vertex AI Agent Runtime containers (or during `deploy/deploy.py`
        packaging where `ENABLE_MCP_STDIO=0`), stdio subprocesses are disabled and
        mock actions run as direct Python function tools.
        """
        if explicit_flag is not None:
            return explicit_flag
        env_flag = os.environ.get("ENABLE_MCP_STDIO", "").strip().lower()
        if env_flag in {"0", "false", "no", "off"}:
            return False
        if env_flag in {"1", "true", "yes", "on"}:
            return True
        # Detect cloud container runtime environments where workstation sys.executable is invalid
        if os.environ.get("AGENT_RUNTIME_DEPLOY") == "1" or os.environ.get("K_SERVICE"):
            return False
        return True
