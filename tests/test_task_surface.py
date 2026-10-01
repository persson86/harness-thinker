"""Exercise the HTTP boundary, not just rendering helpers."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

PATH = Path(__file__).resolve().parents[1] / "payload/harness/scripts/task-surface.py"
SPEC = importlib.util.spec_from_file_location("task_surface", PATH)
surface = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(surface)


class SurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.snapshot = self.root / "snapshot.json"
        self.snapshot.write_text(json.dumps({"schema": 1, "tasks": [], "attention": []}))
        self.server, self.token = surface.make_server(self.snapshot)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, method="GET", **headers):
        request = urllib.request.Request(self.base + path, method=method, headers=headers)
        try:
            return urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            return error

    def test_projection_requires_token_and_never_cors(self):
        self.assertEqual(self.request("/snapshot").status, 403)
        response = self.request("/snapshot", **{"X-Thinker-Token": self.token})
        self.assertEqual(response.status, 200)
        self.assertEqual(json.load(response)["tasks"], [])
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
        self.assertEqual(self.request("/snapshot", **{"X-Thinker-Token": self.token, "Origin": "https://evil.invalid"}).status, 403)

    def test_rebinding_mutation_and_traversal_refused(self):
        self.assertEqual(self.request("/", Host="evil.invalid").status, 403)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertEqual(self.request("/snapshot", method).status, 405)
        for path in ("/../snapshot.json", "/%2e%2e/snapshot.json", "/snapshot?path=/etc/passwd"):
            self.assertEqual(self.request(path).status, 404)

    def test_corruption_never_returns_previous_good_data(self):
        headers = {"X-Thinker-Token": self.token}
        self.assertEqual(self.request("/snapshot", **headers).status, 200)
        self.snapshot.write_text("{")
        self.assertEqual(self.request("/snapshot", **headers).status, 503)
        self.snapshot.write_text(json.dumps({"schema": 2, "tasks": [], "attention": []}))
        self.assertEqual(self.request("/snapshot", **headers).status, 503)

    def test_symlink_replacement_not_served(self):
        other = self.root / "other.json"
        other.write_text(self.snapshot.read_text())
        self.snapshot.unlink()
        self.snapshot.symlink_to(other)
        self.assertEqual(self.request("/snapshot", **{"X-Thinker-Token": self.token}).status, 503)

    def test_assets_have_inert_content_policy(self):
        response = self.request("/")
        self.assertEqual(response.status, 200)
        self.assertIn("script-src 'self'", response.headers["Content-Security-Policy"])
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
