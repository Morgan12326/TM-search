# -*- coding: utf-8 -*-
import re
import unittest

from app.official_interviews import build_answer_excerpt, extract_qa_pairs


class ExplicitQaExtractionTests(unittest.TestCase):
    def test_extracts_question_spanning_following_answer_blocks(self):
        pairs = extract_qa_pairs([
            (0, "Q：第一问？"),
            (1, "奈：第一答。\n武：补充回答。"),
            (2, "Q：第二问？\nA：第二答。"),
        ])
        self.assertEqual([0, 2], [pair["start"] for pair in pairs])
        self.assertEqual([1, 2], [pair["end"] for pair in pairs])
        self.assertEqual("第一问？", pairs[0]["q"])
        self.assertEqual("奈：第一答。\n武：补充回答。", pairs[0]["a"])
        self.assertEqual("第二问？", pairs[1]["q"])
        self.assertEqual("第二答。", pairs[1]["a"])

    def test_extracts_inline_bulleted_question_and_answer(self):
        pairs = extract_qa_pairs([
            (0, "●Q: 这是同行问题吗？ A: 这是同行回答。"),
        ])
        self.assertEqual(1, len(pairs))
        self.assertEqual("这是同行问题吗？", pairs[0]["q"])
        self.assertEqual("这是同行回答。", pairs[0]["a"])

    def test_question_stops_before_inline_answer_speaker(self):
        pairs = extract_qa_pairs([
            (0, "Q：就算失明也能看到东西吗？〈提问者〉\n奈：能感受到死。\n武：不只是眼睛而已。"),
            (1, "武：这段后续谈话不应并入回答。"),
            (2, "Q：下一个问题？\nA：下一个回答。"),
        ])
        self.assertEqual("就算失明也能看到东西吗？〈提问者〉", pairs[0]["q"])
        self.assertEqual("奈：能感受到死。\n武：不只是眼睛而已。", pairs[0]["a"])
        self.assertEqual(0, pairs[0]["end"])

    def test_question_ending_in_question_mark_accepts_unknown_speaker(self):
        pairs = extract_qa_pairs([
            (0, "Q：这个匿名回答者是谁？\n訪談員：这是回答。"),
        ])
        self.assertEqual(1, len(pairs))
        self.assertEqual("这个匿名回答者是谁？", pairs[0]["q"])
        self.assertEqual("訪談員：这是回答。", pairs[0]["a"])

    def test_markless_unknown_speaker_is_not_split(self):
        pairs = extract_qa_pairs([
            (0, "Q：这个问题没有结束标点\n未知答者：这可能是答案"),
            (1, "后续正文。"),
        ])
        self.assertEqual([], pairs)

    def test_does_not_split_unlabelled_question_answer_blocks(self):
        pairs = extract_qa_pairs([
            (0, "这是一条没有标记的问题吗？"),
            (1, "奈须蘑菇\n这是一条没有标记的回答。"),
        ])
        self.assertEqual([], pairs)

    def test_drops_empty_or_placeholder_answers(self):
        pairs = extract_qa_pairs([
            (0, "Q：只有问题？"),
            (1, "A："),
            (2, "Q："),
            (3, "A：没有有效问题。"),
        ])
        self.assertEqual([], pairs)


class AnswerExcerptTests(unittest.TestCase):
    def test_long_answer_without_answer_match_still_returns_a_bounded_opening(self):
        answer = "\n".join("第%d段。" % index + "内容" * 80 for index in range(8))
        excerpt, truncated = build_answer_excerpt(answer, re.compile("不会命中的词"))
        self.assertTrue(truncated)
        self.assertTrue(excerpt.startswith("第0段。"))
        self.assertLessEqual(len(excerpt), 422)


if __name__ == "__main__":
    unittest.main()
