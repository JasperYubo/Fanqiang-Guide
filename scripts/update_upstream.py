"""Refresh public GitHub metadata without changing the authored knowledge snapshot.

Only GITHUB_TOKEN (optional) and GITHUB_STEP_SUMMARY are read from the environment.
Only bounded, explicitly validated GitHub API redirects are followed. Failed
checks retain the last successful payload and its repository identity.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
import email.utils
import http.client
import json
import math
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "config/upstream-repositories.json"
DEFAULT_OUTPUT = ROOT / "data/upstream.json"
MAX_WORKERS = 4
RUN_BUDGET_SECONDS = 18 * 60
REQUEST_TIMEOUT = 10
MAX_ATTEMPTS = 3
MAX_REDIRECTS = 3
MAX_RETRY_DELAY = 10
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
# Historical public accounts such as wangyu- legitimately end in a hyphen.
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")
ENTITY_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,127}\Z")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")


class ValidationError(ValueError):
    """Invalid input or response; messages never contain source values."""


class FetchError(Exception):
    def __init__(self, code, systemic=False):
        super().__init__(code)
        self.code = code
        self.systemic = systemic


class APIResponse(dict):
    """Response plus transport provenance that cannot be supplied by JSON fields."""

    def __init__(self, payload, api_redirect_chain):
        super().__init__(payload)
        self.api_redirect_chain = tuple(api_redirect_chain)


def valid_slug(value):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValidationError("invalid_repository_slug")
    owner, repo = value.split("/")
    if "--" in owner or repo in {".", ".."}:
        raise ValidationError("invalid_repository_slug")
    return value


def valid_text(value, limit=1024):
    if not isinstance(value, str) or not value or len(value) > limit:
        raise ValidationError("invalid_text_field")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValidationError("invalid_text_field")
    return value


def valid_time(value, nullable=False):
    if nullable and value is None:
        return None
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        raise ValidationError("invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValidationError("invalid_timestamp") from None
    if parsed.utcoffset() is None:
        raise ValidationError("invalid_timestamp")
    return value


def checked_time(value=None):
    if value is None:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    valid_time(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def github_url(value, slug, release=False):
    valid_text(value, 4096)
    try:
        parts = urllib.parse.urlsplit(value)
        safe_origin = (parts.scheme == "https" and parts.netloc == "github.com"
                       and parts.username is None and parts.password is None
                       and parts.port is None and not parts.query and not parts.fragment)
    except ValueError:
        raise ValidationError("invalid_github_url") from None
    path = urllib.parse.unquote(parts.path)
    if not safe_origin or "\\" in path or any(ord(c) < 32 for c in path):
        raise ValidationError("invalid_github_url")
    if any(part in {".", ".."} for part in path.split("/")):
        raise ValidationError("invalid_github_url")
    prefix = "/" + slug
    if release:
        prefix += "/releases/tag/"
        matches = path.lower().startswith(prefix.lower()) and len(path) > len(prefix)
    else:
        matches = path.lower() == prefix.lower()
    if not matches:
        raise ValidationError("invalid_github_url")
    return value


def api_repository_url(value, release=False):
    """Accept only the two public repository endpoint forms on the exact API origin."""
    valid_text(value, 4096)
    try:
        parts = urllib.parse.urlsplit(value)
        safe_origin = (parts.scheme == "https" and parts.netloc == "api.github.com"
                       and parts.username is None and parts.password is None
                       and parts.port is None and not parts.query and not parts.fragment)
    except ValueError:
        raise ValidationError("invalid_api_redirect_url") from None
    # No escaping, path normalization, user endpoints, or arbitrary API methods.
    if not safe_origin or "%" in parts.path or "\\" in parts.path:
        raise ValidationError("invalid_api_redirect_url")
    path = parts.path
    if release:
        if not path.endswith("/releases/latest"):
            raise ValidationError("invalid_api_redirect_path")
        path = path[:-len("/releases/latest")]
    if path.startswith("/repos/"):
        valid_slug(path[len("/repos/"):])
    elif not re.fullmatch(r"/repositories/[1-9][0-9]{0,19}", path):
        raise ValidationError("invalid_api_redirect_path")
    return value


def validate_resolution(value, slug, success_at):
    """Validate saved migration provenance; it never changes the authored manifest."""
    if not isinstance(value, dict):
        raise ValidationError("invalid_repository_resolution")
    name = valid_slug(value.get("full_name"))
    valid_time(value.get("checked_at"))
    if value["checked_at"] != success_at:
        raise ValidationError("invalid_resolution_timestamp")
    chain = value.get("api_redirect_chain")
    if not isinstance(chain, list) or not 2 <= len(chain) <= MAX_REDIRECTS + 1:
        raise ValidationError("invalid_resolution_chain")
    for url in chain:
        api_repository_url(url)
    if len(set(chain)) != len(chain) or chain[0] != "https://api.github.com/repos/" + slug:
        raise ValidationError("invalid_resolution_chain")
    final_path = urllib.parse.urlsplit(chain[-1]).path
    if final_path.startswith("/repos/") and final_path[len("/repos/"):].lower() != name.lower():
        raise ValidationError("resolution_identity_mismatch")
    return name


def repository_payload(value, slug, allow_redirect=False):
    if not isinstance(value, dict):
        raise ValidationError("invalid_repository_response")
    required = {"full_name", "html_url", "archived", "disabled", "pushed_at", "default_branch"}
    if not required.issubset(value):
        raise ValidationError("invalid_repository_response")
    name = valid_slug(value["full_name"])
    if name.lower() != slug.lower() and not allow_redirect:
        raise ValidationError("repository_identity_mismatch")
    if type(value["archived"]) is not bool or type(value["disabled"]) is not bool:
        raise ValidationError("invalid_repository_flags")
    return {
        "full_name": name,
        "html_url": github_url(value["html_url"], name),
        "archived": value["archived"],
        "disabled": value["disabled"],
        "pushed_at": valid_time(value["pushed_at"], nullable=True),
        "default_branch": valid_text(value["default_branch"], 255),
    }


def release_payload(value, slug):
    if not isinstance(value, dict) or not {"tag_name", "html_url", "published_at"}.issubset(value):
        raise ValidationError("invalid_release_response")
    tag = valid_text(value["tag_name"])
    url = github_url(value["html_url"], slug, release=True)
    if urllib.parse.unquote(urllib.parse.urlsplit(url).path)[len("/" + slug + "/releases/tag/"):] != tag:
        raise ValidationError("release_tag_url_mismatch")
    return {
        "tag_name": tag,
        "html_url": url,
        "published_at": valid_time(value["published_at"]),
    }


def read_json(path):
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValidationError("input_too_large")
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeError):
        raise ValidationError("invalid_input_json") from None


def validate_manifest(value):
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1 or not isinstance(value.get("repositories"), list)
            or not isinstance(value.get("excluded"), list)):
        raise ValidationError("invalid_manifest")
    rows = value["repositories"]
    if not 1 <= len(rows) <= 1000:
        raise ValidationError("invalid_repository_count")
    names, ids, result = set(), set(), []
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError("invalid_manifest_repository")
        slug = valid_slug(row.get("full_name"))
        if slug.lower() in names:
            raise ValidationError("duplicate_repository")
        names.add(slug.lower())
        entities = row.get("entity_ids")
        if not isinstance(entities, list) or not entities:
            raise ValidationError("invalid_entity_ids")
        for entity_id in entities:
            if not isinstance(entity_id, str) or not ENTITY_ID.fullmatch(entity_id) or entity_id in ids:
                raise ValidationError("invalid_or_duplicate_entity_id")
            ids.add(entity_id)
        result.append(slug)
    for row in value["excluded"]:
        if not isinstance(row, dict):
            raise ValidationError("invalid_excluded_entry")
        entity_id = row.get("entity_id")
        if not isinstance(entity_id, str) or not ENTITY_ID.fullmatch(entity_id) or entity_id in ids:
            raise ValidationError("invalid_or_duplicate_entity_id")
        ids.add(entity_id)
        valid_text(row.get("reason"), 2000)
    return sorted(result, key=lambda x: (x.lower(), x))


def is_complete(entry):
    return entry["repository_status"] == "ok" and entry["release_status"] in {"ok", "none"}


def validate_state(value):
    if (not isinstance(value, dict) or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1 or not isinstance(value.get("repositories"), dict)
            or not isinstance(value.get("last_run"), dict)):
        raise ValidationError("invalid_previous_state")
    run = value["last_run"]
    valid_time(run.get("checked_at"))
    for key in ("repository_count", "ok_count", "error_count"):
        if type(run.get(key)) is not int or run[key] < 0:
            raise ValidationError("invalid_previous_counts")
    entries = value["repositories"]
    if run["repository_count"] != len(entries) or run["ok_count"] + run["error_count"] != len(entries):
        raise ValidationError("invalid_previous_counts")
    names = set()
    for slug, entry in entries.items():
        valid_slug(slug)
        if slug.lower() in names or not isinstance(entry, dict):
            raise ValidationError("invalid_previous_repository")
        names.add(slug.lower())
        valid_time(entry.get("checked_at"))
        if entry.get("repository_status") not in {"ok", "unavailable", "error"}:
            raise ValidationError("invalid_previous_repository_status")
        if entry.get("release_status") not in {"ok", "none", "error", "not_checked"}:
            raise ValidationError("invalid_previous_release_status")
        for key in ("repository", "release", "repository_last_success_at", "release_last_success_at", "error_code"):
            if key not in entry:
                raise ValidationError("incomplete_previous_state")
        valid_time(entry["repository_last_success_at"], nullable=True)
        valid_time(entry["release_last_success_at"], nullable=True)
        repository_name, release_name = slug, slug
        if "repository_resolution" in entry:
            if entry["repository"] is None:
                raise ValidationError("resolution_without_repository")
            repository_name = validate_resolution(entry["repository_resolution"], slug, entry["repository_last_success_at"])
        if "release_resolution" in entry:
            if entry["release"] is None:
                raise ValidationError("resolution_without_release")
            release_name = validate_resolution(entry["release_resolution"], slug, entry["release_last_success_at"])
        if entry["repository"] is not None:
            repository_payload(entry["repository"], repository_name)
            if entry["repository_last_success_at"] is None:
                raise ValidationError("missing_previous_success_time")
        elif entry["repository_status"] == "ok":
            raise ValidationError("missing_previous_repository")
        if entry["release"] is not None:
            release_payload(entry["release"], release_name)
            if entry["release_last_success_at"] is None or entry["release_status"] == "none":
                raise ValidationError("invalid_previous_release")
            if entry["release_status"] == "ok" and release_name.lower() != repository_name.lower():
                raise ValidationError("release_repository_identity_mismatch")
        elif entry["release_status"] == "ok":
            raise ValidationError("missing_previous_release")
        code = entry["error_code"]
        if code is not None and (not isinstance(code, str) or not ERROR_CODE.fullmatch(code)):
            raise ValidationError("invalid_previous_error_code")
    return value


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib must never create a follow-up request. APIClient examines the
        # resulting HTTPError and makes any allowed next request explicitly.
        return None


class APIClient:
    def __init__(self, token=None, opener=None, sleep=time.sleep, monotonic=time.monotonic,
                 wall_time=time.time, budget=RUN_BUDGET_SECONDS):
        if token and (not isinstance(token, str) or any(ord(c) <= 32 or ord(c) == 127 for c in token)):
            raise ValidationError("invalid_token_environment")
        self.token = token
        self.opener = opener or urllib.request.build_opener(NoRedirects())
        self.sleep = sleep
        self.monotonic = monotonic
        self.wall_time = wall_time
        self.deadline = monotonic() + budget
        self.halted = threading.Event()
        self.systemic = threading.Event()

    def _fail_systemic(self, code):
        self.systemic.set()
        self.halted.set()
        return FetchError(code, systemic=True)

    def _delay(self, headers, attempt, rate_limited):
        retry_after = headers.get("Retry-After")
        delay = None
        if retry_after:
            try:
                delay = max(0.0, float(retry_after))
            except ValueError:
                try:
                    delay = max(0.0, email.utils.parsedate_to_datetime(retry_after).timestamp() - self.wall_time())
                except (ValueError, TypeError, OverflowError, AttributeError):
                    if rate_limited:
                        raise self._fail_systemic("rate_limited") from None
                    raise FetchError("invalid_retry_after") from None
        elif rate_limited and headers.get("X-RateLimit-Remaining") == "0":
            try:
                delay = max(0.0, float(headers["X-RateLimit-Reset"]) - self.wall_time())
            except (KeyError, ValueError):
                delay = MAX_RETRY_DELAY + 1
        if delay is None:
            # Without a quota reset/Retry-After, do not hammer a secondary limit.
            delay = MAX_RETRY_DELAY + 1 if rate_limited else 2 ** attempt
        if not math.isfinite(delay):
            if rate_limited:
                raise self._fail_systemic("rate_limited")
            raise FetchError("invalid_retry_after")
        if delay > MAX_RETRY_DELAY or delay >= self.deadline - self.monotonic():
            if rate_limited:
                raise self._fail_systemic("rate_limited")
            raise FetchError("retry_deferred")
        self.sleep(delay)

    def _read_response(self, response, request_deadline):
        """Use bounded reads so a slowly streaming response cannot defeat the run budget."""
        reader = getattr(response, "read1", None)
        if reader is None:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        else:
            chunks, total = [], 0
            while True:
                if self.monotonic() >= request_deadline:
                    raise TimeoutError()
                chunk = reader(min(65536, MAX_RESPONSE_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_RESPONSE_BYTES:
                    raise FetchError("response_too_large")
            body = b"".join(chunks)
        if self.monotonic() >= request_deadline:
            raise TimeoutError()
        if len(body) > MAX_RESPONSE_BYTES:
            raise FetchError("response_too_large")
        return body

    def fetch(self, slug, release=False):
        valid_slug(slug)
        url = "https://api.github.com/repos/" + slug + ("/releases/latest" if release else "")
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "Fanqiang-Guide-upstream/1",
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        chain = [url]
        attempt = 0
        while attempt < MAX_ATTEMPTS:
            if self.halted.is_set():
                raise FetchError("run_halted")
            remaining = self.deadline - self.monotonic()
            if remaining <= 0:
                raise FetchError("budget_exhausted")
            req = urllib.request.Request(url, headers=headers)
            retry_headers, rate_limited, code = {}, False, "network_error"
            try:
                request_deadline = min(self.deadline, self.monotonic() + REQUEST_TIMEOUT)
                with self.opener.open(req, timeout=min(REQUEST_TIMEOUT, remaining)) as response:
                    if response.geturl() != url:
                        raise FetchError("redirect_blocked")
                    if response.status != 200:
                        raise FetchError("unexpected_http_status")
                    body = self._read_response(response, request_deadline)
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (ValueError, UnicodeError):
                    raise FetchError("invalid_json") from None
                if not isinstance(payload, dict):
                    raise FetchError("invalid_json_shape")
                return APIResponse(payload, chain)
            except urllib.error.HTTPError as error:
                status = error.code
                retry_headers = error.headers or {}
                if status in {301, 302, 303, 307, 308}:
                    location = retry_headers.get("Location")
                    error.close()
                    try:
                        target = api_repository_url(location, release=release)
                    except ValidationError:
                        raise FetchError("redirect_blocked") from None
                    if target in chain:
                        raise FetchError("redirect_loop")
                    if len(chain) - 1 >= MAX_REDIRECTS:
                        raise FetchError("redirect_limit")
                    chain.append(target)
                    url = target
                    continue
                try:
                    message = error.read(8192).decode("utf-8", errors="replace").lower()
                except (OSError, http.client.HTTPException):
                    message = ""
                finally:
                    error.close()
                if status == 401:
                    raise self._fail_systemic("authentication_failed") from None
                if status == 404:
                    raise FetchError("not_found") from None
                rate_limited = status == 429 or (status == 403 and (
                    retry_headers.get("X-RateLimit-Remaining") == "0"
                    or retry_headers.get("Retry-After") is not None or "rate limit" in message))
                if rate_limited:
                    code = "rate_limited"
                elif status in {500, 502, 503, 504}:
                    code = "upstream_server_error"
                elif 300 <= status < 400:
                    raise FetchError("redirect_blocked") from None
                else:
                    raise FetchError("forbidden" if status == 403 else "http_error") from None
            except (urllib.error.URLError, TimeoutError, socket.timeout, OSError, http.client.HTTPException):
                code = "network_error"
            if attempt + 1 == MAX_ATTEMPTS:
                if rate_limited:
                    raise self._fail_systemic(code)
                raise FetchError(code)
            self._delay(retry_headers, attempt, rate_limited)
            attempt += 1
        raise FetchError("network_error")


def update_repository(slug, previous, now, client):
    old = previous or {}
    entry = {
        "checked_at": now,
        "repository_status": "error",
        "repository": deepcopy(old.get("repository")),
        "repository_last_success_at": old.get("repository_last_success_at"),
        "release_status": "not_checked",
        "release": deepcopy(old.get("release")),
        "release_last_success_at": old.get("release_last_success_at"),
        "error_code": None,
    }
    for key in ("repository_resolution", "release_resolution"):
        if key in old:
            entry[key] = deepcopy(old[key])
    try:
        response = client.fetch(slug)
        chain = list(response.api_redirect_chain) if isinstance(response, APIResponse) else []
        payload = repository_payload(response, slug, allow_redirect=len(chain) > 1)
        resolution = None
        if len(chain) > 1:
            resolution = {"full_name": payload["full_name"], "checked_at": now, "api_redirect_chain": chain}
            validate_resolution(resolution, slug, now)
    except (FetchError, ValidationError) as error:
        code = error.code if isinstance(error, FetchError) else "invalid_repository_response"
        entry["repository_status"] = "unavailable" if code == "not_found" else "error"
        entry["error_code"] = "repository_not_found" if code == "not_found" else code
        return entry
    entry.update(repository_status="ok", repository=payload, repository_last_success_at=now)
    entry.pop("repository_resolution", None)
    if resolution is not None:
        entry["repository_resolution"] = resolution
    canonical_name = payload["full_name"]
    try:
        payload = release_payload(client.fetch(canonical_name, release=True), canonical_name)
    except (FetchError, ValidationError) as error:
        code = error.code if isinstance(error, FetchError) else "invalid_release_response"
        if code == "not_found":
            entry.update(release_status="none", release=None, release_last_success_at=now)
            entry.pop("release_resolution", None)
        else:
            entry.update(release_status="error", error_code=code)
        return entry
    entry.update(release_status="ok", release=payload, release_last_success_at=now)
    entry.pop("release_resolution", None)
    if resolution is not None:
        entry["release_resolution"] = deepcopy(resolution)
    return entry


def build_state(slugs, previous, now, client):
    old = {slug.lower(): row for slug, row in previous.get("repositories", {}).items()}
    results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        pending = {pool.submit(update_repository, slug, old.get(slug.lower()), now, client): slug for slug in slugs}
        try:
            for future in as_completed(pending):
                results[pending[future]] = future.result()
        except Exception:
            if hasattr(client, "halted"):
                client.halted.set()
            for future in pending:
                future.cancel()
            raise
    results = dict(sorted(results.items()))
    ok = sum(is_complete(row) for row in results.values())
    return {"schema_version": 1,
            "last_run": {"checked_at": now, "repository_count": len(results),
                         "ok_count": ok, "error_count": len(results) - ok},
            "repositories": results}


def atomic_save(path, state):
    content = (json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix="." + path.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def summary(text):
    print(text)
    destination = os.environ.get("GITHUB_STEP_SUMMARY")
    if destination:
        try:
            with open(destination, "a", encoding="utf-8") as handle:
                handle.write("### Upstream metadata check\n\n" + text + "\n\n")
        except OSError:
            print("Step summary could not be written; metadata result is unaffected.", file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--only", help="Comma-separated repositories; requires a separate --output path")
    parser.add_argument("--now", help="Timezone-aware ISO timestamp for reproducible tests")
    args = parser.parse_args(argv)
    try:
        if args.output.resolve() == args.manifest.resolve():
            raise ValidationError("output_conflicts_with_manifest")
        slugs = validate_manifest(read_json(args.manifest))
        if args.only is not None:
            if args.output.resolve() == DEFAULT_OUTPUT.resolve():
                raise ValidationError("only_requires_separate_output")
            selection = [valid_slug(slug.strip()).lower() for slug in args.only.split(",")]
            available = {slug.lower(): slug for slug in slugs}
            if len(selection) != len(set(selection)) or not set(selection).issubset(available):
                raise ValidationError("invalid_only_selection")
            slugs = [available[slug] for slug in sorted(selection)]
        previous = validate_state(read_json(args.output)) if args.output.exists() else {"repositories": {}}
        now = checked_time(args.now)
        client = APIClient(token=os.environ.get("GITHUB_TOKEN") or None)
        state = build_state(slugs, previous, now, client)
        validate_state(state)
        successes = sum(row["repository_status"] == "ok" for row in state["repositories"].values())
        run = state["last_run"]
        failed = [slug + ": " + (row["error_code"] or row["repository_status"])
                  for slug, row in state["repositories"].items() if not is_complete(row)]
        message = (f"Repositories: {run['repository_count']}; complete: {run['ok_count']}; "
                   f"errors/unavailable: {run['error_count']}; repository checks succeeded: {successes}.")
        if failed:
            message += "\n\n" + "\n".join("- " + item for item in failed[:10])
            if len(failed) > 10:
                message += f"\n- {len(failed) - 10} additional failures (log capped at 10 repositories)."
        if not successes:
            summary(message + "\n\nOutput unchanged: no successful repository checks.")
            return 1
        changed = atomic_save(args.output, state)
        summary(message + ("\n\nOutput updated." if changed else "\n\nOutput already identical."))
        return 1 if client.systemic.is_set() else 0
    except (ValidationError, OSError, ValueError) as error:
        code = str(error) if isinstance(error, ValidationError) else "local_io_or_encoding_error"
        print("Upstream update failed: " + code + ". Existing output was not replaced before validation.", file=sys.stderr)
        return 2
    except Exception:
        # Do not print exceptions that might contain authenticated request headers.
        print("Upstream update failed: unexpected_internal_error.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
