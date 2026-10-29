"""Local HTTP server for the Table 2 UI mockup + /api/recreate-hero-image endpoint."""
from __future__ import annotations

import json
import os
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from seed_packs.t02_dynamic_storefronts.mcp_server import generate_hero_lifestyle_image

UI_DIR = Path(__file__).resolve().parent


class StorefrontPreviewHandler(SimpleHTTPRequestHandler):
    """Serves static UI files and handles POST /api/recreate-hero-image."""

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") == "/api/recreate-hero-image":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
                payload = json.loads(raw_body or "{}")
                result_str = generate_hero_lifestyle_image(
                    sku_id=str(payload.get("primary_sku") or payload.get("sku_id") or "SKU-0001"),
                    segment_id=str(payload.get("segment_id") or "SEG-001"),
                    style_theme=str(payload.get("style_theme") or "Nordic_Minimal"),
                    scene_description=str(payload.get("scene_description") or "Editorial interior lifestyle scene"),
                    aspect_ratio=str(payload.get("aspect_ratio") or "16:9"),
                )
                body_bytes = result_str.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body_bytes)))
                self.end_headers()
                self.wfile.write(body_bytes)
            except Exception as exc:
                err_bytes = json.dumps({"status": "ERROR", "error": str(exc)}).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(err_bytes)))
                self.end_headers()
                self.wfile.write(err_bytes)
            return
        self.send_error(404, "Endpoint not found")


def main() -> None:
    port = int(os.environ.get("PORT", "8765"))
    handler = partial(StorefrontPreviewHandler, directory=str(UI_DIR))
    server = HTTPServer(("127.0.0.1", port), handler)
    print(f"Serving Table 2 UI + /api/recreate-hero-image on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
