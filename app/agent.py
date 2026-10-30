"""Root ADK Agent definition (`root_agent`) for the AI Innovators Expedition Starter."""

from __future__ import annotations

import logging
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent

from app.agent_builder import AdkAgentBuilder
from app.config import EnvironmentConfigResolver
from app.loader import (
    LoadedSeedPack,
    REPO_ROOT,
    assert_no_state_tokens,
    is_placeholder,
    load_seed_pack,
    resolve_env_config,
)

# Only the repo's own .env: a bare load_dotenv() walks up parent folders and can
# silently pick up an unrelated ~/.env pointing at another project.
load_dotenv(REPO_ROOT / ".env")

logger = logging.getLogger(__name__)


def _sanitize_agent_name(raw_name: str) -> str:
    return AdkAgentBuilder(repo_root=REPO_ROOT).sanitize_agent_name(raw_name)


def build_agent(
    pack_id: str | None = None,
    *,
    enable_mcp_stdio: bool | None = None,
) -> tuple[LlmAgent, LoadedSeedPack]:
    """Build the ADK `LlmAgent` and return `(agent, loaded_seed_pack)`.

    Model IDs and location are always read from environment variables or
    `.env` / `.env.example` (never hardcoded in Python code).
    """
    builder = AdkAgentBuilder(repo_root=REPO_ROOT)
    return builder.build(pack_id, enable_mcp_stdio=enable_mcp_stdio)


root_agent, active_pack = build_agent()

__all__ = [
    "AdkAgentBuilder",
    "_sanitize_agent_name",
    "build_agent",
    "root_agent",
    "active_pack",
]
