"""Offline parser, transport, privacy, timeout, and snapshot-contract tests."""

import base64
from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("free_proxy_sources", ROOT / "scripts/free_proxy_sources.py")
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)
UID = "550e8400-e29b-41d4-a716-446655440000"
T1, T2, T3 = "2026-09-12T00:00:00Z", "2026-09-13T00:00:00Z", "2026-09-14T00:00:00Z"
SECRET = "PUBLIC-TEST-CREDENTIAL-NOT-FOR-OUTPUT"
URI = "trojan://" + SECRET + "@8.8.8.8:443#test-label"


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def vmess(**overrides):
    value = {"v": "2", "ps": "sample", "add": "8.8.8.8", "port": "443", "id": UID, "aid": "0", "net": "ws"}
    value.update(overrides)
    return "vmess://" + b64(json.dumps(value))


def feed(format="plain_uri", feed_id="example", **kwargs):
    value = {"id": feed_id, "label": "示例来源", "url": "https://raw.githubusercontent.com/Example/project/main/list.txt", "format": format}
    if format == "plain_proxy":
        value["protocol"] = "http"
    value.update(kwargs)
    return value


def manifest(feeds=None):
    return {"schema_version": 1, "sources": [{"id": "source", "name": "示例", "repository": "https://github.com/Example/project",
            "description": "公开来源", "category": "subscription", "feeds": feeds or [feed()]}]}


def fake_fetch(content=URI.encode()):
    def fetch(url, **kwargs):
        return content
    return fetch


def fail_fetch(url, **kwargs):
    raise collector.FetchError("http_404")


class ManifestTests(unittest.TestCase):
    def test_valid_formats_categories_and_return_shape(self):
        value = manifest([feed(), feed("base64_uri", "base64"), feed("plain_proxy", "proxy")])
        self.assertIs(collector.validate_manifest(value), value)
        value["sources"][0]["category"] = "proxy_list"
        collector.validate_manifest(value)
        del value["sources"][0]["category"]
        collector.validate_manifest(value)

    def test_url_allowlist_and_repository_ownership(self):
        invalid = ["http://raw.githubusercontent.com/Example/project/main/list.txt",
                   "https://user@raw.githubusercontent.com/Example/project/main/list.txt",
                   "https://raw.githubusercontent.com:443/Example/project/main/list.txt",
                   "https://raw.githubusercontent.com.evil/Example/project/main/list.txt",
                   "https://raw.githubusercontent.com/Example/project/main/list.txt?token=test",
                   "https://raw.githubusercontent.com/Example/project/main/list.txt#x",
                   "https://raw.githubusercontent.com/Example/project/main/../secret",
                   "https://raw.githubusercontent.com/Example/project/main/%2e%2e/secret",
                   "https://raw.githubusercontent.com/Other/project/main/list.txt",
                   "https://raw.githubusercontent.com/Example/project/main", "https://github.com/Example/project"]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(collector.ValidationError):
                collector.validate_manifest(manifest([feed(url=url)]))

    def test_invalid_types_duplicates_and_plain_proxy_protocol(self):
        variants = []
        for key, value in (("schema_version", True), ("sources", [])):
            item = manifest()
            item[key] = value
            variants.append(item)
        for key, value in (("id", "bad/id"), ("format", "yaml"), ("format", []), ("label", 42)):
            variants.append(manifest([feed(**{key: value})]))
        variants.append(manifest([feed(), feed()]))
        variants.append(manifest([feed("plain_proxy", protocol=None)]))
        item = manifest()
        item["sources"].append(copy.deepcopy(item["sources"][0]))
        variants.append(item)
        item = manifest()
        item["sources"][0]["category"] = []
        variants.append(item)
        for value in variants:
            with self.subTest(value=value), self.assertRaises(collector.ValidationError):
                collector.validate_manifest(value)


class ParsingTests(unittest.TestCase):
    def test_supported_protocols_and_hy2_alias(self):
        values = [vmess(), "vless://" + UID + "@8.8.8.8:443?security=tls", URI,
                  "ss://" + b64("aes-256-gcm:" + SECRET) + "@8.8.8.8:8388",
                  "ssr://" + b64("8.8.8.8:443:origin:aes-256-cfb:plain:" + b64(SECRET) + "/?remarks=dGVzdA"),
                  "hysteria://8.8.8.8:443?auth=" + SECRET,
                  "hysteria2://" + SECRET + "@8.8.8.8:443", "hy2://" + SECRET + "@8.8.8.8:443",
                  "tuic://" + UID + ":" + SECRET + "@8.8.8.8:443"]
        values += [protocol + "://user:password@8.8.8.8:1080" for protocol in ("socks", "socks4", "socks5", "http", "https")]
        result = collector.parse_content("\n".join(values).encode(), feed())
        self.assertEqual(result["valid_count"], 14)
        self.assertEqual(result["unique_count"], 13)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(set(result["protocol_counts"]), collector.PROTOCOLS - {"hy2"})

    def test_fragment_hostname_case_and_ss_encoding_deduplication(self):
        values = ["trojan://pass@Example.com:443#one", "TROJAN://pass@example.COM:443#two",
                  "ss://" + b64("aes-256-gcm:secret") + "@8.8.8.8:8388#first",
                  "ss://" + b64("aes-256-gcm:secret@8.8.8.8:8388") + "#second"]
        result = collector.parse_content("\n".join(values).encode(), feed())
        self.assertEqual((result["valid_count"], result["unique_count"], result["duplicate_count"]), (4, 2, 2))

    def test_distinct_credentials_and_transport_parameters_are_not_merged(self):
        values = ["trojan://first@8.8.8.8:443?type=ws", "trojan://second@8.8.8.8:443?type=ws",
                  "trojan://first@8.8.8.8:443?type=tcp"]
        result = collector.parse_content("\n".join(values).encode(), feed())
        self.assertEqual(result["unique_count"], 3)

    def test_vmess_labels_and_share_versions_do_not_duplicate_connections(self):
        without_metadata = {"add": "8.8.8.8", "port": "443", "id": UID, "aid": "0", "net": "ws"}
        values = [vmess(ps="first"), vmess(ps="second", v="1"),
                  "vmess://" + b64(json.dumps(without_metadata))]
        result = collector.parse_content("\n".join(values).encode(), feed())
        self.assertEqual((result["valid_count"], result["unique_count"], result["duplicate_count"]), (3, 1, 2))

    def test_vmess_connection_options_remain_distinct(self):
        changes = {"add": "1.1.1.1", "port": "8443", "id": "550e8400-e29b-41d4-a716-446655440001",
                   "net": "tcp", "tls": "tls", "host": "example.com", "path": "/ws", "sni": "example.com",
                   "aid": "1", "scy": "auto", "alpn": "h2", "fp": "chrome", "future_option": "preserve"}
        for field, value in changes.items():
            with self.subTest(field=field):
                result = collector.parse_content((vmess() + "\n" + vmess(**{field: value})).encode(), feed())
                self.assertEqual((result["unique_count"], result["duplicate_count"]), (2, 0))

    def test_plain_proxy_uses_only_declared_protocol_and_normalizes_ipv6(self):
        content = b"8.8.8.8:8080\r\n[2606:4700:4700::1111]:1080\n[2606:4700:4700:0:0:0:0:1111]:1080\nexample.com:3128\nuser:pass@8.8.8.8:80\nhttps://example.com/\n"
        result = collector.parse_content(content, feed("plain_proxy", protocol="socks5"))
        self.assertEqual((result["valid_count"], result["unique_count"], result["rejected_count"]), (4, 3, 2))
        self.assertEqual(result["protocol_counts"], {"socks5": 3})

    def test_non_public_and_disguised_hosts_are_rejected_without_dns(self):
        hosts = ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.1.1", "0.0.0.0", "224.0.0.1", "192.0.2.1",
                 "[::1]", "[::ffff:127.0.0.1]", "[fe80::1]", "[fd00::1]", "localhost", "localhost.", "test.localhost",
                 "printer.local", "host.internal", "2130706433", "127.1", "0177.0.0.1", "0x7f.0.0.1"]
        content = (URI + "\n" + "\n".join("trojan://pass@" + host + ":443" for host in hosts)).encode()
        with patch.object(collector.socket, "getaddrinfo", side_effect=AssertionError("DNS must not run")):
            result = collector.parse_content(content, feed())
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["rejected_count"], len(hosts))

    def test_malformed_credentials_ports_vmess_and_web_links_are_rejected(self):
        invalid = ["vless://not-a-uuid@8.8.8.8:443", "trojan://8.8.8.8:443", "tuic://" + UID + "@8.8.8.8:443",
                   "trojan://pass@8.8.8.8:0", "trojan://pass@8.8.8.8:65536", "https://example.com/page",
                   "https://example.com:443/page", "ss://" + b64("aes-256-gcm:") + "@8.8.8.8:443",
                   "vmess://" + b64('{"add":"8.8.8.8","add":"127.0.0.1"}'), vmess(port=True), vmess(id="bad"),
                   "vmess://" + b64("[]"), "vmess://bad!", "unknown://8.8.8.8:443", "trojan://pass@8.8.8.8:443?x=%0A"]
        result = collector.parse_content((URI + "\n" + "\n".join(invalid)).encode(), feed())
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["rejected_count"], len(invalid))

    def test_base64_utf8_bom_comments_and_sha_over_original_bytes(self):
        original = ("\ufeff# comment\n\n" + URI + "\n").encode()
        result = collector.parse_content(original, feed())
        self.assertEqual(result["rejected_count"], 0)
        encoded = base64.b64encode((URI + "\n").encode())
        result = collector.parse_content(encoded, feed("base64_uri"))
        self.assertEqual(result["sha256"], hashlib.sha256(encoded).hexdigest())
        self.assertEqual(result["byte_count"], len(encoded))
        self.assertEqual(result["valid_count"], 1)

    def test_empty_html_oversize_overlong_zero_valid_and_bad_base64_fail(self):
        cases = [(b"", "plain_uri", "empty_content"), (b"<html>bad</html>", "plain_uri", "html_content"),
                 (base64.b64encode(b"<!doctype html>"), "base64_uri", "html_content"),
                 (b"x" * (collector.MAX_BYTES + 1), "plain_uri", "content_too_large"),
                 (b"x" * (collector.MAX_LINE_BYTES + 1), "plain_uri", "line_too_long"),
                 (b"not a node", "plain_uri", "no_valid_entries"), (b"!!!", "base64_uri", "invalid_base64"),
                 (b"\xff", "plain_uri", "invalid_encoding"), (base64.b64encode(b"\xff"), "base64_uri", "invalid_base64")]
        for content, format, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(collector.ValidationError, "^" + code + "$"):
                collector.parse_content(content, feed(format))


class SnapshotTests(unittest.TestCase):
    def test_first_success_same_bytes_then_change_times(self):
        first = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        second = collector.collect(manifest(), first, fetch=fake_fetch(), now=T2)
        third = collector.collect(manifest(), second, fetch=fake_fetch((URI + "\n").encode()), now=T3)
        self.assertEqual(first["feeds"]["example"]["content_changed_at"], T1)
        self.assertEqual(second["feeds"]["example"]["content_changed_at"], T1)
        self.assertEqual(second["feeds"]["example"]["last_success_at"], T2)
        self.assertEqual(third["feeds"]["example"]["content_changed_at"], T3)

    def test_failure_retains_only_last_success_statistics(self):
        first = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        failed = collector.collect(manifest(), first, fetch=fail_fetch, now=T2)
        row = failed["feeds"]["example"]
        for field in collector.STAT_FIELDS:
            self.assertEqual(row[field], first["feeds"]["example"][field])
        self.assertEqual((row["status"], row["error_code"], row["checked_at"]), ("error", "http_404", T2))
        self.assertEqual(failed["last_run"]["ok_count"], 0)
        collector.validate_state(failed)

    def test_first_failure_has_null_statistics_and_zero_successes(self):
        value = collector.collect(manifest(), fetch=fail_fetch, now=T1)
        self.assertTrue(all(value["feeds"]["example"][field] is None for field in collector.STAT_FIELDS))
        self.assertEqual(value["last_run"], {"checked_at": T1, "feed_count": 1, "ok_count": 0, "error_count": 1})

    def test_zero_valid_keeps_previous_counts(self):
        previous = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        value = collector.collect(manifest(), previous, fetch=fake_fetch(b"invalid"), now=T2)
        row = value["feeds"]["example"]
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["error_code"], "no_valid_entries")
        self.assertEqual(row["last_success_at"], T1)
        self.assertEqual(row["valid_count"], 1)

    def test_source_url_format_and_plain_protocol_changes_cannot_keep_old_stats(self):
        previous = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        for changed in (manifest([feed(url="https://raw.githubusercontent.com/Example/project/main/other.txt")]), manifest([feed("base64_uri")])):
            row = collector.collect(changed, previous, fetch=fail_fetch, now=T2)["feeds"]["example"]
            self.assertIsNone(row["sha256"])
        changed = manifest()
        changed["sources"][0]["id"] = "different"
        self.assertIsNone(collector.collect(changed, previous, fetch=fail_fetch, now=T2)["feeds"]["example"]["sha256"])
        previous = collector.collect(manifest([feed("plain_proxy")]), fetch=fake_fetch(b"8.8.8.8:8080"), now=T1)
        changed = manifest([feed("plain_proxy", protocol="socks5")])
        self.assertIsNone(collector.collect(changed, previous, fetch=fail_fetch, now=T2)["feeds"]["example"]["sha256"])

    def test_stats_do_not_contain_nodes_credentials_or_exception_text(self):
        value = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        serialized = json.dumps(value)
        for private in (SECRET, URI, "8.8.8.8", "test-label"):
            self.assertNotIn(private, serialized)
        def failing(url, **kwargs):
            raise RuntimeError(SECRET + URI)
        self.assertNotIn(SECRET, json.dumps(collector.collect(manifest(), fetch=failing, now=T2)))

    def test_invalid_prior_state_is_rejected_before_fetch(self):
        good = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        for key, replacement in (("unique_count", 0), ("duplicate_count", 99), ("sha256", SECRET), ("protocol_counts", {"bad": 1})):
            value = copy.deepcopy(good)
            value["feeds"]["example"][key] = replacement
            with self.subTest(key=key), self.assertRaises(collector.ValidationError):
                collector.collect(manifest(), value, fetch=lambda *a, **k: self.fail("must not fetch"))

    def test_duplicate_json_keys_and_oversize_local_json_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text('{"schema_version":1,"schema_version":2}')
            with self.assertRaisesRegex(collector.ValidationError, "duplicate_json_key"):
                collector.read_json(path)
            path.write_bytes(b"x" * 33)
            with patch.object(collector, "MAX_FILE_BYTES", 32), self.assertRaisesRegex(collector.ValidationError, "json_file_too_large"):
                collector.read_json(path)

    def test_cli_writes_first_failure_but_exits_nonzero_without_exposing_input(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "manifest.json", Path(directory) / "state.json"
            source.write_text(json.dumps(manifest()), encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(collector.main(["--manifest", str(source), "--output", str(output)], fetch=fail_fetch), 1)
            self.assertEqual(collector.read_json(output)["last_run"]["ok_count"], 0)
            with redirect_stdout(stdout):
                self.assertEqual(collector.main(["--manifest", str(source), "--output", str(output)], fetch=fake_fetch()), 0)
            self.assertNotIn(SECRET, stdout.getvalue() + output.read_text())
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_atomic_write_failure_preserves_previous_file(self):
        value = collector.collect(manifest(), fetch=fake_fetch(), now=T1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("previous")
            with patch.object(collector.os, "replace", side_effect=OSError("test")), self.assertRaises(OSError):
                collector.atomic_write(path, value)
            self.assertEqual(path.read_text(), "previous")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_concurrency_is_at_most_three_and_counts_are_per_feed(self):
        lock = threading.Lock()
        active, peak = 0, 0
        def fetching(url, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1
            return (URI + "\n" + URI).encode()
        value = collector.collect(manifest([feed(feed_id="feed-" + str(i)) for i in range(9)]), fetch=fetching, now=T1)
        self.assertLessEqual(peak, 3)
        self.assertEqual(value["last_run"]["ok_count"], 9)
        self.assertTrue(all(row["unique_count"] == 1 and row["duplicate_count"] == 1 for row in value["feeds"].values()))

    def test_run_and_request_deadlines_return_without_waiting_for_stalled_worker(self):
        release = threading.Event()
        def stalled(url, **kwargs):
            release.wait(1)
            return URI.encode()
        try:
            start = time.monotonic()
            value = collector.collect(manifest(), fetch=stalled, budget=0.03, now=T1)
            self.assertLess(time.monotonic() - start, 0.3)
            self.assertEqual(value["feeds"]["example"]["error_code"], "run_deadline")
            with patch.object(collector, "REQUEST_TIMEOUT", 0.03):
                value = collector.collect(manifest(), fetch=stalled, budget=0.4, now=T1)
            self.assertEqual(value["feeds"]["example"]["error_code"], "request_timeout")
        finally:
            release.set()


class FakeResponse:
    def __init__(self, body=b"test", status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def getheader(self, name, default=None):
        return self.headers.get(name, default)
    def read1(self, size):
        part, self.body = self.body[:size], self.body[size:]
        return part


class TransportTests(unittest.TestCase):
    def invoke(self, response, **kwargs):
        calls = []
        class Connection:
            sock = None
            def __init__(self, host, **options):
                calls.append((host, options))
            def request(self, method, path, headers):
                calls.append((method, path, headers))
            def getresponse(self):
                return response
            def close(self):
                pass
        with patch.object(collector.http.client, "HTTPSConnection", Connection):
            result = collector.fetch_public(feed()["url"], **kwargs)
        return result, calls

    def test_request_has_exact_host_path_and_no_auth_or_proxy(self):
        result, calls = self.invoke(FakeResponse(URI.encode()))
        self.assertEqual(result, URI.encode())
        self.assertEqual(calls[0][0], "raw.githubusercontent.com")
        self.assertEqual(calls[1][:2], ("GET", "/Example/project/main/list.txt"))
        self.assertEqual(set(calls[1][2]), {"Accept", "Accept-Encoding", "User-Agent"})
        self.assertEqual(calls[1][2]["Accept-Encoding"], "identity")

    def test_redirect_http_html_compressed_and_size_failures(self):
        cases = [(FakeResponse(status=302, headers={"Location": "https://evil.test/"}), "redirect_blocked"),
                 (FakeResponse(status=404), "http_404"), (FakeResponse(headers={"Content-Type": "text/html"}), "html_content"),
                 (FakeResponse(headers={"Content-Encoding": "gzip"}), "unsupported_content_encoding"),
                 (FakeResponse(headers={"Content-Length": "99999"}), "content_too_large"),
                 (FakeResponse(b"x" * 33), "content_too_large")]
        for response, code in cases:
            with self.subTest(code=code), self.assertRaises(collector.FetchError) as caught:
                self.invoke(response, max_bytes=32)
            self.assertEqual(caught.exception.code, code)

    def test_short_body_with_valid_node_is_not_a_successful_download(self):
        content = URI.encode()
        response = FakeResponse(content, headers={"Content-Length": str(len(content) + 50)})
        with self.assertRaises(collector.FetchError) as caught:
            self.invoke(response)
        self.assertEqual(caught.exception.code, "incomplete_body")


if __name__ == "__main__":
    unittest.main()
