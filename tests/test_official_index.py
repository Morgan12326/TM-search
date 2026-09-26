# -*- coding: utf-8 -*-
import json
import unittest
from pathlib import Path

from app.official_interviews import build_official_index


def fixture():
    docs = [
        {"id": 1, "title": "访谈A", "work": "FZ", "kind": "访谈",
         "file": "设定本 访谈\\访谈\\FZ\\访谈A.txt"},
        {"id": 2, "title": "访谈B", "work": "FSN", "kind": "访谈",
         "file": "设定本 访谈\\访谈\\FSN\\访谈B.txt"},
        {"id": 3, "title": "剧情章节", "work": "FGO", "kind": "原作",
         "file": "原作文本\\FGO\\剧情.txt"},
        {"id": 9, "title": "补充问答", "work": "FSN", "kind": "问答",
         "file": "设定本 访谈\\FSN\\补充问答.txt"},
    ]
    story = {"works": [
        {"work": "FGO", "routes": [{"name": "主线", "chapters": [
            {"doc": 3, "title": "剧情章节", "start": 0, "end": None},
        ]}]},
        {"work": "访谈", "routes": [
            {"name": "FZ", "chapters": [
                {"doc": 1, "title": "访谈A", "start": 0, "end": None},
            ]},
            {"name": "FSN", "chapters": [
                {"doc": 2, "title": "访谈B", "start": 0, "end": None},
            ]},
        ]},
    ]}
    blocks = [
        [1, 0, "Q：主库问题？\nA：主库回答。"],
        [1, 1, "这是没有问答标记的访谈正文。"],
        [2, 0, "普通访谈正文。"],
        [3, 0, "这是剧情正文，不属于访谈索引。"],
    ]
    qa = [
        {"doc": 1, "q": "主库问题？", "a": "主库回答。"},
        {"doc": 2, "q": "只有标题", "a": ""},
        {"doc": 9, "q": "补充问题？", "a": "补充回答。"},
    ]
    return docs, story, blocks, qa


class OfficialIndexBuildTests(unittest.TestCase):
    def test_index_contains_every_primary_story_document(self):
        index = build_official_index(*fixture())
        self.assertEqual([1, 2], [item["doc"] for item in index["primary_docs"]])

    def test_non_interview_story_work_is_excluded(self):
        index = build_official_index(*fixture())
        self.assertNotIn(3, [item["doc"] for item in index["primary_docs"]])

    def test_primary_qa_is_cleaned_and_deduplicated(self):
        index = build_official_index(*fixture())
        primary = index["qa"]
        self.assertEqual(1, len(primary))
        self.assertEqual(1, primary[0]["doc"])
        self.assertEqual("主库问题？", primary[0]["q"])
        self.assertEqual("主库回答。", primary[0]["a"])

    def test_non_story_source_is_kept_only_as_supplement(self):
        index = build_official_index(*fixture())
        self.assertEqual([9], [item["doc"] for item in index["supplements"]])
        self.assertEqual("补充问题？", index["supplements"][0]["q"])
        self.assertNotIn(9, [item["doc"] for item in index["qa"]])

    def test_same_question_prefers_one_complete_extracted_card(self):
        docs, story, blocks, qa = fixture()
        qa.append({"doc": 1, "q": "主库问题？补充追问", "a": "短答。"})
        index = build_official_index(docs, story, blocks, qa)
        same_question = [item for item in index["qa"] if item["q"] == "主库问题？"]
        self.assertEqual(1, len(same_question))
        self.assertEqual("extracted", same_question[0]["source_kind"])
        self.assertIn("主库回答。", same_question[0]["a"])

    def test_legacy_qa_is_dropped_when_question_and_answer_are_far_apart(self):
        docs, story, blocks, qa = fixture()
        blocks = [
            [1, 0, "主库问题？"],
            [1, 1, "无关正文。"],
            [1, 2, "更多无关正文。"],
            [1, 3, "另一段回答。"],
        ]
        index = build_official_index(docs, story, blocks, [{
            "doc": 1, "q": "主库问题？", "a": "另一段回答。"
        }])
        self.assertEqual([], index["qa"])

    def test_extracted_questions_with_same_prefix_are_merged(self):
        docs, story, _blocks, _qa = fixture()
        blocks = [
            [1, 0, "Q：同一问题？\nA：完整回答。"],
            [1, 1, "Q：同一问题？补充追问\nA：短答。"],
        ]
        index = build_official_index(docs, story, blocks, [])
        same = [item for item in index["qa"] if item["q"].startswith("同一问题？")]
        self.assertEqual(1, len(same))
        self.assertIn("完整回答", same[0]["a"])


class OfficialInterviewDataRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "data" / "official_interviews.json"
        cls.data = json.loads(path.read_text(encoding="utf-8"))

    def test_doc_745_direct_answer_is_not_inside_question(self):
        item = next(i for i in self.data["qa"]
                    if i["doc"] == 745 and i["start"] == 91)
        self.assertNotIn("奈：", item["q"])
        self.assertNotIn("武：", item["q"])
        self.assertTrue(item["a"].startswith("奈："))
        self.assertIn("应该说是能感受到死吧", item["a"])
        self.assertNotIn("偷闻式地头发味道", item["a"])


if __name__ == "__main__":
    unittest.main()
