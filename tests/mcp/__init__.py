"""Automated test suite for Table 2 Official FastMCP SDK, OOP Services, and Cloud Run Gateway."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent.parent
_REPO_MCP = _REPO_ROOT / "mcp"
_SP_MCP = (
    Path(sys.prefix)
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
    / "mcp"
)

# 1. Extend __path__ so submodules in repo root mcp (e.g. mcp.http_gateway)
# and official SDK (e.g. mcp.server.fastmcp) are resolvable:
if _REPO_MCP.is_dir() and str(_REPO_MCP) not in __path__:
    __path__.append(str(_REPO_MCP))
if _SP_MCP.is_dir() and str(_SP_MCP) not in __path__:
    __path__.append(str(_SP_MCP))

# 2. Re-export all symbols from site-packages mcp (types, ClientSession, StdioServerParameters, etc.)
if _SP_MCP.is_dir():
    _sp_init = _SP_MCP / "__init__.py"
    if _sp_init.is_file():
        _sp_code = compile(_sp_init.read_text(encoding="utf-8"), str(_sp_init), "exec")
        exec(_sp_code, globals())

# 3. Re-export Table 2 OOP MCP architecture symbols from seed pack / root mcp
from seed_packs.t02_dynamic_storefronts.mcp import (
    CatalogCsvRepository,
    EnterpriseOrchestrationService,
    McpStateStore,
    MerchandisingMemoryService,
    MultimodalHeroService,
    StorefrontActionService,
    T02McpController,
    TribeA2ASyncService,
)

try:
    from mcp.server.fastmcp import FastMCP
except Exception:
    FastMCP = Any  # type: ignore[assignment,misc]


def __getattr__(name: str) -> Any:
    if name == "McpCloudRunGateway":
        from mcp.http_gateway import McpCloudRunGateway

        return McpCloudRunGateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
