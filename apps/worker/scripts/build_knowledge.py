"""Build the compact Worker index only from published Fanqiang Guide JSON."""
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata


def norm(value):
    return unicodedata.normalize("NFKC", str(value)).lower()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    documents = {}
    hashes = {}
    for name in ("guides", "merlin-models", "library"):
        raw = (args.public / "data" / f"{name}.json").read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        documents[name] = json.loads(raw)
    guides = []
    for source in documents["guides"]["topics"]:
        row = {k: source[k] for k in ("slug", "title", "summary", "keywords", "items", "sections", "faq")}
        row["url"] = f'https://fanqiang.guide/guides/{row["slug"]}.html'
        row["search"] = norm(" ".join([row["title"], row["summary"], *row["keywords"], *[f["question"] for f in row["faq"]]]))
        guides.append(row)
    fields = ("id", "name", "aliases", "kind", "summary", "platforms", "verification", "compatibility", "maintenance", "official_urls", "source_url", "source_snapshot_url")
    library = []
    for source in documents["library"]["items"]:
        row = {key: source.get(key) for key in fields}
        row["names"] = list(dict.fromkeys(norm(x) for x in [row["name"], row["id"], *row["aliases"]]))
        library.append(row)
    models = []
    for source in documents["merlin-models"]["items"]:
        row = dict(source)
        row["canonical"] = "".join(c for c in norm(row["model_exact"]) if c.isascii() and c.isalnum())
        models.append(row)
    meta = {"version": "1.0", "guide_version": documents["guides"]["version"], "published_at": documents["guides"]["published_at"], "counts": {"guides": len(guides), "faq": sum(len(g["faq"]) for g in guides), "library": len(library), "models": len(models)}, "public_source_urls": {name: f"https://fanqiang.guide/data/{name}.json" for name in documents}, "sha256": hashes, "library_source": documents["library"]["source"], "model_source": documents["merlin-models"]["source"]}
    if meta["counts"] != {"guides": 10, "faq": 37, "library": 310, "models": 58}:
        raise ValueError(f"Unexpected published snapshot counts: {meta['counts']}")
    blocks = ["// Generated from public JSON by scripts/build_knowledge.py. Do not hand-edit."]
    for name, value in (("KNOWLEDGE_META", meta), ("GUIDES", guides), ("MODELS", models), ("LIBRARY", library)):
        blocks.append(f"export const {name} = " + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + ";")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(blocks) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "bytes": args.output.stat().st_size, "counts": meta["counts"], "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()}, ensure_ascii=True))


if __name__ == "__main__":
    main()
