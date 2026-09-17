"""Offline orchestration tests: all Git, Python, and network commands are fake."""

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("run_update_pipeline", ROOT / "scripts/run_update_pipeline.py")
pipeline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline)
A, B, C = "a" * 40, "b" * 40, "c" * 40
TOKEN = "API-SECRET-MUST-NOT-APPEAR"


def write(root, relative, text):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def snapshot(root):
    return {str(path.relative_to(root)).replace("\\", "/"): path.read_text(encoding="utf-8")
            for path in sorted(Path(root).rglob("*")) if path.is_file()}


class FakeRunner:
    """A local in-memory Git model; does not invoke subprocess or Git at all."""
    def __init__(self, source, revisions, *, failures=None, advances=None, rejection="non_fast_forward", cancel=None,
                 verify_failure=False, unchanged=False):
        self.source = Path(source)
        self.revisions = revisions
        self.failures = set(failures or [])
        self.advances = list(advances or [])
        self.rejection = rejection
        self.cancel = cancel
        self.verify_failure = verify_failure
        self.unchanged = unchanged
        self.calls, self.commits, self.pushed = [], [], []
        self.heads = {self.source: A}
        self.remote = A
        self.push_count = 0
        self.added = {}

    def run(self, command, *, cwd, env, timeout):
        cwd = Path(cwd)
        self.calls.append({"command": list(command), "cwd": cwd, "env": dict(env), "timeout": timeout})
        if command[0] == "git":
            index = 1
            while command[index] == "-c":
                index += 2
            args = command[index:]
            return self.git(args, cwd)
        if command[1:3] == ["-m", "unittest"]:
            return pipeline.CommandResult(1 if self.verify_failure else 0)
        script = Path(command[1]).name
        args = command[2:]
        option = lambda name: Path(args[args.index(name) + 1])
        marker = (cwd / "config/marker.txt").read_text().strip()
        if script == "update_upstream.py":
            write(option("--output").parent, option("--output").name,
                  "FAILED-VERSION-PARTIAL" if "version_collect" in self.failures else "version-state-" + marker)
            return pipeline.CommandResult(1 if "version_collect" in self.failures else 0)
        if script == "build_catalog.py":
            failed = "version_build" in self.failures and "--state" in args
            write(option("--catalog-output").parent, option("--catalog-output").name,
                  "FAILED-CATALOG-PARTIAL" if failed else "catalog-" + marker)
            if failed:
                return pipeline.CommandResult(1)
            write(option("--updates-output").parent, option("--updates-output").name, "updates-" + marker)
            return pipeline.CommandResult()
        if script == "free_proxy_sources.py":
            write(option("--output").parent, option("--output").name,
                  "FAILED-FREE-PARTIAL" if "free_collect" in self.failures else "free-state-" + marker)
            return pipeline.CommandResult(1 if "free_collect" in self.failures else 0)
        if script == "build_free_proxy_pages.py":
            pages = option("--output-dir")
            write(pages, "2026-09-12.md", "FAILED-DAY-PARTIAL" if "free_build" in self.failures else "day12-" + marker)
            if "free_build" in self.failures:
                return pipeline.CommandResult(1)
            names = sorted((p.name for p in pages.glob("*.md") if pipeline.day_file(p.name)), reverse=True)
            write(pages, "README.md", "\n".join(names))
            return pipeline.CommandResult()
        raise AssertionError("Unexpected fake command")

    def git(self, args, cwd):
        if args[0] == "status":
            return pipeline.CommandResult()
        if args[0] == "rev-parse":
            return pipeline.CommandResult(stdout=(self.remote if args[-1] == "refs/remotes/origin/main" else self.heads[cwd]) + "\n")
        if args[:2] == ["worktree", "add"]:
            target, revision = Path(args[-2]), args[-1]
            target.mkdir()
            for relative, content in self.revisions[revision].items():
                write(target, relative, content)
            self.heads[target] = revision
            return pipeline.CommandResult()
        if args[:2] == ["worktree", "remove"]:
            target = Path(args[-1])
            assert target.resolve().is_relative_to(self.source.parent.resolve())
            shutil.rmtree(target)
            return pipeline.CommandResult()
        if args[0] == "add":
            self.added[cwd] = list(args[2:])
            return pipeline.CommandResult()
        if args[:2] == ["diff", "--cached"]:
            return pipeline.CommandResult(0 if self.unchanged else 1)
        if args[0] == "commit":
            state = snapshot(cwd)
            self.commits.append({"cwd": cwd, "files": state, "added": self.added[cwd]})
            self.heads[cwd] = str(len(self.commits)) * 40
            if self.cancel:
                self.cancel()
            return pipeline.CommandResult()
        if args[0] == "push":
            self.push_count += 1
            if self.advances:
                self.remote, paths = self.advances.pop(0)
                self.current_paths = paths
                reason = "[rejected] (fetch first)" if self.rejection == "non_fast_forward" else "[remote rejected] (protected branch hook declined)"
                return pipeline.CommandResult(1, "!\tHEAD:refs/heads/main\t" + reason + "\n", TOKEN)
            self.pushed.append(snapshot(cwd))
            return pipeline.CommandResult(stdout="ok")
        if args[0] == "fetch":
            return pipeline.CommandResult()
        if args[:2] == ["merge-base", "--is-ancestor"]:
            return pipeline.CommandResult()
        if args[0] == "diff":
            return pipeline.CommandResult(stdout="\0".join(self.current_paths) + "\0")
        if args[0] == "rebase":
            write(cwd, "README.md", self.revisions[args[-1]]["README.md"])
            return pipeline.CommandResult()
        raise AssertionError("Unexpected fake Git command: " + args[0])


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.source = self.base / "source"
        self.source.mkdir()
        files = {"README.md": "initial reader home", "config/marker.txt": "v1", "data/upstream.json": "old-version-state",
                 "CATALOG.md": "old-catalog", "UPDATES.md": "old-updates", "data/free-proxy-sources.json": "old-free-state",
                 "free-proxies/2026-09-10.md": "day10", "free-proxies/README.md": "2026-09-10.md",
                 "export/authored.txt": "authored snapshot"}
        for relative, content in files.items():
            write(self.source, relative, content)
        self.initial = snapshot(self.source)
        self.revisions = {A: dict(self.initial), B: dict(self.initial), C: dict(self.initial)}
        self.created = []

    def tearDown(self):
        for item in self.created:
            if item.temp.exists():
                # All fake worktrees live under this test's verified temporary root.
                assert item.temp.resolve().is_relative_to(self.base.resolve())
                shutil.rmtree(item.temp)
        self.temporary.cleanup()

    def make(self, **kwargs):
        cancelled = kwargs.pop("cancelled", None)
        runner = FakeRunner(self.source, self.revisions, **kwargs)
        env = {"GITHUB_TOKEN": TOKEN, "GH_TOKEN": "second-secret", "PATH": "preserved-path",
               "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "include.path", "GIT_CONFIG_VALUE_0": "checkout-auth-config"}
        item = pipeline.Pipeline(self.source, runner=runner, env=env, temp_root=self.base, cancelled=cancelled)
        self.created.append(item)
        return item, runner

    def assert_clean_source_and_no_failed_artifacts(self, runner):
        self.assertEqual(snapshot(self.source), self.initial)
        for commit in runner.commits:
            self.assertFalse(any("FAILED-" in content for content in commit["files"].values()))
            self.assertNotIn("README.md", commit["added"])
            self.assertNotIn("export/authored.txt", commit["added"])

    def test_version_collector_failure_does_not_block_free_line(self):
        item, runner = self.make(failures={"version_collect"})
        result = item.execute()
        self.assertEqual(result["lines"], {"versions": "failure", "free_proxies": "success"})
        published = runner.pushed[-1]
        self.assertEqual(published["data/upstream.json"], "old-version-state")
        self.assertIn("free-proxies/2026-09-12.md", published)
        self.assertFalse(any(Path(call["command"][1]).name == "build_catalog.py" for call in runner.calls if call["command"][0] != "git"))
        self.assert_clean_source_and_no_failed_artifacts(runner)

    def test_all_free_sources_failure_does_not_block_versions(self):
        item, runner = self.make(failures={"free_collect"})
        self.assertEqual(item.execute()["lines"], {"versions": "success", "free_proxies": "failure"})
        published = runner.pushed[-1]
        self.assertEqual(published["CATALOG.md"], "catalog-v1")
        self.assertEqual(published["data/free-proxy-sources.json"], "old-free-state")
        self.assertNotIn("free-proxies/2026-09-12.md", published)
        self.assert_clean_source_and_no_failed_artifacts(runner)

    def test_both_lines_failure_is_explicit_and_never_commits(self):
        item, runner = self.make(failures={"version_collect", "free_collect"})
        with self.assertRaisesRegex(pipeline.PipelineError, "both_update_lines_failed"):
            item.execute()
        self.assertEqual(runner.commits, [])
        self.assertEqual(runner.push_count, 0)
        self.assertEqual(item.worktrees, [])
        self.assert_clean_source_and_no_failed_artifacts(runner)

    def test_partial_renderer_output_is_excluded_for_either_line(self):
        for failure in ("version_build", "free_build"):
            with self.subTest(failure=failure):
                item, runner = self.make(failures={failure})
                result = item.execute()
                self.assertEqual(result["status"], "published")
                self.assert_clean_source_and_no_failed_artifacts(runner)
                if failure == "version_build":
                    self.assertEqual(runner.pushed[-1]["data/upstream.json"], "old-version-state")
                else:
                    self.assertNotIn("free-proxies/2026-09-12.md", runner.pushed[-1])

    def test_readme_only_advance_uses_plain_rebase_without_recollection(self):
        self.revisions[B]["README.md"] = "human changed reader home"
        item, runner = self.make(advances=[(B, ["README.md"])])
        result = item.execute()
        self.assertEqual((result["attempts"], result["rounds"]), (2, 1))
        self.assertEqual(runner.pushed[-1]["README.md"], "human changed reader home")
        self.assertIn("readme_only_rebase", item.events)
        commands = [call["command"] for call in runner.calls]
        self.assertTrue(any("rebase" in command and "--no-autostash" in command for command in commands))
        self.assertFalse(any("-X" in command or "--force" in command or "--force-with-lease" in command for command in commands))

    def test_date_page_advance_is_reverified_and_index_is_regenerated_from_union(self):
        self.revisions[B]["free-proxies/2026-09-11.md"] = "concurrent day11"
        self.revisions[B]["free-proxies/README.md"] = "2026-09-11.md\n2026-09-10.md"
        item, runner = self.make(advances=[(B, ["free-proxies/2026-09-11.md", "free-proxies/README.md"])])
        result = item.execute()
        self.assertEqual((result["attempts"], result["rounds"]), (2, 2))
        published = runner.pushed[-1]
        self.assertEqual(published["free-proxies/README.md"], "2026-09-12.md\n2026-09-11.md\n2026-09-10.md")
        self.assertEqual(published["free-proxies/2026-09-11.md"], "concurrent day11")
        self.assertIn("latest_baseline_verified", item.events)
        self.assertNotIn("readme_only_rebase", item.events)

    def test_config_advance_recollects_from_new_source_after_tests(self):
        self.revisions[B]["config/marker.txt"] = "v2"
        item, runner = self.make(advances=[(B, ["config/marker.txt"])])
        self.assertEqual(item.execute()["rounds"], 2)
        self.assertEqual(runner.pushed[-1]["data/upstream.json"], "version-state-v2")
        self.assertEqual(runner.pushed[-1]["data/free-proxy-sources.json"], "free-state-v2")
        verification = next(i for i, call in enumerate(runner.calls) if call["command"][1:3] == ["-m", "unittest"])
        second_collect = next(i for i, call in enumerate(runner.calls) if call["cwd"] != self.source and Path(call["command"][1]).name == "update_upstream.py")
        self.assertLess(verification, second_collect)

    def test_failed_latest_baseline_tests_stop_before_recollection_or_second_push(self):
        item, runner = self.make(advances=[(B, ["scripts/build_catalog.py"])], verify_failure=True)
        with self.assertRaises(pipeline.PipelineError):
            item.execute()
        self.assertEqual(runner.push_count, 1)
        self.assertEqual(item.round_number, 1)

    def test_retry_requires_actual_main_advance(self):
        item, runner = self.make(advances=[(A, ["README.md"])])
        with self.assertRaisesRegex(pipeline.PipelineError, "main_did_not_advance"):
            item.execute()
        self.assertEqual(runner.push_count, 1)

    def test_protection_rejection_is_not_a_non_fast_forward_retry(self):
        item, runner = self.make(advances=[(B, ["README.md"])], rejection="protected")
        with self.assertRaisesRegex(pipeline.PipelineError, "push_failed_without_non_fast_forward"):
            item.execute()
        self.assertFalse(any("fetch" in call["command"] for call in runner.calls))
        self.assertEqual(runner.push_count, 1)

    def test_three_push_attempt_limit_has_no_force(self):
        item, runner = self.make(advances=[(B, ["README.md"]), (C, ["README.md"]), (C, ["README.md"])])
        with self.assertRaisesRegex(pipeline.PipelineError, "publish_retry_limit"):
            item.execute()
        self.assertEqual(runner.push_count, 3)
        self.assertFalse(any("--force" in call["command"] or "-X" in call["command"] for call in runner.calls))

    def test_cancel_before_push_prevents_publication(self):
        flag = {"cancelled": False}
        item, runner = self.make(cancel=lambda: flag.update(cancelled=True), cancelled=lambda: flag["cancelled"])
        with self.assertRaises(pipeline.Cancelled):
            item.execute()
        self.assertEqual(runner.push_count, 0)
        count = len(runner.calls)
        item.cleanup()
        self.assertEqual(len(runner.calls), count)

    def test_only_api_collector_receives_token_and_git_checkout_environment_is_preserved(self):
        item, runner = self.make()
        item.execute()
        for call in runner.calls:
            api = call["command"][0] != "git" and Path(call["command"][1]).name == "update_upstream.py"
            self.assertEqual(call["env"].get("GITHUB_TOKEN"), TOKEN if api else None)
            self.assertNotIn("GH_TOKEN", call["env"])
            self.assertEqual(call["env"]["GIT_CONFIG_VALUE_0"], "checkout-auth-config")
            self.assertNotIn(TOKEN, " ".join(call["command"]))
        self.assertNotIn(TOKEN, json.dumps(item.events))

    def test_unchanged_outputs_do_not_push(self):
        item, runner = self.make(unchanged=True)
        self.assertEqual(item.execute()["status"], "unchanged")
        self.assertEqual(runner.push_count, 0)

    def test_cleanup_removes_only_owned_temporary_worktrees(self):
        item, runner = self.make()
        item.execute()
        item.cleanup()
        self.assertFalse(item.temp.exists())
        self.assertTrue(self.source.exists())
        self.assertEqual(snapshot(self.source), self.initial)

    def test_main_does_not_echo_child_errors_or_credentials(self):
        runner = FakeRunner(self.source, self.revisions, advances=[(B, ["README.md"])], rejection="protected")
        output = io.StringIO()
        with redirect_stdout(output):
            code = pipeline.main(["--root", str(self.source), "--temp-root", str(self.base)], runner=runner, env={"GITHUB_TOKEN": TOKEN})
        self.assertEqual(code, 1)
        self.assertNotIn(TOKEN, output.getvalue())
        self.assertNotIn("protected branch", output.getvalue())
        self.assertIn('"error_code": "push_failed_without_non_fast_forward"', output.getvalue())

    def test_target_parent_symlink_cannot_escape_publish_worktree(self):
        item, runner = self.make()
        worktree, outside = item.temp / "manual-publish", self.base / "outside"
        worktree.mkdir()
        outside.mkdir()
        write(outside, "upstream.json", "must remain unchanged")
        try:
            (worktree / "data").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable")
        artifact = item.temp / "artifact.json"
        artifact.write_text("new data")
        with self.assertRaisesRegex(pipeline.PipelineError, "unsafe_output_path"):
            item.make_commit(worktree, {"data/upstream.json": artifact})
        self.assertEqual((outside / "upstream.json").read_text(), "must remain unchanged")
        self.assertEqual(runner.commits, [])

    def test_cleanup_rejects_a_temp_path_that_was_not_created_by_pipeline(self):
        item, runner = self.make()
        original = item.temp
        outside = self.base / "not-created-by-pipeline"
        outside.mkdir()
        write(outside, "keep.txt", "keep")
        item.temp = outside
        self.assertFalse(item.cleanup())
        self.assertTrue((outside / "keep.txt").exists())
        self.assertEqual(runner.calls, [])
        item.temp = original

    def test_copy_rejects_path_traversal_before_creating_a_file(self):
        item, runner = self.make()
        artifact = item.temp / "artifact.txt"
        artifact.write_text("data")
        with self.assertRaisesRegex(pipeline.PipelineError, "unsafe_output_path"):
            pipeline.copy_file(artifact, item.temp / "../escape.txt", destination_root=item.temp)
        self.assertFalse((self.base / "escape.txt").exists())


class WorkflowTests(unittest.TestCase):
    def test_workflow_keeps_verification_auth_permissions_and_full_history(self):
        text = (ROOT / ".github/workflows/update-library.yml").read_text(encoding="utf-8")
        self.assertIn("needs: verify", text)
        self.assertIn("ref: ${{ github.sha }}", text)
        self.assertIn("fetch-depth: 0", text)
        self.assertIn("timeout-minutes: 90", text)
        self.assertEqual(text.count("GITHUB_TOKEN: ${{ github.token }}"), 1)
        self.assertIn("run: python scripts/run_update_pipeline.py", text)
        self.assertIn("success() && !cancelled()", text)
        self.assertIn("contents: read", text)
        self.assertIn("contents: write", text)
        self.assertNotIn("-X theirs", text)
        self.assertNotIn("git push", text)


if __name__ == "__main__":
    unittest.main()
