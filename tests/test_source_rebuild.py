# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path

from tools import rebuild_source_data as rebuild

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCE_ROOTS = [
    Path(r'D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版'),
    Path(r'D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版 - 副本'),
]
LEGACY_DATA = Path(r'D:\codex\Projects\Output\发布归档\v1.1.6\型月搜索电脑版_v1.1.6\_internal\data')


class LanguageRunTests(unittest.TestCase):
    def test_paired_japanese_is_removed_and_chinese_is_kept(self):
        text = '日本語の質問です。\n\n这是中文问题。\n\n日本語の答えです。\n\n这是中文回答。\n'
        runs = rebuild.split_language_runs(text)
        visible = rebuild.remove_paired_japanese(runs)
        self.assertEqual(['这是中文问题。', '这是中文回答。'], [r.text.strip() for r in visible])

    def test_unpaired_japanese_is_preserved(self):
        text = '日本語の質問です。\n\nまだ翻訳されていない文章です。\n'
        runs = rebuild.split_language_runs(text)
        visible = rebuild.remove_paired_japanese(runs)
        self.assertEqual(2, len(visible))
        self.assertTrue(all(r.lang == 'ja' for r in visible))


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads((DATA / 'entries.json').read_text(encoding='utf-8'))
        cls.story = json.loads((DATA / 'story.json').read_text(encoding='utf-8'))

    def test_current_tsukihime_manifest_is_incomplete(self):
        route = next(
            r for w in self.story['works'] if w['work'] == '月姬'
            for r in w['routes'] if r['name'] == '月姬本篇'
        )
        jade = [c for c in route['chapters'] if c['doc'] == 512]
        amber = [c for c in route['chapters'] if c['doc'] == 510]
        self.assertEqual(19, len(jade))
        self.assertEqual(5, len(amber))

    def test_current_ddd_groups_follow_source_directories(self):
        work = next(w for w in self.story['works'] if w['work'] == 'DDD')
        self.assertEqual(['Vol.1', 'Vol.2', '宙之外'], [r['name'] for r in work['routes']])
        self.assertEqual([5, 5, 1], [len(r['chapters']) for r in work['routes']])

    def test_fsr_legacy_backup_contains_complete_story(self):
        blocks, metadata = rebuild.extract_legacy_fsr_blocks(LEGACY_DATA, self.entries)
        self.assertEqual(101, len(metadata))
        self.assertEqual(95, sum(1 for doc in metadata if doc in range(2, 97)))
        self.assertTrue(all(text.strip() for rows in blocks.values() for _, text in rows))
        joined = '\n'.join(text for rows in blocks.values() for _, text in rows)
        self.assertNotIn('MELTY BLOOD', joined)
        self.assertNotIn('[P.0]', joined)
        self.assertIn('宫本伊织', joined)
        self.assertIn('盈月之仪', joined)


class FinalDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.story = json.loads((DATA / 'story.json').read_text(encoding='utf-8'))
        cls.blocks = json.loads((DATA / 'story_blocks.json').read_text(encoding='utf-8'))

    def test_final_story_has_full_month_manifest(self):
        route = next(
            r for w in self.story['works'] if w['work'] == '月姬'
            for r in w['routes'] if r['name'] == '月姬本篇'
        )
        self.assertEqual(65, len(route['chapters']))
        titles = [c['title'] for c in route['chapters'] if c['doc'] == 512]
        self.assertEqual('プロローグ', titles[1])
        self.assertEqual('附录3 ひなたのゆめ', titles[-1])

    def test_translated_interview_prefixes_are_removed(self):
        by_doc = {}
        for doc, order, text in self.blocks:
            by_doc.setdefault(doc, []).append((order, text))
        for doc_id in (669, 677, 680):
            text = '\n'.join(text for _, text in sorted(by_doc[doc_id]))
            self.assertTrue(text.strip(), doc_id)
            self.assertEqual('zh', rebuild.classify_language(text[:400]), doc_id)
            self.assertNotRegex(text[:400], r'[\u3040-\u30ff]{20,}')

    def test_final_story_has_no_cross_work_month_text(self):
        route = next(r for w in self.story['works'] if w['work'] == '月姬'
                     for r in w['routes'] if r['name'] == '月姬本篇')
        month_docs = {c['doc'] for c in route['chapters']}
        text = '\n'.join(t for doc, order, t in self.blocks if doc in month_docs)
        self.assertNotIn('MELTY BLOOD', text.upper())
        self.assertNotIn('盈月之仪', text)


class SourceOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.story = json.loads((DATA / 'story.json').read_text(encoding='utf-8'))
        cls.entries = json.loads((DATA / 'entries.json').read_text(encoding='utf-8'))
        rows = json.loads((DATA / 'story_blocks.json').read_text(encoding='utf-8'))
        jp = json.loads((DATA / 'jp_blocks.json').read_text(encoding='utf-8'))
        cls.story_text = {}
        cls.jp_docs = set()
        for doc, order, text in rows:
            cls.story_text.setdefault(doc, []).append(text)
        for doc, order, text in jp:
            cls.jp_docs.add(doc)

    def test_local_source_story_documents_match_source_text(self):
        docs = {d['id']: d for d in self.entries['docs']}
        story_ids = {c['doc'] for w in self.story['works'] for r in w['routes'] for c in r['chapters']}
        checked = 0
        for doc_id in story_ids:
            doc = docs[doc_id]
            path = rebuild.resolve_source_path(doc.get('file', ''), SOURCE_ROOTS)
            if path is None:
                continue
            source_flat = ''.join(rebuild.sanitize_source_text(rebuild.read_source_text(path)).split())
            target = '\n'.join(self.story_text.get(doc_id, []))
            if not target:
                self.assertIn(doc_id, self.jp_docs, doc_id)
                continue
            target_lines = [''.join(line.split()) for line in target.splitlines()]
            samples = [line for line in target_lines if len(line) >= 16][::max(1, len(target_lines) // 3)][:3]
            if not samples:
                continue
            self.assertTrue(any(sample in source_flat for sample in samples),
                            (doc_id, doc['title'], doc['file'], samples))
            checked += 1
        self.assertGreater(checked, 300)


class MbStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.story = json.loads((DATA / 'story.json').read_text(encoding='utf-8'))
        cls.entries = json.loads((DATA / 'entries.json').read_text(encoding='utf-8'))
        cls.blocks = json.loads((DATA / 'story_blocks.json').read_text(encoding='utf-8'))
        cls.mb = next(w for w in cls.story['works'] if w['work'] == 'MB')

    def test_mb_routes_and_source_coverage(self):
        self.assertEqual(['MB汉化', 'MBAA', 'MBAACC', 'MBAC', 'MBR'],
                         [r['name'] for r in self.mb['routes']])
        self.assertEqual([71, 28, 2, 24, 18], [len(r['chapters']) for r in self.mb['routes']])
        docs = {d['id']: d for d in self.entries['docs']}
        source_root = SOURCE_ROOTS[0] / '原作文本' / 'MB'
        expected = {
            str(path.relative_to(SOURCE_ROOTS[0])).replace('/', '\\')
            for path in source_root.rglob('*')
            if path.is_file() and '\\日文\\' not in '\\' + str(path.relative_to(SOURCE_ROOTS[0]))
        }
        actual = {docs[c['doc']]['file'] for r in self.mb['routes'] for c in r['chapters']}
        self.assertEqual(expected, actual)
        self.assertTrue(any(path.endswith('08B_G汉化.txt') for path in actual))

    def test_mb_hanhua_groups_are_preserved_without_japanese(self):
        route = next(r for r in self.mb['routes'] if r['name'] == 'MB汉化')
        self.assertFalse(any('\\日文\\' in self.entries['docs'][c['doc']]['file'] for c in route['chapters']))
        groups = {}
        for chapter in route['chapters']:
            groups[chapter.get('group', '')] = groups.get(chapter.get('group', ''), 0) + 1
        self.assertEqual(2, groups.get('', 0))
        self.assertEqual(21, groups.get('Melty Blood BADEND', 0))
        for group in (
            'Melty Blood K幻影之夏虚言之王路线',
            'Melty Blood L虚言之王路线',
            'Melty Blood M1黎明之时路线',
            'Melty Blood M2幻影之夏路线',
            'Melty Blood N1塔塔利之夜路线',
            'Melty Blood N2闲话月姬路线',
            'Melty Blood O1最强之敌路线',
            'Melty Blood O2真·最强之敌路线',
        ):
            self.assertEqual(6, groups.get(group, 0), group)

    def test_mb_story_blocks_have_no_links(self):
        mb_docs = {c['doc'] for r in self.mb['routes'] for c in r['chapters']}
        pattern = rebuild.URL_RE
        for doc, order, text in self.blocks:
            if doc in mb_docs:
                self.assertIsNone(pattern.search(text), (doc, order, text[:120]))
                self.assertNotRegex(text, r'\[[^\]]+\]\([^)]+\)|<a\b', (doc, order))


class FeCccStoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.story = json.loads((DATA / 'story.json').read_text(encoding='utf-8'))
        cls.entries = json.loads((DATA / 'entries.json').read_text(encoding='utf-8'))
        cls.blocks = json.loads((DATA / 'story_blocks.json').read_text(encoding='utf-8'))

    def test_old_fe_is_replaced_by_feccc_routes_and_root_chapters(self):
        works = {w['work']: w for w in self.story['works']}
        self.assertNotIn('FE', works)
        self.assertIn('FE_CCC', works)
        work = works['FE_CCC']
        self.assertEqual([10, 9, 11, 12, 1, 1], [len(r['chapters']) for r in work['routes']])
        self.assertEqual(['CCC C狐路线', 'CCC 无铭ARHCER路线', 'CCC 赤SABER路线', 'CCC 金闪闪路线',
                          '玉藻前相关', '安徒生相关'], [r['name'] for r in work['routes']])
        self.assertEqual([], work.get('root_chapters', []))

    def test_old_fe_only_documents_are_not_story_chapters(self):
        removed = {218, 228, 258, 259, 260}
        story_docs = {c['doc'] for w in self.story['works'] if w['work'] == 'FE_CCC'
                      for r in w['routes'] for c in r['chapters']}
        self.assertFalse(removed & story_docs)

    def test_feccc_source_files_are_exactly_covered(self):
        root = Path(r'D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版 - 副本')
        source = root / '原作文本' / 'FE CCC'
        expected = {str(p.relative_to(root)).replace('/', '\\') for p in source.rglob('*') if p.is_file()}
        self.assertEqual(44, len(expected))
        docs = {d['id']: d for d in self.entries['docs']}
        work = next(w for w in self.story['works'] if w['work'] == 'FE_CCC')
        chapters = list(work.get('root_chapters', [])) + [c for r in work['routes'] for c in r['chapters']]
        actual = {docs[c['doc']]['file'] for c in chapters}
        self.assertEqual(expected, actual)

    def test_feccc_story_blocks_have_no_links(self):
        work = next(w for w in self.story['works'] if w['work'] == 'FE_CCC')
        docs = {c['doc'] for r in work['routes'] for c in r['chapters']}
        docs.update(c['doc'] for c in work.get('root_chapters', []))
        for doc, order, text in self.blocks:
            if doc in docs:
                self.assertIsNone(rebuild.URL_RE.search(text), (doc, order, text[:120]))
                self.assertNotRegex(text, r'\[[^\]]+\]\([^)]+\)|<a\b', (doc, order))


class StoryNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import server
        cls.store = server.Store()

    def test_story_nodes_emit_chapter_keys(self):
        key = next(k for k, node in self.store.nav.items()
                   if k.startswith('work:FSR') and node.get('chapters'))
        node = self.store.story_node(key)
        self.assertTrue(node['chapters'])
        self.assertTrue(all(c.get('key') for c in node['chapters']))

    def test_fsr_and_tsukihime_text_is_readable(self):
        fsr = self.store.search('盈月之仪', limit=20)
        self.assertTrue(any(2 <= item['doc'] <= 96 for item in fsr['occurrences']))
        moon = self.store.doc_view(510, 0, '')
        self.assertTrue(moon['blocks'])
        self.assertTrue(any(block['lang'] == 'ja' for block in moon['blocks']))

    def test_mb_keeps_existing_search_classification(self):
        docs = {d['id']: d for d in json.loads((DATA / 'entries.json').read_text(encoding='utf-8'))['docs']}
        new_doc = next(d for d in docs.values() if d['file'].endswith('08B_G汉化.txt'))
        self.assertEqual(('月姬', 'Melty Blood'), self.store.doc_scope[new_doc['id']])
        result = self.store.search('漆黑色的兽群迫近', limit=20)
        self.assertTrue(any(item['doc'] == new_doc['id'] for item in result['occurrences']))

    def test_feccc_node_exposes_root_chapters_and_routes(self):
        node = self.store.story_node('work:FE_CCC')
        self.assertEqual([], node['chapters'])
        self.assertEqual(['CCC C狐路线', 'CCC 无铭ARHCER路线', 'CCC 赤SABER路线', 'CCC 金闪闪路线',
                          '玉藻前相关', '安徒生相关'], [c['name'] for c in node['children']])
        self.assertEqual([10, 9, 11, 12, 1, 1], [c['count'] for c in node['children']])
        leaf = self.store.story_leaf('work:FE_CCC')
        self.assertEqual([], leaf['chapters'])
        self.assertEqual(44, leaf['total'])

    def test_feccc_keeps_search_classification(self):
        docs = {d['id']: d for d in json.loads((DATA / 'entries.json').read_text(encoding='utf-8'))['docs']}
        doc = next(d for d in docs.values() if d['file'] == r'原作文本\FE CCC\CCC C狐路线\00序章.txt')
        self.assertEqual(('FE', 'Fate/EXTRA CCC'), self.store.doc_scope[doc['id']])
        result = self.store.search('这里是灵子虚构世界', limit=20)
        self.assertTrue(any(item['doc'] == doc['id'] for item in result['occurrences']))

    def test_mahotsukai_is_sibling_of_ddd_under_other(self):
        tree = self.store.story_tree()
        self.assertFalse(any(top["name"] == "魔法使之箱" for top in tree))
        other = next(top for top in tree if top["name"] == "其他作品与杂项")
        names = [child["name"] for child in other["children"]]
        self.assertIn("DDD", names)
        self.assertIn("魔法使之箱", names)
        self.assertLess(names.index("DDD"), names.index("魔法使之箱"))

    def test_all_story_chapters_round_trip_to_body(self):
        checked = 0
        for work in self.store.story_works:
            groups = [{"name": work["work"], "chapters": work.get("root_chapters", [])}]
            groups.extend(work["routes"])
            for route in groups:
                chapters = route['chapters']
                for index, chapter in enumerate(chapters):
                    start = chapter.get('start') or 0
                    end = chapter.get('end')
                    self.assertIn('key', chapter)
                    view = self.store.doc_view(chapter['doc'], start, '', chap_start=start, chap_end=end,
                                              chapter_key=chapter['key'])
                    self.assertTrue(view['blocks'], (work['work'], route['name'], chapter['title']))
                    story = view.get('story') or {}
                    self.assertEqual(chapter['title'], story.get('title'),
                                     (work['work'], route['name'], chapter['title']))
                    self.assertEqual(index + 1, story.get('index'))
                    self.assertEqual(len(chapters), story.get('total'))
                    self.assertEqual((chapters[index - 1]['title'] if index else None),
                                     (story.get('prev') or {}).get('title'))
                    self.assertEqual((chapters[index + 1]['title'] if index + 1 < len(chapters) else None),
                                     (story.get('next') or {}).get('title'))
                    if index:
                        self.assertEqual(chapters[index - 1]['key'], story['prev']['key'])
                    if index + 1 < len(chapters):
                        self.assertEqual(chapters[index + 1]['key'], story['next']['key'])
                    checked += 1
        self.assertGreaterEqual(checked, 1100)


if __name__ == '__main__':
    unittest.main()


