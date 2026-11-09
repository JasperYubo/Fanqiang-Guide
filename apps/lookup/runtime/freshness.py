"""Live public source-check snapshot, separate from reviewed knowledge facts."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

def utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError):
        return None

class SourceFreshness:
    def __init__(self, path=None, clock=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.records, self.generated_at, self.snapshot = {}, None, {}
        self.signature, self.load_error = None, None
        fallback = Path(__file__).with_name("source-freshness.json")
        if not fallback.exists():
            fallback = Path(__file__).resolve().parents[3] / "data/source-freshness.json"
        self.path = Path(path) if path is not None else fallback
        if path is not None and not self.path.exists() and fallback.exists():
            self._accept(fallback)
        self.refresh()

    def _accept(self, path):
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Invalid source freshness snapshot")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid source freshness schema")
        records = data.get("records")
        if (data.get("schema_version") != 1 or not isinstance(records, dict) or
                len(records) > 10000 or not utc(data.get("generated_at")) or
                any(not isinstance(v, dict) or v.get("status") not in
                    {"current", "stale", "unknown", "unmonitored"} for v in records.values())):
            raise ValueError("Invalid source freshness schema")
        # Never replace successful current metadata with an older file.
        if self.generated_at and utc(data["generated_at"]) < utc(self.generated_at):
            raise ValueError("Source freshness snapshot moved backwards")
        self.snapshot = data
        self.records = records
        self.generated_at = data["generated_at"]
        self.load_error = None

    def refresh(self):
        try:
            info = self.path.stat()
            signature = (info.st_ino, info.st_mtime_ns, info.st_size)
            if signature == self.signature:
                return
            self.signature = signature
            self._accept(self.path)
        except (OSError, ValueError, TypeError, KeyError):
            self.load_error = "latest_snapshot_unavailable_using_last_valid"

    def for_record(self, ident):
        self.refresh()
        result = deepcopy(self.records.get(ident, {
            "status": "unmonitored", "source_checked_at": None, "last_attempt_at": None,
            "expires_at": None, "scope": "repository_metadata_only"}))
        if result.get("status") == "current":
            expiry = utc(result.get("expires_at"))
            if expiry is None or self.clock() >= expiry:
                result["status"] = "stale"
                result["stale_reason"] = "successful_source_check_expired"
        if self.load_error:
            result["snapshot_load_status"] = self.load_error
        result["does_not_revalidate_compatibility"] = True
        return result

    def unavailable_ids(self, reviewed_unavailable=None):
        self.refresh()
        unavailable = {ident for ident, row in self.records.items()
                       if row.get("repository_availability") == "unavailable" or
                       row.get("repository_status") == "unavailable" and row.get("error_code") == "repository_not_found"}
        # Old successful metadata cannot overturn a later unavailable review.
        # Date-only reviews conservatively require success after that UTC day.
        for ident, reviewed_at in (reviewed_unavailable or {}).items():
            row = self.records.get(ident, {})
            repository = row.get("repository") or {}
            success = utc(repository.get("checked_at")) if isinstance(repository, dict) else None
            reviewed = utc(reviewed_at + "T23:59:59.999999Z" if isinstance(reviewed_at, str) and len(reviewed_at) == 10 else reviewed_at)
            if row.get("repository_status") != "ok" or success is None or reviewed is None or success <= reviewed:
                unavailable.add(ident)
        return frozenset(unavailable)

    def public_snapshot(self):
        self.refresh()
        return {**{k: deepcopy(v) for k, v in self.snapshot.items() if k != "records"},
            "records": {ident: self.for_record(ident) for ident in self.records},
            "snapshot_load_status": self.load_error or "ok"}

    def summary(self):
        self.refresh()
        counts = {}
        for ident in self.records:
            status = self.for_record(ident)["status"]
            counts[status] = counts.get(status, 0) + 1
        return {"generated_at": self.generated_at, "record_count": len(self.records),
            "statuses": counts, "scope": "repository_metadata_only",
            "snapshot_load_status": self.load_error or "ok",
            "knowledge_facts_are_not_revalidated_by_release_checks": True}
