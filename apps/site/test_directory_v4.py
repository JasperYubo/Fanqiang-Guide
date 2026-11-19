"""Contracts for the optional directory presentation layer."""

from html.parser import HTMLParser
import json
import unittest

from catalog_v13 import render_library, render_models
from directory_v4 import DIRECTORY_ASSETS, _CatalogMarkup, enhance_directory


def _page(body):
    return '<!doctype html><html><head><title>资料</title></head><body><main>' + body + '</main></body></html>'


def _library():
    row = {
        "id": "alpha", "name": 'A & B "名称"', "kind": "client", "summary": "保留　原始文本与 <边界>。",
        "platforms": ["Windows", "Linux"], "verification": {"status": "primary_reviewed", "checked_at": "2026-11-01"},
        "maintenance": {"status": "archived", "evidence_url": "https://example.org/archive"},
        "compatibility": {"notes": "兼容性须单独确认。"},
        "relations": [{"predicate": "related", "target_name": "别的项目", "evidence_url": "https://example.org/related"}],
        "source_url": "https://example.org/original", "repository": "https://example.org/repo",
    }
    absent = {"id": "beta", "name": "B", "kind": "client", "verification": {"status": "reference_only"}}
    return _page(render_library({"items": [row, absent]}, {"items": [{"kind": "client", "name": "客户端"}]})[2])


def _models():
    return _page(render_models({"items": [{
        "id": "test", "model_exact": "RT-TEST V2", "firmware_entity_id": "asuswrt-merlin", "support_claim": "source_only",
        "tested": False, "vendor": "ASUS", "source_url": "https://example.org/model", "checked_at": "2026-10-01",
    }]})[2])


class _OriginalTokens(HTMLParser):
    """Compare every original token after excluding only new UI/assets/attrs."""

    def __init__(self, raw):
        super().__init__(convert_charrefs=False)
        self.tokens = []
        self.skip = 0
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if self.skip:
            if tag not in {"input", "link", "meta", "br", "hr"}:
                self.skip += 1
            return
        if "data-fg-directory-extra" in attrs or attrs.get("src", "").lstrip("/") in DIRECTORY_ASSETS:
            self.skip = 1
            return
        if attrs.get("href", "").lstrip("/") in DIRECTORY_ASSETS:
            return
        attrs = {key: value for key, value in attrs.items() if not key.startswith("data-fg-")}
        if "class" in attrs:
            attrs["class"] = " ".join(value for value in attrs["class"].split() if not value.startswith("fg-directory"))
            if not attrs["class"]:
                del attrs["class"]
        self.tokens.append(("start", tag, attrs))

    def handle_endtag(self, tag):
        if self.skip:
            self.skip -= 1
        else:
            self.tokens.append(("end", tag))

    def handle_data(self, data):
        if not self.skip:
            self.tokens.append(("text", data))

    def handle_entityref(self, name):
        if not self.skip:
            self.tokens.append(("entity", name))

    def handle_charref(self, name):
        if not self.skip:
            self.tokens.append(("charref", name))


class DirectoryPresentationTests(unittest.TestCase):
    def test_all_original_tokens_and_attributes_survive_library(self):
        raw = _library()
        self.assertEqual(_OriginalTokens(raw).tokens, _OriginalTokens(enhance_directory(raw, "guides/library.html")).tokens)

    def test_all_original_tokens_and_attributes_survive_models(self):
        raw = _models()
        self.assertEqual(_OriginalTokens(raw).tokens, _OriginalTokens(enhance_directory(raw, "guides/merlin-models.html")).tokens)

    def test_filters_use_rendered_platforms_and_maintenance_without_inference(self):
        result = enhance_directory(_library(), "guides/library.html")
        parser = _CatalogMarkup(result)
        parser.feed(result)
        nodes = list(parser.root.all())
        records = [node for node in nodes if "data-record" in node.attrs]
        self.assertEqual(json.loads(records[0].attrs["data-fg-platforms"]), ["Windows", "Linux"])
        self.assertEqual(records[0].attrs["data-fg-maintenance"], "来源记录为已归档")
        self.assertEqual(json.loads(records[1].attrs["data-fg-platforms"]), [])
        self.assertEqual(records[1].attrs["data-fg-maintenance"], "")
        self.assertEqual(records[1].attrs["data-fg-checked"], "")
        self.assertNotIn('value="未记录"', result)
        self.assertNotIn('value="active"', result)

    def test_model_page_does_not_invent_platform_or_archive_fields(self):
        result = enhance_directory(_models(), "guides/merlin-models.html")
        self.assertNotIn("data-fg-directory-filter", result)
        self.assertIn("data-fg-directory-sort", result)
        self.assertIn('data-fg-name="RT-TEST V2"', result)

    def test_enhancement_controls_are_hidden_without_javascript(self):
        result = enhance_directory(_library(), "guides/library.html")
        self.assertIn('data-fg-directory-extra hidden', result)
        self.assertEqual(result.count('<details'), _library().count('<details'))
        self.assertEqual(result.count('data-filter="'), _library().count('data-filter="'))

    def test_only_two_catalog_paths_are_enhanced_and_only_once(self):
        raw = _library()
        self.assertEqual(enhance_directory(raw, "guides/other.html"), raw)
        once = enhance_directory(raw, "/guides/library.html")
        self.assertEqual(enhance_directory(once, "guides/library.html"), once)
        for asset in DIRECTORY_ASSETS:
            self.assertEqual(once.count('"/' + asset + '"'), 1)


if __name__ == "__main__":
    unittest.main()
