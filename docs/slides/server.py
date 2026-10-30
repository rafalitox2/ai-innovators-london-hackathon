"""Standalone Cloud Run HTTP server for the Table 2 Executive Presentation Deck."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path

SLIDES_DIR = Path(__file__).resolve().parent
DECK_FILE = SLIDES_DIR / "t02_executive_deck.html"


def load_deck_html() -> str:
    """Load the executive presentation HTML5 deck from disk."""
    if not DECK_FILE.exists():
        raise FileNotFoundError(f"Executive presentation deck not found at {DECK_FILE}")
    return DECK_FILE.read_text(encoding="utf-8")


class SlidesRequestHandler(BaseHTTPRequestHandler):
    """Security-hardened HTTP handler serving the Table 2 Executive Slide Deck."""

    def _send_security_headers(self, content_type: str) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Cache-Control", "no-cache, max-age=0")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in {"/health", "/healthz", "/api/health"}:
            payload = json.dumps(
                {
                    "status": "ONLINE",
                    "service": "t02-executive-slides",
                    "seed_pack": "t02_dynamic_storefronts",
                    "deck_file": DECK_FILE.name,
                    "routes": ["/", "/slides", "/presentation", "/health"],
                },
                indent=2,
            ).encode("utf-8")
            self.send_response(200)
            self._send_security_headers("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path in {"/", "/slides", "/presentation", "/t02_executive_deck.html"}:
            body = load_deck_html().encode("utf-8")
            self.send_response(200)
            self._send_security_headers("text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        not_found = json.dumps({"status": "NOT_FOUND", "path": path}).encode("utf-8")
        self.send_response(404)
        self._send_security_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(not_found)))
        self.end_headers()
        self.wfile.write(not_found)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return


def main() -> None:
    """Start the standalone executive presentation HTTP server."""
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), SlidesRequestHandler)
    print(f"[t02-executive-slides] Listening on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
