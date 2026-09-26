# -*- coding: utf-8 -*-
import unittest

from app import server
from tools import rebuild_occurrence_index as occurrence


class CleanTextTests(unittest.TestCase):
    def test_removes_links_and_standalone_metadata(self):
        raw = (
            '<a href="https://example.com/a">正文甲</a>\n'
            '来源：https://example.com/source\n'
            '[正文乙](https://example.com/b)\n'
            'https://example.com/raw\n'
            '正文丙'
        )
        cleaned = occurrence.clean_occurrence_text(raw)
        self.assertEqual(cleaned, '正文甲\n正文乙\n正文丙')

    def test_extracts_script_dialogue_without_control_commands(self):
        raw = (
            '*define\n'
            'numalias effect_fst,400\n'
            'mov $msgline0,"第一句。":mov $msgline1,"第二句。"\n'
            'goto *start\n'
        )
        cleaned = occurrence.clean_occurrence_text(raw)
        self.assertEqual(cleaned, '第一句。\n第二句。')


class LanguageSplitTests(unittest.TestCase):
    def test_keeps_chinese_separate_from_japanese(self):
        raw = 'これは日本語です。\n这是中文正文。\n第二行中文。\n日本語の行。'
        visible, japanese = occurrence.split_visible_and_japanese(raw)
        self.assertIn('这是中文正文。', visible)
        self.assertIn('第二行中文。', visible)
        self.assertNotIn('这是中文正文。', japanese)
        self.assertIn('これは日本語です。', japanese)
        self.assertIn('日本語の行。', japanese)

    def test_keeps_chinese_line_that_mentions_a_japanese_term(self):
        raw = 'ツンギレ这个词始终讨论不出一个合适的翻译，虽然它是傲娇衍生出来的词。'
        visible, japanese = occurrence.split_visible_and_japanese(raw)
        self.assertEqual(visible, raw)
        self.assertEqual(japanese, '')


class PathLabelTests(unittest.TestCase):
    def test_shortens_common_work_and_route_names(self):
        self.assertEqual(occurrence.short_label('Fate/stay night'), 'FSN')
        self.assertEqual(occurrence.short_label('远坂凛线（UBW）'), 'UBW线')
        self.assertEqual(occurrence.short_label('Saber线（Fate）'), 'Saber线')
        self.assertEqual(occurrence.short_label('其他'), '未归类资料')

    def test_builds_local_story_locations_from_current_order(self):
        story = {
            'works': [{
                'work': 'FSN',
                'root_chapters': [],
                'routes': [{
                    'name': 'Saber线（Fate）',
                    'chapters': [{
                        'title': '第1日', 'doc': 10, 'start': 0, 'end': 3,
                        'key': 'FSN::route::0',
                    }],
                }],
            }],
        }
        locations = occurrence.build_story_locations(story, {10: [0, 1, 2, 3]})
        self.assertEqual(locations[(10, 0)]['path'], ['FSN', 'Saber线', '第1日'])
        self.assertEqual(locations[(10, 2)]['jump']['kind'], 'viewer')
        self.assertNotIn((10, 3), locations)


class OfficialBlockTests(unittest.TestCase):
    def test_extracts_numeric_prefix_before_title_slashes(self):
        self.assertEqual(occurrence._first_int_prefix(r'atlas\CN\80011_空之境界/the Garden of Order.txt'), 80011)
    def test_builds_official_blocks_and_section_jump(self):
        part = {'part': '活动剧情（按实装年份）'}
        chapter = {
            'war_id': 80002,
            'title': '歌唱的南瓜城的冒险',
            'group': '2016 年',
            'chapters': [
                {'title': '第1节 起始', 'lines': [{'s': '玛修', 't': '我们出发吧。'}]},
                {'title': '第2节 抵达', 'lines': [{'s': '', 't': '夜色降临。'}]},
            ],
        }
        rows, locations = occurrence.build_official_chapter(part, chapter, doc_id=2001)
        self.assertEqual([text for _order, text in rows], ['我们出发吧。', '夜色降临。'])
        self.assertEqual(locations[0]['path'], ['FGO', '活动', '2016 年', '歌唱的南瓜城的冒险', '第1节 起始'])
        self.assertEqual(locations[1]['jump'], {
            'kind': 'official', 'work': 'FGO', 'id': 80002, 'section': 1,
        })


from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCE_ROOTS = [
    Path(r'D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版'),
    Path(r'D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版 - 副本'),
]
LEGACY = Path(r'D:\codex\Projects\Output\发布归档\v1.1.6\型月搜索电脑版_v1.1.6\_internal\data')


class BundleIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = occurrence.build_bundle(DATA, SOURCE_ROOTS, LEGACY)

    def test_bundle_has_full_authoritative_coverage(self):
        self.assertGreaterEqual(self.bundle['stats']['visible_docs'], 1800)
        self.assertGreaterEqual(self.bundle['stats']['official_docs'], 420)
        self.assertTrue(self.bundle['locations'])
        self.assertTrue(self.bundle['excluded'])
        story_ids = set()
        story = occurrence._load_json(DATA / 'story.json')
        for work in story['works']:
            story_ids.update(int(c['doc']) for c in work.get('root_chapters', []))
            for route in work['routes']:
                story_ids.update(int(c['doc']) for c in route['chapters'])
        with_text = {int(row[0]) for row in self.bundle['story_rows']}
        with_text.update(int(row[0]) for row in self.bundle['jp_rows'])
        self.assertFalse(story_ids - with_text, story_ids - with_text)

class VerificationTests(unittest.TestCase):
    def test_excluded_official_duplicate_is_not_reported_missing(self):
        missing = occurrence.missing_official_chapters(
            all_ids={100, 101},
            active_ids={100},
            excluded=[{'reason': 'duplicate_official_chapter', 'evidence': {'war_id': 101}}],
        )
        self.assertEqual(missing, set())


class StoreOccurrenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()

    def test_occurrences_expose_location_jump(self):
        result = self.store.search('希耶尔', limit=30)
        self.assertTrue(result['occurrences'])
        found = [item for item in result['occurrences'] if item.get('jump')]
        self.assertTrue(found)
        self.assertTrue(any(item['jump'].get('kind') in ('viewer', 'official') for item in found))

    def test_official_occurrences_use_official_section_jump(self):
        result = self.store.search('啾……啾……', limit=50)
        official = [item for item in result['occurrences']
                    if (item.get('jump') or {}).get('kind') == 'official']
        self.assertTrue(official)
        self.assertTrue(all(item['jump'].get('work') == 'FGO' for item in official))
        self.assertTrue(all('section' in item['jump'] for item in official))


class ExclusionMergeTests(unittest.TestCase):
    def test_existing_exclusions_are_preserved_without_duplicates(self):
        merged = occurrence.merge_exclusions(
            [{'doc': 1, 'reason': 'a'}],
            [{'doc': 1, 'reason': 'old'}, {'doc': 2, 'reason': 'kept'}],
        )
        self.assertEqual([item['doc'] for item in merged], [1, 2])
        self.assertEqual(merged[0]['reason'], 'a')


class SourceManifestTests(unittest.TestCase):
    def test_manifest_modes_merge_without_dropping_excluded_docs(self):
        merged = occurrence.merge_source_modes({'1': 'story_overlay', '2': 'official'}, {'2': 'source_file', '3': 'source_file'})
        self.assertEqual(merged, {'1': 'story_overlay', '2': 'source_file', '3': 'source_file'})

    def test_manifest_mode_is_used_before_legacy_fallbacks(self):
        self.assertEqual(
            occurrence.source_mode_for_doc({'modes': {'42': 'source_file'}}, 42, {'official': False}),
            'source_file',
        )
        self.assertEqual(
            occurrence.source_mode_for_doc({'modes': {}}, 42, {'official': True}),
            'official',
        )


class CliTests(unittest.TestCase):
    def test_cli_accepts_audit_write_and_check(self):
        parser = occurrence.build_arg_parser()
        for flag in ('--audit', '--write', '--check'):
            args = parser.parse_args([flag])
            self.assertTrue(getattr(args, flag[2:]))


if __name__ == '__main__':
    unittest.main()










