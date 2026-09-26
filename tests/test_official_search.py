# -*- coding: utf-8 -*-
import json
import re
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from app import server


class OfficialStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()

    def test_official_index_contains_130_primary_interviews(self):
        self.assertEqual(130, len(self.store.official_index["primary_docs"]))

    def test_official_view_limits_preview_and_reports_total(self):
        result = self.store.official_view("Saber", offset=0, limit=5)
        self.assertLessEqual(len(result["items"]), 5)
        self.assertGreater(result["total"], 0)
        self.assertIn("counts", result)
        self.assertEqual(result["total"], result["counts"]["qa"] + result["counts"]["pointer"] + result["counts"]["supplement"])

    def test_answer_text_can_match_a_qa_card(self):
        result = self.store.official_view("炸鱼薯条", offset=0, limit=20)
        self.assertTrue(any(item["kind"] == "qa" and item["doc"] == 685 for item in result["items"]))

    def test_qa_results_precede_pointers(self):
        result = self.store.official_view("Saber", offset=0, limit=200)
        kinds = [item["kind"] for item in result["items"]]
        if "pointer" in kinds and "qa" in kinds:
            self.assertLess(max(i for i, kind in enumerate(kinds) if kind == "qa"),
                            min(i for i, kind in enumerate(kinds) if kind == "pointer"))

    def test_supplements_are_sorted_after_primary_results(self):
        result = self.store.official_view("回答", offset=0, limit=1000)
        kinds = [item["kind"] for item in result["items"]]
        if "supplement" in kinds and any(kind in ("qa", "pointer") for kind in kinds):
            self.assertGreater(min(i for i, kind in enumerate(kinds) if kind == "supplement"),
                               max(i for i, kind in enumerate(kinds) if kind in ("qa", "pointer")))

    def test_scope_filters_official_results(self):
        global_result = self.store.official_view("Saber", offset=0, limit=200)
        scoped = self.store.official_view("Saber", offset=0, limit=200, scope="FSN")
        self.assertGreaterEqual(global_result["total"], scoped["total"])
        self.assertTrue(all(item["source"]["work"] == "FSN" for item in scoped["items"]))
    def test_matched_qa_ranges_are_not_repeated_as_pointers(self):
        result = self.store.official_view("炸鱼薯条", offset=0, limit=200)
        qa_ranges = {(item["doc"], item["block"]) for item in result["items"] if item["kind"] == "qa"}
        pointer_ranges = {(item["doc"], item["block"]) for item in result["items"] if item["kind"] == "pointer"}
        self.assertFalse(qa_ranges & pointer_ranges)

    def test_qa_items_expose_compact_answer_excerpt(self):
        result = self.store.official_view("炸鱼薯条", offset=0, limit=20)
        item = next(item for item in result["items"]
                    if item["kind"] == "qa" and item["doc"] == 685)
        self.assertIn("炸鱼薯条", item["a_excerpt"])
        self.assertLessEqual(len(item["a_excerpt"]), 520)
        self.assertTrue(item["a_truncated"])
        self.assertGreater(len(item["a"]), len(item["a_excerpt"]))

    def test_doc_745_question_and_answer_boundary_is_correct(self):
        result = self.store.official_view("直死之魔眼", offset=0, limit=200)
        item = next(item for item in result["items"]
                    if item["kind"] == "qa" and item["doc"] == 745 and item["block"] == 91)
        self.assertNotIn("奈：", item["q"])
        self.assertNotIn("武：", item["q"])
        self.assertTrue(item["a"].startswith("奈："))
        self.assertNotIn("偷闻式地头发味道", item["a"])
        self.assertIn("直死之魔眼", item["q"])

    def test_official_items_open_full_document_at_target_block(self):
        result = self.store.official_view("回答", offset=0, limit=1000)
        self.assertTrue(result["items"])
        for item in result["items"]:
            self.assertIsNone(item["jump"].get("start"))
            self.assertIsNone(item["jump"].get("end"))
            self.assertGreaterEqual(item["block"], 0)
            self.assertEqual(item["jump"]["doc"], item["doc"])

    def test_official_pointer_snippet_uses_bounded_full_paragraph_context(self):
        start, length, _doc, _block = next(
            row for row in self.store.offsets
            if row[2] == 880 and row[3] == 2648)
        text = self.store.corpus[start:start + length]
        match = re.search("直死之魔眼", text)
        self.assertIsNotNone(match)
        snippet = self.store._official_snippet(text, match)
        self.assertIn("应用直死之魔眼", snippet)
        self.assertGreater(len(snippet), 300)
        self.assertLessEqual(len(snippet), 800)

    def test_short_official_snippet_threshold_keeps_twelve_characters(self):
        self.assertFalse(server.official_snippet_is_long_enough("5／ORT"))
        self.assertFalse(server.official_snippet_is_long_enough("关于Saber组"))
        self.assertTrue(server.official_snippet_is_long_enough("历史上最大规模的圣杯战争开幕"))

    def test_ort_removes_short_pointer_but_keeps_qa_and_supplement(self):
        result = self.store.official_view("ort", offset=0, limit=1000)
        kinds = [item["kind"] for item in result["items"]]
        self.assertEqual(2, result["total"])
        self.assertEqual(["qa", "supplement"], kinds)
        self.assertNotIn((731, 7), {(item["doc"], item["block"]) for item in result["items"]})
        self.assertEqual(result["total"], sum(result["counts"].values()))

    def test_saber_removes_short_heading_pointers(self):
        result = self.store.official_view("Saber", offset=0, limit=5000)
        removed = {(663, 35), (683, 22), (154, 10), (159, 2)}
        actual = {(item["doc"], item["block"]) for item in result["items"] if item["kind"] == "pointer"}
        self.assertFalse(removed & actual)
        self.assertTrue(any(item["kind"] == "qa" for item in result["items"]))


    def test_normal_search_exposes_official_preview(self):
        result = self.store.search("Saber", limit=1)
        self.assertIn("official_items", result)
        self.assertIn("official_total", result)
        self.assertIn("official_counts", result)
        self.assertLessEqual(len(result["official_items"]), 5)
        self.assertEqual(result["official_total"],
                         result["official_counts"]["qa"] + result["official_counts"]["pointer"] + result["official_counts"]["supplement"])

    def test_multi_search_exposes_official_preview(self):
        result = self.store.search_multi("Saber，士郎", limit=1)
        self.assertIn("official_items", result)
        self.assertIn("official_total", result)
        self.assertLessEqual(len(result["official_items"]), 5)

class OfficialApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.store.STORE = server.Store()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path):
        with urllib.request.urlopen(self.base + path, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_official_endpoint_paginates_typed_results(self):
        data = self.get_json("/api/official?" + urllib.parse.urlencode({"q": "Saber", "limit": 3}))
        self.assertLessEqual(len(data["items"]), 3)
        self.assertIn("counts", data)
        self.assertTrue(all(item["kind"] in ("qa", "pointer", "supplement") for item in data["items"]))

    def test_search_endpoint_exposes_official_preview(self):
        data = self.get_json("/api/search?" + urllib.parse.urlencode({"q": "炸鱼薯条"}))
        self.assertIn("official_items", data)
        self.assertLessEqual(len(data["official_items"]), 5)
        self.assertTrue(any(item["kind"] == "qa" and item["doc"] == 685 for item in data["official_items"]))

    def test_official_page_is_served(self):
        with urllib.request.urlopen(self.base + "/official.html", timeout=10) as response:
            body = response.read().decode("utf-8")
        self.assertEqual(200, response.status)
        self.assertIn("全部官方回答与访谈原文", body)
    def test_doc_endpoint_without_range_returns_full_document(self):
        data = self.get_json("/api/doc?" + urllib.parse.urlencode({
            "id": 657, "block": 118, "q": "直死之魔眼"
        }))
        self.assertEqual(118, data["target"])
        self.assertGreater(len(data["blocks"]), 1)
        self.assertTrue(any(block["o"] == 118 for block in data["blocks"]))


    def test_official_endpoint_supports_multi_term_mode(self):
        query = urllib.parse.urlencode({"q": "Saber，士郎", "multi": "1", "limit": 5})
        data = self.get_json("/api/official?" + query)
        self.assertGreater(data["total"], 0)
        self.assertLessEqual(len(data["items"]), 5)
        self.assertTrue(any(item["kind"] == "qa" for item in data["items"]))


if __name__ == "__main__":
    unittest.main()

