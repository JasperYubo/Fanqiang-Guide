"""Build the public applications in an isolated directory; never deploy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

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
        (scratch / "tools").mkdir()
        shutil.copyfile(ROOT / "tools/ilang_grammar_validator.py", scratch / "tools/ilang_grammar_validator.py")
        site, worker, lookup = (scratch / "apps" / name for name in ("site", "worker", "lookup"))
        run(site / "build-site-v1.4-2026-09-13.py")
        run(site / "verify-content-v1.4-2026-09-13.py")
        run(worker / "frontend/patch_frontend.py", "--base", site / "public", "--output", scratch / "site-intake")
        run(worker / "frontend/patch_external_browser.py", "--base", scratch / "site-intake", "--output", scratch / "site-final")
        run(worker / "scripts/build_knowledge.py", "--public", scratch / "site-final", "--output", worker / "src/knowledge.mjs")
        output.mkdir()
        shutil.copytree(scratch / "site-final", output / "site")
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
    return {"ok": True, "output": str(output), "files": len(files), "static_files": sum(x.startswith("site/") for x in files)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(build(options.output), ensure_ascii=False))

if __name__ == "__main__":
    main()
