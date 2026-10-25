import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "payload/harness/scripts/release.py"
sys.path.insert(0, str(SCRIPT.parent))
import release  # noqa: E402

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_NOSYSTEM": "1"}


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, env=ENV, capture_output=True, text=True, check=True).stdout.strip()


class ReleaseHelperTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="release-helper-")
        base = Path(self.tmp.name)
        self.remote = base / "remote.git"
        self.repo = base / "work"
        sh(base, "git", "init", "-q", "--bare", "-b", "main", str(self.remote))
        sh(base, "git", "init", "-q", "-b", "main", str(self.repo))
        sh(self.repo, "git", "remote", "add", "origin", str(self.remote))
        self.commit("VERSION", "1.0.0\n", "init")
        sh(self.repo, "git", "tag", "-a", "v1.0.0", "-m", "v1.0.0")
        sh(self.repo, "git", "push", "-q", "origin", "main", "v1.0.0")

    def tearDown(self):
        self.tmp.cleanup()

    def commit(self, name, text, message):
        (self.repo / name).write_text(text, encoding="utf-8")
        sh(self.repo, "git", "add", name)
        sh(self.repo, "git", "commit", "-q", "-m", message)
        return sh(self.repo, "git", "rev-parse", "HEAD")

    def run_helper(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), *args],
                                env=ENV, capture_output=True, text=True)
        return result.returncode, json.loads(result.stdout)

    def remote_tags(self):
        return sorted(sh(self.remote, "git", "tag", "--list").splitlines())

    def test_next_version_drops_suffix_and_bumps_last_number_by_default(self):
        self.assertEqual("7.23.0", release.next_version("7.23.0-rc.14"))
        self.assertEqual("7.23.1", release.next_version("7.23.0"))
        self.assertEqual("7.24.0", release.next_version("7.23.4", "minor"))
        self.assertEqual("8.0.0", release.next_version("7.23.4", "major"))
        self.assertLess(release.version_key("7.3.0"), release.version_key("7.23.0"))
        self.assertLess(release.version_key("7.23.0-rc.14"), release.version_key("7.23.0"))

    def test_check_suggests_next_version_and_lists_ahead_and_pending(self):
        self.commit("VERSION", "1.0.1\n", "bump")
        (self.repo / "scratch.txt").write_text("x", encoding="utf-8")
        code, data = self.run_helper("check", "--current", "1.0.0")
        self.assertEqual(0, code, data)
        self.assertEqual("1.0.1", data["next_version"])
        self.assertEqual(1, len(data["ahead"]))
        self.assertTrue(any("scratch.txt" in line for line in data["pending"]))

    def test_check_refuses_lower_version_existing_tag_and_prerelease(self):
        code, data = self.run_helper("check", "--version", "0.9.0")
        self.assertEqual(1, code)
        self.assertTrue(any("não é maior" in p for p in data["problems"]))
        code, data = self.run_helper("check", "--version", "1.0.0")
        self.assertTrue(any("já existe" in p for p in data["problems"]))
        code, data = self.run_helper("check", "--version", "1.1.0-rc.1")
        self.assertTrue(any("pré-lançamento" in p for p in data["problems"]))

    def test_check_flags_local_behind_remote(self):
        other = Path(self.tmp.name) / "other"
        sh(Path(self.tmp.name), "git", "clone", "-q", str(self.remote), str(other))
        (other / "x.txt").write_text("x", encoding="utf-8")
        sh(other, "git", "add", "x.txt")
        sh(other, "git", "commit", "-q", "-m", "remote work")
        sh(other, "git", "push", "-q", "origin", "main")
        code, data = self.run_helper("check")
        self.assertEqual(1, code)
        self.assertEqual(1, data["behind"])

    def test_push_sends_only_release_tag_even_with_follow_tags(self):
        sh(self.repo, "git", "config", "push.followTags", "true")
        self.commit("a.txt", "a", "feature")
        sh(self.repo, "git", "tag", "-a", "stray", "-m", "stray annotated tag")
        head = self.commit("VERSION", "1.0.1\n", "release 1.0.1")
        self.assertEqual(0, self.run_helper("tag", "--version", "1.0.1", "--message", "v1.0.1 — test")[0])
        code, data = self.run_helper("push", "--version", "1.0.1")
        self.assertEqual(0, code, data)
        self.assertEqual(head, data["remote_branch"])
        self.assertEqual(head, data["remote_tag"])
        self.assertEqual(["v1.0.0", "v1.0.1"], self.remote_tags())

    def test_push_refuses_when_tag_is_not_head(self):
        self.commit("VERSION", "1.0.1\n", "release 1.0.1")
        self.run_helper("tag", "--version", "1.0.1")
        self.commit("late.txt", "late", "after tag")
        code, data = self.run_helper("push", "--version", "1.0.1")
        self.assertEqual(2, code)
        self.assertEqual("tag_mismatch", data["error"])
        self.assertEqual(["v1.0.0"], self.remote_tags())

    def test_push_refuses_non_fast_forward(self):
        other = Path(self.tmp.name) / "other"
        sh(Path(self.tmp.name), "git", "clone", "-q", str(self.remote), str(other))
        (other / "x.txt").write_text("x", encoding="utf-8")
        sh(other, "git", "add", "x.txt")
        sh(other, "git", "commit", "-q", "-m", "remote work")
        sh(other, "git", "push", "-q", "origin", "main")
        self.commit("VERSION", "1.0.1\n", "release 1.0.1")
        self.run_helper("tag", "--version", "1.0.1")
        code, data = self.run_helper("push", "--version", "1.0.1")
        self.assertEqual(2, code)
        self.assertEqual("not_fast_forward", data["error"])

    def test_tag_refuses_existing_remote_tag(self):
        self.commit("VERSION", "1.0.1\n", "release 1.0.1")
        sh(self.repo, "git", "tag", "-d", "v1.0.0")
        code, data = self.run_helper("tag", "--version", "1.0.0")
        self.assertEqual(2, code)
        self.assertEqual("not_releasable", data["error"])
        self.assertIn("já existe", data["message"])

    def test_tag_and_push_enforce_version_policy(self):
        self.commit("VERSION", "1.0.1\n", "release")
        for version in ("0.9.0", "1.1.0-rc.1"):
            code, data = self.run_helper("tag", "--version", version)
            self.assertEqual(2, code, version)
            self.assertEqual("not_releasable", data["error"])
        sh(self.repo, "git", "tag", "-a", "v0.9.0", "-m", "manual lower tag")
        code, data = self.run_helper("push", "--version", "0.9.0")
        self.assertEqual(2, code)
        self.assertEqual("not_releasable", data["error"])
        self.assertEqual(["v1.0.0"], self.remote_tags())

    def test_push_refuses_lightweight_tag(self):
        self.commit("VERSION", "1.0.1\n", "release")
        sh(self.repo, "git", "tag", "v1.0.1")
        code, data = self.run_helper("push", "--version", "1.0.1")
        self.assertEqual(2, code)
        self.assertEqual("tag_not_annotated", data["error"])
        self.assertEqual(["v1.0.0"], self.remote_tags())

    def test_first_release_to_remote_without_branch(self):
        empty = Path(self.tmp.name) / "empty.git"
        sh(Path(self.tmp.name), "git", "init", "-q", "--bare", "-b", "main", str(empty))
        sh(self.repo, "git", "remote", "add", "fresh", str(empty))
        code, data = self.run_helper("--remote", "fresh", "check", "--current", "1.0.0")
        self.assertEqual(0, code, data)
        self.assertIsNone(data["remote_branch"])
        self.commit("VERSION", "1.0.1\n", "release")
        self.assertEqual(0, self.run_helper("--remote", "fresh", "tag", "--version", "1.0.1")[0])
        code, data = self.run_helper("--remote", "fresh", "push", "--version", "1.0.1")
        self.assertEqual(0, code, data)
        self.assertEqual(["v1.0.1"], sorted(sh(empty, "git", "tag", "--list").splitlines()))

    def test_check_reports_diverged_local_tag(self):
        sh(self.repo, "git", "tag", "-d", "v1.0.0")
        self.commit("other.txt", "x", "elsewhere")
        sh(self.repo, "git", "tag", "-a", "v1.0.0", "-m", "moved locally")
        code, data = self.run_helper("check", "--current", "1.0.0")
        self.assertEqual(2, code)
        self.assertEqual("tag_diverged", data["error"])
        self.assertIn("v1.0.0", data["message"])

    def test_empty_version_file_is_reported_as_json(self):
        self.commit("VERSION", "\n", "empty version")
        code, data = self.run_helper("check")
        self.assertEqual(2, code)
        self.assertEqual("invalid_version", data["error"])

    def test_prerelease_parts_compare_numerically_and_ignored_bump_is_reported(self):
        self.assertLess(release.version_key("7.23.0-rc.9"), release.version_key("7.23.0-rc.14"))
        code, data = self.run_helper("check", "--current", "1.1.0-rc.3", "--bump", "minor")
        self.assertEqual("1.1.0", data["next_version"])
        self.assertTrue(data["notes"])

    def test_verify_reports_unpushed_release(self):
        self.commit("VERSION", "1.0.1\n", "release 1.0.1")
        self.run_helper("tag", "--version", "1.0.1")
        code, data = self.run_helper("verify", "--version", "1.0.1")
        self.assertEqual(1, code)
        self.assertEqual(2, len(data["problems"]))


if __name__ == "__main__":
    unittest.main()
