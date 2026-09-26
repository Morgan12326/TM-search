# -*- coding: utf-8 -*-
import json, re, unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


class StoryRebuildTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = json.loads((DATA / "entries.json").read_text(encoding="utf-8"))["docs"]
        cls.story = json.loads((DATA / "story.json").read_text(encoding="utf-8"))
        cls.offsets = json.loads((DATA / "offsets.json").read_text(encoding="utf-8"))
        cls.story_blocks = json.loads((DATA / "story_blocks.json").read_text(encoding="utf-8"))
        cls.by_id = {d["id"]: d for d in cls.docs}
        cls.works = {w["work"]: w for w in cls.story["works"]}
        cls.have = Counter(o[2] for o in cls.offsets)
        cls.overlay = defaultdict(dict)
        for doc, order, text in cls.story_blocks:
            cls.overlay[doc][order] = text

    def chapters(self, work):
        return sum(len(r["chapters"]) for r in self.works[work]["routes"])

    def test_story_shape(self):
        self.assertEqual(len(self.story["works"]), 24)
        self.assertEqual(sum(len(r["chapters"]) for w in self.story["works"] for r in w["routes"]) + sum(len(w.get("root_chapters", [])) for w in self.story["works"]), 1305)
        self.assertNotIn("其他", self.works)
        self.assertEqual(self.chapters("广播剧"), 27)
        self.assertEqual(self.chapters("访谈"), 130)
        self.assertEqual(self.chapters("FUC"), 17)
        self.assertEqual(self.chapters("月姬"), 90)
        self.assertEqual(self.chapters("MB"), 143)
        self.assertEqual(self.chapters("FireGirl"), 15)

    def test_fz_fp_radio_removed(self):
        for work in ("FZ", "FP"):
            self.assertFalse(any(r.get("extra") for r in self.works[work]["routes"]))

    def test_tsukihime_routes(self):
        names = {r["name"] for r in self.works["月姬"]["routes"]}
        self.assertEqual(names, {"月姬本篇", "歌月十夜", "月姬plus", "Talk 宵明星[中]", "The Dark Six[中]", "真月谭月姬prologue[中]"})
        self.assertNotIn("Melty Blood", names)
        self.assertNotIn("其他资料", names)
        self.assertNotIn("歌月十夜合并文本[中]", names)

    def test_firegirl_chapters_and_text(self):
        route = self.works["FireGirl"]["routes"][0]
        titles = [c["title"] for c in route["chapters"]]
        self.assertEqual(titles, ["彩页"] + [str(i) for i in range(1, 14)] + ["解说"])
        text = "\n".join(self.overlay[332].values())
        self.assertIn("日之冈穗群", text)
        self.assertNotIn("MELTY BLOOD", text.upper())

    def test_every_chapter_has_text(self):
        for w in self.story["works"]:
            for route in w["routes"]:
                for chapter in route["chapters"]:
                    doc = chapter["doc"]
                    self.assertIn(doc, self.by_id)
                    if doc in self.overlay:
                        source_orders = self.overlay[doc]
                        start = chapter.get("start") or 0
                        end = chapter.get("end")
                        self.assertTrue(source_orders, (w["work"], route["name"], chapter["title"]))
                        self.assertTrue(
                            any(order == start or (order >= start and (end is None or order < end))
                                for order in source_orders),
                            (w["work"], route["name"], chapter["title"], doc, start, end),
                        )
                    else:
                        self.assertGreater(self.have[doc], 0, (w["work"], route["name"], chapter["title"], doc))

    def test_no_links_in_story_overlay(self):
        pattern = re.compile(r"(?i)(?:https?://|www\\.)")
        for doc, order, text in self.story_blocks:
            self.assertIsNone(pattern.search(text), (doc, order))

    def test_unpaired_japanese_stays_out_of_overlay(self):
        jp = json.loads((DATA / "jp_blocks.json").read_text(encoding="utf-8"))
        interview_docs = {c["doc"] for r in self.works["访谈"]["routes"] for c in r["chapters"]}
        unpaired = []
        for doc, order, text in jp:
            if doc in interview_docs and order not in self.overlay.get(doc, {}):
                if len(text) >= 25 and (any(ch in text for ch in "。！？!?") or len(text.splitlines()) >= 2):
                    unpaired.append((doc, order))
        self.assertGreater(len(unpaired), 0)
        for doc, order in unpaired:
            self.assertNotIn(order, self.overlay.get(doc, {}))

if __name__ == "__main__":
    unittest.main()





