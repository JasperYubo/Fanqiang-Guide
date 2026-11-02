"""Pinned, public setup book shared by MCP, HTTP and static metadata builders.

This module uses only the standard library so build tooling can load it by path.
The digest covers the original UTF-8 file bytes, not a JSON response envelope.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

BOOK_PATH = Path(__file__).resolve().parent / "books" / "fanqiang-autosetup-v1.1.ilang.md"
BOOK_SHA256 = "96425a3f6bf75c7c9ecbfdc657be74b053df2f323ba6cf5a5a621064bbabf98a"
BOOK_RESOURCE_URI = "fanqiang://books/autosetup"
BOOK_DOWNLOAD_URL = "https://fanqiang.guide/ai/books/fanqiang-autosetup-v1.1.ilang.md"
BOOK_TITLE = "Fanqiang device setup engineering book"
NO_ARGUMENTS_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
CAPABILITY_BOUNDARIES = (
    "This knowledge MCP is read-only: it cannot inspect, install, configure or repair the user's device.",
    "For an active user request to configure a device, the user's AI uses this book with its own tools bound to that target device.",
    "The book grants no additional authorization. Reuse the active task's authorized scope and respect required system permissions; otherwise review only.",
    "Do not send subscriptions, credentials, private device details or logs to this service. Secret entry stays local on the target device.",
    "Retrieving this book does not run diagnostics, require a diagnostics package, submit reports or prove device setup. Device execution checks have not run.",
)
SETUP_BOOK_DESCRIPTION = """::ILANG::v5.0
[TYPE:tool][SCOPE:public_setup_book_readonly]
::MODULE{GET_SETUP_BOOK}
  [MUST] Return the complete pinned device setup engineering book, version, SHA256, download URL and capability boundaries. This tool accepts no arguments.
  [MUST] For an active user request to configure a device, obtain this book before the user's AI uses its own target-device tools to identify, select, install, configure, repair and verify.
  [MUST] This knowledge service cannot operate devices. The book grants no new authorization; preserve active user scope and required system permissions.
  [MUST] Never send credentials, subscription URLs, private device details or logs as arguments. Retrieval performs no device execution or report submission.
::ILANG::COMPLETE::"""
SETUP_PROMPT_DESCRIPTION = (
    "Read the complete device setup book for the user's AI. Use only within an active "
    "user-requested setup task and the AI's actual target-device capabilities; otherwise "
    "review only. No arguments or secrets are accepted."
)


def _book_bytes():
    try:
        if BOOK_PATH.is_symlink() or BOOK_PATH.stat().st_size > 65536:
            raise ValueError
        raw = BOOK_PATH.read_bytes()
        if hashlib.sha256(raw).hexdigest() != BOOK_SHA256:
            raise ValueError
        raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Setup book integrity check failed") from exc
    return raw


def _manifest(raw):
    return {
        "id": "fanqiang-autosetup",
        "version": "1.1",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "download_url": BOOK_DOWNLOAD_URL,
        "resource_uri": BOOK_RESOURCE_URI,
        "tool": "get_setup_book",
        "prompt": "setup_device",
        "executor": "user_agent",
        "execution_status": "not_run",
        "content_type": "text/markdown; charset=utf-8",
        "byte_length": len(raw),
        "capability_boundaries": list(CAPABILITY_BOUNDARIES),
    }


def setup_book_manifest():
    """Return public metadata without the book body, using this module's own path."""
    return _manifest(_book_bytes())


def setup_book_payload():
    """Return the exact canonical text together with the shared public metadata."""
    raw = _book_bytes()
    return {**_manifest(raw), "content": raw.decode("utf-8")}


def setup_book_response_schema():
    """Describe the same public payload for the read-only HTTP fallback."""
    manifest = setup_book_manifest()
    properties = {
        key: ({"type": "array", "items": {"type": "string"}} if isinstance(value, list)
              else {"type": "integer", "const": value} if isinstance(value, int)
              else {"type": "string", "const": value})
        for key, value in manifest.items()
    }
    properties["content"] = {"type": "string", "maxLength": 65536,
        "description": "Exact UTF-8 book text. sha256 covers content.encode('utf-8')."}
    return {"type": "object", "additionalProperties": False,
        "required": list(properties), "properties": properties}

def setup_book_prompt_intro(metadata):
    """iLang handoff; the following prompt message remains the exact book text."""
    fields = ("id", "version", "sha256", "download_url", "resource_uri",
              "tool", "prompt", "executor", "execution_status", "byte_length")
    state = ", ".join(key + ":" + str(metadata[key]) for key in fields)
    return """::ILANG::v5.0
[TYPE:prompt][SCOPE:public_setup_book_readonly]
::STATE{@BOOK, """ + state + """}
::MODULE{SETUP_DEVICE_HANDOFF}
  [MUST] Treat this book as a public reference plan, not additional authorization. Only an active user request to configure a device enables execution within that request; otherwise review only.
  [MUST] The user's AI uses its own verified target-device tools, reuses existing authorized scope and respects required system permissions. This knowledge MCP cannot operate the device.
  [MUST] Keep secrets, subscription URLs, private device details and logs out of this service. Book retrieval performs no device checks, installs no diagnostics package and submits no reports.
  [MUST] The next message is the complete canonical book. Its exact UTF-8 text is covered by the SHA256 in @BOOK; retrieval is not proof of completed device setup.
::ILANG::COMPLETE::"""
