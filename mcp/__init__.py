"""Unified MCP package bridging the official MCP SDK and Table 2 OOP MCP services."""

from __future__ import annotations

import pathlib
import sys
from typing import Any

_THIS_DIR = pathlib.Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent

# 1. Extend __path__ with installed site-packages 'mcp' so submodules like
#    `from mcp.server.fastmcp import FastMCP` resolve seamlessly.
for _sys_p in sys.path:
    try:
        _candidate = pathlib.Path(_sys_p).resolve()
    except Exception:
        continue
    if _candidate == _REPO_ROOT:
        continue
    _sdk_mcp_dir = _candidate / "mcp"
    _sdk_init = _sdk_mcp_dir / "__init__.py"
    if _sdk_init.is_file() and str(_sdk_mcp_dir) not in __path__:
        __path__.append(str(_sdk_mcp_dir))
        _sdk_code = compile(_sdk_init.read_text(encoding="utf-8"), str(_sdk_init), "exec")
        exec(_sdk_code, globals())
        break

# 2. Re-export Table 2 OOP MCP Architecture classes
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


def __getattr__(name: str) -> Any:
    if name == "McpCloudRunGateway":
        from mcp.http_gateway import McpCloudRunGateway

        return McpCloudRunGateway
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CatalogCsvRepository",
    "McpStateStore",
    "StorefrontActionService",
    "MultimodalHeroService",
    "TribeA2ASyncService",
    "MerchandisingMemoryService",
    "EnterpriseOrchestrationService",
    "T02McpController",
    "McpCloudRunGateway",
]
