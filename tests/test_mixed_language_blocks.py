# -*- coding: utf-8 -*-
import json
import os
import unittest

from app import server
from app.language_blocks import looks_like_chinese_block

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')


class RecoveredLanguageDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(DATA, 'jp_blocks.json'), encoding='utf-8') as f:
            cls.jp_blocks = json.load(f)
        with open(os.path.join(DATA, 'zh_recovered_blocks.json'), encoding='utf-8') as f:
            cls.recovered = json.load(f)
        with open(os.path.join(DATA, 'corpus.txt'), encoding='utf-8') as f:
            cls.corpus = f.read()

    def test_recovery_partition_is_complete_and_unique(self):
        self.assertEqual(1, self.recovered['version'])
        self.assertEqual(len(self.corpus), self.recovered['base_corpus_length'])
        recovered_rows = [(b['doc'], b['order'], b['text']) for b in self.recovered['blocks']]
        jp_rows = [(d, o, t) for d, o, t in self.jp_blocks]
        self.assertEqual([], recovered_rows)
        self.assertEqual(len(jp_rows), len(set(jp_rows)))
        self.assertFalse(any(looks_like_chinese_block(t) for _, _, t in jp_rows))

    def test_known_all_around_type_moon_boundary(self):
        with open(os.path.join(DATA, 'story_blocks.json'), encoding='utf-8') as f:
            story_blocks = json.load(f)
        story_keys = {(d, o) for d, o, _ in story_blocks}
        jp_keys = {(d, o) for d, o, _ in self.jp_blocks}
        for order in (0, 2, 230, 264):
            self.assertIn((103, order), story_keys)
        self.assertNotIn((103, 265), jp_keys)


class MixedLanguageStoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()

    def test_doc_view_unfolds_chinese_and_keeps_japanese_collapsed(self):
        out = self.store.doc_view(103, 1, '', chap_start=1)
        by_order = {}
        for block in out['blocks']:
            by_order.setdefault(block['o'], []).append(block['lang'])
        self.assertGreater(len(out['blocks']), 600)
        self.assertGreater(out['untranslated'], 0)
        for order in (2, 230, 264):
            self.assertIn('zh', by_order[order])
            self.assertNotIn('ja', by_order[order])

    def test_recovered_text_is_searchable(self):
        result = self.store.search('开店前的杀人', limit=20)
        self.assertGreaterEqual(result['total'], 1)
        self.assertTrue(any(item['doc'] == 103 for item in result['occurrences']))
        self.assertTrue(any('开店前的杀人' in (item.get('snippet') or '')
                            for item in result['occurrences'] if item['doc'] == 103))

    def test_recovered_multi_term_search_is_searchable(self):
        result = self.store.search('开店前,杀人', limit=20)
        self.assertTrue(any((item.get('source') or {}).get('id') == 103 or item.get('doc') == 103
                            for item in result['occurrences']))


if __name__ == '__main__':
    unittest.main()
