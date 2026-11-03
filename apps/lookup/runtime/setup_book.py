"""Pinned public books, shared rules and scoped validation metadata.

Resources are the canonical MCP book interface. The historical setup-book
helpers remain only as compatibility adapters to the autosetup registry entry.
"""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BOOK_PATH = ROOT / "books/fanqiang-autosetup-v2.0.ilang.md"
BOOK_SHA256 = "181d28bd238f2a7d3d29a2f72ab569aec83d7e983bc3e7457a14c2ae3da51093"
BOOK_TITLE = "Device setup, phone selection and household hotspot engineering book"
BOOK_RESOURCE_URI = "fanqiang://books/autosetup"
BOOK_DOWNLOAD_URL = "https://fanqiang.guide/ai/books/" + BOOK_PATH.name
BOOK_RESOURCE_TEMPLATE = "fanqiang://books/{book_id}"
RULES_PATH = ROOT / "answer-rules.ilang"
RULES_RESOURCE_URI = "fanqiang://rules/answer"
NO_ARGUMENTS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
BOOK_REGISTRY = {
    "autosetup": {"path": BOOK_PATH, "sha256": BOOK_SHA256, "title": BOOK_TITLE,
        "version": "2.0", "last_updated": "2026-11-02",
        "evidence_path": ROOT / "books/fanqiang-autosetup-v2.0.evidence.json",
        "evidence_sha256": "498b37722693a052c785932bc963327969c58f872bc5ca676655f5e574798190"},
}
CAPABILITY_BOUNDARIES = (
    "This knowledge MCP is read-only; the user's authorized AI operates the actual target device.",
    "The book grants no extra authorization. Respect the active task and required system permissions.",
    "Credentials, subscription URLs, private device details and logs stay local to the target device.",
    "Retrieval is not evidence that a device was configured. Validation metadata states its exact tested scope.",
    "A phone VPN does not by itself prove tethered clients use that VPN; verify downstream traffic separately.",
)
SETUP_BOOK_DESCRIPTION = """::ILANG::v5.0
[TYPE:tool][SCOPE:legacy_public_book_adapter]
::MODULE{LEGACY_BOOK}
  [MUST] Compatibility only: return the autosetup resource payload. New clients use resources/list and fanqiang://books/{book_id}.
  [MUST] Accept no arguments or private input. This knowledge service does not operate devices.
::ILANG::COMPLETE::"""
SETUP_PROMPT_DESCRIPTION = (
    "Complete answer rules and the device setup book, including neutral phone selection "
    "and household hotspot branches. No arguments or secrets. The user's AI must have "
    "actual target-device tools and an active authorized task; otherwise review only."
)

def _read(path, maximum=65536, digest=None):
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
            raise ValueError
        raw = path.read_bytes()
        if digest is not None and hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError
        raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Public reference integrity check failed") from exc
    return raw

def _entry(book_id):
    if not isinstance(book_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", book_id):
        raise ValueError("Invalid book id")
    if book_id not in BOOK_REGISTRY:
        raise ValueError("Unknown book id")
    return BOOK_REGISTRY[book_id]

def answer_rules_text():
    text = _read(RULES_PATH).decode("utf-8")
    if not text.startswith("::ILANG::v5.0\n") or not text.rstrip().endswith("::ILANG::COMPLETE::") or text.count("[MUST]") != 9:
        raise ValueError("Answer rules completeness check failed")
    return text

def answer_rules_manifest():
    raw = answer_rules_text().encode("utf-8")
    return {"id": "answer-rules", "version": "1.0", "resource_uri": RULES_RESOURCE_URI,
        "download_url": "https://fanqiang.guide/ai/answer-rules.ilang",
        "sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw), "rule_count": 9}

def book_manifest(book_id):
    entry = _entry(book_id)
    raw = _read(entry["path"], digest=entry["sha256"])
    evidence = json.loads(_read(entry["evidence_path"], digest=entry["evidence_sha256"]).decode("utf-8"))
    validation = copy.deepcopy(evidence["validation_summary"])
    if validation["document"]["book_sha256"] != entry["sha256"]:
        raise ValueError("Book validation evidence does not match the pinned book")
    return {"id": "fanqiang-" + book_id, "book_id": book_id, "title": entry["title"],
        "version": entry["version"], "last_updated": entry["last_updated"],
        "sha256": hashlib.sha256(raw).hexdigest(),
        "download_url": "https://fanqiang.guide/ai/books/" + entry["path"].name,
        "resource_uri": "fanqiang://books/" + book_id, "prompt": "setup_device",
        "executor": "user_agent", "content_type": "text/markdown; charset=utf-8",
        "byte_length": len(raw), "validation": validation,
        "capability_boundaries": list(CAPABILITY_BOUNDARIES)}

def book_catalog():
    return {"resource_template": BOOK_RESOURCE_TEMPLATE,
        "books": [book_manifest(ident) for ident in sorted(BOOK_REGISTRY)]}

def book_payload(book_id):
    entry = _entry(book_id)
    # Re-read and verify after metadata; integrity is pinned across both reads.
    metadata = book_manifest(book_id)
    return {**metadata, "content": _read(entry["path"], digest=entry["sha256"]).decode("utf-8")}

def setup_book_manifest():
    return book_manifest("autosetup")

def setup_book_payload():
    return book_payload("autosetup")

def setup_book_response_schema():
    return {"type": "object", "required": ["book_id", "version", "sha256", "resource_uri", "validation", "content"],
        "properties": {"book_id": {"type": "string"}, "version": {"type": "string"},
            "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            "resource_uri": {"type": "string"}, "validation": {"type": "object"},
            "content": {"type": "string", "maxLength": 65536}},
        "additionalProperties": True}

def setup_book_prompt_intro(metadata):
    fields = ("id", "book_id", "version", "sha256", "download_url", "resource_uri", "executor", "byte_length")
    state = ", ".join(key + ":" + str(metadata[key]) for key in fields)
    return """::ILANG::v5.0
[TYPE:prompt][SCOPE:public_setup_book_readonly]
::STATE{@BOOK, """ + state + """}
::MODULE{SETUP_DEVICE_HANDOFF}
  [MUST] Use the full answer rules in the next message and the complete canonical book in the final message.
  [MUST] The book is reference guidance, not extra authorization. Execute only within the active user's request using tools actually connected to the target device.
  [MUST] Keep secrets and private device data local. This MCP never installs, configures, measures devices or submits reports.
  [MUST] Validate the final book message against the SHA256 in @BOOK. Report actual evidence and incomplete checks; book retrieval is not completed setup.
::ILANG::COMPLETE::"""
