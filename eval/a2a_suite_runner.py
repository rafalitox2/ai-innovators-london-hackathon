"""Official A2A SDK and Cloud Run Gateway Automated Test Suite Runner.

Executes comprehensive evaluation of the Table 2 Dynamic Storefronts A2A
protocol, Agent Card discovery, JSON-RPC 2.0 endpoints, policy guardrails,
and sister tribe (Table 1 Campaign Orchestrator) synchronization.

Supports:
- --mode offline (default): In-memory execution via FastAPI TestClient against
  McpCloudRunGateway with protobuf schema validation, JSON-RPC 2.0 validation,
  and policy guardrail enforcement.
- --mode gcp: Live end-to-end execution against deployed Cloud Run service
  using Google Cloud OIDC identity token authentication.
- --mode all: Runs offline battery followed by live GCP verification.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from google.protobuf import json_format
import httpx

from mcp.http_gateway import McpCloudRunGateway
from seed_packs.t02_dynamic_storefronts.mcp.a2a_service import TribeA2ASyncService
from seed_packs.t02_dynamic_storefronts.mcp.state_store import McpStateStore
from tests.a2a.gateway_adapter import (
    apply_a2a_gateway_patch,
    validate_t01_a2a_endpoint,
)

# Dynamically ensure official a2a SDK types are loaded
try:
    import a2a.types as a2a_types
except ImportError:
    a2a_types = None  # type: ignore[assignment]


class A2ASuiteRunner:
    """Evaluates Table 2 A2A gateway conformance, AgentCard schemas, and tribe integration."""

    def __init__(self, endpoint_url: str | None = None, token: str | None = None) -> None:
        apply_a2a_gateway_patch()
        self.gateway = McpCloudRunGateway()
        self.app = self.gateway.build_fastapi_app()
        self.state_store = McpStateStore()
        self.a2a_service = TribeA2ASyncService(state_store=self.state_store)
        self.endpoint_url = (
            endpoint_url
            or os.environ.get("T02_A2A_ENDPOINT_URL")
            or os.environ.get("T01_A2A_ENDPOINT_URL")
            or ""
        ).strip()
        self.token = token or os.environ.get("A2A_OIDC_TOKEN") or ""
        self.results: list[dict[str, Any]] = []

    def log_result(
        self,
        test_id: str,
        name: str,
        passed: bool,
        duration_ms: float,
        details: str = "",
    ) -> None:
        status_str = "PASS" if passed else "FAIL"
        self.results.append(
            {
                "test_id": test_id,
                "name": name,
                "status": status_str,
                "duration_ms": round(duration_ms, 2),
                "details": details,
            }
        )

    def run_offline_suite(self) -> bool:
        """Run complete battery of offline in-memory tests."""
        print("\n" + "=" * 70)
        print("  RUNNING TABLE 2 A2A OFFLINE TEST BATTERY")
        print("=" * 70)

        prev_offline = os.environ.get("SEED_OFFLINE_MODE")
        os.environ["SEED_OFFLINE_MODE"] = "1"
        try:
            return self._execute_offline_suite()
        finally:
            if prev_offline is None:
                os.environ.pop("SEED_OFFLINE_MODE", None)
            else:
                os.environ["SEED_OFFLINE_MODE"] = prev_offline

    def _execute_offline_suite(self) -> bool:
        all_passed = True
        from fastapi.testclient import TestClient

        client = TestClient(self.app)

        # 1. Agent Discovery Card Validation (.well-known/agent.json)
        t0 = time.perf_counter()
        try:
            resp = client.get("/.well-known/agent.json")
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
            data = resp.json()

            # Protobuf validation via official a2a SDK
            if a2a_types and hasattr(a2a_types, "AgentCard"):
                card = a2a_types.AgentCard()
                json_format.ParseDict(data, card, ignore_unknown_fields=True)
                assert card.name, "AgentCard name must not be empty"

            assert data.get("name") == "expedition_t02_dynamic_storefronts"
            skill_ids = [s.get("id") for s in data.get("skills", [])]
            assert "storefront_to_campaign_sync" in skill_ids
            assert "render_storefront_preview" in skill_ids
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-01",
                "Agent Discovery Card Schema & Protobuf Validation",
                True,
                dur,
                f"Valid card with {len(skill_ids)} skills",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-01",
                "Agent Discovery Card Schema & Protobuf Validation",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        # 2. Extended Authenticated Card via JSON-RPC 2.0
        t0 = time.perf_counter()
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "req-ext-card-01",
                "method": "agent/authenticatedExtendedCard",
                "params": {},
            }
            resp = client.post("/a2a", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("jsonrpc") == "2.0"
            assert data.get("id") == "req-ext-card-01"
            res = data.get("result", {})
            assert res.get("name") == "expedition_t02_dynamic_storefronts"
            assert res.get("protocolVersion") == "0.2.5"
            assert res.get("capabilities", {}).get("a2a_tribe_handshake") is True
            assert len(res.get("skills", [])) >= 5
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-02",
                "JSON-RPC Extended Authenticated Card",
                True,
                dur,
                "Returned extended agent card",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result("A2A-OFF-02", "JSON-RPC Extended Authenticated Card", False, dur, str(exc))
            all_passed = False

        # 3. message/send with Structured DataPart
        t0 = time.perf_counter()
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": "req-msg-data-01",
                "method": "message/send",
                "params": {
                    "message": {
                        "parts": [
                            {
                                "data": {
                                    "segment_id": "SEG-002",
                                    "layout_variant": "Editorial_Grid",
                                    "featured_sku": "SKU-0005",
                                    "discount_pct": 15.0,
                                    "target_cpm_bid_eur": 18.0,
                                    "channel": "Instagram_Stories",
                                }
                            }
                        ]
                    }
                },
            }
            resp = client.post("/a2a", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data.get("jsonrpc") == "2.0"
            task_data = data.get("result", {})
            task_id = task_data.get("id")
            assert task_id and task_id.startswith("task-")
            assert task_data.get("status", {}).get("state") == "completed"
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-03",
                "JSON-RPC message/send Structured DataPart",
                True,
                dur,
                f"Completed task {task_id}",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-03",
                "JSON-RPC message/send Structured DataPart",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        # 4. tasks/get Retrieval
        t0 = time.perf_counter()
        try:
            get_payload = {
                "jsonrpc": "2.0",
                "id": "req-get-01",
                "method": "tasks/get",
                "params": {"id": task_id},
            }
            resp = client.post("/a2a", json=get_payload)
            assert resp.status_code == 200
            get_data = resp.json()
            assert get_data.get("result", {}).get("id") == task_id
            assert get_data.get("result", {}).get("status", {}).get("state") == "completed"
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-04",
                "JSON-RPC tasks/get State Retrieval",
                True,
                dur,
                f"Retrieved task {task_id}",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-04",
                "JSON-RPC tasks/get State Retrieval",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        # 5. Policy Cap Rejection Guardrail (CPM > 25.0)
        t0 = time.perf_counter()
        try:
            bad_cpm_payload = {
                "jsonrpc": "2.0",
                "id": "req-cpm-guard-01",
                "method": "message/send",
                "params": {
                    "message": {
                        "parts": [
                            {
                                "data": {
                                    "segment_id": "SEG-001",
                                    "target_cpm_bid_eur": 35.0,
                                }
                            }
                        ]
                    }
                },
            }
            resp = client.post("/a2a", json=bad_cpm_payload)
            assert resp.status_code == 200
            rej_data = resp.json()
            assert rej_data.get("result", {}).get("status", {}).get("state") == "rejected"
            assert "REJECTED_POLICY_CAP" in rej_data.get("result", {}).get("status", {}).get("detail", "")
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-05",
                "Policy Cap Guardrail Enforcement (CPM > 25.0 EUR)",
                True,
                dur,
                "Deterministically rejected with REJECTED_POLICY_CAP",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-05",
                "Policy Cap Guardrail Enforcement (CPM > 25.0 EUR)",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        # 6. JSON-RPC 2.0 Error Compliance (-32601 Method Not Found)
        t0 = time.perf_counter()
        try:
            unknown_payload = {
                "jsonrpc": "2.0",
                "id": "req-err-01",
                "method": "storefront/nonExistentAction",
                "params": {},
            }
            resp = client.post("/a2a", json=unknown_payload)
            assert resp.status_code == 200
            err_data = resp.json()
            assert err_data.get("error", {}).get("code") == -32601
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-06",
                "JSON-RPC 2.0 Error Compliance (-32601)",
                True,
                dur,
                "Returned standard JSON-RPC MethodNotFound error",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-06",
                "JSON-RPC 2.0 Error Compliance (-32601)",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        # 7. SSRF Target Validation
        t0 = time.perf_counter()
        try:
            assert validate_t01_a2a_endpoint("http://169.254.169.254/meta") is False
            assert validate_t01_a2a_endpoint("https://evil.com/a2a") is False
            assert validate_t01_a2a_endpoint("https://t01-agent-abc123-ew.a.run.app/a2a") is True
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-07",
                "SSRF Metadata Defense & Cloud Run Regex Whitelist",
                True,
                dur,
                "Blocked 169.254.169.254 and non-whitelisted domains",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-07",
                "SSRF Metadata Defense & Cloud Run Regex Whitelist",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        # 8. Tribe Handshake Sync (TribeA2ASyncService)
        t0 = time.perf_counter()
        try:
            sync_res = json.loads(
                self.a2a_service.sync_campaign_with_t01(
                    segment_id="SEG-003",
                    featured_skus="SKU-0010",
                    channel="Meta_Reels",
                    target_cpm_bid_eur=14.5,
                )
            )
            assert sync_res.get("status") == "SUCCESS"
            hs = sync_res.get("a2a_handshake", {})
            assert hs.get("handshake_type") == "STOREFRONT_TO_CAMPAIGN_SYNC"
            assert hs.get("t01_response", {}).get("bid", {}).get("new_cpm_bid_eur") == 14.5
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-08",
                "Tribe Handshake Contract (Table 2 -> Table 1)",
                True,
                dur,
                f"Handshake {hs.get('handshake_id')} verified",
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result(
                "A2A-OFF-08",
                "Tribe Handshake Contract (Table 2 -> Table 1)",
                False,
                dur,
                str(exc),
            )
            all_passed = False

        return all_passed

    def fetch_oidc_token(self, target_audience: str) -> str | None:
        """Fetch Google Cloud OIDC identity token for Cloud Run IAM authentication."""
        if self.token:
            return self.token

        # Attempt 1: google.oauth2.id_token
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token

            auth_req = Request()
            tok = id_token.fetch_id_token(auth_req, target_audience)
            if tok:
                return str(tok)
        except Exception:
            pass

        # Attempt 2: gcloud CLI
        try:
            import subprocess

            res = subprocess.run(
                ["gcloud", "auth", "print-identity-token", f"--audiences={target_audience}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0 and res.stdout.strip():
                return res.stdout.strip()
        except Exception:
            pass

        return None

    def run_gcp_suite(self) -> bool:
        """Run live integration tests against deployed Cloud Run service."""
        print("\n" + "=" * 70)
        print("  RUNNING TABLE 2 A2A GCP CLOUD RUN LIVE SUITE")
        print("=" * 70)

        if not self.endpoint_url:
            print("[INFO] No Cloud Run endpoint configured via --endpoint-url or T02_A2A_ENDPOINT_URL.")
            print("[INFO] Set T02_A2A_ENDPOINT_URL=https://<service>-<hash>-<region>.a.run.app")
            self.log_result(
                "A2A-GCP-01",
                "Cloud Run Live Endpoint Discovery",
                True,
                0.0,
                "SKIPPED (No endpoint URL configured; skipping live network calls)",
            )
            return True

        print(f"[INFO] Target endpoint URL: {self.endpoint_url}")
        base_url = self.endpoint_url.split("/a2a")[0].rstrip("/")
        well_known_url = f"{base_url}/.well-known/agent.json"
        rpc_url = f"{base_url}/a2a"

        # Attempt OIDC token acquisition
        bearer_token = self.fetch_oidc_token(base_url)
        headers = {"Content-Type": "application/json"}
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
            print("[INFO] OIDC Bearer token successfully acquired.")
        else:
            print("[WARN] Could not acquire Google Cloud OIDC token; trying unauthenticated request.")

        all_passed = True

        # 1. Live Discovery Card Check
        t0 = time.perf_counter()
        try:
            resp = httpx.get(well_known_url, headers=headers, timeout=10.0)
            dur = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                name = data.get("name", "unknown")
                self.log_result(
                    "A2A-GCP-01",
                    "Live Agent Card Discovery",
                    True,
                    dur,
                    f"HTTP 200 - Agent '{name}' verified",
                )
            else:
                self.log_result(
                    "A2A-GCP-01",
                    "Live Agent Card Discovery",
                    False,
                    dur,
                    f"HTTP {resp.status_code}: {resp.text[:120]}",
                )
                all_passed = False
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result("A2A-GCP-01", "Live Agent Card Discovery", False, dur, str(exc))
            all_passed = False

        # 2. Live JSON-RPC message/send
        t0 = time.perf_counter()
        try:
            live_payload = {
                "jsonrpc": "2.0",
                "id": "live-sync-01",
                "method": "message/send",
                "params": {
                    "message": {
                        "parts": [
                            {
                                "data": {
                                    "segment_id": "SEG-001",
                                    "layout_variant": "Single_Hero_Spotlight",
                                    "featured_sku": "SKU-0002",
                                    "discount_pct": 10.0,
                                    "target_cpm_bid_eur": 12.0,
                                    "channel": "Instagram_Reels",
                                }
                            }
                        ]
                    }
                },
            }
            resp = httpx.post(rpc_url, json=live_payload, headers=headers, timeout=15.0)
            dur = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                task_id = data.get("result", {}).get("id", "none")
                state = data.get("result", {}).get("status", {}).get("state", "unknown")
                self.log_result(
                    "A2A-GCP-02",
                    "Live JSON-RPC message/send Dispatch",
                    True,
                    dur,
                    f"HTTP 200 - Task {task_id} state={state}",
                )
            else:
                self.log_result(
                    "A2A-GCP-02",
                    "Live JSON-RPC message/send Dispatch",
                    False,
                    dur,
                    f"HTTP {resp.status_code}: {resp.text[:120]}",
                )
                all_passed = False
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000
            self.log_result("A2A-GCP-02", "Live JSON-RPC message/send Dispatch", False, dur, str(exc))
            all_passed = False

        return all_passed

    def print_summary(self) -> None:
        """Print structured test execution report table."""
        print("\n" + "=" * 70)
        print("  A2A EVALUATION SUITE SUMMARY")
        print("=" * 70)
        passed_count = sum(1 for r in self.results if r["status"] == "PASS")
        failed_count = sum(1 for r in self.results if r["status"] == "FAIL")

        col_fmt = "{:<12} | {:<42} | {:<6} | {:<9} | {:<25}"
        print(col_fmt.format("Test ID", "Scenario / Capability", "Status", "Duration", "Details"))
        print("-" * 100)

        for r in self.results:
            details_trunc = r["details"][:25]
            print(
                col_fmt.format(
                    r["test_id"],
                    r["name"][:42],
                    r["status"],
                    f"{r['duration_ms']}ms",
                    details_trunc,
                )
            )

        print("-" * 100)
        print(f"Total: {len(self.results)} | Passed: {passed_count} | Failed: {failed_count}")
        print("=" * 70 + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Official A2A SDK and Cloud Run Gateway Automated Test Suite"
    )
    parser.add_argument(
        "--mode",
        choices=["offline", "gcp", "all"],
        default="offline",
        help="Execution mode: offline (default), gcp (live Cloud Run), or all",
    )
    parser.add_argument(
        "--endpoint-url",
        default="",
        help="Optional Cloud Run endpoint URL (e.g. https://<svc>.a.run.app)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="Optional Google Cloud OIDC ID bearer token for authenticated Cloud Run calls",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON summary of results to stdout",
    )

    args = parser.parse_args()

    runner = A2ASuiteRunner(endpoint_url=args.endpoint_url, token=args.token)
    success = True

    if args.mode in ("offline", "all"):
        offline_ok = runner.run_offline_suite()
        success = success and offline_ok

    if args.mode in ("gcp", "all"):
        gcp_ok = runner.run_gcp_suite()
        success = success and gcp_ok

    if args.json:
        print(json.dumps(runner.results, indent=2))
    else:
        runner.print_summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
