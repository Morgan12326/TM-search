# -*- coding: utf-8 -*-
import json
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORY = os.path.join(ROOT, "data", "fgo_story.json")


def load_story():
    with open(STORY, encoding="utf-8") as fh:
        return json.load(fh)


def chapters_by_war(bundle):
    rows = {}
    for part in bundle:
        for chapter in part.get("chapters", []):
            rows[chapter.get("war_id")] = chapter
    return rows


class FgoStoryDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_story()
        cls.by_war = chapters_by_war(cls.bundle)

    def test_rebuilt_chapters_have_complete_sections(self):
        expected = {
            203: 17,
            300: 8,
            301: 23,
            302: 18,
            303: 18,
            304: 21,
            305: 28,
            306: 28,
            307: 17,
            308: 43,
            309: 15,
            310: 23,
            311: 28,
            401: 5,
            402: 18,
            403: 27,
            404: 26,
            405: 32,
        }
        for war_id, count in expected.items():
            with self.subTest(war_id=war_id):
                chapter = self.by_war.get(war_id)
                self.assertIsNotNone(chapter, f"missing war {war_id}")
                sections = chapter.get("chapters", [])
                self.assertEqual(len(sections), count)
                for section in sections:
                    self.assertTrue(section.get("lines"), f"empty section: {war_id} {section.get('title')}")

    def test_special_titles_and_ordeal_call_mapping(self):
        titles = {wid: [s.get("title") for s in self.by_war[wid]["chapters"]] for wid in (203, 308, 309, 311, 401)}
        self.assertEqual(titles[203][0], "前置标题")
        self.assertEqual(titles[203][-1], "第十六节 ——天元之花，后会有期")
        self.assertIn("第10节 卡美洛", titles[308])
        self.assertEqual(titles[308][-1], "尾声 了")
        self.assertEqual(titles[309][-1], "尾声")
        self.assertEqual(titles[311][-1], "第24节 前往南极")
        self.assertEqual(titles[401], [
            "奏章 Ordeal call 序章",
            "奥尔加玛丽 Quest 1",
            "奥尔加玛丽 Quest 2",
            "奥尔加玛丽 Quest 3",
            "奥尔加玛丽 Quest 4",
        ])
        self.assertNotIn(400, self.by_war)

    def test_key_body_text_is_present(self):
        flat = {
            wid: "\n".join(
                line.get("t", "")
                for section in self.by_war[wid].get("chapters", [])
                for line in section.get("lines", [])
            )
            for wid in (203, 308, 311, 401)
        }
        self.assertIn("感谢你详尽的说明。", flat[203])
        self.assertIn("众多妖精栖息的黄昏之岛", flat[308])
        self.assertIn("救援行动重启", flat[311])
        self.assertIn("奥尔加玛丽", flat[401])

    def test_rebuilt_sections_have_no_raw_control_markers(self):
        bad = ("＠", "[r]", "[k]", "[#", "[&", "[line ")
        for war_id in (203, *range(300, 312), *range(401, 406)):
            for section in self.by_war[war_id]["chapters"]:
                for line in section["lines"]:
                    text = line.get("t", "")
                    for token in bad:
                        self.assertNotIn(token, text, f"{war_id} {section['title']}: {token}")


    def test_appendix_is_moved_to_ordeal_call_two(self):
        chapter = self.by_war[403]
        self.assertEqual(chapter["chapters"][-1]["title"], "appendix")
        self.assertTrue(chapter["chapters"][-1]["lines"])


if __name__ == "__main__":
    unittest.main()
