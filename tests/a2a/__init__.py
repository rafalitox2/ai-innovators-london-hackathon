"""A2A automated test suite for Table 2 (`t02_dynamic_storefronts`).

Contains test suites verifying:
1. Official A2A SDK (`a2a.types`), AgentCard schema compliance, and Google ADK RemoteA2aAgent converters.
2. JSON-RPC 2.0 protocol compliance, task registry (_a2a_tasks), and Gateway routing.
3. Tribe A2A campaign synchronization handshake, CPM/discount guardrails, and SSRF defense.
"""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure official site-packages a2a submodules (a2a.types, a2a.client, etc.) are reachable
# even when pytest adds the tests/ directory to sys.path:
sp_a2a = (
    Path(sys.prefix)
    / "lib"
    / f"python{sys.version_info.major}.{sys.version_info.minor}"
    / "site-packages"
    / "a2a"
)
if sp_a2a.exists() and str(sp_a2a) not in __path__:
    __path__.append(str(sp_a2a))

from tests.a2a.gateway_adapter import (
    apply_a2a_gateway_patch,
    create_a2a_task_record,
    extract_data_parts,
    validate_t01_a2a_endpoint,
)

apply_a2a_gateway_patch()

__all__ = [
    "apply_a2a_gateway_patch",
    "create_a2a_task_record",
    "extract_data_parts",
    "validate_t01_a2a_endpoint",
]
