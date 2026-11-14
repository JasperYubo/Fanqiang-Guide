"""Create commit-bound receipts for the Linux origin and its dispatched Pages run.

Receipts contain public release identity only. This helper writes candidate
artifacts; it does not connect to production or dispatch any workflow.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import runpy
import subprocess

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_FIELDS = ("source_sha", "sync_id", "contract_sha256")


def product_contract() -> dict:
    return runpy.run_path(str(ROOT / "apps/site/product_contract.py"))["public_contract"]()


def contract_digest(contract: dict) -> str:
    raw = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def installer_digest() -> str:
    return hashlib.sha256((ROOT / "apps/server/install.sh").read_bytes()).hexdigest()


def identity(source_sha: str, sync_id: str, contract_sha256: str) -> dict:
    if not isinstance(source_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", source_sha):
        raise ValueError("source_sha must be a complete lowercase Git commit SHA")
    if not isinstance(sync_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,95}", sync_id):
        raise ValueError("sync_id must contain 1-96 letters, digits, dots, underscores or hyphens")
    if not isinstance(contract_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", contract_sha256):
        raise ValueError("contract_sha256 must be a lowercase SHA256")
    return {"schema_version": 1, "source_sha": source_sha, "sync_id": sync_id, "contract_sha256": contract_sha256}


def verify_checkout(source_sha: str) -> None:
    actual = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if actual != source_sha:
        raise ValueError("Checkout HEAD differs from the requested source_sha")
    clean = subprocess.run(["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if clean.returncode:
        raise ValueError("Tracked source differs from the requested commit; build from a clean checkout")
    untracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
    if set(untracked) - {"apps/pages/deployment.json"}:
        raise ValueError("Checkout contains untracked files; use an isolated clean source checkout")


def verify_origin_build(public: Path, expected: dict) -> Path:
    """Bind the receipt to the clean build manifest, not an arbitrary old directory."""
    manifest_path = public.parent / "release-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    spec = importlib.util.spec_from_file_location("receipt_build_inputs", ROOT / "developer/build_apps.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    if manifest["source_inputs"] != build.source_inputs():
        raise ValueError("Origin artifact was not built from the current source inputs")
    if json.loads((public / "data/product-contract.json").read_text(encoding="utf-8")) != expected:
        raise ValueError("Origin artifact product contract differs from the requested source")
    for relative, metadata in manifest["files"].items():
        path = public.parent / relative
        if Path(relative).is_absolute() or ".." in Path(relative).parts or path.is_symlink():
            raise ValueError("Invalid release-manifest file path")
        raw = path.read_bytes()
        if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
            raise ValueError("Origin artifact differs from its build manifest: " + relative)
    return manifest_path


def write_receipt(surface: str, public: Path, receipt: dict, *, run_id=None, run_attempt=None) -> dict:
    receipt = identity(receipt["source_sha"], receipt["sync_id"], receipt["contract_sha256"])
    public = public.resolve(strict=True)
    verify_checkout(receipt["source_sha"])
    expected = product_contract()
    if contract_digest(expected) != receipt["contract_sha256"]:
        raise ValueError("Requested contract_sha256 differs from the checked-out product contract")
    receipt = {**receipt, "installer_sha256": installer_digest()}
    if surface == "origin":
        verify_origin_build(public, expected)
        if hashlib.sha256((public / "server/install.sh").read_bytes()).hexdigest() != receipt["installer_sha256"]:
            raise ValueError("Origin installer differs from the requested source")
        target = public / "data/site-release.json"
    elif surface == "pages":
        if not re.fullmatch(r"[1-9][0-9]*", str(run_id)) or not re.fullmatch(r"[1-9][0-9]*", str(run_attempt)):
            raise ValueError("Pages receipt requires the exact workflow run_id and run_attempt")
        spec = importlib.util.spec_from_file_location("receipt_pages_source", ROOT / "developer/sync_pages_contract.py")
        sync = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sync)
        raw_index = (public / "index.html").read_bytes()
        if raw_index != sync.render(sync.TEMPLATE.read_text(encoding="utf-8")).encode("utf-8"):
            raise ValueError("Pages index differs from the requested source template and facts")
        receipt = {**receipt, "run_id": str(run_id), "run_attempt": int(run_attempt),
                   "index_sha256": hashlib.sha256(raw_index).hexdigest()}
        target = public / "deployment.json"
    else:
        raise ValueError("Unknown receipt surface")
    raw = (json.dumps(receipt, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    if surface == "origin":
        target.with_suffix(target.suffix + ".gz").write_bytes(gzip.compress(raw, mtime=0))
    # The Linux publisher seals these new files into its release manifest.
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("surface", choices=("origin", "pages"))
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--sync-id", required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--public-dir", type=Path, required=True)
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID"))
    parser.add_argument("--run-attempt", default=os.environ.get("GITHUB_RUN_ATTEMPT"))
    args = parser.parse_args()
    receipt = identity(args.source_sha, args.sync_id, args.contract_sha256)
    print(json.dumps(write_receipt(args.surface, args.public_dir, receipt,
                                  run_id=args.run_id, run_attempt=args.run_attempt), ensure_ascii=False))


if __name__ == "__main__":
    main()
