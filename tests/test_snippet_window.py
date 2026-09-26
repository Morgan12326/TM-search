# -*- coding: utf-8 -*-
import unittest

from app import server


def assert_boundary(test, text, index):
    test.assertTrue(index == 0 or index == len(text) or text[index - 1] in "\n\r。！？!?…，；：,;:",
                    (index, text[max(0, index - 20):index + 20]))

    def test_short_paragraph_accepts_single_newline_gap(self):
        first = "命中" + "短" * 158
        second = "邻" * 100
        text = first + "\n" + second
        start, end = server.select_block_snippet_span(
            text, [(0, len(first)), (len(first) + 1, len(text))], 2, 4)
        self.assertEqual((0, len(text)), (start, end))

    def test_short_paragraph_accepts_small_whitespace_gap(self):
        first = "命中" + "短" * 158
        second = "邻" * 100
        text = first + " \n " + second
        start, end = server.select_block_snippet_span(
            text, [(0, len(first)), (len(first) + 3, len(text))], 2, 4)
        self.assertEqual((0, len(text)), (start, end))

    def test_non_whitespace_gap_is_not_crossed(self):
        first = "命中" + "短" * 158
        gap = "不属于相邻段的内容"
        second = "邻" * 100
        text = first + gap + second
        start, end = server.select_block_snippet_span(
            text, [(0, len(first)), (len(first) + len(gap), len(text))], 2, 4)
        self.assertEqual((0, len(first)), (start, end))


class SnippetSpanUnitTests(unittest.TestCase):
    def test_short_sentences_are_expanded_without_cutting_a_sentence(self):
        match = "命中词" + "甲" * 40 + "。"
        previous = "前" * 180 + "。"
        following = "后" * 180 + "。"
        text = previous + match + following
        pos = text.index("命中词")
        start, end = server.select_snippet_span(text, pos, pos + 3)
        self.assertEqual(match + following, text[start:end])
        assert_boundary(self, text, start)
        assert_boundary(self, text, end)

    def test_many_short_sentences_stay_within_target_length(self):
        sentences = ["第%02d句%s。" % (index, "内容" * 20) for index in range(12)]
        text = "".join(sentences)
        pos = text.index("第06句")
        start, end = server.select_snippet_span(text, pos, pos + 4)
        snippet = text[start:end]
        self.assertIn("第06句", snippet)
        self.assertLessEqual(len(snippet), 360)
        assert_boundary(self, text, start)
        assert_boundary(self, text, end)

    def test_single_sentence_between_target_and_hard_limit_is_kept_whole(self):
        sentence = "命" + "乙" * 499 + "。"
        text = "前文。" + sentence + "后文。"
        pos = text.index("命")
        start, end = server.select_snippet_span(text, pos, pos + 1)
        self.assertEqual(sentence, text[start:end])
        self.assertGreater(len(text[start:end]), 360)
        self.assertLessEqual(len(text[start:end]), 600)

    def test_oversized_sentence_falls_back_to_clause_boundaries(self):
        clause = "段" * 100 + "，"
        text = clause * 9 + "命中词" + "尾" * 80 + "。"
        pos = text.index("命中词")
        start, end = server.select_snippet_span(text, pos, pos + 3)
        snippet = text[start:end]
        self.assertIn("命中词", snippet)
        self.assertLessEqual(len(snippet), 600)
        assert_boundary(self, text, start)
        assert_boundary(self, text, end)

    def test_unpunctuated_sentence_uses_hard_limit(self):
        text = "甲" * 450 + "命中词" + "乙" * 450
        pos = text.index("命中词")
        start, end = server.select_snippet_span(text, pos, pos + 3)
        snippet = text[start:end]
        self.assertIn("命中词", snippet)
        self.assertLessEqual(len(snippet), 600)

class ParagraphSnippetSpanTests(unittest.TestCase):
    def test_medium_paragraph_is_returned_whole(self):
        text = "命中" + "甲" * 298
        start, end = server.select_block_snippet_span(
            text, [(0, len(text))], 2, 4)
        self.assertEqual((0, len(text)), (start, end))

    def test_long_but_allowed_paragraph_is_returned_whole(self):
        text = "命中" + "乙" * 699
        start, end = server.select_block_snippet_span(
            text, [(0, len(text))], 2, 4)
        self.assertEqual((0, len(text)), (start, end))

    def test_short_paragraph_adds_adjacent_complete_paragraph(self):
        first = "命中" + "短" * 158
        second = "邻" * 100
        text = first + second
        start, end = server.select_block_snippet_span(
            text, [(0, len(first)), (len(first), len(text))], 2, 4)
        self.assertEqual((0, len(text)), (start, end))

    def test_adjacent_paragraph_is_skipped_if_it_exceeds_target(self):
        first = "命中" + "短" * 158
        second = "邻" * 600
        text = first + second
        start, end = server.select_block_snippet_span(
            text, [(0, len(first)), (len(first), len(text))], 2, 4)
        self.assertEqual((0, len(first)), (start, end))

    def test_oversized_paragraph_returns_multiple_complete_sentences(self):
        sentences = ["第%02d句%s。" % (index, "内容" * 35) for index in range(12)]
        text = "".join(sentences)
        pos = text.index("第06句")
        start, end = server.select_block_snippet_span(
            text, [(0, len(text))], pos, pos + 4)
        snippet = text[start:end]
        self.assertIn("第06句", snippet)
        self.assertLessEqual(len(snippet), 800)
        self.assertGreater(len(snippet), 360)
        self.assertGreaterEqual(snippet.count("。"), 3)



class StoreSnippetRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()

    def test_screenshot_fgo_blocks_include_adjacent_context(self):
        cases = [
            (912, 8586, "魔眼所视之物", "无论对手"),
            (1056, 182, "我以前听说过", "魔眼的位阶"),
            (1056, 703, "你还打算用那把小刀", "我觉得那种东西"),
        ]
        data = self.store.scan("直死之魔眼")
        by_block = {(item["doc"], item["block"]): item for item in data["items"]}
        for doc, block, before, after in cases:
            item = by_block[(doc, block)]
            snippet = self.store.snippet(item["pos"], "直死之魔眼", terms=["直死之魔眼"])
            self.assertIn(before, snippet, (doc, block))
            self.assertIn(after, snippet, (doc, block))
            self.assertGreater(len(snippet), 80, (doc, block))

    def test_representative_queries_keep_bounded_complete_boundaries(self):
        for query in ("直死之魔眼", "Saber", "魔术"):
            data = self.store.scan(query)
            for item in data["items"][:20]:
                start, end = self.store.snippet_window(
                    item["pos"], query, terms=[query])
                snippet = self.store.corpus[start:end]
                if snippet:
                    self.assertLessEqual(len(snippet), 800, query)
                if start > 0:
                    self.assertIn(self.store.corpus[start - 1],
                                  "\n\r。！？!?…」』”\"）)》〉】，；：,;:")
                if end < len(self.store.corpus) and end > start:
                    if self.store.corpus[end] not in "\n\r":
                        self.assertIn(self.store.corpus[end - 1],
                                      "\n\r。！？!?…」』”\"）)》〉】，；：,;:")


if __name__ == "__main__":
    unittest.main()
