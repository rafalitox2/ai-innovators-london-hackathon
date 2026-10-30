"""Environment and instruction configuration resolution for the AI Innovators Expedition."""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, overload

# Regex to catch accidental `{identifier}` tokens in ADK instructions, which ADK
# interprets as session-state lookups (raising KeyError and blanking the reply).
STATE_TOKEN_RE = re.compile(r"{+[^{}]*}+")
ALLOWED_STATE_PREFIXES = ("{app:", "{user:", "{temp:")

PLACEHOLDER_MARKERS = ("your-gcp-project-id", "your-project-id")


class InstructionSanitizer:
    """Validates and sanitizes prompt instructions to prevent ADK session-state errors."""

    def __init__(
        self,
        token_pattern: re.Pattern[str] = STATE_TOKEN_RE,
        allowed_prefixes: tuple[str, ...] = ALLOWED_STATE_PREFIXES,
    ) -> None:
        self.token_pattern = token_pattern
        self.allowed_prefixes = allowed_prefixes

    def assert_no_state_tokens(self, text: str, source: str = "instruction") -> None:
        """Raise ValueError if `text` contains raw `{...}` ADK session-state tokens."""
        bad = [
            tok
            for tok in self.token_pattern.findall(text or "")
            if not tok.startswith(self.allowed_prefixes)
        ]
        if bad:
            prefix = f"{source.capitalize()} contains" if source != "instruction" else "Instruction contains"
            raise ValueError(
                f"{prefix} unescaped ADK session-state tokens {bad[:5]}. "
                "Remove curly braces or use square brackets instead."
            )

    def _replace_token(self, match: re.Match[str]) -> str:
        tok = match.group(0)
        if tok.startswith(self.allowed_prefixes):
            return tok
        inner = tok.strip("{}")
        return f"[{inner}]"

    def sanitize(self, text: str) -> str:
        """Replace accidental `{identifier}` tokens with `[identifier]` so ADK never crashes."""
        return self.token_pattern.sub(self._replace_token, text or "")


class EnvironmentConfigResolver:
    """Resolves runtime configuration from os.environ, falling back to repo .env files."""

    def __init__(
        self,
        repo_root: Path | None = None,
        placeholder_markers: tuple[str, ...] = PLACEHOLDER_MARKERS,
    ) -> None:
        self.repo_root = repo_root or Path(__file__).resolve().parent.parent
        self.placeholder_markers = placeholder_markers

    def is_placeholder(self, value: str | None) -> bool:
        """Return True for template values copied verbatim from `.env.example`."""
        lowered = (value or "").strip().lower()
        return any(marker in lowered for marker in self.placeholder_markers)

    def load_dotenv_if_present(self) -> None:
        """Load repo-local `.env` file if it exists."""
        from dotenv import load_dotenv

        env_path = self.repo_root / ".env"
        if env_path.exists():
            load_dotenv(env_path)

    def resolve_key(self, key: str, default: str = "") -> str:
        """Read a single config key from os.environ, falling back to .env or .env.example."""
        val = os.environ.get(key, "").strip()
        if val and not self.is_placeholder(val):
            return val
        for env_file in (self.repo_root / ".env", self.repo_root / ".env.example"):
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    k, v = stripped.split("=", 1)
                    if k.strip() == key:
                        parsed = v.strip().strip("'").strip('"')
                        if parsed and not self.is_placeholder(parsed):
                            return parsed
        return default

    def resolve_all(self, overrides: dict[str, str] | None = None) -> dict[str, str]:
        """Resolve a full dictionary of standard environment configuration keys."""
        standard_keys = (
            "GEMINI_MODEL",
            "GEMINI_IMAGE_MODEL",
            "GEMMA_MODEL",
            "GOOGLE_CLOUD_PROJECT",
            "AGENT_ENGINE_PROJECT",
            "GOOGLE_CLOUD_LOCATION",
            "GEMINI_LOCATION",
            "AGENT_RUNTIME_LOCATION",
            "SEED_PACK",
            "SEED_BQ_DATASET",
            "ENABLE_MCP_STDIO",
            "STAGING_BUCKET",
            "BQ_LOCATION",
        )
        resolved: dict[str, str] = {}
        for key in standard_keys:
            resolved[key] = self.resolve_key(key)
        if overrides:
            for k, v in overrides.items():
                if v and not self.is_placeholder(v):
                    resolved[k] = v
        return resolved

    @overload
    def resolve(self, key_or_overrides: str, default: str = "") -> str: ...

    @overload
    def resolve(self, key_or_overrides: dict[str, str] | None = None) -> dict[str, str]: ...

    def resolve(
        self,
        key_or_overrides: str | dict[str, str] | None = None,
        default: str = "",
    ) -> str | dict[str, str]:
        """Polymorphic resolver supporting both `resolve(key, default)` and `resolve(overrides)`."""
        if isinstance(key_or_overrides, str):
            return self.resolve_key(key_or_overrides, default)
        return self.resolve_all(key_or_overrides)
