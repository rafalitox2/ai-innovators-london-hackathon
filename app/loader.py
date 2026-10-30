"""Seed Pack plugin loader for the AI Innovators Expedition Starter repo.

Loads `seed_packs/<pack_id>/pack.yaml`, imports `TOOLS` from `tools.py`, and
optionally attaches `mcp_server.py` via ADK `McpToolset` (stdio) for local runs
while falling back to plain Python function tools for Vertex AI Agent Runtime.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Any, Callable

from app.config import (
    ALLOWED_STATE_PREFIXES,
    PLACEHOLDER_MARKERS,
    STATE_TOKEN_RE,
    EnvironmentConfigResolver,
    InstructionSanitizer,
)
from app.mcp_bridge import McpBridgeFactory
from app.pack_loader import (
    LoadedSeedPack,
    SeedPackLoader,
    _tool_name,
    hello_expedition_status,
)

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_PACKS_DIR = REPO_ROOT / "seed_packs"

_STATE_TOKEN_RE = STATE_TOKEN_RE
_ALLOWED_STATE_PREFIXES = ALLOWED_STATE_PREFIXES
_PLACEHOLDER_MARKERS = PLACEHOLDER_MARKERS

_default_sanitizer = InstructionSanitizer()


def assert_no_state_tokens(instruction: str) -> None:
    """Raise ValueError if `instruction` contains raw `{...}` ADK session-state tokens."""
    _default_sanitizer.assert_no_state_tokens(instruction)


def _replace_state_token(match: re.Match[str]) -> str:
    return _default_sanitizer._replace_token(match)


def sanitize_instruction(instruction: str) -> str:
    """Replace accidental `{identifier}` tokens with `[identifier]` so ADK never crashes."""
    return _default_sanitizer.sanitize(instruction)


def is_placeholder(value: str | None) -> bool:
    """Return True for template values copied verbatim from `.env.example`."""
    return EnvironmentConfigResolver.is_placeholder(EnvironmentConfigResolver(), value)


def resolve_env_config(key: str, default: str = "") -> str:
    """Read a config key from os.environ, falling back to .env or .env.example.

    Template placeholders such as `your-gcp-project-id` are treated as unset so
    that a half-edited `.env` never sends requests to a non-existent project or
    bucket.
    """
    resolver = EnvironmentConfigResolver(repo_root=REPO_ROOT)
    return resolver.resolve_key(key, default)


def resolve_pack_directory(pack_id: str, seed_packs_dir: Path | None = None) -> Path:
    """Locate `seed_packs/<pack_id>` (exact match or `<pack_id>_*` prefix match)."""
    target_dir = seed_packs_dir if seed_packs_dir is not None else REPO_ROOT / "seed_packs"
    loader = SeedPackLoader(repo_root=REPO_ROOT)
    return loader.resolve_pack_directory(pack_id, seed_packs_dir=target_dir)


def _extract_mcp_module_functions(mcp_module_path: str) -> list[Callable[..., Any]]:
    """Import the pack's `mcp_server` module and return its explicit `MCP_TOOLS` list."""
    bridge = McpBridgeFactory(repo_root=REPO_ROOT)
    return bridge.extract_module_functions(mcp_module_path)


def _build_mcp_stdio_toolset(mcp_module_path: str) -> Any | None:
    """Create an ADK McpToolset connected to `python -m <mcp_module_path>` over stdio."""
    bridge = McpBridgeFactory(repo_root=REPO_ROOT)
    return bridge.build_stdio_toolset(mcp_module_path)


def _should_use_mcp_stdio(explicit_flag: bool | None) -> bool:
    """Determine whether to attach McpToolset (stdio) vs plain Python function tools."""
    bridge = McpBridgeFactory(repo_root=REPO_ROOT)
    return bridge.should_use_stdio(explicit_flag)


def load_seed_pack(
    pack_id: str | None = None,
    *,
    seed_packs_dir: Path | None = None,
    enable_mcp_stdio: bool | None = None,
    strict_state_tokens: bool = False,
) -> LoadedSeedPack:
    """Load a Seed Pack by ID, or return the generic fallback pack when `pack_id` is unset."""
    target_dir = seed_packs_dir if seed_packs_dir is not None else REPO_ROOT / "seed_packs"
    loader = SeedPackLoader(repo_root=REPO_ROOT)
    return loader.load(
        pack_selector=pack_id,
        seed_packs_dir=target_dir,
        enable_mcp_stdio=enable_mcp_stdio,
        strict_state_tokens=strict_state_tokens,
    )


__all__ = [
    "REPO_ROOT",
    "SEED_PACKS_DIR",
    "LoadedSeedPack",
    "EnvironmentConfigResolver",
    "InstructionSanitizer",
    "McpBridgeFactory",
    "SeedPackLoader",
    "assert_no_state_tokens",
    "sanitize_instruction",
    "is_placeholder",
    "resolve_env_config",
    "hello_expedition_status",
    "resolve_pack_directory",
    "_extract_mcp_module_functions",
    "_build_mcp_stdio_toolset",
    "_should_use_mcp_stdio",
    "load_seed_pack",
]
