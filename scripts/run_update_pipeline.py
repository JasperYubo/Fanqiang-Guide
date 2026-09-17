"""Isolate update outputs and publish them with bounded, validated Git retries.

Only the GitHub metadata collector receives GITHUB_TOKEN. Git keeps the checkout
authentication configuration and environment. Child output is captured, never
echoed: public logs contain fixed status messages, not commands or credentials.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
MAX_ATTEMPTS = 3
RUN_SECONDS = 88 * 60
SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}\.md\Z")
API_ENV_NAMES = {"GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"}
ERROR_CODES = {"command_timeout", "command_unavailable", "missing_or_invalid_output", "unsafe_output_path",
               "unsafe_temp_path", "pipeline_timeout", "command_failed", "invalid_git_revision", "missing_date_page",
               "both_update_lines_failed", "publish_worktree_not_clean", "cannot_check_staged_changes",
               "source_checkout_not_clean", "push_failed_without_non_fast_forward", "publish_retry_limit",
               "main_did_not_advance"}
VERSION_PATHS = ("data/upstream.json", "CATALOG.md", "UPDATES.md")
BOT_CONFIG = ("-c", "user.name=github-actions[bot]", "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com", "-c", "commit.gpgSign=false")


class PipelineError(RuntimeError):
    pass


class Cancelled(PipelineError):
    pass


class CommandResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class Runner:
    def run(self, command, *, cwd, env, timeout):
        try:
            result = subprocess.run(command, cwd=cwd, env=env, timeout=timeout,
                                    capture_output=True, text=True, encoding="utf-8", errors="replace")
            return CommandResult(result.returncode, result.stdout, result.stderr)
        except subprocess.TimeoutExpired:
            raise PipelineError("command_timeout") from None
        except OSError:
            raise PipelineError("command_unavailable") from None


def contained_path(path, root):
    root, path = Path(root).absolute(), Path(path).absolute()
    if root.is_symlink() or not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise PipelineError("unsafe_output_path")
    relative = path.relative_to(root)
    if any(part in {".", ".."} for part in relative.parts):
        raise PipelineError("unsafe_output_path")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise PipelineError("unsafe_output_path")
    return path


def copy_file(source, destination, *, source_root=None, destination_root=None):
    source, destination = Path(source), Path(destination)
    if source_root is not None:
        contained_path(source, source_root)
    if destination_root is not None:
        contained_path(destination, destination_root)
    if not source.is_file() or source.is_symlink():
        raise PipelineError("missing_or_invalid_output")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def day_file(name):
    if not DAY.fullmatch(name):
        return False
    try:
        datetime.strptime(name, "%Y-%m-%d.md")
    except ValueError:
        return False
    return True


class Pipeline:
    def __init__(self, root=ROOT, *, runner=None, env=None, temp_root=None, max_attempts=MAX_ATTEMPTS, cancelled=None):
        self.root = Path(root).resolve()
        self.runner = runner or Runner()
        inherited = dict(os.environ if env is None else env)
        self.token = inherited.get("GITHUB_TOKEN")
        self.env = {key: value for key, value in inherited.items() if key not in API_ENV_NAMES}
        self.cancelled = cancelled or (lambda: False)
        self.max_attempts = max(1, min(int(max_attempts), MAX_ATTEMPTS))
        self.deadline = time.monotonic() + RUN_SECONDS
        self.temp_parent = Path(temp_root or tempfile.gettempdir()).resolve()
        self.temp = Path(tempfile.mkdtemp(prefix="fanqiang-pipeline-", dir=self.temp_parent)).resolve()
        self.created_temp = self.temp
        self.worktrees = []
        self.events = []
        self.round_number = 0

    def valid_temp(self):
        return (self.temp == self.created_temp and not self.temp.is_symlink()
                and self.temp.resolve() == self.created_temp and self.temp.parent == self.temp_parent
                and self.temp.name.startswith("fanqiang-pipeline-"))

    def check(self):
        if self.cancelled():
            raise Cancelled("cancelled")
        if time.monotonic() >= self.deadline:
            raise PipelineError("pipeline_timeout")

    def command(self, args, *, cwd=None, api=False, timeout=120, check=True):
        self.check()
        env = dict(self.env)
        if api and self.token:
            env["GITHUB_TOKEN"] = self.token
        result = self.runner.run(list(args), cwd=Path(cwd or self.root), env=env,
                                 timeout=min(timeout, max(0.01, self.deadline - time.monotonic())))
        self.check()
        if check and result.returncode:
            raise PipelineError("command_failed")
        return result

    def git(self, *args, cwd=None, check=True):
        return self.command(["git", *BOT_CONFIG, *args], cwd=cwd, timeout=90, check=check)

    def sha(self, ref, cwd=None):
        value = self.git("rev-parse", "--verify", ref, cwd=cwd).stdout.strip()
        if not SHA.fullmatch(value):
            raise PipelineError("invalid_git_revision")
        return value

    def python(self, source, script, *args, api=False, timeout=120):
        return self.command([sys.executable, str(Path(source) / "scripts" / script), *map(str, args)],
                            cwd=source, api=api, timeout=timeout)

    def worktree(self, revision):
        path = self.temp / ("publish-" + str(len(self.worktrees) + 1))
        self.git("worktree", "add", "--detach", str(path), revision)
        self.worktrees.append(path)
        return path

    def verify_latest(self, source):
        self.command([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=source, timeout=300)
        destination = self.temp / ("verify-" + str(len(self.worktrees)))
        destination.mkdir()
        self.python(source, "build_catalog.py", "--catalog-output", destination / "CATALOG.md",
                    "--updates-output", destination / "UPDATES.md")
        self.events.append("latest_baseline_verified")

    def collect_lines(self, source):
        self.round_number += 1
        stage = self.temp / ("round-" + str(self.round_number))
        stage.mkdir()
        artifacts, statuses = {}, {}
        for name in ("versions", "free_proxies"):
            self.check()
            directory = stage / name
            directory.mkdir()
            try:
                if name == "versions":
                    state = directory / "upstream.json"
                    previous = Path(source) / "data/upstream.json"
                    if previous.exists():
                        copy_file(previous, state, source_root=source, destination_root=self.temp)
                    self.python(source, "update_upstream.py", "--output", state, api=True, timeout=19 * 60)
                    self.python(source, "build_catalog.py", "--state", state,
                                "--catalog-output", directory / "CATALOG.md", "--updates-output", directory / "UPDATES.md")
                    produced = dict(zip(VERSION_PATHS, (state, directory / "CATALOG.md", directory / "UPDATES.md")))
                else:
                    state, pages = directory / "free-proxy-sources.json", directory / "free-proxies"
                    previous = Path(source) / "data/free-proxy-sources.json"
                    if previous.exists():
                        copy_file(previous, state, source_root=source, destination_root=self.temp)
                    pages.mkdir()
                    old_pages = Path(source) / "free-proxies"
                    if old_pages.is_dir():
                        for page in sorted(old_pages.glob("*.md")):
                            if page.name == "README.md" or day_file(page.name):
                                copy_file(page, pages / page.name, source_root=source, destination_root=self.temp)
                    self.python(source, "free_proxy_sources.py", "--output", state, timeout=6 * 60)
                    self.python(source, "build_free_proxy_pages.py", "--state", state, "--output-dir", pages)
                    produced = {"data/free-proxy-sources.json": state}
                    produced.update({"free-proxies/" + path.name: path for path in sorted(pages.glob("*.md"))
                                     if path.name == "README.md" or day_file(path.name)})
                    if "free-proxies/README.md" not in produced or len(produced) < 3:
                        raise PipelineError("missing_date_page")
                if any(not path.is_file() or path.is_symlink() for path in produced.values()):
                    raise PipelineError("missing_or_invalid_output")
                artifacts.update(produced)
                statuses[name] = "success"
            except Cancelled:
                raise
            except (PipelineError, OSError):
                statuses[name] = "failure"
            self.events.append(name + "_" + statuses[name])
        if not artifacts:
            raise PipelineError("both_update_lines_failed")
        return artifacts, statuses

    def make_commit(self, worktree, artifacts):
        self.check()
        if self.git("status", "--porcelain", cwd=worktree).stdout.strip():
            raise PipelineError("publish_worktree_not_clean")
        for relative, source in sorted(artifacts.items()):
            copy_file(source, worktree / relative, source_root=self.temp, destination_root=worktree)
        self.git("add", "--", *sorted(artifacts), cwd=worktree)
        changed = self.git("diff", "--cached", "--quiet", cwd=worktree, check=False)
        if changed.returncode == 0:
            return False
        if changed.returncode != 1:
            raise PipelineError("cannot_check_staged_changes")
        self.git("commit", "-m", "更新工具版本与每日免费代理资料", cwd=worktree)
        if self.git("status", "--porcelain", cwd=worktree).stdout.strip():
            raise PipelineError("publish_worktree_not_clean")
        return True

    @staticmethod
    def rejected_non_fast_forward(result):
        # --porcelain emits a distinct rejection reason; authentication and server
        # policy failures must not be treated as an optimistic-concurrency retry.
        return any(line.startswith("!\t") and "[rejected]" in line
                   and ("(fetch first)" in line or "(non-fast-forward)" in line)
                   for line in result.stdout.splitlines())

    def execute(self):
        if self.git("status", "--porcelain").stdout.strip():
            raise PipelineError("source_checkout_not_clean")
        base = self.sha("HEAD")
        artifacts, statuses = self.collect_lines(self.root)
        worktree = self.worktree(base)
        if not self.make_commit(worktree, artifacts):
            return {"status": "unchanged", "attempts": 0, "rounds": self.round_number, "lines": statuses}
        for attempt in range(1, self.max_attempts + 1):
            self.check()
            pushed = self.git("push", "--porcelain", "origin", "HEAD:main", cwd=worktree, check=False)
            if pushed.returncode == 0:
                return {"status": "published", "attempts": attempt, "rounds": self.round_number, "lines": statuses}
            if not self.rejected_non_fast_forward(pushed):
                raise PipelineError("push_failed_without_non_fast_forward")
            if attempt == self.max_attempts:
                raise PipelineError("publish_retry_limit")
            self.git("fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main")
            latest = self.sha("refs/remotes/origin/main")
            if latest == base or self.git("merge-base", "--is-ancestor", base, latest, check=False).returncode != 0:
                raise PipelineError("main_did_not_advance")
            changed = self.git("diff", "--name-only", "-z", base, latest, "--").stdout
            paths = {path for path in changed.split("\0") if path}
            if paths and paths <= {"README.md"}:
                self.git("rebase", "--no-autostash", latest, cwd=worktree)
                if self.git("status", "--porcelain", cwd=worktree).stdout.strip():
                    raise PipelineError("publish_worktree_not_clean")
                self.events.append("readme_only_rebase")
            else:
                worktree = self.worktree(latest)
                self.verify_latest(worktree)
                artifacts, statuses = self.collect_lines(worktree)
                if not self.make_commit(worktree, artifacts):
                    return {"status": "unchanged", "attempts": attempt, "rounds": self.round_number, "lines": statuses}
                self.events.append("regenerated_after_main_advance")
            base = latest
        raise PipelineError("publish_retry_limit")

    def cleanup(self):
        # Never launch a command after cancellation. Hosted runner disposal cleans
        # up its temporary workspace; normal completion removes our worktrees.
        if self.cancelled():
            return False
        if not self.valid_temp():
            self.events.append("unsafe_temp_path")
            return False
        remaining = []
        for worktree in reversed(self.worktrees):
            try:
                result = self.git("worktree", "remove", "--", str(worktree), check=False)
                if result.returncode:
                    remaining.append(worktree)
            except PipelineError:
                remaining.append(worktree)
        if not remaining:
            shutil.rmtree(self.temp)
            return True
        self.events.append("temporary_worktree_retained")
        return False


def main(argv=None, *, runner=None, env=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--temp-root", type=Path, default=None)
    parser.add_argument("--max-attempts", type=int, choices=range(1, MAX_ATTEMPTS + 1), default=MAX_ATTEMPTS)
    args = parser.parse_args(argv)
    cancellation = {"value": False}
    handlers = {}

    def cancel(signum, frame):
        cancellation["value"] = True
        raise Cancelled("cancelled")

    for signum in (signal.SIGINT, signal.SIGTERM):
        handlers[signum] = signal.signal(signum, cancel)
    pipeline = None
    try:
        inherited = dict(os.environ if env is None else env)
        temp_root = args.temp_root or inherited.get("RUNNER_TEMP")
        pipeline = Pipeline(args.root, runner=runner, env=inherited, temp_root=temp_root,
                            max_attempts=args.max_attempts, cancelled=lambda: cancellation["value"])
        result = pipeline.execute()
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Cancelled:
        print("Update pipeline cancelled; no further publication attempted.")
        return 130
    except (PipelineError, OSError, ValueError) as error:
        # Do not print arbitrary exception strings: child failures can contain
        # authenticated remote URLs or other process configuration.
        code = str(error) if isinstance(error, PipelineError) and str(error) in ERROR_CODES else "local_or_internal_error"
        print(json.dumps({"status": "failed", "error_code": code, "events": pipeline.events if pipeline else []}, sort_keys=True))
        return 1
    finally:
        try:
            if pipeline:
                try:
                    clean = pipeline.cleanup()
                    if not clean and not cancellation["value"]:
                        print('Temporary cleanup incomplete; owned runner files retained.')
                except OSError:
                    print('Temporary cleanup incomplete; owned runner files retained.')
        finally:
            for signum, handler in handlers.items():
                signal.signal(signum, handler)


if __name__ == "__main__":
    raise SystemExit(main())
