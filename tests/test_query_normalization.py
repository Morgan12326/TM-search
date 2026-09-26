# -*- coding: utf-8 -*-
import unittest

from app.core import normalize_query
from app.store import Store


class QueryNormalizationUnitTests(unittest.TestCase):
    def test_compound_title_is_not_rewritten_from_alias_substring(self):
        self.assertEqual(
            ("黄金公主·白银公主", []),
            normalize_query("黄金公主·白银公主"),
        )

    def test_whole_query_alias_is_still_rewritten(self):
        self.assertEqual(
            ("爱尔奎特·布伦史塔德", ["公主→爱尔奎特·布伦史塔德"]),
            normalize_query("公主"),
        )

    def test_terms_containing_alias_substrings_are_preserved(self):
        cases = (
            ("吉尔·德·莱斯", "吉尔·德·莱斯"),
            ("七夜的短刀", "七夜的短刀"),
            ("Archer（弓兵）", "Archer(弓兵)"),
            ("光之高扬斯卡娅", "光之高扬斯卡娅"),
        )
        for query, expected in cases:
            with self.subTest(query=query):
                self.assertEqual((expected, []), normalize_query(query))


class QueryNormalizationDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = Store()

    def test_compound_title_search_uses_exact_definition_and_occurrences(self):
        query = "黄金公主·白银公主"
        result = self.store.search(query, limit=10)

        self.assertEqual(query, result["q"])
        self.assertEqual([], result["normalization"])
        self.assertEqual(1, result["total"])
        self.assertTrue(result["definitions"])
        self.assertEqual(query, result["definitions"][0]["term"])
        self.assertEqual("exact", result["definitions"][0]["match"])
        self.assertNotIn("爱尔奎特", result["definitions"][0]["term"])

    def test_explicit_multi_term_aliases_are_resolved_per_full_fragment(self):
        groups = self.store.multi_term_groups("黄金公主·白银公主，公主")
        self.assertEqual(2, len(groups))
        self.assertEqual("黄金公主·白银公主", groups[0]["canonical"])
        self.assertEqual("爱尔奎特·布伦史塔德", groups[1]["canonical"])


if __name__ == "__main__":
    unittest.main()