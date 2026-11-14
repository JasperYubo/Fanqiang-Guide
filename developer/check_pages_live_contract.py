"""Block Pages publication until the main site's shared product facts are live.

This check is used only by the Pages deployment job, after offline rendering.
It never publishes, changes server state, or requires credentials.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 128 * 1024
REQUEST_TIMEOUT = 8
MAX_ATTEMPTS = 3
LIVE_CONTRACT_URL = "https://fanqiang.guide/data/product-contract.json"


def expected_contract() -> dict:
    provider = runpy.run_path(str(ROOT / "apps/site/product_contract.py"))
    return provider["public_contract"]()


def differences(expected, actual, path="") -> list[str]:
    if type(expected) is not type(actual):
        return [path or "root"]
    if isinstance(expected, dict):
        result = []
        for key in sorted(expected.keys() | actual.keys()):
            child = path + "." + key if path else key
            if key not in expected or key not in actual:
                result.append(child)
            else:
                result.extend(differences(expected[key], actual[key], child))
        return result
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [path + ".length"]
        result = []
        for index, (left, right) in enumerate(zip(expected, actual)):
            result.extend(differences(left, right, path + "[" + str(index) + "]"))
        return result
    return [] if expected == actual else [path]


def fetch_contract(url: str) -> dict:
    request = Request(url, headers={"Accept": "application/json", "Cache-Control": "no-cache",
                                  "User-Agent": "Fanqiang-Pages-Publish-Gate/1.0"})
    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("main-site contract exceeds 128 KiB")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("main-site contract is not a JSON object")
    return value


def require_live_contract(expected: dict) -> str:
    encoded = json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    fingerprint = hashlib.sha256(encoded).hexdigest()
    if expected["site_url"] != "https://fanqiang.guide/":
        raise ValueError("Unexpected main-site origin in the shared contract")
    endpoint = LIVE_CONTRACT_URL
    last_error = "not checked"
    for attempt in range(MAX_ATTEMPTS):
        # A unique query avoids accepting a stale CDN object after the origin switch.
        url = endpoint + "?v=" + fingerprint + "&check=" + str(time.time_ns())
        try:
            actual = fetch_contract(url)
            changed = differences(expected, actual)
            if not changed:
                return fingerprint
            last_error = "shared facts differ: " + ", ".join(changed[:12])
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            last_error = type(error).__name__ + ": " + str(error)
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(1)
    raise RuntimeError("Pages publication blocked: " + last_error +
                       ". Publish the matching main-site release first, then rerun this Pages job. Existing Pages remains deployed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        fingerprint = require_live_contract(expected_contract())
    except RuntimeError as error:
        raise SystemExit(str(error)) from None
    print("Main site and Pages shared facts match: " + fingerprint)


if __name__ == "__main__":
    main()
