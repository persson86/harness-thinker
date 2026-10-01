"""Projection filesystem boundary; no port or browser required."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("projection", Path(__file__).resolve().parents[1] / "payload/harness/scripts/task-surface.py")
surface = importlib.util.module_from_spec(spec)
spec.loader.exec_module(surface)


class ProjectionTests(unittest.TestCase):
    def test_snapshot_read_and_unsafe_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            folder = root / "snapshots"
            folder.mkdir()
            path = folder / "snapshot.json"
            payload = {"schema": 1, "tasks": [], "attention": []}
            path.write_text(json.dumps(payload))
            self.assertEqual(payload, json.loads(surface.read_snapshot(path)))
            folder.rename(root / "moved")
            folder.symlink_to(root / "moved", target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                surface.read_snapshot(path)
            folder.unlink()
            folder.mkdir()
            path.symlink_to(root / "moved/snapshot.json")
            with self.assertRaises((OSError, ValueError)):
                surface.read_snapshot(path)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                surface.read_snapshot(path)

    def test_size_and_schema_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "snapshot.json"
            for content in ('{', '{"schema":2,"tasks":[],"attention":[]}', 'x' * (surface.MAX_SNAPSHOT + 1)):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    surface.read_snapshot(path)
