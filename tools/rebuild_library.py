#!/usr/bin/env python3
"""Rebuild the maintained knowledge snapshot locally, without network access."""

import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile


ROOT = Path(__file__).resolve().parents[1]
STAMP = "v0.1-2026-09-11"
ENTITY_INPUTS = (
    "baseline.json", "concepts.json", "github-extra.json", "routers.json",
    "source-lists.json", "baseline-reviewed.json", "relationship-extra.json",
)
MODEL_INPUT = "merlin-model-matrix.json"
KNOWLEDGE_INPUTS = (
    "merlin-guide-v0.1-2026-09-11.md",
    "merlin-model-matrix-v0.1-2026-09-11.md",
    "taxonomy-v0.1-2026-09-11.md",
)
CORE_FILES = tuple(name + "-" + STAMP + suffix for name, suffix in (
    ("library", ".json"), ("library", ".jsonl"), ("library", ".sqlite"),
    ("relationships", ".jsonl"), ("sources", ".jsonl"),
    ("rag-all", ".jsonl"), ("rag-reviewed", ".jsonl"),
    ("review-queue", ".jsonl"), ("merlin-model-matrix", ".json"),
    ("merlin-model-matrix", ".jsonl"), ("rag-compatibility", ".jsonl"),
    ("INDEX", ".md"),
))
DB_TABLES = ("entities", "relations", "sources", "search", "hardware_compatibility")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core = load_module("fanqiang_rebuild_core", ROOT / "tools/_build_core.py")
catalog = load_module("fanqiang_rebuild_catalog", ROOT / "scripts/build_catalog.py")


def read_json_bytes(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("invalid_json_constant")

    return json.loads(content.decode("utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=invalid_constant)


def read_source_snapshot(source_dir):
    """Only fixed source filenames are opened; JSON fields never become paths."""
    source_dir = Path(source_dir).resolve(strict=True)
    snapshot = {}
    names = list(ENTITY_INPUTS) + [MODEL_INPUT]
    names += ["knowledge/" + name for name in KNOWLEDGE_INPUTS]
    for name in names:
        path = source_dir / name
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError:
            raise ValueError("missing_required_input: " + name) from None
        if not resolved.is_relative_to(source_dir) or not resolved.is_file():
            raise ValueError("input_outside_source_or_not_file: " + name)
        content = resolved.read_bytes()
        if not content:
            raise ValueError("empty_required_input: " + name)
        if name.endswith(".json"):
            rows = read_json_bytes(content)
            if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
                raise ValueError("input_must_be_nonempty_record_list: " + name)
        else:
            content.decode("utf-8-sig")
        snapshot[name] = content
    return snapshot


def jsonl(path):
    return [read_json_bytes(line) for line in path.read_bytes().splitlines() if line.strip()]


def database_snapshot(path):
    """Compare logical tables and FTS results, excluding SQLite storage layout."""
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("sqlite_integrity_failed")
        # Extra application tables mean this is not the same generated snapshot.
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        allowed = set(DB_TABLES) | {"search_data", "search_idx", "search_content", "search_docsize", "search_config"}
        if tables != allowed:
            raise ValueError("unexpected_sqlite_tables")
        result = {}
        for table in DB_TABLES:
            schema = connection.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()
            if schema is None:
                raise ValueError("missing_sqlite_table")
            rows = connection.execute('SELECT * FROM "' + table + '"').fetchall()
            result[table] = (schema[0], sorted(rows, key=lambda row: json.dumps(row, ensure_ascii=True)))
        result["fts_queries"] = {
            query: connection.execute("SELECT id FROM search WHERE search MATCH ? ORDER BY id", (query,)).fetchall()
            for query in ("merlin", "clash", "rebuild")
        }
        return result


def same_database(first, second):
    if not Path(first).is_file():
        return False
    try:
        return database_snapshot(first) == database_snapshot(second)
    except (sqlite3.Error, ValueError, OSError):
        return False


def validate_exports(export_dir):
    rows = read_json_bytes((export_dir / ("library-" + STAMP + ".json")).read_bytes())
    catalog.validate_library(rows)
    entities = {row["id"]: row for row in rows}
    ids = set(entities)
    if jsonl(export_dir / ("library-" + STAMP + ".jsonl")) != rows:
        raise ValueError("library_json_jsonl_mismatch")
    all_chunks = jsonl(export_dir / ("rag-all-" + STAMP + ".jsonl"))
    reviewed = jsonl(export_dir / ("rag-reviewed-" + STAMP + ".jsonl"))
    pending = jsonl(export_dir / ("review-queue-" + STAMP + ".jsonl"))
    checked_ids = {row["id"] for row in rows if row["verification"]["status"] == "primary_reviewed"}
    for chunks, expected in ((all_chunks, ids), (reviewed, checked_ids), (pending, ids - checked_ids)):
        actual = [chunk["entity_id"] for chunk in chunks]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError("rag_or_review_queue_coverage_mismatch")
    models = jsonl(export_dir / ("merlin-model-matrix-" + STAMP + ".jsonl"))
    if read_json_bytes((export_dir / ("merlin-model-matrix-" + STAMP + ".json")).read_bytes()) != models:
        raise ValueError("model_json_jsonl_mismatch")
    model_ids = {row["id"] for row in models}
    if len(model_ids) != len(models) or any(row["firmware_entity_id"] not in ids for row in models):
        raise ValueError("invalid_model_references")
    if {row["id"] for row in jsonl(export_dir / ("rag-compatibility-" + STAMP + ".jsonl"))} != {"compat:" + name for name in model_ids}:
        raise ValueError("compatibility_rag_mismatch")
    sources = jsonl(export_dir / ("sources-" + STAMP + ".jsonl"))
    source_ids = {row["id"] for row in sources}
    allowed_references = ids | {"compat:" + name for name in model_ids}
    if len(source_ids) != len(sources) or any(set(row["referenced_by"]) - allowed_references for row in sources):
        raise ValueError("invalid_source_references")
    if any(set(row["source_ids"]) - source_ids for row in rows):
        raise ValueError("missing_entity_sources")
    for row in jsonl(export_dir / ("relationships-" + STAMP + ".jsonl")):
        if row["source_id"] not in ids or (row["target_id"] is not None and row["target_id"] not in ids):
            raise ValueError("invalid_relationship_references")
    expected_cards = {entity_id + "-" + STAMP + ".md" for entity_id in ids}
    if {path.name for path in (export_dir / "cards").glob("*.md")} != expected_cards:
        raise ValueError("card_coverage_mismatch")
    snapshot = database_snapshot(export_dir / ("library-" + STAMP + ".sqlite"))
    if {row[0] for row in snapshot["entities"][1]} != ids:
        raise ValueError("sqlite_entity_coverage_mismatch")
    return rows


def atomic_bytes(path, content):
    if path.is_file() and path.read_bytes() == content:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".rebuild-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def rebuild(source_dir, output_dir, state_path):
    # Read all required inputs before generating or replacing any published file.
    inputs = read_source_snapshot(source_dir)
    state_bytes = Path(state_path).read_bytes()
    state = read_json_bytes(state_bytes)
    catalog.validate_state(state)
    output_dir = Path(output_dir).resolve()
    with tempfile.TemporaryDirectory(prefix="fanqiang-core-rebuild-") as temporary:
        stage = Path(temporary)
        staged_sources = stage / "source"
        for name, content in inputs.items():
            path = staged_sources / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        generated = stage / "result"
        report = core.build(staged_sources, generated / "export")
        library = validate_exports(generated / "export")
        manifest = catalog.make_manifest(library)
        catalog_text, updates_text = catalog.render(library, manifest, state)
        (generated / "config").mkdir()
        (generated / "config/upstream-repositories.json").write_bytes(
            (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
        (generated / "CATALOG.md").write_bytes(catalog_text.encode("utf-8"))
        (generated / "UPDATES.md").write_bytes(updates_text.encode("utf-8"))
        (generated / "knowledge").mkdir()
        for name in KNOWLEDGE_INPUTS:
            (generated / "knowledge" / name).write_bytes(inputs["knowledge/" + name])
        paths = [Path("export") / name for name in CORE_FILES]
        paths += sorted(Path("export/cards") / path.name for path in (generated / "export/cards").glob("*.md"))
        paths += [Path("config/upstream-repositories.json"), Path("CATALOG.md"), Path("UPDATES.md")]
        paths += [Path("knowledge") / name for name in KNOWLEDGE_INPUTS]
        expected_cards = {path.name for path in paths if path.parent == Path("export/cards")}
        cards_dir = output_dir / "export/cards"
        stale = [path for path in cards_dir.glob("*-" + STAMP + ".md") if path.name not in expected_cards]
        for path in [output_dir / item for item in paths] + stale:
            if not path.resolve().is_relative_to(output_dir):
                raise ValueError("output_path_escapes_destination")
        changed, unchanged = [], []
        for relative in paths:
            source, target = generated / relative, output_dir / relative
            if relative.suffix == ".sqlite" and same_database(target, source):
                unchanged.append(relative.as_posix())
            elif atomic_bytes(target, source.read_bytes()):
                changed.append(relative.as_posix())
            else:
                unchanged.append(relative.as_posix())
        for path in stale:
            path.unlink()
        return {"entity_count": report["unique_entities"], "repository_count": len(manifest["repositories"]),
                "excluded_count": len(manifest["excluded"]), "changed": changed, "unchanged_count": len(unchanged),
                "removed_cards": sorted(path.name for path in stale)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=ROOT / "tools/source")
    parser.add_argument("--output-dir", type=Path, default=ROOT)
    parser.add_argument("--state", type=Path, default=ROOT / "data/upstream.json")
    args = parser.parse_args(argv)
    try:
        result = rebuild(args.source_dir, args.output_dir, args.state)
    except (OSError, ValueError, KeyError, TypeError, AssertionError, sqlite3.Error) as error:
        print("Rebuild failed: " + str(error))
        return 1
    summary = {key: value for key, value in result.items() if key not in {"changed", "removed_cards"}}
    summary["changed_count"] = len(result["changed"])
    summary["removed_card_count"] = len(result["removed_cards"])
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
