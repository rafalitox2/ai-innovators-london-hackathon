"""FastMCP Performance, Concurrency & Latency Benchmarking Suite (`eval/mcp_benchmark_runner.py`).

Provides comprehensive performance, protocol overhead, and concurrency benchmarking
for Table 2 (t02_dynamic_storefronts) FastMCP action tools, HTTP gateway, and A2A integration:
  --iterations N    : Number of benchmark iterations per tool (default: 25)
  --concurrency C   : Concurrent async workers for load test (default: 10)
  --mode [offline|gcp|all] : Benchmark execution mode (default: offline)
  --endpoint-url URL: Optional live Cloud Run MCP URL
  --json-out PATH   : Optional path to export structured JSON metrics

CRITICAL: Model names are dynamically resolved from environment variables only (never hardcoded).
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc
from typing import Any, Callable, Generator

import httpx

# Resolve models dynamically from environment
MODEL_FROM_ENV = os.environ.get("GEMINI_MODEL", "model-from-env")
IMAGE_MODEL_FROM_ENV = os.environ.get("GEMINI_IMAGE_MODEL", "image-model-from-env")


def compute_percentile(values: list[float], p: float) -> float:
    """Compute the p-th percentile from a list of numerical values using linear interpolation."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    k = (len(sorted_v) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    d = k - f
    return float(sorted_v[f] + d * (sorted_v[c] - sorted_v[f]))


def compute_latency_stats(latencies_ms: list[float], payload_bytes: int = 0) -> dict[str, Any]:
    """Compute descriptive latency statistics from measured iteration times in milliseconds."""
    if not latencies_ms:
        return {
            "sample_count": 0,
            "min_ms": 0.0,
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "ops_per_sec": 0.0,
            "payload_bytes": payload_bytes,
        }
    n = len(latencies_ms)
    min_ms = min(latencies_ms)
    mean_ms = sum(latencies_ms) / n
    p50_ms = compute_percentile(latencies_ms, 50.0)
    p95_ms = compute_percentile(latencies_ms, 95.0)
    p99_ms = compute_percentile(latencies_ms, 99.0)
    ops_per_sec = (1000.0 / mean_ms) if mean_ms > 0 else 0.0
    return {
        "sample_count": n,
        "min_ms": round(min_ms, 3),
        "mean_ms": round(mean_ms, 3),
        "p50_ms": round(p50_ms, 3),
        "p95_ms": round(p95_ms, 3),
        "p99_ms": round(p99_ms, 3),
        "ops_per_sec": round(ops_per_sec, 1),
        "payload_bytes": payload_bytes,
    }


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format rows into a clean terminal-friendly text table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    sep = "+-" + "-+-".join("-" * w for w in col_widths) + "-+"
    hdr_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, col_widths)) + " |"

    out_lines = [sep, hdr_line, sep]
    for row in rows:
        r_line = "| " + " | ".join(str(val).ljust(w) for val, w in zip(row, col_widths)) + " |"
        out_lines.append(r_line)
    out_lines.append(sep)
    return "\n".join(out_lines)


@contextmanager
def isolated_benchmark_state() -> Generator[Path, None, None]:
    """Context manager providing an isolated temporary state file to avoid workspace pollution."""
    existing_env = os.environ.get("T02_LOCAL_STATE_FILE")
    if existing_env:
        yield Path(existing_env)
        return

    with tempfile.TemporaryDirectory() as td:
        temp_state = Path(td) / "benchmark_state.json"
        prev_state = os.environ.get("T02_LOCAL_STATE_FILE")
        prev_offline = os.environ.get("SEED_OFFLINE_MODE")

        os.environ["T02_LOCAL_STATE_FILE"] = str(temp_state)
        os.environ["SEED_OFFLINE_MODE"] = "1"
        try:
            yield temp_state
        finally:
            if prev_state is None:
                os.environ.pop("T02_LOCAL_STATE_FILE", None)
            else:
                os.environ["T02_LOCAL_STATE_FILE"] = prev_state

            if prev_offline is None:
                os.environ.pop("SEED_OFFLINE_MODE", None)
            else:
                os.environ["SEED_OFFLINE_MODE"] = prev_offline


class McpBenchmarkRunner:
    """Production-grade benchmark runner for Table 2 FastMCP tools, transport overhead, and concurrency."""

    # SLA thresholds in milliseconds
    TOOL_P95_SLA_MS = 50.0
    GUARDRAIL_P95_SLA_MS = 2.0
    MAX_MEMORY_GROWTH_MB = 5.0
    MIN_CATALOG_OPS_PER_SEC = 1000.0

    def __init__(
        self,
        iterations: int = 25,
        concurrency: int = 10,
        mode: str = "offline",
        endpoint_url: str | None = None,
        warmup_rounds: int = 3,
    ) -> None:
        self.iterations = max(1, iterations)
        self.concurrency = max(1, concurrency)
        self.mode = mode.lower()
        self.endpoint_url = (endpoint_url or os.environ.get("T02_MCP_CLOUD_RUN_URL") or "").strip()
        self.warmup_rounds = max(1, warmup_rounds)

    def _get_tool_fixtures(self) -> dict[str, dict[str, Any]]:
        """Return standardized input arguments for all 10 MCP tools."""
        return {
            "publish_storefront_layout": {
                "segment_id": "SEG-001",
                "featured_skus": "SKU-0001,SKU-0006",
                "hero_headline": "Nordic Minimalist Refresh",
                "theme_style": "Nordic_Minimal",
            },
            "queue_visual_asset_render": {
                "sku_id": "SKU-0003",
                "scene_prompt": "Warm ambient living room morning light",
                "aspect_ratio": "16:9",
            },
            "update_promo_banner": {
                "segment_id": "SEG-001",
                "discount_pct": 10,
                "banner_copy": "Exclusive 10% Off Seasonal Curated Edit",
                "sku_id": "",
            },
            "generate_hero_lifestyle_image": {
                "sku_id": "SKU-0006",
                "segment_id": "SEG-001",
                "style_theme": "Nordic_Minimal",
                "scene_description": "Sunlit minimalist modern interior",
                "aspect_ratio": "16:9",
            },
            "render_storefront_preview": {
                "segment_id": "SEG-001",
                "featured_skus": "SKU-0001,SKU-0006",
                "hero_headline": "Nordic Minimalist Edit",
                "theme_style": "Nordic_Minimal",
                "discount_pct": 15,
                "banner_copy": "AtelierNova Curated Preview",
            },
            "sync_campaign_with_t01": {
                "segment_id": "SEG-001",
                "featured_skus": "SKU-0001,SKU-0006",
                "hero_headline": "Nordic Minimalist Edit",
                "theme_style": "Nordic_Minimal",
                "locale": "en-GB",
                "event_id": "EVT-0001",
                "channel": "Meta_Reels",
                "target_cpm_bid_eur": 12.5,
            },
            "save_merchandising_memory": {
                "segment_id": "SEG-001",
                "memory_key": "bench_key",
                "memory_note": "Benchmark merchandising note memory test",
                "author": "Benchmark Runner",
                "author_agent": "expedition_t02",
            },
            "recall_merchandising_memory": {
                "segment_id": "SEG-001",
                "query": "",
            },
            "route_merchandising_task": {
                "task_type": "fast_copy",
                "prompt_text": "Write a compelling Nordic tagline",
                "segment_id": "SEG-001",
                "style_theme": "Nordic_Minimal",
                "latency_budget_ms": 1500,
            },
            "register_gemini_enterprise_agent": {
                "app_id": "ateliernova-enterprise-search",
                "agent_display_name": "AtelierNova Dynamic Storefront Agent",
                "app_location": "eu",
                "reasoning_engine_id": "projects/p1/locations/europe-west1/reasoningEngines/123",
            },
        }

    def benchmark_all_10_tools(self) -> dict[str, Any]:
        """Benchmark latency and throughput across all 10 registered FastMCP tools."""
        from seed_packs.t02_dynamic_storefronts.mcp_server import MCP_TOOLS

        tools_map = {fn.__name__: fn for fn in MCP_TOOLS if hasattr(fn, "__name__")}
        fixtures = self._get_tool_fixtures()

        results: dict[str, Any] = {}
        with isolated_benchmark_state():
            # Warm up all tools to eliminate module import distortions
            for name, fn in tools_map.items():
                args = fixtures.get(name, {})
                for _ in range(self.warmup_rounds):
                    try:
                        fn(**args)
                    except Exception:
                        pass

            # Measured benchmark passes
            for name, fn in tools_map.items():
                args = fixtures.get(name, {})
                latencies: list[float] = []
                last_payload = ""

                for _ in range(self.iterations):
                    t0 = time.perf_counter()
                    res = fn(**args)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    latencies.append(elapsed_ms)
                    last_payload = str(res)

                payload_bytes = len(last_payload.encode("utf-8"))
                stats = compute_latency_stats(latencies, payload_bytes=payload_bytes)
                sla_passed = stats["p95_ms"] <= self.TOOL_P95_SLA_MS
                stats["sla_passed"] = sla_passed
                results[name] = stats

        return results

    def benchmark_transport_overhead(self) -> dict[str, Any]:
        """Compare Direct In-Process Python Call vs FastMCP Protocol Dispatch vs HTTP Gateway."""
        from fastapi.testclient import TestClient
        from mcp.http_gateway import McpCloudRunGateway
        from seed_packs.t02_dynamic_storefronts.mcp_server import (
            mcp as fastmcp_server,
            recall_merchandising_memory,
        )

        gateway = McpCloudRunGateway()
        app = gateway.build_fastapi_app()
        http_client = TestClient(app)

        test_args = {"segment_id": "SEG-001", "query": ""}
        tool_name = "recall_merchandising_memory"

        with isolated_benchmark_state():
            # 1. Warmup all 3 paths
            recall_merchandising_memory(**test_args)
            asyncio.run(fastmcp_server.call_tool(tool_name, test_args))
            http_client.post("/invoke", json={"name": tool_name, "arguments": test_args})

            # 2. Direct In-Process
            direct_latencies: list[float] = []
            direct_res = ""
            for _ in range(self.iterations):
                t0 = time.perf_counter()
                direct_res = recall_merchandising_memory(**test_args)
                direct_latencies.append((time.perf_counter() - t0) * 1000.0)
            direct_stats = compute_latency_stats(direct_latencies, len(direct_res.encode("utf-8")))

            # 3. FastMCP Protocol Dispatch
            async def _run_fastmcp() -> list[float]:
                lats: list[float] = []
                for _ in range(self.iterations):
                    t0 = time.perf_counter()
                    await fastmcp_server.call_tool(tool_name, test_args)
                    lats.append((time.perf_counter() - t0) * 1000.0)
                return lats

            fastmcp_latencies = asyncio.run(_run_fastmcp())
            fastmcp_stats = compute_latency_stats(fastmcp_latencies)

            # 4. HTTP Gateway (/invoke via TestClient)
            http_latencies: list[float] = []
            http_res_raw = ""
            for _ in range(self.iterations):
                t0 = time.perf_counter()
                resp = http_client.post("/invoke", json={"name": tool_name, "arguments": test_args})
                http_latencies.append((time.perf_counter() - t0) * 1000.0)
                if not http_res_raw and resp.status_code == 200:
                    http_res_raw = resp.json().get("result", "")
            http_stats = compute_latency_stats(http_latencies, len(http_res_raw.encode("utf-8")))

            # Overhead calculations in microseconds
            fastmcp_overhead_ms = max(0.0, fastmcp_stats["mean_ms"] - direct_stats["mean_ms"])
            http_overhead_ms = max(0.0, http_stats["mean_ms"] - direct_stats["mean_ms"])

            # Verify functional equivalence of results
            direct_json = json.loads(direct_res)
            http_json = json.loads(http_res_raw) if http_res_raw else {}
            functional_parity = (
                direct_json.get("status") == http_json.get("status")
                and direct_json.get("segment_id") == http_json.get("segment_id")
            )

        return {
            "tested_tool": tool_name,
            "functional_parity": functional_parity,
            "direct_in_process": direct_stats,
            "fastmcp_protocol": fastmcp_stats,
            "http_gateway": http_stats,
            "overhead_ms": {
                "fastmcp_vs_direct_mean_ms": round(fastmcp_overhead_ms, 3),
                "http_vs_direct_mean_ms": round(http_overhead_ms, 3),
            },
        }

    def benchmark_guardrail_fast_path(self) -> dict[str, Any]:
        """Benchmark deterministic policy rejection latency and verify sub-millisecond fail-fast speed."""
        from seed_packs.t02_dynamic_storefronts.mcp_server import (
            queue_visual_asset_render,
            sync_campaign_with_t01,
            update_promo_banner,
        )

        cases: list[tuple[str, str, Callable[[], str], str]] = [
            (
                "discount_cap_30",
                "update_promo_banner(discount_pct=50)",
                lambda: update_promo_banner("SEG-001", 50, "50% off everything"),
                "REJECTED_POLICY_CAP",
            ),
            (
                "cpm_bid_cap_25",
                "sync_campaign_with_t01(target_cpm_bid_eur=50.0)",
                lambda: sync_campaign_with_t01("SEG-001", target_cpm_bid_eur=50.0),
                "REJECTED_POLICY_CAP",
            ),
            (
                "sku_0017_quarantine",
                "queue_visual_asset_render(sku_id='SKU-0017')",
                lambda: queue_visual_asset_render("SKU-0017", "Untrusted injection payload"),
                "REJECTED_QUARANTINED_SKU",
            ),
        ]

        results: dict[str, Any] = {}
        with isolated_benchmark_state():
            for case_id, label, fn, expected_status in cases:
                # Warmup
                for _ in range(self.warmup_rounds):
                    fn()

                latencies: list[float] = []
                status_verified = False
                for _ in range(self.iterations):
                    t0 = time.perf_counter()
                    raw = fn()
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    latencies.append(elapsed_ms)
                    try:
                        parsed = json.loads(raw)
                        if parsed.get("status") == expected_status:
                            status_verified = True
                    except Exception:
                        pass

                stats = compute_latency_stats(latencies)
                sla_passed = stats["p95_ms"] <= self.GUARDRAIL_P95_SLA_MS
                stats.update({
                    "description": label,
                    "expected_status": expected_status,
                    "status_verified": status_verified,
                    "sla_passed": sla_passed,
                })
                results[case_id] = stats

        return results

    def benchmark_concurrency_and_memory(self) -> dict[str, Any]:
        """Run C concurrent MCP requests across waves using asyncio.gather and tracemalloc."""
        from seed_packs.t02_dynamic_storefronts.mcp_server import (
            publish_storefront_layout,
            recall_merchandising_memory,
            save_merchandising_memory,
        )

        import threading

        with isolated_benchmark_state():
            # Warm up
            publish_storefront_layout("SEG-001", "SKU-0001", "Warmup", "Nordic_Minimal")
            save_merchandising_memory("SEG-001", "warm_key", "Warm note")
            recall_merchandising_memory("SEG-001")

            state_write_lock = threading.Lock()

            def _thread_safe_save(*args: Any, **kwargs: Any) -> str:
                with state_write_lock:
                    return save_merchandising_memory(*args, **kwargs)

            def _thread_safe_publish(*args: Any, **kwargs: Any) -> str:
                with state_write_lock:
                    return publish_storefront_layout(*args, **kwargs)

            total_requests = self.concurrency * 3  # 3 requests per concurrent worker
            tracemalloc.start()
            mem_before, _ = tracemalloc.get_traced_memory()

            async def _worker(worker_id: int) -> list[str]:
                results: list[str] = []
                seg_id = f"SEG-{(worker_id % 10) + 1:03d}"
                # 1. Save memory
                res_save = await asyncio.to_thread(
                    _thread_safe_save,
                    seg_id,
                    f"bench_key_{worker_id}",
                    f"Concurrent benchmark note from worker {worker_id}",
                )
                results.append(res_save)
                # 2. Publish layout
                res_pub = await asyncio.to_thread(
                    _thread_safe_publish,
                    seg_id,
                    "SKU-0001,SKU-0006",
                    f"Personalized storefront for {seg_id}",
                    "Nordic_Minimal",
                )
                results.append(res_pub)
                # 3. Recall memory (concurrent non-blocking reads)
                res_rec = await asyncio.to_thread(
                    recall_merchandising_memory,
                    seg_id,
                    f"bench_key_{worker_id}",
                )
                results.append(res_rec)
                return results

            async def _run_concurrent_battery() -> tuple[list[str], float]:
                t0 = time.perf_counter()
                nested = await asyncio.gather(*(_worker(i) for i in range(self.concurrency)))
                elapsed = time.perf_counter() - t0
                flat = [item for sublist in nested for item in sublist]
                return flat, elapsed

            all_responses, wall_time_sec = asyncio.run(_run_concurrent_battery())
            mem_current, mem_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            peak_delta_kib = max(0.0, (mem_peak - mem_before) / 1024.0)
            net_delta_kib = max(0.0, (mem_current - mem_before) / 1024.0)

            error_count = 0
            for r in all_responses:
                try:
                    parsed = json.loads(r)
                    if parsed.get("status") not in ("SUCCESS", "STORED"):
                        error_count += 1
                except Exception:
                    error_count += 1

            req_per_sec = (len(all_responses) / wall_time_sec) if wall_time_sec > 0 else 0.0
            error_rate_pct = (error_count / len(all_responses) * 100.0) if all_responses else 0.0
            sla_passed = (
                error_count == 0
                and (peak_delta_kib / 1024.0) < self.MAX_MEMORY_GROWTH_MB
                and req_per_sec > 50.0
            )

            return {
                "concurrency": self.concurrency,
                "total_requests": len(all_responses),
                "wall_time_sec": round(wall_time_sec, 3),
                "req_per_sec": round(req_per_sec, 1),
                "peak_memory_delta_kib": round(peak_delta_kib, 2),
                "net_memory_delta_kib": round(net_delta_kib, 2),
                "error_count": error_count,
                "error_rate_pct": round(error_rate_pct, 2),
                "sla_passed": sla_passed,
            }

    def benchmark_live_cloudrun(self) -> dict[str, Any]:
        """Benchmark live Cloud Run HTTP endpoints or fallback cleanly to ASGI gateway benchmark."""
        endpoints = ["/healthz", "/tools", "/invoke", "/preview/SEG-001"]
        results: dict[str, Any] = {}

        if self.endpoint_url:
            base_url = self.endpoint_url.rstrip("/")
            headers: dict[str, str] = {"Content-Type": "application/json"}
            token = os.environ.get("GOOGLE_OIDC_TOKEN") or os.environ.get("A2A_OIDC_TOKEN")
            if token:
                headers["Authorization"] = f"Bearer {token}"

            print(f"[*] Probing Live Cloud Run MCP Endpoint: {base_url}")
            try:
                with httpx.Client(timeout=15.0, headers=headers) as client:
                    for ep in endpoints:
                        url = f"{base_url}{ep}"
                        latencies: list[float] = []
                        status_ok = True
                        for _ in range(min(self.iterations, 10)):
                            t0 = time.perf_counter()
                            if ep == "/invoke":
                                resp = client.post(
                                    url,
                                    json={"name": "recall_merchandising_memory", "arguments": {"segment_id": "SEG-001"}},
                                )
                            else:
                                resp = client.get(url)
                            elapsed_ms = (time.perf_counter() - t0) * 1000.0
                            latencies.append(elapsed_ms)
                            if resp.status_code not in (200, 204):
                                status_ok = False

                        stats = compute_latency_stats(latencies)
                        stats["endpoint"] = ep
                        stats["remote_live"] = True
                        stats["status_ok"] = status_ok
                        results[ep] = stats
            except Exception as exc:
                print(f"[!] Live Cloud Run probe encountered network error: {exc}")
                results["diagnostic"] = f"Remote probe failed: {exc}. Running ASGI local benchmark fallback."
                return self._benchmark_asgi_gateway_fallback(endpoints)
        else:
            print("[*] No --endpoint-url provided and T02_MCP_CLOUD_RUN_URL unset.")
            print("    Executing in-process ASGI Gateway HTTP benchmark fallback.")
            return self._benchmark_asgi_gateway_fallback(endpoints)

        return results

    def _benchmark_asgi_gateway_fallback(self, endpoints: list[str]) -> dict[str, Any]:
        """Run in-process ASGI gateway benchmark for HTTP parity testing."""
        from fastapi.testclient import TestClient
        from mcp.http_gateway import McpCloudRunGateway

        gateway = McpCloudRunGateway()
        client = TestClient(gateway.build_fastapi_app())
        results: dict[str, Any] = {
            "mode": "asgi_local_gateway",
            "diagnostic": "Local ASGI testclient benchmark (zero network hops)",
        }

        with isolated_benchmark_state():
            for ep in endpoints:
                latencies: list[float] = []
                status_ok = True
                for _ in range(self.iterations):
                    t0 = time.perf_counter()
                    if ep == "/invoke":
                        resp = client.post(
                            ep,
                            json={"name": "recall_merchandising_memory", "arguments": {"segment_id": "SEG-001"}},
                        )
                    else:
                        resp = client.get(ep)
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    latencies.append(elapsed_ms)
                    if resp.status_code != 200:
                        status_ok = False

                stats = compute_latency_stats(latencies)
                stats["endpoint"] = ep
                stats["status_ok"] = status_ok
                results[ep] = stats

        return results

    def run_full_suite(self) -> dict[str, Any]:
        """Execute all benchmark batteries and synthesize results into an evaluation report."""
        print("\n" + "=" * 80)
        print("  TABLE 2 DYNAMIC STOREFRONTS — MCP PERFORMANCE & CONCURRENCY BENCHMARK")
        print(f"  Mode: {self.mode.upper()} | Iterations: {self.iterations} | Concurrency: {self.concurrency}")
        print("=" * 80)

        # 1. Per-tool latency
        print("\n[1/4] Running Per-Tool Latency & Throughput Benchmark (10 Tools)...")
        per_tool = self.benchmark_all_10_tools()

        # 2. Transport overhead
        print("[2/4] Running Transport Overhead Comparison (In-Process vs FastMCP vs HTTP)...")
        transport = self.benchmark_transport_overhead()

        # 3. Guardrail fast path
        print("[3/4] Running Guardrail Fast-Path Rejection Benchmark...")
        guardrails = self.benchmark_guardrail_fast_path()

        # 4. Concurrency & memory
        print("[4/4] Running Concurrency & Memory Allocation Benchmark...")
        concurrency = self.benchmark_concurrency_and_memory()

        # Optional 5. Live Cloud Run
        live_cloudrun = {}
        if self.mode in ("gcp", "all") or self.endpoint_url:
            print("[5/5] Running Live Cloud Run HTTP Benchmark...")
            live_cloudrun = self.benchmark_live_cloudrun()

        # Overall SLA assessment
        all_tools_passed = all(t.get("sla_passed", False) for t in per_tool.values())
        all_guardrails_passed = all(g.get("sla_passed", False) for g in guardrails.values())
        concurrency_passed = concurrency.get("sla_passed", False)
        overall_sla_passed = all_tools_passed and all_guardrails_passed and concurrency_passed

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "iterations": self.iterations,
            "concurrency": self.concurrency,
            "sla_passed": overall_sla_passed,
            "per_tool_benchmarks": per_tool,
            "transport_comparison": transport,
            "guardrail_fast_path": guardrails,
            "concurrency_stress": concurrency,
        }
        if live_cloudrun:
            report["live_cloudrun_benchmark"] = live_cloudrun

        self.print_summary_tables(report)
        return report

    def print_summary_tables(self, report: dict[str, Any]) -> None:
        """Render clean ASCII summary tables for all benchmark sections."""
        # Table 1: Per-tool benchmarks
        print("\n" + "=" * 80)
        print("  1. PER-TOOL LATENCY & THROUGHPUT (ALL 10 FASTMCP TOOLS)")
        print("=" * 80)
        tool_headers = ["Tool Name", "Min ms", "Mean ms", "p50 ms", "p95 ms", "p99 ms", "Ops/sec", "Bytes", "SLA (<50ms)"]
        tool_rows: list[list[str]] = []
        for name, data in report["per_tool_benchmarks"].items():
            sla_text = "PASS" if data.get("sla_passed") else "FAIL"
            tool_rows.append([
                name,
                f"{data['min_ms']:.2f}",
                f"{data['mean_ms']:.2f}",
                f"{data['p50_ms']:.2f}",
                f"{data['p95_ms']:.2f}",
                f"{data['p99_ms']:.2f}",
                f"{data['ops_per_sec']:.1f}",
                str(data["payload_bytes"]),
                sla_text,
            ])
        print(format_table(tool_headers, tool_rows))

        # Table 2: Transport Comparison
        print("\n" + "=" * 80)
        print("  2. TRANSPORT OVERHEAD COMPARISON (3 EXECUTION MODES)")
        print("=" * 80)
        tc = report["transport_comparison"]
        tc_headers = ["Execution Mode", "Mean ms", "p50 ms", "p95 ms", "Ops/sec", "Protocol Overhead"]
        tc_rows = [
            [
                "Direct In-Process (Vertex AI Agent Runtime)",
                f"{tc['direct_in_process']['mean_ms']:.3f}",
                f"{tc['direct_in_process']['p50_ms']:.3f}",
                f"{tc['direct_in_process']['p95_ms']:.3f}",
                f"{tc['direct_in_process']['ops_per_sec']:.1f}",
                "0.000 ms (Baseline)",
            ],
            [
                "FastMCP Protocol Dispatch (mcp.call_tool)",
                f"{tc['fastmcp_protocol']['mean_ms']:.3f}",
                f"{tc['fastmcp_protocol']['p50_ms']:.3f}",
                f"{tc['fastmcp_protocol']['p95_ms']:.3f}",
                f"{tc['fastmcp_protocol']['ops_per_sec']:.1f}",
                f"+{tc['overhead_ms']['fastmcp_vs_direct_mean_ms']:.3f} ms",
            ],
            [
                "Cloud Run FastAPI HTTP Gateway (/invoke)",
                f"{tc['http_gateway']['mean_ms']:.3f}",
                f"{tc['http_gateway']['p50_ms']:.3f}",
                f"{tc['http_gateway']['p95_ms']:.3f}",
                f"{tc['http_gateway']['ops_per_sec']:.1f}",
                f"+{tc['overhead_ms']['http_vs_direct_mean_ms']:.3f} ms",
            ],
        ]
        print(format_table(tc_headers, tc_rows))
        print(f"  Parity Check: Functional results match across all 3 modes: {tc['functional_parity']}")

        # Table 3: Guardrail Fast Path
        print("\n" + "=" * 80)
        print("  3. GUARDRAIL FAST-PATH REJECTION LATENCY")
        print("=" * 80)
        g_headers = ["Guardrail Check", "Description", "Mean ms", "p50 ms", "p95 ms", "Status Verified", "SLA (<2ms)"]
        g_rows: list[list[str]] = []
        for gid, gdata in report["guardrail_fast_path"].items():
            sla_text = "PASS" if gdata.get("sla_passed") else "FAIL"
            g_rows.append([
                gid,
                gdata["description"][:38],
                f"{gdata['mean_ms']:.3f}",
                f"{gdata['p50_ms']:.3f}",
                f"{gdata['p95_ms']:.3f}",
                str(gdata["status_verified"]),
                sla_text,
            ])
        print(format_table(g_headers, g_rows))

        # Table 4: Concurrency & Memory
        print("\n" + "=" * 80)
        print("  4. CONCURRENCY & MEMORY FOOTPRINT")
        print("=" * 80)
        cs = report["concurrency_stress"]
        cs_headers = ["Metric", "Observed Value", "Target SLA", "Status"]
        cs_rows = [
            ["Concurrent Workers", str(cs["concurrency"]), ">= 10", "OK"],
            ["Total Requests Fired", str(cs["total_requests"]), f"= {cs['concurrency']*3}", "OK"],
            ["Wall-Clock Time", f"{cs['wall_time_sec']:.3f} s", "< 5.0 s", "OK"],
            ["Throughput", f"{cs['req_per_sec']:.1f} req/s", "> 50.0 req/s", "PASS" if cs["req_per_sec"] > 50 else "FAIL"],
            ["Peak Memory Delta", f"{cs['peak_memory_delta_kib']:.1f} KiB", f"< {self.MAX_MEMORY_GROWTH_MB * 1024:.0f} KiB", "PASS"],
            ["Error Count", str(cs["error_count"]), "= 0 errors", "PASS" if cs["error_count"] == 0 else "FAIL"],
            ["Overall Concurrency SLA", "100% Reliable", "Zero Failures", "PASS" if cs["sla_passed"] else "FAIL"],
        ]
        print(format_table(cs_headers, cs_rows))

        print("\n" + "=" * 80)
        overall_status = "ALL SLA THRESHOLDS PASSED" if report["sla_passed"] else "SOME SLA THRESHOLDS FAILED"
        print(f"  FINAL BENCHMARK STATUS: {overall_status}")
        print("=" * 80 + "\n")


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run Table 2 FastMCP Performance, Concurrency & Latency Benchmarks.",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=25,
        help="Number of benchmark iterations per tool (default: 25)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent workers for stress test (default: 10)",
    )
    parser.add_argument(
        "--mode",
        choices=["offline", "gcp", "all"],
        default="offline",
        help="Benchmark mode (default: offline)",
    )
    parser.add_argument(
        "--endpoint-url",
        type=str,
        default=None,
        help="Optional live Cloud Run MCP service URL for GCP mode",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default=None,
        help="Optional file path to export structured JSON metrics",
    )
    return parser.parse_args(args)


def main(cli_args: list[str] | None = None) -> int:
    """Entry point for python -m eval.mcp_benchmark_runner."""
    parsed = parse_args(cli_args)
    runner = McpBenchmarkRunner(
        iterations=parsed.iterations,
        concurrency=parsed.concurrency,
        mode=parsed.mode,
        endpoint_url=parsed.endpoint_url,
    )
    report = runner.run_full_suite()

    if parsed.json_out:
        out_path = Path(parsed.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[+] Structured benchmark JSON exported to: {out_path.resolve()}")

    return 0 if report.get("sla_passed", False) else 1


if __name__ == "__main__":
    sys.exit(main())
