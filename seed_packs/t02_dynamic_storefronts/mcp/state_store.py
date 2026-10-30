"""State storage and CSV catalog repository for Table 2 FastMCP."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_PACK_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = _DEFAULT_PACK_DIR / "data"
_DEFAULT_STATE_FILE = _DEFAULT_PACK_DIR / ".state.json"
_FALLBACK_STATE_FILE = Path("/tmp/t02_dynamic_storefronts_state.json")
_GCS_STATE_BLOB_PATH = "t02_dynamic_storefronts/state.json"


class CatalogCsvRepository:
    """Repository for querying read-only catalog and segment CSV data."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or _DEFAULT_DATA_DIR

    def read_csv_rows(self, name: str) -> list[dict[str, Any]]:
        """Read CSV rows from data directory as dicts."""
        path = self.data_dir / f"{name}.csv"
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fp:
            return list(csv.DictReader(fp))

    def load_catalog_by_sku(self) -> dict[str, dict[str, Any]]:
        """Return a mapping of upper-cased SKU IDs to product catalog records."""
        rows = self.read_csv_rows("products_catalog")
        return {r.get("sku_id", "").strip().upper(): r for r in rows if r.get("sku_id")}

    def load_segment_by_id(self, segment_id: str) -> dict[str, Any]:
        """Return audience segment data or a standard fallback dict."""
        seg_clean = (segment_id or "SEG-001").strip()
        rows = self.read_csv_rows("audience_segments")
        match = next(
            (r for r in rows if r.get("segment_id", "").strip().upper() == seg_clean.upper()),
            None,
        )
        if match is not None:
            return match
        return {
            "segment_id": seg_clean,
            "segment_name": f"{seg_clean}_Default",
            "region": "EU",
            "preferred_style": "Nordic_Minimal",
            "device_type": "Desktop_Web",
            "avg_order_value_eur": "450.00",
            "conversion_rate_pct": "3.50",
        }


class McpStateStore:
    """Manages persistent and cached state across local JSON files and Google Cloud Storage."""

    def __init__(
        self,
        default_state_path: Path | None = None,
        fallback_state_path: Path | None = None,
    ) -> None:
        self.default_state_path = default_state_path or _DEFAULT_STATE_FILE
        self.fallback_state_path = fallback_state_path or _FALLBACK_STATE_FILE

    def resolve_local_state_path(self, for_write: bool = False) -> Path:
        """Resolve the local JSON file path, giving precedence to T02_LOCAL_STATE_FILE."""
        env_file = os.environ.get("T02_LOCAL_STATE_FILE", "").strip()
        if env_file:
            return Path(env_file)

        if not for_write:
            for candidate in (self.default_state_path, self.fallback_state_path):
                if candidate.exists():
                    return candidate
            return self.default_state_path

        # For writing, prefer default if writable/creatable, else fallback
        try:
            self.default_state_path.parent.mkdir(parents=True, exist_ok=True)
            return self.default_state_path
        except OSError:
            return self.fallback_state_path

    def resolve_gcs_target(self) -> tuple[str, str]:
        """Return (project_id, bucket_name) when GCS state sync is active, or ('', '')."""
        use_offline = os.environ.get("SEED_OFFLINE_MODE", "").lower() in {"1", "true", "yes"}
        sync_enabled = (
            os.environ.get("AGENT_RUNTIME_DEPLOY") == "1"
            or os.environ.get("T02_ENABLE_GCS_STATE") == "1"
        )
        if use_offline or not sync_enabled:
            return "", ""
        project = (
            os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("AGENT_ENGINE_PROJECT")
            or ""
        ).strip()
        raw_bucket = (os.environ.get("STAGING_BUCKET") or "").strip()
        if not raw_bucket and project:
            raw_bucket = f"{project}-hackathon-staging"
        bucket_name = raw_bucket.removeprefix("gs://").strip("/")
        return project, bucket_name

    def create_empty_state(self) -> dict[str, Any]:
        """Create an empty state dictionary with all standard table collections."""
        return {
            "published_layouts": [],
            "render_queue": [],
            "promo_banners": [],
            "storefront_previews": [],
            "a2a_handshakes": [],
            "memories": [],
            "model_routings": [],
            "gemini_enterprise_registrations": [],
        }

    def ensure_state_keys(self, data: dict[str, Any]) -> dict[str, Any]:
        """Ensure all required list collections exist in the state dictionary."""
        for key in (
            "published_layouts",
            "render_queue",
            "promo_banners",
            "storefront_previews",
            "a2a_handshakes",
            "memories",
            "model_routings",
            "gemini_enterprise_registrations",
        ):
            if key not in data or not isinstance(data[key], list):
                data[key] = []
        return data

    def load_state(self) -> dict[str, Any]:
        """Load state from local file or GCS, falling back to an empty structure."""
        env_file = os.environ.get("T02_LOCAL_STATE_FILE", "").strip()
        if env_file:
            env_path = Path(env_file)
            if env_path.exists():
                try:
                    loaded = json.loads(env_path.read_text(encoding="utf-8"))
                    return self.ensure_state_keys(loaded)
                except Exception:
                    pass
            return self.create_empty_state()

        for candidate in (self.default_state_path, self.fallback_state_path):
            if candidate.exists():
                try:
                    loaded = json.loads(candidate.read_text(encoding="utf-8"))
                    return self.ensure_state_keys(loaded)
                except Exception:
                    continue

        project, bucket_name = self.resolve_gcs_target()
        if bucket_name:
            try:
                from google.cloud import storage

                client = storage.Client(project=project or None)
                blob = client.bucket(bucket_name).blob(_GCS_STATE_BLOB_PATH)
                if blob.exists():
                    loaded = json.loads(blob.download_as_text(encoding="utf-8"))
                    return self.ensure_state_keys(loaded)
            except Exception:
                pass

        return self.create_empty_state()

    def save_state(self, state: dict[str, Any]) -> str:
        """Persist state to local file and optionally GCS."""
        payload = json.dumps(state, indent=2)
        local_written = ""

        env_file = os.environ.get("T02_LOCAL_STATE_FILE", "").strip()
        if env_file:
            target = Path(env_file)
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(payload, encoding="utf-8")
                local_written = str(target)
            except OSError:
                pass
        else:
            for candidate in (self.default_state_path, self.fallback_state_path):
                try:
                    candidate.parent.mkdir(parents=True, exist_ok=True)
                    candidate.write_text(payload, encoding="utf-8")
                    local_written = str(candidate)
                    break
                except OSError:
                    continue

        project, bucket_name = self.resolve_gcs_target()
        if bucket_name:
            try:
                from google.cloud import storage

                client = storage.Client(project=project or None)
                blob = client.bucket(bucket_name).blob(_GCS_STATE_BLOB_PATH)
                blob.upload_from_string(payload, content_type="application/json")
                gcs_uri = f"gs://{bucket_name}/{_GCS_STATE_BLOB_PATH}"
                return f"{gcs_uri}+{local_written}" if local_written else gcs_uri
            except Exception:
                pass

        return local_written or "memory-only"
