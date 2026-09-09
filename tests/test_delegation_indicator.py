#!/usr/bin/env python3
"""Indicador compacto: estado externo, sanitizado e sem progresso inventado."""
import datetime as dt
import fcntl
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload/harness/scripts"))
from thinker_delegation import board  # noqa: E402


class IndicatorRenderTests(unittest.TestCase):
    def test_compact_counts_and_sanitized_models(self):
        data = {"board": {"queued": 1, "running": 2, "pending": 3, "failed": 4},
                "jobs": [{"agent": "luna\x1b[31m", "state": "running"},
                         {"agent": "sonnet", "state": "queued"},
                         {"agent": "luna\x1b[31m", "state": "running"}]}
        text = board.render_indicator(data)
        self.assertEqual("delegacao externa: q1 r2 p3 f4 · luna, sonnet · nativa reportada: r0 c0 f0 u0", text)
        self.assertNotIn("%", text)
        self.assertNotIn("\x1b", text)

    def test_empty_snapshot_is_explicitly_zero_not_unknown(self):
        data = {"board": {"queued": 0, "running": 0, "pending": 0, "failed": 0}, "jobs": []}
        self.assertEqual("delegacao externa: q0 r0 p0 f0 · nativa reportada: r0 c0 f0 u0", board.render_indicator(data))


class IndicatorCLITests(unittest.TestCase):
    def install(self, root):
        scripts = root / "scripts"
        scripts.mkdir()
        shutil.copy(ROOT / "payload/harness/scripts/delegation-indicator.py", scripts)
        shutil.copytree(ROOT / "payload/harness/scripts/thinker_delegation", scripts / "thinker_delegation",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return scripts

    def test_inaccessible_state_is_unknown_and_nonblocking(self):
        with tempfile.TemporaryDirectory(prefix="delegation-indicator-") as directory:
            root = Path(directory)
            scripts = self.install(root)
            result = subprocess.run([sys.executable, "-B", str(scripts / "delegation-indicator.py"),
                                     "--vault", str(root / "missing")],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode)
        self.assertEqual("delegacao externa: estado desconhecido\n", result.stdout)

    def test_lock_contention_is_unknown_without_waiting(self):
        with tempfile.TemporaryDirectory(prefix="delegation-indicator-") as directory:
            root = Path(directory)
            scripts = self.install(root)
            vault, state = root / "vault", root / "state"
            vault.mkdir()
            state.mkdir(mode=0o700)
            (state / ".lock").touch(mode=0o600)
            with (state / ".lock").open("rb") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                result = subprocess.run([sys.executable, "-B", str(scripts / "delegation-indicator.py"),
                                         "--vault", str(vault), "--state-dir", str(state)],
                                        capture_output=True, text=True, timeout=2)
        self.assertEqual(0, result.returncode)
        self.assertEqual("delegacao externa: estado desconhecido\n", result.stdout)

    def test_fresh_real_cli_is_healthy_and_has_no_traceback(self):
        with tempfile.TemporaryDirectory(prefix="delegation-indicator-") as directory:
            root = Path(directory)
            scripts = self.install(root)
            vault = root / "vault"
            vault.mkdir()
            result = subprocess.run([sys.executable, "-B", str(scripts / "delegation-indicator.py"),
                                     "--vault", str(vault)], capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode)
        self.assertEqual("delegacao externa: q0 r0 p0 f0 · nativa reportada: r0 c0 f0 u0\n", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_populated_real_cli_renders_reported_state(self):
        with tempfile.TemporaryDirectory(prefix="delegation-indicator-") as directory:
            root = Path(directory)
            scripts = self.install(root)
            vault, state = root / "vault", root / "state"
            vault.mkdir(); state.mkdir(mode=0o700)
            identifier = "00000000-0000-4000-8000-000000000001"
            job_path = state / "jobs" / identifier / "job.json"
            job_path.parent.mkdir(parents=True)
            job_path.write_text(json.dumps({"id": identifier, "vault": str(vault.resolve()),
                                            "session": "host-a", "state": "running", "validation": "pending",
                                            "profile": {"model": "gpt-5.6-luna", "requested_profile": "luna"},
                                            "reason": "fixture"}), encoding="utf-8")
            (state / ".lock").touch(mode=0o600)
            result = subprocess.run([sys.executable, "-B", str(scripts / "delegation-indicator.py"),
                                     "--vault", str(vault), "--state-dir", str(state), "--session", "host-a"],
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode)
        self.assertIn("q0 r1 p0 f0 · luna", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_claude_statusline_empty_stdin_uses_all_sessions_fallback(self):
        with tempfile.TemporaryDirectory(prefix="delegation-indicator-") as directory:
            root = Path(directory)
            scripts = self.install(root)
            vault, state = root / "vault", root / "state"
            vault.mkdir(); state.mkdir(mode=0o700)
            for tail, session in (("2", "host-a"), ("3", "host-b")):
                identifier = "00000000-0000-4000-8000-00000000000" + tail
                path = state / "jobs" / identifier / "job.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({"id": identifier, "vault": str(vault.resolve()),
                                            "session": session, "state": "queued", "validation": "pending",
                                            "profile": {"requested_profile": "luna"}, "reason": "fixture"}),
                                encoding="utf-8")
            (state / ".lock").touch(mode=0o600)
            result = subprocess.run([sys.executable, "-B", str(scripts / "delegation-indicator.py"),
                                     "--vault", str(vault), "--state-dir", str(state), "--claude-statusline"], input="",
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(0, result.returncode)
        self.assertIn("delegacao externa: q2 r0 p0 f0 · luna", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
