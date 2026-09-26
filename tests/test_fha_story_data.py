# -*- coding: utf-8 -*-
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


class FhaStoryDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads((DATA / "entries.json").read_text(encoding="utf-8"))
        cls.story = json.loads((DATA / "story.json").read_text(encoding="utf-8"))
        cls.blocks = json.loads((DATA / "story_blocks.json").read_text(encoding="utf-8"))
        cls.fha = next(w for w in cls.story["works"] if w["work"] == "FHA")
        cls.docs = {d["id"]: d for d in cls.entries["docs"]}
        cls.by_doc = {}
        for doc, order, text in cls.blocks:
            cls.by_doc.setdefault(doc, {})[order] = text

    def route(self, name):
        return next(r for r in self.fha["routes"] if r["name"] == name)

    def test_route_shape_and_counts(self):
        self.assertEqual(
            [r["name"] for r in self.fha["routes"]],
            [
                "主线：复仇者与巴泽特",
                "日常事件 · 10月8日",
                "日常事件 · 10月9日",
                "日常事件 · 10月10日",
                "日常事件 · 10月11日",
                "日常事件 · 艾因兹贝伦城",
                "其他番外",
            ],
        )
        self.assertEqual(
            [len(r["chapters"]) for r in self.fha["routes"]],
            [64, 40, 23, 29, 27, 19, 39],
        )
        self.assertEqual(241, sum(len(r["chapters"]) for r in self.fha["routes"]))

    def test_mainline_order_and_merges(self):
        main = self.route("主线：复仇者与巴泽特")["chapters"]
        self.assertEqual("01 柳洞寺怪谈（prologue. 柳洞寺の怪談）", main[0]["title"])
        self.assertEqual("64 终章（epilogue.）", main[-1]["title"])
        self.assertEqual(
            ["03 再会 I（サイカイ）", "48 再会 II（サイカイ）"],
            [c["title"] for c in main if "再会" in c["title"]],
        )
        self.assertEqual(5, sum(1 for c in main if "卡莲" in c["title"]))
        self.assertEqual(3, sum(1 for c in main if "异常记录" in c["title"] or "死桥" in c["title"]))
        self.assertEqual(64, len({c["doc"] for c in main}))
        self.assertTrue(any("【前置】" in c["title"] for c in main))
        self.assertTrue(any(not c.get("prereq") for c in main))

    def test_other_extras_groups(self):
        extras = self.route("其他番外")["chapters"]
        counts = Counter(c.get("group") for c in extras)
        self.assertEqual(
            {"夜间短篇": 22, "Eclipse 番外": 6, "其他特别篇": 6, "小游戏": 3, "杂项": 2},
            dict(counts),
        )

    def test_every_fha_chapter_has_text_and_is_unique(self):
        docs = [c["doc"] for r in self.fha["routes"] for c in r["chapters"]]
        self.assertEqual(len(docs), len(set(docs)))
        for doc_id in docs:
            self.assertIn(doc_id, self.docs)
            self.assertTrue(self.by_doc.get(doc_id), doc_id)

    def test_last_night_was_imported(self):
        matches = [d for d in self.entries["docs"]
                   if d.get("meta", {}).get("fha_source_stem") == "おしまいの夜"]
        self.assertEqual(1, len(matches))
        doc = matches[0]
        self.assertIn("最后一夜", doc["title"])
        self.assertIn(1958, self.by_doc)
        text = "\n".join(self.by_doc[1958].values())
        self.assertIn("最后一夜结束", text)

    def test_navigation_has_second_level_extras(self):
        from app import server
        store = server.Store()
        root = store.story_node("work:FHA")
        self.assertIn("其他番外", [c["name"] for c in root["children"]])
        extras = store.story_node("work:FHA||route:其他番外")
        self.assertEqual(
            ["夜间短篇", "Eclipse 番外", "其他特别篇", "小游戏", "杂项"],
            [c["name"] for c in extras["children"]],
        )


if __name__ == "__main__":
    unittest.main()

