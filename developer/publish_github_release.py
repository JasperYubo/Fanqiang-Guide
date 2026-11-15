"""Publish a commit-bound GitHub Release only after both public sites agree.

Uses the job-scoped GITHUB_TOKEN, creates a draft first, verifies every asset,
then publishes. Existing published releases are immutable to this publisher.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "JasperYubo/Fanqiang-Guide"
ORIGIN = "https://fanqiang.guide/"
PAGES = "https://jasperyubo.github.io/Fanqiang-Guide/"
API_ROOT = "https://api.github.com"
UPLOAD_ROOT = "https://uploads.github.com"
MAX_BYTES = 2 * 1024 * 1024
MAX_ATTEMPTS = 6


class ReleaseError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def read_response(response):
    raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ReleaseError("response_too_large")
    return raw


def fetch_public(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ReleaseError("invalid_public_url")
    if parsed.hostname not in {"fanqiang.guide", "jasperyubo.github.io", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com"}:
        raise ReleaseError("public_host_not_allowed")
    try:
        request = Request(url, headers={"User-Agent": "Fanqiang-Release/1.0", "Cache-Control": "no-cache"})
        with build_opener(NoRedirect).open(request, timeout=8) as response:
            return read_response(response)
    except (HTTPError, URLError, TimeoutError, OSError):
        raise ReleaseError("public_fetch_failed") from None


def json_object(raw):
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError, TypeError):
        raise ReleaseError("invalid_json") from None
    if not isinstance(value, dict):
        raise ReleaseError("expected_json_object")
    return value


def load_receipt_module():
    spec = importlib.util.spec_from_file_location("release_receipt_helper", ROOT / "developer/release_receipt.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_identity(actual, expected, fields, label):
    if not isinstance(actual, dict) or any(actual.get(key) != expected[key] for key in fields):
        raise ReleaseError(label + "_identity_mismatch")


def verify_live(expected, contract, *, fetch=fetch_public, attempts=MAX_ATTEMPTS, sleep=time.sleep):
    """Every retry checks all surfaces together; a stale partial match never passes."""
    fields = ("schema_version", "source_sha", "sync_id", "contract_sha256", "installer_sha256")
    last_error = "unverified"
    for attempt in range(attempts):
        suffix = "?source=" + expected["source_sha"] + "&check=" + str(time.time_ns())
        try:
            origin = json_object(fetch(ORIGIN + "data/site-release.json" + suffix))
            pages = json_object(fetch(PAGES + "deployment.json" + suffix))
            live_contract = json_object(fetch(ORIGIN + "data/product-contract.json" + suffix))
            require_identity(origin, expected, fields, "origin")
            require_identity(pages, expected, fields + ("run_id", "run_attempt", "index_sha256"), "pages")
            if live_contract != contract:
                raise ReleaseError("live_contract_mismatch")
            if digest(fetch(ORIGIN + "server/install.sh" + suffix)) != expected["installer_sha256"]:
                raise ReleaseError("live_installer_mismatch")
            if digest(fetch(PAGES + suffix)) != expected["index_sha256"]:
                raise ReleaseError("live_pages_index_mismatch")
            return {"schema_version": 1, "source_sha": expected["source_sha"], "sync_id": expected["sync_id"],
                    "contract_sha256": expected["contract_sha256"], "installer_sha256": expected["installer_sha256"],
                    "run_id": expected["run_id"], "run_attempt": expected["run_attempt"],
                    "origin_url": ORIGIN, "pages_url": PAGES, "origin_receipt": origin, "pages_receipt": pages,
                    "verified": {"origin_installer": True, "pages_index": True, "shared_contract": True}}
        except ReleaseError as error:
            last_error = str(error)
        if attempt + 1 < attempts:
            sleep(5)
    raise ReleaseError("public_verification_failed:" + last_error)


def source_assets(root, contract):
    mappings = {
        "huarun-install.sh": root / "apps/server/install.sh",
        "AGENT.ilang.md": root / "apps/server/assistant/AGENT.md",
        "SOUL.ilang.md": root / "apps/server/assistant/SOUL.md",
        "huarun.SKILL.ilang.md": root / "apps/server/assistant/skills/huarun/SKILL.md",
    }
    for book_id in ("server", "troubleshooting"):
        matches = [book for book in contract["books"] if book["book_id"] == book_id]
        if len(matches) != 1:
            raise ReleaseError("missing_release_book")
        book = matches[0]
        name = urlsplit(book["download_url"]).path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"fanqiang-[a-z0-9.-]+\.ilang\.md", name):
            raise ReleaseError("invalid_release_book_name")
        path = root / "apps/lookup/runtime/books" / name
        if path.is_symlink() or digest(path.read_bytes()) != book["sha256"]:
            raise ReleaseError("release_book_hash_mismatch")
        mappings[name] = path
    assets = {}
    for name, path in mappings.items():
        if path.is_symlink() or not path.is_file():
            raise ReleaseError("invalid_release_asset")
        raw = path.read_bytes()
        if not raw or len(raw) > MAX_BYTES:
            raise ReleaseError("invalid_release_asset_size")
        assets[name] = raw
    return assets


def asset_manifest(assets):
    return {name: {"sha256": digest(raw), "bytes": len(raw)} for name, raw in sorted(assets.items())}


def complete_assets(static_assets, proof):
    assets = dict(static_assets)
    proof = {**proof, "assets": asset_manifest(static_assets)}
    assets["deployment-proof.json"] = encoded(proof)
    assets["SHA256SUMS"] = "".join(digest(raw) + "  " + name + "\n" for name, raw in sorted(assets.items())).encode()
    return assets


class GitHub:
    def __init__(self, token):
        if not token:
            raise ReleaseError("github_token_missing")
        self._token = token
        self.prefix = "/repos/" + REPOSITORY

    def request(self, method, path, data=None, *, upload=False, binary=False, missing_ok=False):
        if not path.startswith(self.prefix + "/"):
            raise ReleaseError("github_path_not_allowed")
        headers = {"Authorization": "Bearer " + self._token, "User-Agent": "Fanqiang-Release/1.0",
                   "X-GitHub-Api-Version": "2026-03-10", "Accept": "application/octet-stream" if binary else "application/vnd.github+json"}
        if data is not None:
            if isinstance(data, bytes):
                headers["Content-Type"] = "application/octet-stream"
            else:
                headers["Content-Type"] = "application/json"
                data = json.dumps(data).encode()
        request = Request((UPLOAD_ROOT if upload else API_ROOT) + path, data=data, headers=headers, method=method)
        try:
            with build_opener(NoRedirect).open(request, timeout=30) as response:
                raw = read_response(response)
        except HTTPError as error:
            if error.code == 404 and missing_ok:
                return None
            if error.code == 302 and binary and method == "GET":
                # Never forward the GitHub token to the signed asset URL.
                return fetch_public(error.headers.get("Location", ""))
            raise ReleaseError("github_http_" + str(error.code)) from None
        except (URLError, TimeoutError, OSError):
            raise ReleaseError("github_network_error") from None
        if binary:
            return raw
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError):
            raise ReleaseError("github_invalid_json") from None

    def tag_commit(self, tag):
        ref = self.request("GET", self.prefix + "/git/ref/tags/" + quote(tag, safe=""), missing_ok=True)
        if ref is None:
            return None
        obj = ref.get("object", {})
        for _ in range(4):
            if obj.get("type") == "commit":
                return obj.get("sha")
            if obj.get("type") != "tag" or not re.fullmatch(r"[0-9a-f]{40}", str(obj.get("sha", ""))):
                break
            obj = self.request("GET", self.prefix + "/git/tags/" + obj["sha"]).get("object", {})
        raise ReleaseError("invalid_release_tag")

    def find_release(self, tag):
        release = self.request("GET", self.prefix + "/releases/tags/" + quote(tag, safe=""), missing_ok=True)
        if release is not None:
            return release
        # Tag lookup can omit drafts; authenticated listing includes them.
        for page in range(1, 11):
            releases = self.request("GET", self.prefix + "/releases?per_page=100&page=" + str(page))
            if not isinstance(releases, list):
                raise ReleaseError("invalid_release_list")
            found = [item for item in releases if item.get("tag_name") == tag]
            if len(found) > 1:
                raise ReleaseError("duplicate_release_tag")
            if found:
                return found[0]
            if len(releases) < 100:
                return None
        raise ReleaseError("release_lookup_limit")

    def create(self, payload):
        return self.request("POST", self.prefix + "/releases", payload)

    def get(self, release_id):
        return self.request("GET", self.prefix + "/releases/" + str(release_id))

    def assets(self, release_id):
        assets = self.request("GET", self.prefix + "/releases/" + str(release_id) + "/assets?per_page=100")
        if not isinstance(assets, list) or len(assets) >= 100:
            raise ReleaseError("invalid_release_assets")
        return assets

    def read_asset(self, asset):
        return self.request("GET", self.prefix + "/releases/assets/" + str(asset["id"]), binary=True)

    def upload(self, release_id, name, raw):
        return self.request("POST", self.prefix + "/releases/" + str(release_id) + "/assets?name=" + quote(name, safe=""), raw, upload=True)

    def delete_asset(self, asset):
        self.request("DELETE", self.prefix + "/releases/assets/" + str(asset["id"]))

    def publish(self, release_id):
        return self.request("PATCH", self.prefix + "/releases/" + str(release_id), {"draft": False, "make_latest": "true"})


def asset_map(assets):
    mapped = {}
    for asset in assets:
        if not isinstance(asset, dict) or not isinstance(asset.get("id"), int) or asset["id"] <= 0:
            raise ReleaseError("invalid_asset_metadata")
        name = asset.get("name")
        if not isinstance(name, str) or name in mapped:
            raise ReleaseError("duplicate_asset_name")
        mapped[name] = asset
    return mapped


def asset_matches(api, asset, raw):
    if asset.get("state") != "uploaded" or asset.get("size") != len(raw):
        return False
    checksum = asset.get("digest")
    if checksum:
        return checksum == "sha256:" + digest(raw)
    return digest(api.read_asset(asset)) == digest(raw)


def release_identity(release, source_sha, tag):
    if not isinstance(release, dict) or not isinstance(release.get("id"), int) or release["id"] <= 0:
        raise ReleaseError("invalid_release_metadata")
    if release.get("tag_name") != tag or release.get("target_commitish") != source_sha:
        raise ReleaseError("existing_release_wrong_source")


def validate_historical_proof(proof, expected, static_assets):
    fields = ("schema_version", "source_sha", "contract_sha256", "installer_sha256")
    require_identity(proof, expected, fields, "published_proof")
    if not re.fullmatch(r"[1-9][0-9]*", str(proof.get("run_id", ""))) or not isinstance(proof.get("run_attempt"), int) or proof["run_attempt"] < 1:
        raise ReleaseError("invalid_published_proof_run")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", str(proof.get("sync_id", ""))):
        raise ReleaseError("invalid_published_proof_sync")
    require_identity(proof.get("origin_receipt"), proof, fields + ("sync_id",), "published_origin_proof")
    require_identity(proof.get("pages_receipt"), {**proof, "index_sha256": expected["index_sha256"]},
                     fields + ("sync_id", "run_id", "run_attempt", "index_sha256"), "published_pages_proof")
    if proof.get("assets") != asset_manifest(static_assets) or proof.get("verified") != {"origin_installer": True, "pages_index": True, "shared_contract": True}:
        raise ReleaseError("published_proof_asset_mismatch")


def publish_release(api, expected, proof, static_assets, title, body, *, before_publish=lambda: None):
    tag = "release-" + expected["source_sha"][:12]
    target = api.tag_commit(tag)
    if target is not None and target != expected["source_sha"]:
        raise ReleaseError("existing_tag_wrong_source")
    release = api.find_release(tag)
    if release is None:
        release = api.create({"tag_name": tag, "target_commitish": expected["source_sha"], "name": title,
                              "body": body, "draft": True, "prerelease": False})
    release_identity(release, expected["source_sha"], tag)
    release_id = release["id"]
    assets = asset_map(api.assets(release_id))
    files = complete_assets(static_assets, proof)
    if not release.get("draft"):
        if target != expected["source_sha"]:
            raise ReleaseError("published_tag_missing")
        if "deployment-proof.json" not in assets:
            raise ReleaseError("published_proof_missing")
        historical_raw = api.read_asset(assets["deployment-proof.json"])
        historical = json_object(historical_raw)
        validate_historical_proof(historical, expected, static_assets)
        # Preserve the original verified deployment receipt on repeat runs.
        files = complete_assets(static_assets, historical)
        if files["deployment-proof.json"] != historical_raw:
            raise ReleaseError("published_proof_encoding_mismatch")
        if set(assets) != set(files) or any(not asset_matches(api, assets[name], raw) for name, raw in files.items()):
            raise ReleaseError("published_assets_mismatch")
        return {"status": "already_published", "tag": tag, "url": "https://github.com/" + REPOSITORY + "/releases/tag/" + tag}
    if set(assets) - set(files):
        raise ReleaseError("unexpected_draft_assets")
    for name, raw in files.items():
        existing = assets.get(name)
        if existing and asset_matches(api, existing, raw):
            continue
        if existing:
            # Only unpublished receipt/checksum data or failed uploads can be
            # replaced. Never silently replace source artifacts or a release.
            if name not in {"deployment-proof.json", "SHA256SUMS"} and existing.get("state") != "starter":
                raise ReleaseError("draft_source_asset_mismatch")
            api.delete_asset(existing)
        uploaded = api.upload(release_id, name, raw)
        if not asset_matches(api, uploaded, raw):
            raise ReleaseError("upload_verification_failed")
    assets = asset_map(api.assets(release_id))
    if set(assets) != set(files) or any(not asset_matches(api, assets[name], raw) for name, raw in files.items()):
        raise ReleaseError("draft_assets_incomplete")
    before_publish()
    api.publish(release_id)
    observed = api.get(release_id)
    release_identity(observed, expected["source_sha"], tag)
    if observed.get("draft") or api.tag_commit(tag) != expected["source_sha"]:
        raise ReleaseError("publication_not_observed")
    return {"status": "published", "tag": tag, "url": "https://github.com/" + REPOSITORY + "/releases/tag/" + tag}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--sync-id", required=True)
    parser.add_argument("--contract-sha256", required=True)
    args = parser.parse_args()
    if os.environ.get("GITHUB_REPOSITORY", "").lower() != REPOSITORY.lower():
        raise ReleaseError("wrong_github_repository")
    helper = load_receipt_module()
    expected = helper.identity(args.source_sha, args.sync_id, args.contract_sha256)
    helper.verify_checkout(args.source_sha)
    contract = helper.product_contract()
    if helper.contract_digest(contract) != args.contract_sha256:
        raise ReleaseError("source_contract_mismatch")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(r"[1-9][0-9]*", run_attempt):
        raise ReleaseError("workflow_run_identity_missing")
    expected.update({"installer_sha256": helper.installer_digest(), "run_id": run_id, "run_attempt": int(run_attempt),
                     "index_sha256": digest((ROOT / "apps/pages/index.html").read_bytes())})
    proof = verify_live(expected, contract)
    static_assets = source_assets(ROOT, contract)
    installer = static_assets["huarun-install.sh"].decode()
    version = re.search(r'^VERSION="([0-9]+\.[0-9]+\.[0-9]+)"$', installer, re.M)
    if not version:
        raise ReleaseError("assistant_version_missing")
    title = "华润服务器助手 v" + version[1] + " · 本机自动升级"
    body = ("华润服务器助手：先查本站 MCP 文档与排障资料，资料不足时使用 DeepSeek 搜索，修复后复查。VPS 本机定时升级助手，保留节点配置、白名单和 Key，失败自动回滚。\n\n"
            "- [主站与安装入口](https://fanqiang.guide/server/)\n"
            "- [GitHub 项目入口](https://jasperyubo.github.io/Fanqiang-Guide/)\n"
            "- [MCP 与工程书](https://fanqiang.guide/ai/)\n\n"
            "附件包含安装脚本、iLang SOUL 与技能、工程书、SHA256 校验和及双站发布证明。\n\n"
            "源码版本：`" + args.source_sha + "`\n"
            "署名：fanqiang guide <info@fanqiang.guide>\n")
    result = publish_release(GitHub(os.environ.get("GITHUB_TOKEN", "")), expected, proof, static_assets, title, body,
                             before_publish=lambda: verify_live(expected, contract))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        # Controlled codes only; never print API bodies, request headers or tokens.
        code = str(error) if isinstance(error, ReleaseError) else type(error).__name__
        raise SystemExit("Release publication stopped: " + code) from None
