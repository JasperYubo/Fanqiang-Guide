"""Copy a static release; add the external-browser notice to every HTML page."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BASE = HERE.parent / "public-v1.1"
ASSETS = ("external-browser-v1.0.css", "external-browser-v1.0.js", "chat-v1.1.1.js")
INJECTION = '<link rel="stylesheet" href="/assets/external-browser-v1.0.css"><script data-cfasync="false" src="/assets/external-browser-v1.0.js"></script>'


def is_google_site_verification(file: Path, base: Path, content: str) -> bool:
    """Recognize Google's root-level plain-text verification response."""
    return (
        file.parent == base
        and re.fullmatch(r"google[A-Za-z0-9_-]+\.html", file.name) is not None
        and content == f"google-site-verification: {file.name}"
    )


def patch(base: Path, output: Path) -> dict:
    base = base.resolve(strict=True)
    output = output.resolve()
    if base == output or base in output.parents or output in base.parents:
        raise ValueError("Output must be separate from the source directory.")
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    html_files = sorted(base.rglob("*.html"))
    if not html_files:
        raise ValueError("No HTML pages found.")
    transformed = {}
    preserved_verification = []
    for file in html_files:
        before = file.read_bytes().decode("utf-8")
        if is_google_site_verification(file, base, before):
            preserved_verification.append(file.relative_to(base).as_posix())
            continue
        if "external-browser-v1.0.js" in before:
            raise ValueError(f"Already patched: {file}")
        heads = list(re.finditer(r"<head(?:\s[^>]*)?>", before, re.I))
        if len(heads) != 1:
            raise ValueError(f"Expected one head: {file}")
        position = heads[0].end()
        after = before[:position] + INJECTION + before[position:]
        after = after.replace('src="/assets/chat-v1.1.js"', 'src="/assets/chat-v1.1.1.js"')
        after = after.replace("src='/assets/chat-v1.1.js'", "src='/assets/chat-v1.1.1.js'")
        restored = after.replace(INJECTION, "", 1).replace('src="/assets/chat-v1.1.1.js"', 'src="/assets/chat-v1.1.js"').replace("src='/assets/chat-v1.1.1.js'", "src='/assets/chat-v1.1.js'")
        assert restored == before, f"Unexpected content changes: {file}"
        transformed[file.relative_to(base).as_posix()] = after.encode("utf-8")
    shutil.copytree(base, output)
    for relative, content in transformed.items():
        (output / relative).write_bytes(content)
    for name in ASSETS:
        shutil.copyfile(HERE / "assets" / name, output / "assets" / name)
    changed = list(transformed) + ["assets/" + name for name in ASSETS]
    for relative in changed:
        file = output / relative
        content = file.read_bytes()
        compressed = gzip.compress(content, mtime=0)
        assert gzip.decompress(compressed) == content
        file.with_name(file.name + ".gz").write_bytes(compressed)
    return {"version": "external-browser-v1.0", "source": str(base), "output": str(output),
            "html_pages": len(transformed), "changed": changed,
            "preserved_verification": preserved_verification,
            "preserved": "Original HTML bytes remain identical after reversing only guard head injection and chat asset reference.",
            "sha256": {relative: hashlib.sha256((output / relative).read_bytes()).hexdigest() for relative in changed}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(patch(options.base, options.output), ensure_ascii=False, indent=2))
