"""Exercise install/update/rollback on a synthetic target, without accounts."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def manifest(target):
    result = {}
    for line in (target / "harness/.manifest").read_text().splitlines():
        digest, name = line.split("  ", 1)
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe managed manifest")
        result[name] = digest
    return result


class TaskReleaseTests(unittest.TestCase):
    def test_install_update_and_rollback_preserve_content_and_portable_context(self):
        with tempfile.TemporaryDirectory(prefix="thinker-release-") as tmp:
            root = Path(tmp).resolve()
            home = root / "home"
            home.mkdir()
            env = {"PATH": os.environ["PATH"], "HOME": str(home),
                   "PYTHONDONTWRITEBYTECODE": "1", "CODEX_HOME": str(home / "codex"),
                   "CLAUDE_CONFIG_DIR": str(home / "claude"), "XDG_STATE_HOME": str(home / "xdg")}

            def run(args, cwd=ROOT):
                result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                                        capture_output=True, text=True, timeout=90)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return result.stdout

            archive = subprocess.check_output(["git", "archive", "v7.22.1"], cwd=ROOT)
            baseline = root / "baseline-source"
            baseline.mkdir()
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                for member in tar.getmembers():
                    path = baseline / member.name
                    self.assertTrue(path.resolve().is_relative_to(baseline))
                    self.assertTrue(member.isdir() or member.isfile())
                    if member.isdir():
                        path.mkdir(parents=True, exist_ok=True)
                    else:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(tar.extractfile(member).read())
                        path.chmod(member.mode & 0o755)
            target = root / "synthetic-target"
            run(["bash", baseline / "install.sh", "--init", target])
            old_manifest = manifest(target)
            source = target / "source.md"
            source.write_text("Synthetic source: deadline Thursday; analysis only.\n")
            settings = target / ".claude/settings.json"
            config = json.loads(settings.read_text())
            config.setdefault("permissions", {}).setdefault("deny", []).append("Bash(synthetic-prohibited-command)")
            settings.write_text(json.dumps(config))
            content_files = [source, target / "vault.config.json", target / "wiki/log.md"]
            before = {str(p): p.read_bytes() for p in content_files}
            run(["bash", ROOT / "install.sh", target, "--update"])
            self.assertEqual((ROOT / "VERSION").read_text().strip(), (target / "harness/.version").read_text().strip())
            candidate_manifest = manifest(target)
            cli = [sys.executable, "-B", target / "harness/scripts/task.py",
                   "--workspace", target, "--state-dir", root / "task-state"]
            task = json.loads(run(cli + ["create", "--title", "Rollback exercise", "--objective", "Preserve corrected decision"]))
            checkpoint = root / "checkpoint.json"
            checkpoint.write_text(json.dumps({"schema": 1, "state": "Awaiting revised proposal",
                "decisions": [{"id": "deadline", "text": "OLD_FRIDAY", "status": "proposed"}],
                "corrections": [{"id": "correction", "supersedes": "deadline", "text": "CURRENT_THURSDAY"}],
                "constraints": [{"id": "scope", "text": "ANALYSIS_ONLY", "critical": True}],
                "pending": [{"id": "next", "text": "REVISE_PROPOSAL", "status": "open"}],
                "evidence": [{"path": "source.md", "critical": True}]}))
            run(cli + ["checkpoint", task["task_id"], "--expected-revision", "1", "--request-id", "release-checkpoint", "--file", checkpoint])
            run(cli + ["export", task["task_id"], "--name", "portable.md"])
            handoff = root / "task-state/exports/portable.md"
            exported = handoff.read_text()
            for marker in ("CURRENT_THURSDAY", "ANALYSIS_ONLY", "REVISE_PROPOSAL"):
                self.assertIn(marker, exported)
            self.assertNotIn("OLD_FRIDAY", exported)
            # Preflight ALL extras before any removal. Preserve modified files.
            extras = sorted(set(candidate_manifest) - set(old_manifest))
            self.assertTrue(extras)
            for name in extras:
                path = target / name
                self.assertFalse(any(p.is_symlink() for p in (path, *path.parents)))
                self.assertEqual(candidate_manifest[name], hashlib.sha256(path.read_bytes()).hexdigest())
            run(["bash", baseline / "install.sh", target, "--update"])
            for name in extras:
                (target / name).unlink()
            self.assertEqual("7.22.1", (target / "harness/.version").read_text().strip())
            self.assertEqual(set(old_manifest), set(manifest(target)))
            for name, digest in manifest(target).items():
                self.assertEqual(digest, hashlib.sha256((target / name).read_bytes()).hexdigest())
            self.assertEqual(before, {str(p): p.read_bytes() for p in content_files})
            self.assertIn("Bash(synthetic-prohibited-command)", json.loads(settings.read_text())["permissions"]["deny"])
            self.assertEqual(exported, handoff.read_text())
            self.assertFalse((target / "harness/scripts/task.py").exists())
            run(["bash", "harness/scripts/verify.sh"], cwd=target)
