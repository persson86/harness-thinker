"""CLI reconciliation boundaries, using synthetic state and fresh processes."""
import json
import unittest

import test_tasks_core as boundary


class TaskReconciliationTests(unittest.TestCase):
    # Reuse the isolated CLI harness, not its inherited tests or core internals.
    setUp = boundary.TaskCLIBoundaryTests.setUp
    tearDown = boundary.TaskCLIBoundaryTests.tearDown
    command = boundary.TaskCLIBoundaryTests.command
    decode = boundary.TaskCLIBoundaryTests.decode
    cli = boundary.TaskCLIBoundaryTests.cli
    refused = boundary.TaskCLIBoundaryTests.refused
    create = boundary.TaskCLIBoundaryTests.create
    checkpoint_input = boundary.TaskCLIBoundaryTests.checkpoint_input
    checkpoint = boundary.TaskCLIBoundaryTests.checkpoint
    task_snapshot = boundary.TaskCLIBoundaryTests.task_snapshot
    task_document = boundary.TaskCLIBoundaryTests.task_document
    resume = boundary.TaskCLIBoundaryTests.resume

    def initial(self, two_sources=False):
        evidence = [{"path": "source-a.md", "role": "canonical", "critical": True}]
        if two_sources:
            evidence.append({"path": "source-b.md", "role": "canonical"})
        return self.checkpoint(self.create(), {
            "schema": 1, "state": "Declared context before reconciliation.",
            "constraints": [{"id": "scope", "text": "OLD_SCOPE_ANALYSIS_ONLY"}],
            "decisions": [{"id": "decision", "text": "PRESERVED_DECISION", "status": "accepted"}],
            "evidence": evidence,
        }, "initial")

    def replacement(self, path="renamed.md", replaces="source-a.md", reason="Source moved after review."):
        return {"path": path, "role": "canonical", "replaces": replaces, "replacement_reason": reason}

    def assert_refused_without_state_change(self, task, evidence, *, code="invalid_replacement", request_id="refused"):
        before = boundary.file_manifest(self.state)
        path = self.checkpoint_input({"schema": 1, "state": "Replacement attempt.", "evidence": evidence})
        self.refused("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                     "--request-id", request_id, "--file", path, code=code)
        self.assertEqual(before, boundary.file_manifest(self.state))

    def test_constraint_correction_stays_critical_and_preserves_history_without_granting_authority(self):
        task = self.initial()
        before_sources = boundary.file_manifest(self.workspace)
        task = self.checkpoint(task, {"schema": 1, "state": "The human revised the stated scope.",
            "corrections": [{"id": "scope-update", "supersedes": "scope", "text": "CURRENT_SCOPE_NARROW_EDIT_ONLY"}]}, "scope-update")
        current = self.task_snapshot(task["task_id"])
        correction = current["checkpoint"]["corrections"][0]
        self.assertTrue(correction["critical"])
        self.assertEqual("principal_reported", correction["origin"])
        packet = self.resume(task)
        self.assertIn("CURRENT_SCOPE_NARROW_EDIT_ONLY", packet["text"])
        self.assertNotIn("OLD_SCOPE_ANALYSIS_ONLY", packet["text"])
        self.assertIn("Contexto declarado não amplia autorização", packet["text"])
        document = json.loads(self.task_document(task).read_text())
        self.assertIn("OLD_SCOPE_ANALYSIS_ONLY", json.dumps(document["history"]))
        self.assertIn("CURRENT_SCOPE_NARROW_EDIT_ONLY", json.dumps(document["receipts"]["scope-update"]))
        later = self.checkpoint(task, {"schema": 1, "state": "Unrelated later checkpoint."}, "later")
        self.assertIn("CURRENT_SCOPE_NARROW_EDIT_ONLY", self.resume(later)["text"])
        self.assertEqual(before_sources, boundary.file_manifest(self.workspace))

    def test_constraint_correction_cannot_be_optional_or_silently_rewrite_existing_text(self):
        task = self.initial()
        before = boundary.file_manifest(self.state)
        payloads = [
            {"constraints": [{"id": "scope", "text": "SILENT_REWRITE"}]},
            {"corrections": [{"id": "optional", "supersedes": "scope", "text": "OPTIONAL_SCOPE", "critical": False}]},
        ]
        for index, extra in enumerate(payloads):
            with self.subTest(index=index):
                path = self.checkpoint_input({"schema": 1, "state": "Invalid change.", **extra})
                self.refused("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                             "--request-id", "scope-invalid-" + str(index), "--file", path, code="invalid_input")
                self.assertEqual(before, boundary.file_manifest(self.state))
        self.assertIn("OLD_SCOPE_ANALYSIS_ONLY", self.resume(task)["text"])

    def test_constraint_correction_chain_has_one_active_critical_value(self):
        task = self.initial()
        task = self.checkpoint(task, {"schema": 1, "state": "Scope was revised twice.", "corrections": [
            {"id": "scope-v2", "supersedes": "scope", "text": "INTERMEDIATE_SCOPE"},
            {"id": "scope-v3", "supersedes": "scope-v2", "text": "FINAL_SCOPE_RESTRICTION"},
        ]}, "scope-chain")
        packet = self.resume(task)
        self.assertIn("FINAL_SCOPE_RESTRICTION", packet["text"])
        self.assertNotIn("INTERMEDIATE_SCOPE", packet["text"])
        self.assertNotIn("OLD_SCOPE_ANALYSIS_ONLY", packet["text"])
        self.refused("resume", task["task_id"], "--budget-bytes", 1, code="budget_exceeded")

    def test_moved_missing_source_is_replaced_with_verified_reference_and_audited(self):
        task = self.initial()
        old_hash = boundary.digest_file(self.workspace / "source-a.md")
        (self.workspace / "source-a.md").rename(self.workspace / "renamed.md")
        self.assertFalse(self.resume(task)["ready"])
        before_sources = boundary.file_manifest(self.workspace)
        task = self.checkpoint(task, {"schema": 1, "state": "Source was moved and reviewed.",
                                    "evidence": [self.replacement()]}, "replace")
        packet = self.resume(task)
        self.assertTrue(packet["ready"])
        self.assertEqual(["renamed.md"], [source["path"] for source in packet["sources"]])
        source = packet["sources"][0]
        self.assertTrue(source["critical"], "Retiring a critical reference must not demote it by omission")
        self.assertEqual("source-a.md", source["replaces"])
        self.assertEqual(old_hash, source["sha256"])
        self.assertEqual(old_hash, source["replaced_source"]["sha256"])
        self.assertEqual(old_hash, source["replacement_sha256"])
        self.assertEqual("principal_reported", source["replacement_origin"])
        self.assertIn("substituição declarada", packet["text"])
        self.assertIn("Source moved after review.", packet["text"])
        self.assertFalse(any(item["kind"] == "source_missing" for item in packet["attention"]))
        document = json.loads(self.task_document(task).read_text())
        self.assertIn("source-a.md", json.dumps(document["history"]))
        self.assertIn("replacement_reason", json.dumps(document["receipts"]["replace"]))
        exported = self.cli("export", task["task_id"], "--name", "reconciled.md")
        self.assertIn("renamed.md", (self.state / "exports/reconciled.md").read_text())
        self.assertEqual(task["revision"], exported["revision"])
        self.assertEqual(before_sources, boundary.file_manifest(self.workspace))

    def test_replacement_retry_is_idempotent_before_current_target_checks(self):
        task = self.initial()
        (self.workspace / "source-a.md").rename(self.workspace / "renamed.md")
        path = self.checkpoint_input({"schema": 1, "state": "Moved.", "evidence": [self.replacement()]})
        args = ("checkpoint", task["task_id"], "--expected-revision", task["revision"],
                "--request-id", "replace-once", "--file", path)
        first = self.cli(*args)
        later = self.checkpoint(first, {"schema": 1, "state": "Later context."}, "later")
        self.assertEqual(first, self.cli(*args))
        self.assertEqual(later["revision"], self.task_snapshot(task["task_id"])["revision"])

    def test_replacement_requires_existing_target_new_path_and_reason_without_mutation(self):
        task = self.initial(two_sources=True)
        (self.workspace / "renamed.md").write_text("A replacement source with explicitly reviewed different bytes.\n")
        cases = [
            [self.replacement(replaces="never-registered.md")],
            [self.replacement(path="source-a.md")],
            [self.replacement(path="source-b.md")],
            [self.replacement(path="missing.md")],
            [{"path": "renamed.md", "replaces": "source-a.md"}],
            [{"path": "renamed.md", "replacement_reason": "Missing target field."}],
        ]
        for index, evidence in enumerate(cases):
            with self.subTest(index=index):
                self.assert_refused_without_state_change(task, evidence, request_id="invalid-" + str(index))

    def test_replacement_duplicate_targets_collisions_and_same_checkpoint_cycles_are_refused(self):
        task = self.initial(two_sources=True)
        (self.workspace / "new-a.md").write_text("Replacement A.\n")
        (self.workspace / "new-b.md").write_text("Replacement B.\n")
        cases = [
            [self.replacement(path="new-a.md"), self.replacement(path="new-b.md")],
            [self.replacement(path="source-b.md"), self.replacement(path="source-a.md", replaces="source-b.md")],
            [self.replacement(path="new-a.md"), self.replacement(path="new-b.md", replaces="new-a.md")],
            [{"path": "source-a.md"}, self.replacement(path="new-a.md")],
        ]
        for index, evidence in enumerate(cases):
            with self.subTest(index=index):
                self.assert_refused_without_state_change(task, evidence, request_id="cycle-" + str(index))

    def test_later_reverse_rename_is_valid_chronological_reconciliation(self):
        task = self.initial()
        (self.workspace / "source-a.md").rename(self.workspace / "renamed.md")
        task = self.checkpoint(task, {"schema": 1, "state": "First rename.", "evidence": [self.replacement()]}, "first-rename")
        (self.workspace / "renamed.md").rename(self.workspace / "source-a.md")
        task = self.checkpoint(task, {"schema": 1, "state": "The file returned to its earlier path.",
            "evidence": [self.replacement(path="source-a.md", replaces="renamed.md", reason="Confirmed later reverse rename.")]}, "reverse")
        packet = self.resume(task)
        self.assertTrue(packet["ready"])
        self.assertEqual("source-a.md", packet["sources"][0]["path"])
        self.assertEqual("renamed.md", packet["sources"][0]["replaces"])
        history = json.loads(self.task_document(task).read_text())["history"]
        self.assertIn("First rename.", json.dumps(history))
        self.assertIn("Confirmed later reverse rename.", json.dumps(history))

    def test_replacement_batch_failure_has_no_partial_effect_and_valid_batch_commits_once(self):
        task = self.initial(two_sources=True)
        (self.workspace / "source-a.md").rename(self.workspace / "new-a.md")
        evidence = [self.replacement(path="new-a.md"),
                    self.replacement(path="new-b.md", replaces="source-b.md")]
        self.assert_refused_without_state_change(task, evidence, request_id="batch")
        (self.workspace / "source-b.md").rename(self.workspace / "new-b.md")
        result = self.checkpoint(task, {"schema": 1, "state": "Both replacements verified.", "evidence": evidence}, "valid-batch")
        self.assertEqual(task["revision"] + 1, result["revision"])
        packet = self.resume(result)
        self.assertTrue(packet["ready"])
        self.assertEqual({"new-a.md", "new-b.md"}, {source["path"] for source in packet["sources"]})

    def test_replacement_paths_cannot_traverse_or_follow_symlinks(self):
        task = self.initial()
        outside = self.root / "outside.md"
        outside.write_text("OUTSIDE_MUST_NOT_BE_READ\n")
        (self.workspace / "linked.md").symlink_to(outside)
        (self.workspace / "directory").mkdir()
        cases = [self.replacement(path="../outside.md"), self.replacement(path=str(outside)),
                 self.replacement(path="linked.md"), self.replacement(path="directory"),
                 self.replacement(replaces="../source-a.md")]
        for index, source in enumerate(cases):
            with self.subTest(index=index):
                code = "invalid_replacement" if source["path"] == "directory" else "unsafe_path"
                self.assert_refused_without_state_change(task, [source], code=code, request_id="unsafe-" + str(index))

    def test_refresh_preserves_substitution_provenance_but_does_not_claim_semantic_equivalence(self):
        task = self.initial()
        (self.workspace / "source-a.md").rename(self.workspace / "renamed.md")
        task = self.checkpoint(task, {"schema": 1, "state": "Moved.", "evidence": [self.replacement()]}, "replace")
        original_substitution_hash = self.resume(task)["sources"][0]["replacement_sha256"]
        (self.workspace / "renamed.md").write_text("Different source content, explicitly reconsidered later.\n")
        self.assertFalse(self.resume(task)["ready"])
        task = self.checkpoint(task, {"schema": 1, "state": "Bytes explicitly rechecked.",
                                    "evidence": [{"path": "renamed.md", "critical": False}]}, "refresh")
        packet = self.resume(task)
        source = packet["sources"][0]
        self.assertTrue(packet["ready"])
        self.assertTrue(source["critical"])
        self.assertEqual("source-a.md", source["replaces"])
        self.assertEqual(original_substitution_hash, source["replacement_sha256"])
        self.assertNotEqual(source["replacement_sha256"], source["sha256"])
        self.assertEqual("byte_identity_only", source["verification_scope"])

    def test_stored_substitution_corruption_is_unavailable_and_not_repaired(self):
        task = self.initial()
        (self.workspace / "source-a.md").rename(self.workspace / "renamed.md")
        task = self.checkpoint(task, {"schema": 1, "state": "Moved.", "evidence": [self.replacement()]}, "replace")
        path = self.task_document(task)
        original = path.read_bytes()
        for field, value in (("replacement_sha256", "invalid"), ("replacement_origin", "host_event"),
                             ("critical", False), ("replaced_source", {"path": "wrong.md"})):
            with self.subTest(field=field):
                document = json.loads(original)
                document["checkpoint"]["evidence"][0][field] = value
                path.write_text(json.dumps(document))
                before = boundary.file_manifest(self.state)
                self.refused("snapshot", code="state_unavailable")
                self.assertEqual(before, boundary.file_manifest(self.state))
                path.write_bytes(original)


if __name__ == "__main__":
    unittest.main()
