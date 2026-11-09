"""Project the existing allowlisted GitHub checks into entity freshness metadata.

This module performs no network access and reads no credentials. Repository and
stable-release observations do not re-verify authored device compatibility or
installation facts. Failed upstream checks already retain their last successful
payloads; this projection preserves their timestamps and marks the result stale.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("fanqiang_existing_upstream", ROOT / "scripts/update_upstream.py")
upstream = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(upstream)
TTL_HOURS = 48
MAX_RECORDS = 2000
SCOPE = "repository_metadata_only"


def utc(value):
    upstream.valid_time(value)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def stamp(value):
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def knowledge_records(value):
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_RECORDS:
        raise upstream.ValidationError("invalid_knowledge_records")
    result = {}
    for item in value:
        if not isinstance(item, dict):
            raise upstream.ValidationError("invalid_knowledge_record")
        identifier = item.get("id")
        verification = item.get("verification")
        if (not isinstance(identifier, str) or not upstream.ENTITY_ID.fullmatch(identifier)
                or identifier in result or not isinstance(verification, dict)):
            raise upstream.ValidationError("invalid_knowledge_identity")
        checked = verification.get("checked_at")
        try:
            if not isinstance(checked, str) or date.fromisoformat(checked).isoformat() != checked:
                raise ValueError()
        except (TypeError, ValueError):
            raise upstream.ValidationError("invalid_knowledge_checked_at") from None
        result[identifier] = item
    return result


def base_record(item):
    return {"scope": SCOPE, "status": "unmonitored", "knowledge_checked_at": item["verification"]["checked_at"],
            "source_checked_at": None, "last_attempt_at": None, "expires_at": None,
            "repository_status": "not_monitored", "release_status": "not_checked", "error_code": None,
            "requested_repository": None, "repository": None, "latest_release": None,
            "repository_resolution": None, "release_resolution": None,
            "repository_availability": "not_monitored", "installation_source_status": "not_verified",
            "availability_checked_at": None, "availability_notice": None}


def project_record(item, slug, entry, as_of):
    result = base_record(item)
    result.update(status="unknown", requested_repository=slug, repository_status=entry["repository_status"],
                  release_status=entry["release_status"], error_code=entry["error_code"],
                  last_attempt_at=entry["checked_at"])
    for key in ("checked_at", "repository_last_success_at", "release_last_success_at"):
        if entry.get(key) and utc(entry[key]) > as_of:
            raise upstream.ValidationError("future_observation_timestamp")
    repo, release = entry["repository"], entry["release"]
    if repo is not None:
        result["repository"] = {"full_name": repo["full_name"], "url": repo["html_url"],
                                "archived": repo["archived"], "disabled": repo["disabled"],
                                "pushed_at": repo["pushed_at"], "checked_at": entry["repository_last_success_at"]}
    if release is not None:
        release_name = entry.get("release_resolution", {}).get("full_name", slug)
        result["latest_release"] = {"tag_name": release["tag_name"], "url": release["html_url"],
                                    "published_at": release["published_at"], "checked_at": entry["release_last_success_at"],
                                    "repository_full_name": release_name}
    for key in ("repository_resolution", "release_resolution"):
        if key in entry:
            result[key] = deepcopy(entry[key])
    repo_success, release_success = entry["repository_last_success_at"], entry["release_last_success_at"]
    same_identity = (repo is not None and (release is None or
                     result["latest_release"]["repository_full_name"].lower() == repo["full_name"].lower()))
    complete_evidence = same_identity and repo_success is not None and release_success is not None
    if complete_evidence:
        observed = min(utc(repo_success), utc(release_success))
        expires = observed + timedelta(hours=TTL_HOURS)
        result.update(source_checked_at=stamp(observed), expires_at=stamp(expires))
        result["status"] = "current" if upstream.is_complete(entry) and entry["error_code"] is None and as_of < expires else "stale"
    elif repo is not None or release is not None:
        result["status"] = "stale"
    if entry["repository_status"] == "unavailable" and entry["error_code"] == "repository_not_found":
        result.update(repository_availability="unavailable", installation_source_status="withheld",
                      availability_checked_at=entry["checked_at"],
                      availability_notice="原始仓库当前返回 404；历史版本仅作参考，暂不作为安装或下载来源。未确认删除或官方迁移，不以镜像或同名分支替代。")
    elif entry["repository_status"] == "ok":
        result.update(repository_availability="available", installation_source_status="requires_release_verification",
                      availability_checked_at=entry["checked_at"])
    else:
        result.update(repository_availability="unknown", installation_source_status="not_verified",
                      availability_checked_at=entry["checked_at"])
    return result


def build_projection(library, manifest, state, *, as_of, input_sha256=None):
    """Deterministic for the same validated inputs and explicit as_of timestamp."""
    now = utc(as_of)
    records = knowledge_records(library)
    upstream.validate_manifest(manifest)
    upstream.validate_state(state)
    if utc(state["last_run"]["checked_at"]) > now:
        raise upstream.ValidationError("future_source_run_timestamp")
    configured = {row["full_name"].lower(): row for row in manifest["repositories"]}
    observations = {slug.lower(): entry for slug, entry in state["repositories"].items()}
    if set(configured) != set(observations):
        raise upstream.ValidationError("source_manifest_repository_set_mismatch")
    covered = {entity for row in manifest["repositories"] for entity in row["entity_ids"]}
    excluded = {row["entity_id"] for row in manifest["excluded"]}
    if covered | excluded != set(records):
        raise upstream.ValidationError("source_manifest_entity_set_mismatch")
    projected = {identifier: base_record(item) for identifier, item in records.items()}
    for key, configured_repo in configured.items():
        slug = configured_repo["full_name"]
        for identifier in configured_repo["entity_ids"]:
            projected[identifier] = project_record(records[identifier], slug, observations[key], now)
    projected = dict(sorted(projected.items()))
    counts = {status: sum(row["status"] == status for row in projected.values())
              for status in ("current", "stale", "unknown", "unmonitored")}
    return {"schema_version": 1, "generated_at": stamp(now), "source_run_at": state["last_run"]["checked_at"],
            "freshness_ttl_hours": TTL_HOURS, "scope": SCOPE,
            "input_sha256": input_sha256 or {}, "record_count": len(projected),
            "repository_count": len(configured), "counts": counts,
            "availability_counts": {status: sum(row["repository_availability"] == status for row in projected.values())
                                    for status in ("available", "unavailable", "unknown", "not_monitored")},
            "records": projected}


def atomic_save(path, value):
    encoded = (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > upstream.MAX_FILE_BYTES:
        raise upstream.ValidationError("projection_too_large")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise upstream.ValidationError("output_symlink_blocked")
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=ROOT / "apps/lookup/runtime/library.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "config/upstream-repositories.json")
    parser.add_argument("--state", type=Path, default=ROOT / "data/upstream.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/source-freshness.json")
    parser.add_argument("--as-of", help="Explicit UTC evaluation time; defaults to current UTC.")
    args = parser.parse_args(argv)
    try:
        paths = {"library": args.library, "manifest": args.manifest, "upstream": args.state}
        if args.output.resolve() in {path.resolve() for path in paths.values()}:
            raise upstream.ValidationError("output_overlaps_source_input")
        raw = {}
        for name, path in paths.items():
            with path.open("rb") as stream:
                raw[name] = stream.read(upstream.MAX_FILE_BYTES + 1)
        if any(len(body) > upstream.MAX_FILE_BYTES for body in raw.values()):
            raise upstream.ValidationError("input_too_large")
        data = {name: json.loads(body.decode("utf-8-sig")) for name, body in raw.items()}
        as_of = args.as_of or stamp(datetime.now(timezone.utc))
        result = build_projection(data["library"], data["manifest"], data["upstream"], as_of=as_of,
                                  input_sha256={name: hashlib.sha256(body).hexdigest() for name, body in raw.items()})
        atomic_save(args.output, result)
    except (upstream.ValidationError, ValueError, UnicodeError, OSError):
        print(json.dumps({"ok": False, "error_code": "freshness_projection_failed"}), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "record_count": result["record_count"], "repository_count": result["repository_count"],
                      "counts": result["counts"], "generated_at": result["generated_at"],
                      "source_run_at": result["source_run_at"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
