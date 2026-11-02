"""Keep sitemap dates tied to reviewed content changes, never build time."""
from datetime import date
import gzip
from pathlib import Path
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
ET.register_namespace("", NS)

def canonical_path(relative):
    path = "/" + str(relative).lstrip("/")
    if path == "/index.html":
        return "/"
    if path.endswith("/index.html") and path.startswith(("/answers/", "/ai/", "/cases/")):
        return path[:-len("index.html")]
    return path

def normalize_sitemaps(public, changed_paths=(), modification_date="2026-11-02"):
    """Use a declared content revision date for changed pages; omit unknown dates.

    Existing answer/case timestamps come from their reviewed source data. The
    base builder's fixed release date is not evidence of a page's modification.
    """
    date.fromisoformat(modification_date)
    public = Path(public)
    changed = {canonical_path(path) for path in changed_paths}
    for name in ("sitemap.xml", "sitemap-answers.xml"):
        target = public / name
        if not target.is_file():
            continue
        tree = ET.fromstring(target.read_bytes())
        for node in tree:
            location = node.find(f"{{{NS}}}loc")
            if location is None or not location.text:
                continue
            path = urlsplit(location.text).path
            stamp = node.find(f"{{{NS}}}lastmod")
            if path in changed:
                if stamp is None:
                    stamp = ET.SubElement(node, f"{{{NS}}}lastmod")
                existing = (stamp.text or "")[:10]
                try:
                    date.fromisoformat(existing)
                except ValueError:
                    existing = ""
                stamp.text = max(existing, modification_date)
            elif not path.startswith(("/answers/", "/cases/")) and stamp is not None:
                node.remove(stamp)
        payload = ET.tostring(tree, encoding="utf-8", xml_declaration=True) + b"\n"
        target.write_bytes(payload)
        compressed = target.with_name(target.name + ".gz")
        if compressed.exists():
            compressed.write_bytes(gzip.compress(payload, mtime=0))
