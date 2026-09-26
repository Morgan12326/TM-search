# -*- coding: utf-8 -*-
import json
import re
import unittest
from pathlib import Path

from tools import rebuild_fsf_story as fsf

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


class FsfParserTests(unittest.TestCase):
    def test_extract_blocks_keeps_story_text_and_drops_images_and_urls(self):
        html = (
            '<p>目录</p><p>第一卷 序章</p><p>第一卷 第一章</p>'
            '<h1>序章</h1><p>甲段。</p>'
            '<figure><img src="cover.jpg"><figcaption>图注</figcaption></figure>'
            '<p>乙段。</p><p>https://example.com/source</p>'
            '<h1>第一章</h1><p>丙段。</p>'
        )
        self.assertEqual(
            [
                {"kind": "paragraph", "text": "目录"},
                {"kind": "paragraph", "text": "第一卷 序章"},
                {"kind": "paragraph", "text": "第一卷 第一章"},
                {"kind": "heading", "text": "序章"},
                {"kind": "paragraph", "text": "甲段。"},
                {"kind": "paragraph", "text": "乙段。"},
                {"kind": "heading", "text": "第一章"},
                {"kind": "paragraph", "text": "丙段。"},
            ],
            fsf.extract_blocks(html),
        )

    def test_build_volume_uses_toc_and_keeps_special_title(self):
        articles = [
            {
                "article_id": 1,
                "title": "第五卷①",

                "html": (
                    "<p>第五卷 【——】</p><p>第五卷 接续章【轮舞曲】</p>"
                    "<h1>【——】</h1><p>卷首正文。</p>"
                    "<h1>接续章【轮舞曲】</h1><p>甲。</p>"
                ),
            },
            {
                "article_id": 2,
                "title": "第五卷②",

                "html": "<p>乙。</p><h1>幕间【佣兵】</h1><p>丙。</p>",
            },
        ]
        chapters = fsf.build_volume_chapters(5, articles)
        self.assertEqual(["【——】", "接续章【轮舞曲】", "幕间【佣兵】"],
                         [c["title"] for c in chapters])
        self.assertEqual(["卷首正文。", "甲。\n乙。", "丙。"],
                         [c["text"] for c in chapters])

    def test_first_article_excludes_material_pages_before_first_toc_chapter(self):
        articles = [{
            "article_id": 1,
            "title": "第六卷①",

            "html": (
                "<p>第六卷 接续章【追走曲】</p><p>第六卷 十七章</p>"
                "<p>PS：以下为技能资料。</p><p>技能A说明。</p>"
                "<h1>接续章【追走曲】</h1><p>正文甲。</p>"
                "<h1>十七章</h1><p>正文乙。</p>"
            ),
        }]
        chapters = fsf.build_volume_chapters(6, articles)
        self.assertEqual(["接续章【追走曲】", "十七章"], [c["title"] for c in chapters])
        self.assertEqual(["正文甲。", "正文乙。"], [c["text"] for c in chapters])

    def test_toc_title_can_have_annotated_heading_suffix(self):
        articles = [{
            "article_id": 1,
            "title": "第三卷①",
            "html": "<p>第三卷 后记</p><h1>后记（含本篇剧透，请读完后观看）</h1><p>后记正文。</p>",
        }]
        chapters = fsf.build_volume_chapters(3, articles)
        self.assertEqual(["后记"], [c["title"] for c in chapters])
        self.assertEqual(["后记正文。"], [c["text"] for c in chapters])
    def test_commentary_toc_entries_are_not_story_chapters(self):
        articles = [{
            "article_id": 1,
            "title": "第一卷③",
            "words": 14,
            "html": (
                "<p>第一卷 后记</p><p>第一卷 解说</p>"
                "<h1>后记</h1><p>后记正文。</p><h1>解说</h1><p>解说资料。</p>"
            ),
        }]
        chapters = fsf.build_volume_chapters(1, articles)
        self.assertEqual(["后记"], [c["title"] for c in chapters])
        self.assertEqual(["后记正文。"], [c["text"] for c in chapters])
    def test_build_volume_rejects_article_word_count_mismatch(self):
        articles = [{
            "article_id": 1,
            "title": "第一卷①",
            "words": 100,
            "html": "<p>第一卷 序章</p><h1>序章</h1><p>太短。</p>",
        }]
        with self.assertRaisesRegex(ValueError, "article coverage mismatch"):
            fsf.build_volume_chapters(1, articles)

    def test_build_volume_chapters_crosses_article_boundaries(self):
        articles = [
            {
                "article_id": 1,
                "title": "第一卷①",

                "html": (
                    "<p>第一卷 序章</p><p>第一卷 第一章</p>"
                    "<h1>序章</h1><p>甲。</p><h1>第一章</h1><p>乙。</p>"
                ),
            },
            {
                "article_id": 2,
                "title": "第一卷②",

                "html": "<p>乙续。</p><h1>第二章</h1><p>丙。</p><h1>后记</h1><p>丁。</p>",
            },
        ]
        chapters = fsf.build_volume_chapters(1, articles)
        self.assertEqual(["序章", "第一章", "第二章", "后记"], [c["title"] for c in chapters])
        self.assertEqual(["甲。", "乙。\n乙续。", "丙。", "丁。"], [c["text"] for c in chapters])

    def test_build_prototype_cleans_translator_banner_and_appendix(self):
        rows = [
            (0, "译者：测试"),
            (1, "仅供个人学习交流使用"),
            (2, "序章"),
            (3, "正文甲。"),
            (4, "ACT1 Archer"),
            (5, "正文乙。"),
            (6, "后记"),
            (7, "作者留言。"),
            (8, "成田良悟"),
            (9, "附录《监修》"),
            (10, "资料正文。"),
        ]
        blocks, chapters = fsf.build_prototype_segments(rows)
        self.assertEqual("序章", blocks[0][1])
        self.assertNotIn("仅供个人学习交流使用", "\n".join(t for _, t in blocks))
        self.assertNotIn("资料正文", "\n".join(t for _, t in blocks))
        self.assertEqual(["序章", "ACT1 Archer", "后记"], [c["title"] for c in chapters])
    def test_resolve_volume_doc_id_reuses_existing_file_key(self):
        docs = [{"id": 1955, "work": "FSF", "kind": "原作",
                 "file": "剧情大全\\FSF\\第5卷.txt"}]
        self.assertEqual(1955, fsf.resolve_volume_doc_id(docs, 5))

    def test_stale_fsf_doc_ids_returns_unreferenced_volume_docs(self):
        docs = [
            {"id": 1955, "work": "FSF", "kind": "原作", "file": "剧情大全\\FSF\\第5卷.txt"},
            {"id": 1958, "work": "FSF", "kind": "原作", "file": "剧情大全\\FSF\\第5卷.txt"},
            {"id": 304, "work": "FSF", "kind": "原作", "file": "原作文本\\FSF\\原文\\FAKE.txt"},
        ]
        self.assertEqual({1955}, fsf.stale_fsf_doc_ids(docs, {1958}))

    def test_prototype_route_name_is_fate_states_night(self):
        self.assertEqual("《Fate/states night》", fsf.PROTOTYPE_ROUTE)
    def test_find_prototype_route_accepts_legacy_and_new_names(self):
        for name in ("fake states night", "原型企划《fake states night》", fsf.PROTOTYPE_ROUTE):
            work = {"routes": [{"name": name, "chapters": []}]}
            self.assertEqual(name, fsf.find_prototype_route(work)["name"])

class FinalFsfDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = json.loads((DATA / "entries.json").read_text(encoding="utf-8"))
        cls.story = json.loads((DATA / "story.json").read_text(encoding="utf-8"))
        cls.blocks = json.loads((DATA / "story_blocks.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((ROOT / "tools" / "fsf_story_sources.json").read_text(encoding="utf-8"))
        cls.work = next(w for w in cls.story["works"] if w["work"] == "FSF")
        cls.docs = {d["id"]: d for d in cls.entries["docs"]}
        cls.by_doc = {}
        for doc, order, text in cls.blocks:
            cls.by_doc.setdefault(doc, []).append((order, text))

    def route(self, name):
        return next(r for r in self.work["routes"] if r["name"] == name)

    def test_route_shape_and_source_alignment(self):
        self.assertEqual(
            [fsf.PROTOTYPE_ROUTE] + [f"第{i}卷" for i in range(1, 8)],
            [r["name"] for r in self.work["routes"]],
        )
        for volume in self.manifest["volumes"]:
            route = self.route(f"第{volume['volume']}卷")
            self.assertEqual(
                [c["title"] for c in volume["chapters"]],
                [c["title"] for c in route["chapters"]],
            )

    def test_every_fsf_chapter_has_text_and_valid_range(self):
        for route in self.work["routes"][1:]:
            for chapter in route["chapters"]:
                rows = self.by_doc.get(chapter["doc"], [])
                start = chapter.get("start") or 0
                end = chapter.get("end")
                selected = [text for order, text in rows
                            if order >= start and (end is None or order < end)]
                self.assertTrue(selected, (route["name"], chapter["title"]))
                self.assertTrue(all(text.strip() for text in selected),
                                (route["name"], chapter["title"]))

    def test_volume_documents_are_stable_and_have_keys(self):
        mainline = {d["id"] for d in self.entries["docs"]
                    if d.get("work") == "FSF" and d.get("kind") == "原作"
                    and str(d.get("file", "")).startswith("剧情大全\\FSF\\")}
        self.assertEqual({299, 300, 301, 302, 303, 1955, 1956, 1957}, mainline)
        self.assertTrue(all(c.get("key") for r in self.work["routes"] for c in r["chapters"]))
    def test_no_duplicate_or_bad_legacy_titles(self):
        titles = [c["title"] for r in self.work["routes"] for c in r["chapters"]]
        self.assertNotIn("幕间：『看守者（Watcherr）』", titles)
        for route in self.work["routes"][1:]:
            route_titles = [c["title"] for c in route["chapters"]]
            self.assertEqual(len(route_titles), len(set(route_titles)), route["name"])

    def test_prototype_is_separate_and_volumes_eight_nine_are_absent(self):
        names = [r["name"] for r in self.work["routes"]]
        self.assertEqual(fsf.PROTOTYPE_ROUTE, names[0])
        self.assertNotIn("第8卷", names)
        self.assertNotIn("第9卷", names)

    def test_article_audit_matches_source_word_counts(self):
        for volume in self.manifest["volumes"]:
            for index, article in enumerate(volume["articles"]):
                self.assertIn("api_words", article)
                self.assertIn("covered_chars", article)
                tolerance = 0.07 if index == 0 else 0.02
                delta = abs(article["covered_chars"] - article["api_words"])
                self.assertLessEqual(delta / max(1, article["api_words"]), tolerance,
                                     (volume["volume"], article["article_id"]))

    def test_known_continuation_segments_are_present(self):
        expected = {
            2: ["呈现出妖娆光辉的刀身"],
            3: ["实际上那段时期确实曾引发一般市民集体昏倒"],
            5: ["那是一位拥有良好体态的男性", "这次,魔术师们的脑袋变成了一片空白"],
        }
        for volume, sentinels in expected.items():
            route = self.route(f"第{volume}卷")
            texts = []
            for chapter in route["chapters"]:
                start = chapter.get("start") or 0
                end = chapter.get("end")
                texts.extend(text for order, text in self.by_doc.get(chapter["doc"], [])
                             if order >= start and (end is None or order < end))
            joined = "\n".join(texts)
            for sentinel in sentinels:
                self.assertIn(sentinel, joined, (volume, sentinel))

    def test_prototype_does_not_duplicate_volume_one_paragraphs(self):
        prototype = self.work["routes"][0]
        prototype_text = "\n".join(t for _, t in self.by_doc.get(prototype["chapters"][0]["doc"], []))
        volume_one_text = "\n".join(t for c in self.route("第1卷")["chapters"]
                                    for _, t in self.by_doc.get(c["doc"], []))
        proto_paras = {re.sub(r"\s+", "", p) for p in prototype_text.split("\n") if len(p) >= 80}
        vol1_paras = {re.sub(r"\s+", "", p) for p in volume_one_text.split("\n") if len(p) >= 80}
        self.assertFalse(proto_paras & vol1_paras)
    def test_recovered_language_baseline_matches_new_corpus(self):
        recovered = json.loads((DATA / "zh_recovered_blocks.json").read_text(encoding="utf-8"))
        corpus = (DATA / "corpus.txt").read_text(encoding="utf-8")
        self.assertEqual(len(corpus), recovered["base_corpus_length"])
    def test_story_text_has_no_markup_or_source_links(self):
        pattern = re.compile(r"(?i)(?:https?://|www\.)|<(?:p|h[1-6]|figure|div|img)\b")
        for route in self.work["routes"]:
            for chapter in route["chapters"]:
                text = "\n".join(t for _, t in self.by_doc.get(chapter["doc"], []))
                self.assertIsNone(pattern.search(text), (route["name"], chapter["title"]))


if __name__ == "__main__":
    unittest.main()