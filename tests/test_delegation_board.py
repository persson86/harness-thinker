#!/usr/bin/env python3
"""Board da delegação: eixos de estado, alinhamento e sanitização. Sem contas."""
import datetime as dt
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "payload/harness/scripts"))
from thinker_delegation import board  # noqa: E402


def moment(**delta):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(**delta)).isoformat()


def job(**overrides):
    base = {"id": "0" * 8, "session": "host-a", "state": "completed", "validation": "valid",
            "acceptance": "pending", "feedback": "unknown", "acknowledged": False,
            "transport_success": True, "timeout": 300, "task_type": "review",
            "reason": "Conferir as atribuições da transcrição",
            "created_at": moment(minutes=5), "started_at": moment(minutes=5),
            "finished_at": moment(minutes=4),
            "profile": {"provider": "codex", "model": "gpt-5.6-luna", "effort": "low",
                        "requested_profile": "luna"}}
    base.update(overrides)
    return base


class FakeStore:
    def __init__(self, jobs, enabled=True, concurrency=2):
        self._jobs, self._enabled, self._concurrency = jobs, enabled, concurrency

    def list_jobs(self, session=None):
        return [j for j in self._jobs if session is None or j["session"] == session]

    def status(self, session=None):
        return {"enabled": self._enabled, "global_enabled": True, "mode": "request",
                "concurrency": self._concurrency, "session": session}


class DeliveryAxisTests(unittest.TestCase):
    """Execução e entrega são eixos distintos: o que se perde não é o job que
    quebrou, é o que terminou e ninguém leu."""

    def test_completed_and_unread_is_the_actionable_cell(self):
        self.assertEqual("inbox", board.delivery_of(job()))

    def test_acknowledged_leaves_the_inbox(self):
        self.assertEqual("read", board.delivery_of(job(acknowledged=True)))

    def test_accepted_is_materialized(self):
        self.assertEqual("materialized", board.delivery_of(job(acceptance="accepted")))

    def test_accepted_over_changed_input_is_flagged_stale(self):
        self.assertEqual("stale", board.delivery_of(job(acceptance="accepted", accepted_stale=True)))

    def test_unvalidated_output_never_counts_as_delivery(self):
        self.assertEqual("none", board.delivery_of(job(state="failed", validation="invalid")))
        self.assertEqual("none", board.delivery_of(job(state="completed", validation="unavailable")))

    def test_transport_failure_and_malformed_output_are_different_states(self):
        _, malformed, _, note = board.execution_of(job(state="failed", transport_success=True))
        self.assertEqual("saída inválida", malformed)
        self.assertIn("estrutura", note)
        _, broken, _, note = board.execution_of(job(state="failed", transport_success=False))
        self.assertEqual("falhou", broken)
        self.assertEqual("transporte", note)

    def test_returned_is_never_labelled_ok(self):
        # exit 0 só prova transporte; qualidade é a coluna de feedback.
        _, label, _, _ = board.execution_of(job())
        self.assertEqual("voltou", label)

    def test_running_past_timeout_is_reported_without_claiming_death(self):
        _, _, _, note = board.execution_of(job(state="running", finished_at=None,
                                               started_at=moment(minutes=9), timeout=60))
        self.assertIn("timeout", note)


class PresentationTests(unittest.TestCase):
    def test_alias_is_not_repeated_inside_the_model_cell(self):
        alias, model = board.agent_of(job())
        self.assertEqual("luna", alias)
        self.assertEqual("gpt-5.6 · low", model)

    def test_model_equal_to_alias_falls_back_to_provider(self):
        alias, model = board.agent_of(job(profile={"provider": "claude", "model": "opus",
                                                   "effort": "high", "requested_profile": "opus"}))
        self.assertEqual(("opus", "claude · high"), (alias, model))

    def test_chain_and_retry_are_marked(self):
        self.assertEqual("review·s2/rev ↻",
                         board.task_of(job(run_id="r1", stage=2, role="reviewer", retry_of="x")))
        self.assertEqual("review", board.task_of(job()))

    def test_bar_measures_elapsed_against_timeout_not_task_progress(self):
        self.assertEqual("", board.bar(10, None))
        self.assertTrue(board.bar(150, 300).startswith("▓▓▓▓░░░░"))
        self.assertTrue(board.bar(9999, 300).startswith("▓▓▓▓▓▓▓▓"))


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore([
            job(id="a", state="running", finished_at=None, started_at=moment(seconds=70)),
            job(id="b", state="queued", started_at=None, finished_at=None, validation="pending"),
            job(id="c", state="failed", transport_success=False, validation="unavailable"),
            job(id="d", acceptance="accepted", accepted_stale=True, acknowledged=True,
                feedback="not_useful"),
            job(id="e", acknowledged=True, feedback="useful",
                profile={"provider": "grok", "model": "grok-4.6", "effort": "high",
                         "requested_profile": "grok"}),
            job(id="f"),
        ])
        self.data = board.payload(self.store, "host-a")

    def test_no_line_overflows_at_any_reasonable_width(self):
        # Uma linha que quebra destrói o alinhamento da tabela inteira.
        for width in (80, 90, 100, 110, 120, 140, 160, 200):
            text = board.render(self.data, width=width)
            for line in text.split("\n"):
                self.assertLessEqual(board.visible_len(line), width,
                                     "largura %d estourou: %r" % (width, line))

    def test_columns_degrade_in_order_of_dispensability(self):
        narrow = board.render(self.data, width=80)
        wide = board.render(self.data, width=200)
        self.assertNotIn("MODELO", narrow)
        self.assertIn("MODELO", wide)
        self.assertIn("QUALIDADE", wide)

    def test_colour_does_not_shift_any_column(self):
        plain = board.render(self.data, color=False, width=160)
        painted = re.sub(r"\x1b\[[0-9;]*m", "", board.render(self.data, color=True, width=160))
        self.assertEqual([l.rstrip() for l in plain.split("\n")],
                         [l.rstrip() for l in painted.split("\n")])

    def test_ascii_mode_emits_no_wide_or_ambiguous_glyphs(self):
        text = board.render(self.data, ascii_only=True, width=160)
        self.assertTrue(all(ord(c) < 128 or c.isalpha() for c in text),
                        [c for c in text if ord(c) >= 128 and not c.isalpha()])

    def test_quality_column_appears_only_once_feedback_exists(self):
        self.assertIn("QUALIDADE", board.render(self.data, width=200))
        silent = board.payload(FakeStore([job(id="g")]), "host-a")
        self.assertNotIn("QUALIDADE", board.render(silent, width=200))

    def test_stale_delivery_is_explained_below_its_own_row(self):
        self.assertIn("versão antiga", board.render(self.data, width=160))

    def test_active_jobs_lead_and_older_ones_are_capped_by_limit(self):
        data = board.payload(self.store, "host-a", limit=1)
        self.assertEqual(["a", "b"], [j["id"] for j in data["jobs"]][:2])
        self.assertEqual(3, data["board"]["hidden"])

    def test_counters_separate_running_waiting_and_broken(self):
        head = self.data["board"]
        self.assertEqual(1, head["running"])
        self.assertEqual(1, head["waiting"], "só o job f está concluído e não lido")
        self.assertEqual(1, head["failed"])

    def test_empty_board_says_so_instead_of_drawing_an_empty_table(self):
        text = board.render(board.payload(FakeStore([]), "host-a"))
        self.assertIn("Nenhum job", text)
        self.assertNotIn("AGENTE", text)


class InjectionTests(unittest.TestCase):
    def test_job_text_cannot_smuggle_escapes_into_the_terminal(self):
        hostile = job(reason="normal\x1b[31mVERMELHO\x1b[0m\nsegunda linha\x07")
        text = board.render(board.payload(FakeStore([hostile]), "host-a"), width=200)
        self.assertNotIn("\x1b[31m", text)
        self.assertNotIn("\x07", text)
        self.assertEqual(1, sum(1 for l in text.split("\n") if "normal" in l))


class WatchTests(unittest.TestCase):
    def test_refresh_expires_rows_and_clears_tty_without_color(self):
        store = FakeStore([job()])
        stream = io.StringIO()
        stream.isatty = lambda: True

        def tick():
            store._jobs[0]["finished_at"] = moment(hours=1)

        with mock.patch.dict(board.os.environ, {"TERM": "xterm", "NO_COLOR": "1"}):
            # First frame gets a fresh timestamp; first sleep makes it expire.
            store._jobs[0]["finished_at"] = moment(seconds=1)
            calls = 0

            def sleep(_):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt
                tick()

            with mock.patch.object(board.time, "sleep", side_effect=sleep):
                self.assertEqual(0, board.watch(store, "host-a", False, 10, 5, False, False,
                                               stream=stream, recent_seconds=10))
        frames = stream.getvalue().split("\033[H\033[J")
        self.assertEqual(3, len(frames))
        self.assertIn("luna", frames[1])
        self.assertNotIn("luna", frames[2])
        self.assertIn("1 na inbox", frames[2])
        self.assertNotIn("\033[36m", stream.getvalue())

    def test_redirected_output_contains_no_terminal_clear(self):
        stream = io.StringIO()
        with mock.patch.object(board.time, "sleep", side_effect=KeyboardInterrupt):
            board.watch(FakeStore([]), "host-a", False, 10, 5, False, False, stream=stream)
        self.assertNotIn("\033", stream.getvalue())


class BoardCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="delegation-board-")
        self.root = Path(self.temporary.name).resolve()
        self.vault = self.root / "vault"
        scripts = self.vault / "harness/scripts"
        scripts.mkdir(parents=True)
        shutil.copy(ROOT / "payload/harness/scripts/delegate.py", scripts / "delegate.py")
        shutil.copytree(ROOT / "payload/harness/scripts/thinker_delegation",
                        scripts / "thinker_delegation",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.cli_path = scripts / "delegate.py"
        self.state = self.root / "state"
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.root), "LANG": "en_US.UTF-8",
                    "TMPDIR": str(self.root), "PYTHONDONTWRITEBYTECODE": "1"}

    def tearDown(self):
        self.temporary.cleanup()

    def run_cli(self, *args, session="host-a", env=None):
        command = [sys.executable, "-B", str(self.cli_path), "--state-dir", str(self.state)]
        if session is not None:
            command += ["--session", session]
        return subprocess.run(command + list(args), cwd=self.root, env={**self.env, **(env or {})},
                              capture_output=True, text=True, timeout=20)

    def test_board_reads_while_delegation_is_off(self):
        # Desligada é justamente quando se quer conferir o que ficou para trás.
        result = self.run_cli("board")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("DELEGAÇÃO", result.stdout)

    def test_board_never_starts_an_agent_or_writes_jobs(self):
        self.run_cli("board")
        status = json.loads(self.run_cli("--json", "status").stdout)
        self.assertTrue(status["enabled"], "disponibilidade default-on e intencional")
        self.assertEqual([], status["jobs"])

    def test_recent_and_history_flags_reach_json(self):
        result = self.run_cli("--json", "board", "--recent-seconds", "120", "--history")
        self.assertEqual(0, result.returncode, result.stderr)
        head = json.loads(result.stdout)["board"]
        self.assertEqual(120, head["recent_seconds"])
        self.assertTrue(head["history"])

    def test_negative_recent_window_is_rejected(self):
        result = self.run_cli("board", "--recent-seconds", "-1")
        self.assertEqual(2, result.returncode)

    def test_native_report_confirmation_names_the_model(self):
        result = self.run_cli("native", "report", "--id", "review", "--model", "gpt-5.6-terra",
                              "--state", "running", "--task", "review board")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("gpt-5.6-terra", result.stdout)

    def test_json_output_carries_data_not_a_drawn_table(self):
        payload = json.loads(self.run_cli("--json", "board").stdout)
        self.assertIn("board", payload)
        self.assertNotIn("text", payload)

    def test_board_requires_a_session_unless_scanning_every_terminal(self):
        self.assertEqual(2, self.run_cli("board", session=None).returncode)
        self.assertEqual(0, self.run_cli("board", "--all-sessions", session=None).returncode)

    def test_collaborator_cannot_inspect_the_principal(self):
        for extra in ([], ["--watch", "1"]):
            result = self.run_cli("board", *extra, env={"THINKER_DELEGATION_CHILD": "1"})
            self.assertEqual(2, result.returncode, result.stdout)
            self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
