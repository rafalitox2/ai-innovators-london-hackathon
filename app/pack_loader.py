"""Seed Pack plugin loader and configuration resolver for ADK agents."""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

import yaml

from app.config import EnvironmentConfigResolver, InstructionSanitizer
from app.mcp_bridge import McpBridgeFactory

logger = logging.getLogger(__name__)


def _tool_name(tool_obj: Any) -> str | None:
    if callable(tool_obj):
        try:
            return str(tool_obj.__name__)
        except AttributeError:
            return None
    return None


def hello_expedition_status(
    table_name: str = "Unassigned Table",
    query: str = "ping",
) -> str:
    """Return a status check for the AI Innovators Expedition Starter agent when no Seed Pack is set.

    Args:
        table_name: Name or number of the hackathon Table (e.g., 'Table 8').
        query: Optional status query probe.

    Returns:
        JSON string confirming the Starter agent is online and explaining how to activate a Seed Pack.
    """
    try:
        project = (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("AGENT_ENGINE_PROJECT")
            or "unset"
        )
        return json.dumps({
            "status": "ONLINE",
            "mode": "hello_fallback",
            "table_name": table_name,
            "project": project,
            "hint": "Set SEED_PACK=t01..t10 (or t00_example) in .env and run `make seed PACK=<id>`.",
        })
    except Exception as exc:
        return json.dumps({"status": "ERROR", "error": str(exc)})


@dataclass
class LoadedSeedPack:
    """Resolved Seed Pack configuration and assembled ADK tool list."""

    pack_id: str
    table: int | str | None
    title: str
    tribe: str
    short_description: str
    instruction: str
    bigquery_dataset: str | None
    gcs_prefix: str | None
    mcp_server: str | None
    pack_dir: Path | None
    tools: list[Any] = field(default_factory=list)
    mcp_stdio_attached: bool = False
    before_model_callback: Any = None
    before_tool_callback: Any = None
    after_tool_callback: Any = None
    after_model_callback: Any = None


class SeedPackLoader:
    """Object-Oriented loader that resolves, inspects, and binds Seed Pack plugins."""

    def __init__(
        self,
        repo_root: Path | None = None,
        config_resolver: EnvironmentConfigResolver | None = None,
        mcp_bridge: McpBridgeFactory | None = None,
        sanitizer: InstructionSanitizer | None = None,
    ) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parent.parent
        self.config_resolver = config_resolver or EnvironmentConfigResolver(self.repo_root)
        self.mcp_bridge = mcp_bridge or McpBridgeFactory(self.repo_root)
        self.sanitizer = sanitizer or InstructionSanitizer()

    @property
    def seed_packs_dir(self) -> Path:
        return self.repo_root / "seed_packs"

    def resolve_pack_directory(
        self,
        pack_selector: str | None = None,
        seed_packs_dir: Path | None = None,
    ) -> Path:
        """Locate `seed_packs/<pack_selector>` (exact match or `<pack_selector>_*` prefix match)."""
        clean_id = (
            pack_selector if pack_selector is not None else os.environ.get("SEED_PACK", "")
        ).strip()
        target_packs_dir = seed_packs_dir or self.seed_packs_dir

        if not clean_id:
            raise ValueError("Seed Pack selector cannot be empty.")

        exact = target_packs_dir / clean_id
        if exact.is_dir() and (exact / "pack.yaml").exists():
            return exact

        matches = sorted(
            p for p in target_packs_dir.glob(f"{clean_id}_*")
            if p.is_dir() and (p / "pack.yaml").exists()
        )
        if matches:
            return matches[0]

        raise FileNotFoundError(
            f"Seed Pack '{clean_id}' not found under {target_packs_dir}. "
            f"Expected '{exact / 'pack.yaml'}' or '{clean_id}_*/pack.yaml'."
        )

    def build_fallback_pack(self, selector: str = "hello_fallback") -> LoadedSeedPack:
        """Return the generic fallback starter pack when no Seed Pack is activated."""
        fallback_instruction = (
            "You are the AI Innovators Expedition Starter Agent running in fallback mode "
            "(no SEED_PACK selected). Use `hello_expedition_status` to check system readiness "
            "and guide the user to configure SEED_PACK in their .env file."
        )
        return LoadedSeedPack(
            pack_id="hello_fallback",
            table=0,
            title="AI Innovators Expedition — Hello Starter Agent",
            tribe="Common Starter",
            short_description="Fallback starter agent used when SEED_PACK is unset.",
            instruction=fallback_instruction,
            bigquery_dataset=None,
            gcs_prefix=None,
            mcp_server=None,
            pack_dir=None,
            tools=[hello_expedition_status],
            mcp_stdio_attached=False,
        )

    def load(
        self,
        pack_selector: str | None = None,
        *,
        seed_packs_dir: Path | None = None,
        enable_mcp_stdio: bool | None = None,
        strict_state_tokens: bool = False,
    ) -> LoadedSeedPack:
        """Load a Seed Pack by ID, or return the generic fallback pack when unset."""
        resolved_id = (
            pack_selector if pack_selector is not None else os.environ.get("SEED_PACK", "")
        ).strip()

        if not resolved_id or resolved_id.lower() in {"none", "null", "hello"}:
            return self.build_fallback_pack(resolved_id or "hello_fallback")

        target_packs_dir = seed_packs_dir or self.seed_packs_dir
        pack_dir = self.resolve_pack_directory(resolved_id, seed_packs_dir=target_packs_dir)
        yaml_path = pack_dir / "pack.yaml"
        raw_cfg: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}

        raw_instruction = str(raw_cfg.get("instruction") or "").strip()
        if strict_state_tokens:
            self.sanitizer.assert_no_state_tokens(raw_instruction)
        safe_instruction = self.sanitizer.sanitize(raw_instruction)

        bq_dataset = raw_cfg.get("bigquery_dataset")
        if bq_dataset:
            os.environ.setdefault("SEED_BQ_DATASET", str(bq_dataset).strip())

        # Import TOOLS from seed_packs.<dir_name>.tools
        module_prefix = f"seed_packs.{pack_dir.name}"
        tools_mod = importlib.import_module(f"{module_prefix}.tools")
        raw_tools = list(vars(tools_mod).get("TOOLS", []))
        pack_before_model_callback = vars(tools_mod).get("BEFORE_MODEL_CALLBACK")
        pack_before_tool_callback = vars(tools_mod).get("BEFORE_TOOL_CALLBACK")
        pack_after_tool_callback = vars(tools_mod).get("AFTER_TOOL_CALLBACK")
        pack_after_model_callback = vars(tools_mod).get("AFTER_MODEL_CALLBACK")

        mcp_server_mod = raw_cfg.get("mcp_server")
        mcp_server_str = str(mcp_server_mod).strip() if mcp_server_mod else None
        mcp_funcs = (
            self.mcp_bridge.extract_module_functions(mcp_server_str, pack_name=pack_dir.name)
            if mcp_server_str
            else []
        )
        mcp_func_names = {fn.__name__ for fn in mcp_funcs}

        use_stdio = self.mcp_bridge.should_use_stdio(enable_mcp_stdio)
        final_tools: list[Any] = []
        mcp_attached = False

        if mcp_server_str and use_stdio:
            mcp_toolset = self.mcp_bridge.build_stdio_toolset(mcp_server_str)
            if mcp_toolset is not None:
                # Avoid duplicate FunctionDeclaration names when tools.py also re-exports MCP functions
                final_tools = [
                    fn for fn in raw_tools
                    if _tool_name(fn) not in mcp_func_names
                ]
                final_tools.append(mcp_toolset)
                mcp_attached = True

        if not mcp_attached:
            # Plain function mode (Agent Runtime or fallback): ensure all MCP functions are present
            existing_names = {_tool_name(fn) for fn in raw_tools}
            final_tools = list(raw_tools)
            for fn in mcp_funcs:
                if fn.__name__ not in existing_names:
                    final_tools.append(fn)

        return LoadedSeedPack(
            pack_id=str(raw_cfg.get("id") or pack_dir.name),
            table=raw_cfg.get("table"),
            title=str(raw_cfg.get("title") or pack_dir.name),
            tribe=str(raw_cfg.get("tribe") or ""),
            short_description=str(raw_cfg.get("short_description") or ""),
            instruction=safe_instruction,
            bigquery_dataset=str(bq_dataset) if bq_dataset else None,
            gcs_prefix=str(raw_cfg.get("gcs_prefix")) if raw_cfg.get("gcs_prefix") else None,
            mcp_server=mcp_server_str,
            pack_dir=pack_dir,
            tools=final_tools,
            mcp_stdio_attached=mcp_attached,
            before_model_callback=pack_before_model_callback,
            before_tool_callback=pack_before_tool_callback,
            after_tool_callback=pack_after_tool_callback,
            after_model_callback=pack_after_model_callback,
        )
