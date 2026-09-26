# -*- coding: utf-8 -*-
import json
import threading
import unittest
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

from app import server


class FgoStoryReaderRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()
        server.store.STORE = cls.store
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
            self.assertEqual(200, response.status)
            return json.loads(response.read().decode("utf-8"))

    def test_status_exposes_current_live_build(self):
        data = self.get_json("/api/status")
        self.assertEqual(server.SERVER_BUILD, data["build"])

    def test_official_story_index_is_not_overwritten_by_interview_index(self):
        self.assertIn("primary_docs", self.store.official_index)
        self.assertIn(("FGO", 100), self.store.official_story_index)

        chapter = self.store.official_chapter("FGO", 100)
        self.assertIsNotNone(chapter)
        self.assertEqual("特异点F 燃烧污染都市 冬木", chapter["title"])
        self.assertEqual(11, len(chapter["chapters"]))
        self.assertEqual(1028, chapter["lines"])
        self.assertIn("啾……啾……", chapter["chapters"][0]["lines"][0]["t"])

    def test_story_route_chapter_cards_keep_official_metadata(self):
        root = self.store.story_node("work:FGO")
        self.assertEqual(6, len(root["children"]))

        route = self.store.story_node(root["children"][0]["key"])
        self.assertTrue(route["children"])
        first = route["children"][0]
        self.assertEqual("FGO", first["official"])
        self.assertEqual(100, first["id"])
        self.assertEqual(11, first["section_count"])

    def test_both_official_reader_endpoints_return_fgo_text(self):
        official = self.get_json(
            "/api/official/chapter?" + urllib.parse.urlencode({"work": "FGO", "id": 100})
        )
        legacy = self.get_json("/api/fgo/chapter?" + urllib.parse.urlencode({"id": 100}))

        for chapter in (official, legacy):
            self.assertEqual("特异点F 燃烧污染都市 冬木", chapter["title"])
            self.assertEqual(11, len(chapter["chapters"]))
            self.assertIn("啾……啾……", chapter["chapters"][0]["lines"][0]["t"])

    def test_occurrence_official_jump_resolves_to_target_fgo_section(self):
        data = self.get_json(
            "/api/search?" + urllib.parse.urlencode({"q": "啾……啾……", "limit": 50})
        )
        occurrence = next(
            item for item in data["occurrences"]
            if item.get("jump") == {
                "kind": "official", "work": "FGO", "id": 100, "section": 0,
            }
        )
        self.assertEqual("FGO", occurrence["source"]["work"])

        target = self.get_json(
            "/api/official/chapter?" + urllib.parse.urlencode({"work": "FGO", "id": 100})
        )
        section = target["chapters"][occurrence["jump"]["section"]]
        self.assertIn("啾……啾……", "\n".join(line["t"] for line in section["lines"]))


if __name__ == "__main__":
    unittest.main()
