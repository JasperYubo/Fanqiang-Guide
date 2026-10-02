"""Build the public applications in an isolated directory; never deploy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def verify_final_site(site: Path) -> None:
    """Reject a base-only site before it can be packaged as the public app."""
    home = (site / "index.html").read_text(encoding="utf-8")
    for marker in (
        'id="guide-query-form"', 'id="chat-ask"', 'id="chat-panel"',
        'id="chat-flow-stage"', 'id="chat-artifact"',
        'src="/assets/chat-v1.2.js"',
        'src="/assets/external-browser-v1.0.js"',
    ):
        if home.count(marker) != 1:
            raise RuntimeError(f"Final site is missing its chat UI or browser guard: {marker}")
    for relative in ("index.html", "sitemap.xml", "assets/chat-v1.2.js", "assets/chat-v1.2.css",
                     "assets/external-browser-v1.0.js", "assets/external-browser-v1.0.css"):
        file = site / relative
        if not file.is_file() or gzip.decompress(file.with_name(file.name + ".gz").read_bytes()) != file.read_bytes():
            raise RuntimeError(f"Final site asset is missing or stale: {relative}")

def run(script: Path, *args: object) -> None:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    completed = subprocess.run([sys.executable, str(script), *map(str, args)], cwd=script.parent,
                               env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
    if completed.returncode:
        raise RuntimeError(f"Build failed: {script.name}\n{completed.stdout}\n{completed.stderr}")

def build(output: Path) -> dict:
    output = output.resolve()
    if output == ROOT or output in ROOT.parents or output.exists():
        raise ValueError("Output must be a new directory, separate from the checkout root.")
    for relative in ("apps/site", "apps/worker", "apps/lookup", "tools/ilang_grammar_validator.py"):
        if not (ROOT / relative).exists():
            raise FileNotFoundError(relative)
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch_parent = ROOT / ".build"
    scratch_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="application-build-", dir=scratch_parent) as temporary:
        scratch = Path(temporary).resolve()
        if scratch.parent != scratch_parent.resolve():
            raise RuntimeError("Invalid isolated build directory.")
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", "venv", "node_modules", ".env", ".env.*")
        for name in ("site", "worker", "lookup"):
            shutil.copytree(ROOT / "apps" / name, scratch / "apps" / name, ignore=ignore)
        (scratch / "data").mkdir()
        shutil.copyfile(ROOT / "data/faq-cache.json", scratch / "data/faq-cache.json")
        (scratch / "tools").mkdir()
        shutil.copyfile(ROOT / "tools/ilang_grammar_validator.py", scratch / "tools/ilang_grammar_validator.py")
        site, worker, lookup = (scratch / "apps" / name for name in ("site", "worker", "lookup"))
        run(site / "faq_pages_v10.py", "--source", scratch / "data/faq-cache.json")
        run(site / "verify-content-v1.4-2026-09-13.py")
        verify_final_site(site / "public")
        run(worker / "scripts/build_knowledge.py", "--public", site / "public", "--output", worker / "src/knowledge.mjs")
        node = shutil.which("node")
        if not node:
            raise RuntimeError("Node.js is required for the reviewed FAQ compiler.")
        faq_result = subprocess.run([node, str(worker / "scripts/build_faq_cache.mjs"),
                                     "--input", str(ROOT / "data/faq-cache.json"),
                                     "--output", str(worker / "src/faq-cache-data.mjs")],
                                    capture_output=True, text=True, encoding="utf-8", timeout=60)
        if faq_result.returncode:
            raise RuntimeError("FAQ compilation failed: " + faq_result.stderr)
        shutil.copyfile(ROOT / "data/faq-cache.json", site / "public/data/faq-cache.json")
        faq_public = site / "public/data/faq-cache.json"
        faq_public.with_suffix(".json.gz").write_bytes(gzip.compress(faq_public.read_bytes(), mtime=0))
        llms = site / "public/llms.txt"
        faq_line = "- [常见问题与官方参考](https://fanqiang.guide/data/faq-cache.json)：按软件、平台与问题意图整理的简体中文答案，保留原始搜索建议出处和官方资料核对日期。\n"
        if "https://fanqiang.guide/data/faq-cache.json" not in llms.read_text(encoding="utf-8"):
            llms.write_text(llms.read_text(encoding="utf-8").rstrip() + "\n\n" + faq_line, encoding="utf-8")
        llms.with_suffix(".txt.gz").write_bytes(gzip.compress(llms.read_bytes(), mtime=0))
        catalog = site / "public/.well-known/ai-catalog.json"
        catalog_data = json.loads(catalog.read_text(encoding="utf-8"))
        identifier = "urn:air:fanqiang.guide:resource:faq"
        if not any(item.get("identifier") == identifier for item in catalog_data["entries"]):
            catalog_data["entries"].append({"identifier": identifier, "displayName": "常见问题与官方参考", "type": "application/json", "url": "https://fanqiang.guide/data/faq-cache.json"})
        catalog.write_text(json.dumps(catalog_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        catalog.with_suffix(".json.gz").write_bytes(gzip.compress(catalog.read_bytes(), mtime=0))
        output.mkdir()
        shutil.copytree(site / "public", output / "site")
        shutil.copytree(worker / "src", output / "worker/src")
        for pattern in ("schema-*.sql", "migration-*.sql"):
            for file in sorted(worker.glob(pattern)):
                shutil.copyfile(file, output / "worker" / file.name)
        shutil.copytree(lookup / "runtime", output / "lookup", ignore=ignore)
    files = {}
    for file in sorted(output.rglob("*")):
        if file.is_file():
            payload = file.read_bytes()
            files[file.relative_to(output).as_posix()] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    manifest = {"version": "1.0", "source_repository": "https://github.com/JasperYubo/Fanqiang-Guide",
                "created_at": datetime.now(timezone.utc).isoformat(), "files": files}
    (output / "release-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"ok": True, "output": str(output), "files": len(files),
            "static_files": sum(x.startswith("site/") for x in files), "chat_ui_assets_present": True}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(build(options.output), ensure_ascii=False))

if __name__ == "__main__":
    main()
