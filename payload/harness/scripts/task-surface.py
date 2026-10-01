#!/usr/bin/env python3
"""Read-only, loopback viewer for an explicitly exported task projection."""
import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import stat
import sys
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
MAX_SNAPSHOT = 4 * 1024 * 1024
ASSETS = Path(__file__).resolve().parents[1] / "task-surface"


def read_snapshot(path):
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("Projection unavailable")
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Projection must be a regular file")
            raw = stream.read(MAX_SNAPSHOT + 1)
    finally:
        os.close(directory)
    if len(raw) > MAX_SNAPSHOT:
        raise ValueError("Projection exceeds limit")
    value = json.loads(raw)
    if not isinstance(value, dict) or value.get("schema") != 1:
        raise ValueError("Unsupported projection")
    if not isinstance(value.get("tasks"), list) or not isinstance(value.get("attention"), list):
        raise ValueError("Invalid projection")
    return raw


def make_server(snapshot, port=0):
    snapshot = Path(snapshot).absolute()
    # The projection is the only data file this process can serve.
    for part in (snapshot, *snapshot.parents):
        if part.is_symlink():
            raise ValueError("Use a canonical projection path without symlinks")
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Tokens and task content must not enter HTTP access logs.

        def send(self, status, body, mime="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            host = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != host:
                return self.send(403, b'{"error":"host_rejected"}')
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + host:
                return self.send(403, b'{"error":"origin_rejected"}')
            route = urlsplit(self.path)
            if route.query:
                return self.send(404, b'{"error":"not_found"}')
            if route.path == "/snapshot":
                if not hmac.compare_digest(self.headers.get("X-Thinker-Token", ""), token):
                    return self.send(403, b'{"error":"access_denied"}')
                try:
                    return self.send(200, read_snapshot(snapshot))
                except (OSError, ValueError, json.JSONDecodeError):
                    return self.send(503, b'{"error":"projection_unavailable"}')
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/style.css": ("style.css", "text/css; charset=utf-8")}
            if route.path not in assets:
                return self.send(404, b'{"error":"not_found"}')
            name, mime = assets[route.path]
            return self.send(200, (ASSETS / name).read_bytes(), mime)

        def do_POST(self):
            self.send(405, b'{"error":"read_only"}')

        do_PUT = do_PATCH = do_DELETE = do_POST

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    try:
        server, token = make_server(args.snapshot, args.port)
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/#{token}",
                          "mode": "read_only", "projection": "explicit_snapshot"}), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
