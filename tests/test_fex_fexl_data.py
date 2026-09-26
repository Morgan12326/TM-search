# -*- coding: utf-8 -*-
import json
import os
import re
import unittest
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')

class FexFexlDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(DATA, 'entries.json'), encoding='utf-8') as f:
            cls.bundle = json.load(f)
        with open(os.path.join(DATA, 'offsets.json'), encoding='utf-8') as f:
            cls.offsets = json.load(f)
        with open(os.path.join(DATA, 'story.json'), encoding='utf-8') as f:
            cls.story = json.load(f)
        with open(os.path.join(DATA, 'corpus.txt'), encoding='utf-8') as f:
            cls.corpus = f.read()
        cls.docs = {d['id']: d for d in cls.bundle['docs']}
        cls.entries = cls.bundle['entries']
        cls.by_doc = defaultdict(list)
        for start, length, doc_id, order in cls.offsets:
            cls.by_doc[doc_id].append((order, start, length))

    def story_text(self, doc_id):
        return '\n'.join(self.corpus[s:s+l] for _, s, l in self.by_doc[doc_id])

    def test_story_directory_shape(self):
        fex = next(w for w in self.story['works'] if w['work'] == 'FEX')
        fexl = next(w for w in self.story['works'] if w['work'] == 'FEXL')
        self.assertEqual(29, sum(len(r['chapters']) for r in fex['routes'] if r['name'] in ('焰诗篇', '兰词篇', '未明篇', '金诗篇')))
        self.assertEqual(26, sum(len(r['chapters']) for r in fex['routes'] if r['name'] not in ('焰诗篇', '兰词篇', '未明篇', '金诗篇')))
        self.assertEqual(28, sum(len(r['chapters']) for r in fexl['routes']))

    def test_only_story_events_and_no_raw_codes(self):
        forbidden = re.compile(r'(?:【|BC\.\d+|\b(?:TALK|BSS|BTS|BTP|BSC|MYR|SYS)_)')
        for work in ('FEX', 'FEXL'):
            docs = [d for d in self.bundle['docs'] if d.get('work') == work and d.get('file', '').startswith('剧情大全\\')]
            self.assertTrue(docs)
            for d in docs:
                text = self.story_text(d['id'])
                self.assertIsNone(forbidden.search(text), (work, d['file'], forbidden.search(text)))
                self.assertNotIn('_f', text)

    def test_expected_story_counts(self):
        fex = [d for d in self.bundle['docs'] if d.get('work') == 'FEX' and d.get('file', '').startswith('剧情大全\\')]
        fexl = [d for d in self.bundle['docs'] if d.get('work') == 'FEXL' and d.get('file', '').startswith('剧情大全\\')]
        self.assertEqual(55, len(fex))
        self.assertEqual(28, len(fexl))

    def test_glossary_pairs_and_indexes(self):
        for work, count in [('FEX', 118), ('FEXL', 104)]:
            docs = {d['id'] for d in self.bundle['docs'] if d.get('work') == work}
            rows = [e for e in self.entries if e.get('doc') in docs and e.get('cat') == '用语辞典']
            self.assertEqual(count + 1, len(rows))
            source = '《Fate/EXTELLA用语辞典》' if work == 'FEX' else '《Fate/EXTELLA LINK用语辞典》'
            self.assertIn(source + '索引', [e['term'] for e in rows])
            glossary_docs = [d for d in self.bundle['docs'] if d.get('work') == work and d.get('kind') == '用语辞典']
            self.assertTrue(all('游戏内用语辞典' not in d.get('file', '') for d in glossary_docs))
            self.assertTrue(all(d.get('meta', {}).get('出处') == source for d in glossary_docs))

    def test_glossary_display_source_matches_dictionary_title(self):
        for work, count in [('FEX', 118), ('FEXL', 104)]:
            display_title = 'Fate/EXTELLA用语辞典' if work == 'FEX' else 'Fate/EXTELLA LINK用语辞典'
            source = f'《{display_title}》'
            prefix = f'原作文本\\{work}\\'
            glossary_docs = [d for d in self.bundle['docs']
                             if d.get('work') == work and d.get('file', '').startswith(prefix)]
            self.assertEqual(count + 1, len(glossary_docs))
            self.assertTrue(all(d.get('title') == display_title for d in glossary_docs),
                            (work, [(d.get('title'), d.get('file')) for d in glossary_docs if d.get('title') != display_title][:3]))
            self.assertTrue(all(d.get('kind') == '用语辞典' for d in glossary_docs),
                            (work, [(d.get('kind'), d.get('file')) for d in glossary_docs if d.get('kind') != '用语辞典'][:3]))
            self.assertTrue(all((d.get('meta') or {}).get('出处') == source for d in glossary_docs))
            glossary_ids = {d['id'] for d in glossary_docs}
            rows = [e for e in self.entries if e.get('doc') in glossary_ids]
            self.assertEqual(count + 1, len(rows))
            self.assertTrue(all((e.get('source_refs') or [{}])[0].get('title') == display_title for e in rows),
                            (work, [(e.get('term'), (e.get('source_refs') or [{}])[0].get('title')) for e in rows
                                    if (e.get('source_refs') or [{}])[0].get('title') != display_title][:3]))

    def test_offsets_reference_valid_docs(self):
        valid = set(self.docs)
        self.assertTrue(all(row[2] in valid for row in self.offsets))
        self.assertEqual(len(self.corpus), max(row[0] + row[1] for row in self.offsets))

    def test_duplicate_primary_priority(self):
        chosen = {e['term']: e for e in self.entries if e.get('is_primary')}
        for term in ('Saber', '宝具'):
            self.assertIn(term, chosen)
            self.assertIn(self.docs[chosen[term]['doc']]['work'], ('FSN', 'FE'))

class FexFexlWikiMergeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import server
        cls.store = server.Store()

    def merged_leaf(self, key="work:FEX"):
        return self.store.wiki_leaf(key, 0, 500, "", "")

    def test_extella_merge_count_and_legacy_key(self):
        merged = self.merged_leaf()
        self.assertEqual(174, merged["total"])
        self.assertEqual("Fate/EXTELLA", merged["name"])
        legacy = self.merged_leaf("sub:FE|Fate/EXTRA Extella")
        self.assertEqual(174, legacy["total"])
        self.assertEqual("Fate/EXTELLA", legacy["name"])
        self.assertEqual({item["term"] for item in merged["items"]},
                         {item["term"] for item in legacy["items"]})

    def test_tree_removes_extra_extella_and_keeps_link(self):
        fate = next(top for top in self.store.wiki_tree if top["key"] == "top:fate")
        children = {child["key"]: child for child in fate["children"]}
        sub_names = [sub["name"] for sub in children["work:FE"]["children"]]
        self.assertNotIn("Fate/EXTRA Extella", sub_names)
        self.assertEqual(174, children["work:FEX"]["terms"])
        self.assertEqual(105, children["work:FEXL"]["terms"])

    def test_priority_keeps_extra_extella_definition(self):
        items = {item["term"]: item for item in self.merged_leaf()["items"]}
        for term, doc_id in (("NPC", 615), ("SE.RA.PH", 789)):
            self.assertEqual(doc_id, items[term]["source"]["id"], term)
            self.assertEqual(("FE", "Fate/EXTRA Extella"),
                             self.store.doc_scope[items[term]["source"]["id"]], term)
        labels = [item["name"] for item in self.store.term_classifications("NPC")]
        self.assertNotIn("Fate/EXTRA 系列 · Fate/EXTRA Extella", labels)
        self.assertIn("Fate/EXTELLA", labels)

    def test_extra_page_title_override(self):
        leaf = self.store.wiki_leaf("sub:FE|Fate/EXTRA", 0, 1, "", "")
        self.assertEqual("Fate/EXTRA 系列", leaf["name"])


if __name__ == '__main__':
    unittest.main()
