"""Regression checks across the real manifest, collector, and renderer."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_catalog
import update_upstream


class PipelineContractTests(unittest.TestCase):
    def test_real_manifest_is_accepted_by_both_stages(self):
        manifest = json.loads((ROOT / 'config/upstream-repositories.json').read_text(encoding='utf-8'))
        library = json.loads((ROOT / build_catalog.LIBRARY_PATH).read_text(encoding='utf-8'))
        build_catalog.validate_manifest(library, manifest)
        slugs = update_upstream.validate_manifest(manifest)
        self.assertIn('wangyu-/udp2raw', slugs)
        self.assertEqual(len(slugs), len(manifest['repositories']))
        self.assertEqual(sum(len(r['entity_ids']) for r in manifest['repositories']) + len(manifest['excluded']), len(library))

    def test_actual_collector_state_renders_none_and_stale_correctly(self):
        now = '2026-09-12T00:00:00Z'
        slug = 'wangyu-/udp2raw'
        entity = {'id':'udp2raw', 'name':'udp2raw', 'kind':'transport', 'platforms':[],
                  'repository':'https://github.com/' + slug, 'verification':{'status':'reference_only'}}
        class Client:
            def fetch(self, name, release=False):
                if release:
                    raise update_upstream.FetchError('not_found')
                return {'full_name':name, 'html_url':'https://github.com/' + name,
                        'archived':False, 'disabled':False, 'pushed_at':now, 'default_branch':'master'}
        state = update_upstream.build_state([slug], {'repositories':{}}, now, Client())
        update_upstream.validate_state(state)
        catalog, updates = build_catalog.render([entity], build_catalog.make_manifest([entity]), state)
        self.assertIn('未查到正式发布版', catalog)
        self.assertIn('来源待核实', catalog)
        class FailedClient:
            def fetch(self, name, release=False):
                raise update_upstream.FetchError('network_error')
        stale = update_upstream.build_state([slug], state, '2026-09-13T00:00:00Z', FailedClient())
        update_upstream.validate_state(stale)
        catalog, updates = build_catalog.render([entity], build_catalog.make_manifest([entity]), stale)
        self.assertIn('旧信息', catalog)
        self.assertIn('2026-09-12 08:00（北京时间）', catalog)


if __name__ == '__main__':
    unittest.main()
