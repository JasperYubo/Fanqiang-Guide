"""Count public proxy-list entries without connecting to or persisting any node."""

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import queue
import re
import socket
import ssl
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
import uuid


ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 2 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_WORKERS = 3
REQUEST_TIMEOUT = 15
RUN_BUDGET_SECONDS = 5 * 60
FORMATS = {"plain_uri", "base64_uri", "plain_proxy"}
PROTOCOLS = {"vmess", "vless", "trojan", "ss", "ssr", "hysteria", "hysteria2", "hy2", "tuic", "socks", "socks4", "socks5", "http", "https"}
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]{0,127}\Z")
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}\Z")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z")
STAT_FIELDS = ("last_success_at", "content_changed_at", "sha256", "byte_count", "valid_count", "unique_count", "duplicate_count", "rejected_count", "protocol_counts")
HTML = re.compile(r"<(?:!doctype\s+html|html|head|body|script|title)(?:\s|>)", re.I)


class ValidationError(ValueError):
    """Messages contain only fixed error codes, never untrusted source text."""


class FetchError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def fail(code):
    raise ValidationError(code)


def valid_text(value, limit=4096, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not value and not empty):
        fail("invalid_text")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        fail("invalid_text")
    return value


def valid_id(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        fail("invalid_id")
    return value


def valid_time(value):
    if not isinstance(value, str) or not TIMESTAMP.fullmatch(value):
        fail("invalid_timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("invalid_timestamp")


def checked_time(value=None):
    parsed = datetime.now(timezone.utc) if value is None else valid_time(value)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def source_repository(value):
    valid_text(value)
    prefix = "https://github.com/"
    if not value.startswith(prefix) or not SLUG.fullmatch(value[len(prefix):]):
        fail("invalid_repository")
    slug = value[len(prefix):]
    if slug.split("/")[1] in {".", ".."}:
        fail("invalid_repository")
    return slug


def raw_url(value, repository=None):
    valid_text(value)
    try:
        parsed = urlsplit(value)
        safe = (parsed.scheme == "https" and parsed.netloc == "raw.githubusercontent.com"
                and parsed.username is None and parsed.password is None and parsed.port is None
                and not parsed.query and not parsed.fragment)
    except ValueError:
        fail("invalid_feed_url")
    parts = parsed.path.split("/")
    if (not safe or len(parts) < 5 or parts[0] != "" or "%" in parsed.path
            or any(not re.fullmatch(r"[A-Za-z0-9_.~+-]+", p) or p in {".", ".."} for p in parts[1:])):
        fail("invalid_feed_url")
    slug = "/".join(parts[1:3])
    if not SLUG.fullmatch(slug):
        fail("invalid_feed_url")
    if repository is not None and slug.casefold() != source_repository(repository).casefold():
        fail("feed_repository_mismatch")
    return value


def validate_manifest(value):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        fail("invalid_manifest_schema")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources or len(sources) > 1000:
        fail("invalid_sources")
    source_ids, feed_ids = set(), set()
    for source in sources:
        if not isinstance(source, dict):
            fail("invalid_source")
        source_id = valid_id(source.get("id"))
        if source_id in source_ids:
            fail("duplicate_source_id")
        source_ids.add(source_id)
        valid_text(source.get("name"), 256)
        valid_text(source.get("description"), empty=True)
        if "category" in source and (not isinstance(source["category"], str) or source["category"] not in {"subscription", "proxy_list"}):
            fail("invalid_source_category")
        source_repository(source.get("repository"))
        feeds = source.get("feeds")
        if not isinstance(feeds, list) or not feeds or len(feeds) > 1000:
            fail("invalid_feeds")
        for feed in feeds:
            if not isinstance(feed, dict):
                fail("invalid_feed")
            feed_id = valid_id(feed.get("id"))
            if feed_id in feed_ids:
                fail("duplicate_feed_id")
            feed_ids.add(feed_id)
            valid_text(feed.get("label"), 256)
            if not isinstance(feed.get("format"), str) or feed["format"] not in FORMATS:
                fail("invalid_format")
            if feed["format"] == "plain_proxy" and (not isinstance(feed.get("protocol"), str) or feed["protocol"] not in {"http", "socks4", "socks5"}):
                fail("invalid_plain_proxy_protocol")
            raw_url(feed.get("url"), source["repository"])
    if len(feed_ids) > 1000:
        fail("too_many_feeds")
    return value


def validate_state(value):
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        fail("invalid_state_schema")
    feeds, run = value.get("feeds"), value.get("last_run")
    if not isinstance(feeds, dict) or not isinstance(run, dict):
        fail("invalid_state")
    valid_time(run.get("checked_at"))
    for key in ("feed_count", "ok_count", "error_count"):
        if type(run.get(key)) is not int or run[key] < 0:
            fail("invalid_run_count")
    if run["feed_count"] != len(feeds) or run["ok_count"] + run["error_count"] != len(feeds):
        fail("invalid_run_count")
    successes = 0
    for feed_id, row in feeds.items():
        valid_id(feed_id)
        if not isinstance(row, dict):
            fail("invalid_feed_state")
        valid_id(row.get("source_id"))
        raw_url(row.get("url"))
        if (not isinstance(row.get("format"), str) or row["format"] not in FORMATS
                or not isinstance(row.get("status"), str) or row["status"] not in {"ok", "error"}):
            fail("invalid_feed_state")
        valid_time(row.get("checked_at"))
        if row["status"] == "ok":
            successes += 1
            if row.get("error_code") is not None:
                fail("invalid_error_code")
        elif not isinstance(row.get("error_code"), str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", row["error_code"]):
            fail("invalid_error_code")
        if any(field not in row for field in STAT_FIELDS):
            fail("missing_stat_fields")
        if row["last_success_at"] is None:
            if row["status"] == "ok" or any(row[field] is not None for field in STAT_FIELDS):
                fail("invalid_empty_stats")
            continue
        valid_time(row["last_success_at"])
        valid_time(row["content_changed_at"])
        if not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            fail("invalid_digest")
        for field in ("byte_count", "valid_count", "unique_count", "duplicate_count", "rejected_count"):
            if type(row[field]) is not int or row[field] < 0:
                fail("invalid_stat_count")
        if not 1 <= row["byte_count"] <= MAX_BYTES or not 1 <= row["unique_count"] <= row["valid_count"]:
            fail("invalid_stat_count")
        if row["valid_count"] != row["unique_count"] + row["duplicate_count"]:
            fail("invalid_stat_count")
        counts = row["protocol_counts"]
        if not isinstance(counts, dict) or any(k not in PROTOCOLS or type(n) is not int or n <= 0 for k, n in counts.items()):
            fail("invalid_protocol_counts")
        if sum(counts.values()) != row["unique_count"]:
            fail("invalid_protocol_counts")
    if successes != run["ok_count"]:
        fail("invalid_run_count")
    return value


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail("duplicate_json_key")
        result[key] = value
    return result


def reject_constant(value):
    fail("invalid_json_constant")


def read_json(path):
    with Path(path).open("rb") as handle:
        content = handle.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        fail("json_file_too_large")
    try:
        return json.loads(content.decode("utf-8-sig"), object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        fail("invalid_json")


def decode_base64(value):
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9+/_-]+={0,2}", value):
        fail("invalid_base64")
    try:
        result = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if len(result) > MAX_BYTES:
            fail("content_too_large")
        return result.decode("utf-8")
    except (ValueError, UnicodeError):
        fail("invalid_base64")


def public_host(value):
    if not isinstance(value, str) or not value or any(c in value for c in "%/\\@?#[]"):
        fail("invalid_host")
    value = value.lower().removesuffix(".")
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        address = None
    if address is not None:
        mapped = getattr(address, "ipv4_mapped", None)
        if (not address.is_global or address.is_multicast or address.is_reserved
                or (mapped is not None and not mapped.is_global)):
            fail("non_public_host")
        return address.compressed
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError:
        fail("invalid_host")
    labels = value.split(".")
    if (len(value) > 253 or len(labels) < 2
            or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)
            or all(re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]+)", label) for label in labels)
            or labels[-1] in {"localhost", "local", "localdomain", "internal", "lan", "home", "invalid", "test"}):
        fail("non_public_host")
    return value


def port_number(value):
    if type(value) not in {str, int} or not re.fullmatch(r"[0-9]{1,5}", str(value)) or not 1 <= int(value) <= 65535:
        fail("invalid_port")
    return int(value)


def uri_text(value):
    if not value or re.search(r"[\s\x00-\x1f\x7f<>\\]", value) or re.search(r"%(?![0-9A-Fa-f]{2})", value):
        fail("invalid_uri")
    if re.search(r"[\x00-\x1f\x7f]", unquote(value)):
        fail("invalid_uri")
    return value


def endpoint(value):
    uri_text(value)
    try:
        parsed = urlsplit("//" + value)
        if parsed.username is not None or parsed.password is not None or parsed.path or parsed.query or parsed.fragment:
            fail("invalid_endpoint")
        return public_host(parsed.hostname), port_number(parsed.port)
    except (ValueError, TypeError):
        fail("invalid_endpoint")


def identity(protocol, values):
    serialized = json.dumps([protocol, values], ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return protocol, hashlib.sha256(serialized.encode("utf-8")).digest()


def uuid_text(value):
    try:
        if not isinstance(value, str):
            fail("invalid_uuid")
        return str(uuid.UUID(value))
    except ValueError:
        fail("invalid_uuid")


def parse_uri(line):
    line = line.split("#", 1)[0]
    uri_text(line)
    if "://" not in line:
        fail("invalid_uri")
    protocol, body = line.split("://", 1)
    protocol = protocol.lower()
    if protocol not in PROTOCOLS:
        fail("unsupported_protocol")
    if protocol == "hy2":
        protocol = "hysteria2"
    if protocol == "vmess":
        try:
            data = json.loads(decode_base64(body), object_pairs_hook=no_duplicate_keys, parse_constant=reject_constant)
        except (json.JSONDecodeError, RecursionError):
            fail("invalid_vmess")
        if not isinstance(data, dict):
            fail("invalid_vmess")
        data["add"] = public_host(data.get("add"))
        data["port"] = port_number(data.get("port"))
        data["id"] = uuid_text(data.get("id"))
        # Display label and share-format version do not change the connection.
        # Preserve every other field, including transport/TLS and future options.
        data.pop("ps", None)
        data.pop("v", None)
        return identity(protocol, data)
    if protocol == "ssr":
        decoded = decode_base64(body)
        main, separator, query_string = decoded.partition("/?")
        parts = main.rsplit(":", 5)
        if len(parts) != 6:
            fail("invalid_ssr")
        host, port, transport, method, obfs, password = parts
        host = host[1:-1] if host.startswith("[") and host.endswith("]") else host
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", field) for field in (transport, method, obfs)):
            fail("invalid_ssr")
        password = valid_text(decode_base64(password))
        return identity(protocol, [public_host(host), port_number(port), transport, method, obfs, password, query_string])
    if protocol == "ss":
        authority, _, query_string = body.partition("?")
        authority = authority.removesuffix("/")
        if "@" not in authority:
            authority = decode_base64(authority)
        if "@" not in authority:
            fail("invalid_ss")
        credentials, target = authority.rsplit("@", 1)
        credentials = unquote(credentials)
        if ":" not in credentials:
            credentials = decode_base64(credentials)
        method, separator, password = credentials.partition(":")
        if not separator or not re.fullmatch(r"[A-Za-z0-9_-]+", method):
            fail("invalid_ss")
        valid_text(password)
        host, port = endpoint(target)
        return identity(protocol, [host, port, method, password, query_string])
    try:
        parsed = urlsplit(protocol + "://" + body)
        host, port = public_host(parsed.hostname), port_number(parsed.port)
        username, password = parsed.username, parsed.password
    except (ValueError, TypeError):
        fail("invalid_uri")
    username = unquote(username) if username is not None else None
    password = unquote(password) if password is not None else None
    if username is not None:
        valid_text(username)
    if password is not None:
        valid_text(password)
    if protocol == "vless":
        username = uuid_text(username)
        if password is not None:
            fail("invalid_vless")
    elif protocol == "trojan" and not username:
        fail("invalid_trojan")
    elif protocol == "tuic":
        username = uuid_text(username)
        if not password:
            fail("invalid_tuic")
    if protocol in {"http", "https", "socks", "socks4", "socks5"} and (parsed.path not in {"", "/"} or parsed.query):
        fail("invalid_proxy_uri")
    return identity(protocol, [host, port, username, password, parsed.path, parsed.query])


def parse_content(content, feed):
    if not isinstance(content, bytes):
        fail("invalid_response_type")
    if len(content) > MAX_BYTES:
        fail("content_too_large")
    if not content:
        fail("empty_content")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeError:
        fail("invalid_encoding")
    if HTML.search(text):
        fail("html_content")
    if feed["format"] == "base64_uri":
        text = decode_base64("".join(text.split()))
        if HTML.search(text):
            fail("html_content")
    seen, counts = set(), {}
    valid, rejected = 0, 0
    for line in text.splitlines():
        if len(line.encode("utf-8")) > MAX_LINE_BYTES:
            fail("line_too_long")
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        try:
            if feed["format"] == "plain_proxy":
                protocol = feed["protocol"]
                kind, digest = identity(protocol, endpoint(line))
            else:
                kind, digest = parse_uri(line)
        except (ValidationError, ValueError, TypeError, RecursionError):
            rejected += 1
            continue
        valid += 1
        if digest not in seen:
            seen.add(digest)
            counts[kind] = counts.get(kind, 0) + 1
    if valid == 0:
        fail("no_valid_entries")
    return {"sha256": hashlib.sha256(content).hexdigest(), "byte_count": len(content),
            "valid_count": valid, "unique_count": len(seen), "duplicate_count": valid - len(seen),
            "rejected_count": rejected, "protocol_counts": dict(sorted(counts.items()))}


def fetch_public(url, timeout=REQUEST_TIMEOUT, max_bytes=MAX_BYTES, deadline=None):
    """Direct HTTPS, no environment proxy, credentials, redirects, or decompression."""
    raw_url(url)
    remaining = min(timeout, (deadline - time.monotonic()) if deadline is not None else timeout)
    if remaining <= 0:
        raise FetchError("run_deadline")
    request_deadline = time.monotonic() + remaining
    connection = http.client.HTTPSConnection("raw.githubusercontent.com", timeout=remaining, context=ssl.create_default_context())

    def abort():
        sock = connection.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        connection.close()

    timer = threading.Timer(remaining, abort)
    timer.daemon = True
    timer.start()
    try:
        connection.request("GET", urlsplit(url).path, headers={"Accept": "text/plain, application/octet-stream", "Accept-Encoding": "identity", "User-Agent": "FanqiangGuideSourceStats/1.0"})
        with connection.getresponse() as response:
            if 300 <= response.status <= 399:
                raise FetchError("redirect_blocked")
            if response.status != 200:
                raise FetchError("http_" + str(response.status))
            if "html" in response.getheader("Content-Type", "").lower():
                raise FetchError("html_content")
            if response.getheader("Content-Encoding", "identity").lower() not in {"", "identity"}:
                raise FetchError("unsupported_content_encoding")
            length = response.getheader("Content-Length")
            if length is not None:
                if not re.fullmatch(r"[0-9]+", length):
                    raise FetchError("invalid_content_length")
                if int(length) > max_bytes:
                    raise FetchError("content_too_large")
            chunks, size = [], 0
            while True:
                remaining = request_deadline - time.monotonic()
                if remaining <= 0:
                    raise FetchError("request_timeout")
                if connection.sock is not None:
                    connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, max_bytes + 1 - size))
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise FetchError("content_too_large")
                chunks.append(chunk)
            if time.monotonic() > request_deadline:
                raise FetchError("request_timeout")
            if length is not None and size != int(length):
                raise FetchError("incomplete_body")
            return b"".join(chunks)
    except (socket.timeout, TimeoutError):
        raise FetchError("request_timeout") from None
    except (OSError, http.client.HTTPException, ValueError):
        code = "request_timeout" if time.monotonic() >= request_deadline else "network_error"
        raise FetchError(code) from None
    finally:
        timer.cancel()
        connection.close()


def compatible_previous(previous, source_id, feed):
    if (not previous or previous["source_id"] != source_id or previous["url"] != feed["url"]
            or previous["format"] != feed["format"]):
        return None
    if (feed["format"] == "plain_proxy" and previous["protocol_counts"] is not None
            and set(previous["protocol_counts"]) != {feed["protocol"]}):
        return None
    return previous


def feed_result(source_id, feed, previous, checked_at, stats=None, error_code=None):
    old = compatible_previous(previous, source_id, feed)
    row = {"source_id": source_id, "url": feed["url"], "format": feed["format"], "checked_at": checked_at,
           "status": "ok" if stats is not None else "error", "error_code": error_code}
    row.update({field: deepcopy(old[field]) if old else None for field in STAT_FIELDS})
    if stats is not None:
        row.update(stats)
        row["last_success_at"] = checked_at
        row["content_changed_at"] = old["content_changed_at"] if old and old["sha256"] == stats["sha256"] else checked_at
    return row


def collect(manifest, previous=None, fetch=fetch_public, now=None, budget=RUN_BUDGET_SECONDS):
    validate_manifest(manifest)
    if previous is not None:
        validate_state(previous)
    checked_at = checked_time(now)
    deadline = time.monotonic() + min(max(float(budget), 0), RUN_BUDGET_SECONDS)
    jobs = [(source["id"], feed) for source in manifest["sources"] for feed in source["feeds"]]
    pending, completed = queue.Queue(), queue.Queue()
    stop = threading.Event()
    for job in jobs:
        pending.put(job)

    def worker():
        while not stop.is_set():
            try:
                source_id, feed = pending.get_nowait()
            except queue.Empty:
                return
            stats, error = None, None
            request_started = time.monotonic()
            completed.put(("started", feed["id"], request_started, None))
            if time.monotonic() >= deadline:
                error = "run_deadline"
            else:
                try:
                    content = fetch(feed["url"], timeout=min(REQUEST_TIMEOUT, deadline - time.monotonic()), max_bytes=MAX_BYTES, deadline=deadline)
                    if time.monotonic() >= deadline:
                        raise FetchError("run_deadline")
                    stats = parse_content(content, feed)
                except FetchError as exc:
                    error = exc.code if isinstance(exc.code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", exc.code) else "fetch_error"
                except ValidationError as exc:
                    error = str(exc)
                except Exception:
                    error = "unexpected_error"
            completed.put(("done", feed["id"], stats, error))

    # Daemon workers keep an abnormal DNS/transport stall from holding process exit.
    # At most three workers exist; a stalled worker is never replaced by another.
    threads = [threading.Thread(target=worker, daemon=True) for _ in range(min(MAX_WORKERS, len(jobs)))]
    for thread in threads:
        thread.start()
    results, active = {}, {}
    while len(results) < len(jobs):
        current = time.monotonic()
        for feed_id, started in list(active.items()):
            if current - started >= REQUEST_TIMEOUT:
                results[feed_id] = (None, "request_timeout")
                del active[feed_id]
        if len(results) == len(jobs):
            break
        remaining = deadline - current
        if remaining <= 0:
            break
        if active:
            remaining = min(remaining, max(0, min(active.values()) + REQUEST_TIMEOUT - current))
        try:
            event, feed_id, stats, error = completed.get(timeout=remaining)
        except queue.Empty:
            continue
        if event == "started":
            active[feed_id] = stats
        elif feed_id not in results:
            started = active.pop(feed_id, current)
            results[feed_id] = (None, "request_timeout") if time.monotonic() - started >= REQUEST_TIMEOUT else (stats, error)
    stop.set()
    old_feeds = previous["feeds"] if previous else {}
    rows = {}
    for source_id, feed in jobs:
        stats, error = results.get(feed["id"], (None, "run_deadline"))
        rows[feed["id"]] = feed_result(source_id, feed, old_feeds.get(feed["id"]), checked_at, stats, error)
    ok_count = sum(row["status"] == "ok" for row in rows.values())
    value = {"schema_version": 1, "last_run": {"checked_at": checked_at, "feed_count": len(rows), "ok_count": ok_count, "error_count": len(rows) - ok_count}, "feeds": dict(sorted(rows.items()))}
    validate_state(value)
    return value


def atomic_write(path, value):
    validate_state(value)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", prefix="." + path.name + ".", suffix=".tmp", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None, fetch=fetch_public):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "config/free-proxy-sources.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/free-proxy-sources.json")
    args = parser.parse_args(argv)
    try:
        manifest = read_json(args.manifest)
        previous = read_json(args.output) if args.output.exists() else None
        result = collect(manifest, previous, fetch=fetch)
        atomic_write(args.output, result)
    except (OSError, ValueError, RecursionError):
        print("Source check failed: invalid input or output.")
        return 2
    run = result["last_run"]
    print("Checked %d feeds: %d succeeded, %d failed." % (run["feed_count"], run["ok_count"], run["error_count"]))
    return 0 if run["ok_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
