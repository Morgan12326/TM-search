import unittest

from app import server


class MultiTermParsingTests(unittest.TestCase):
    def test_splits_all_supported_separators_and_drops_empty_items(self):
        raw = " A ,，B;；C |｜D、E\nF,, "
        self.assertEqual(
            server.split_multi_terms(raw),
            ["A", "B", "C", "D", "E", "F"],
        )

    def test_returns_no_multi_terms_for_single_item(self):
        self.assertEqual(server.split_multi_terms("A，"), [])

    def test_combination_count_excludes_singletons_and_permutations(self):
        self.assertEqual(server.combination_membership_count(2), 1)
        self.assertEqual(server.combination_membership_count(3), 4)

    def test_shortest_span_requires_each_group(self):
        self.assertEqual(server.shortest_span([[1, 20], [5, 22], [10]]), 9)
        self.assertIsNone(server.shortest_span([[1], []]))


class MultiTermLevelTests(unittest.TestCase):
    def test_first_matching_level_stops_at_highest_non_empty_level(self):
        self.assertEqual(server.first_matching_level([0b011, 0b101, 0b001], 3), 2)
        self.assertEqual(server.first_matching_level([0b111], 3), 3)
        self.assertEqual(server.first_matching_level([], 3), 0)


class MultiTermStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()

    def test_groups_ciel_and_shirohime_synonyms(self):
        groups = self.store.multi_term_groups("ciel，白姬")
        self.assertEqual(len(groups), 2)
        first = {value.casefold() for value in groups[0]["variants"]}
        second = {value.casefold() for value in groups[1]["variants"]}
        self.assertIn("ciel", first)
        self.assertIn("希耶尔", first)
        self.assertIn("白姬", second)
        self.assertIn("爱尔奎特·布伦史塔德", second)
    def test_search_multi_returns_existing_result_sections(self):
        result = self.store.search_multi("ciel，白姬", limit=20)
        self.assertEqual(result["search_mode"], "multi_term")
        self.assertGreaterEqual(result["multi_term"]["effective_level"], 1)
        for key in ("definitions", "qa", "interviews", "occurrences"):
            self.assertIn(key, result)
        self.assertEqual(result["multi_term"]["requested_terms"], ["ciel", "白姬"])
    def test_three_term_relaxation_stops_at_two_terms(self):
        result = self.store.search_multi("Saber，士郎，绝对不存在XYZ", limit=5)
        self.assertEqual(result["multi_term"]["effective_level"], 2)
        self.assertTrue(result["multi_term"]["relaxed"])
        self.assertTrue(result["occurrences"])
        self.assertTrue(all(len(item["matched_terms"]) == 2 for item in result["occurrences"]))
    def test_multi_term_returns_passing_story_segments(self):
        result = self.store.search_multi("Saber，士郎", limit=5)
        self.assertEqual(result["multi_term"]["effective_level"], 2)
        self.assertGreater(result["total"], 0)
        self.assertGreater(len(result["occurrences"]), 0)
        self.assertEqual(result["occurrences"][0]["matched_terms"], ["Saber", "士郎"])
    def test_multi_term_relaxes_to_single_group_when_full_set_is_absent(self):
        result = self.store.search_multi("绝对不存在XYZ，白姬", limit=1)
        self.assertEqual(result["multi_term"]["effective_level"], 1)
        self.assertTrue(result["multi_term"]["relaxed"])
        self.assertIn("已放宽", result["multi_term"]["notice"])

    def test_single_term_query_keeps_existing_search_mode(self):
        result = self.store.search("圣杯战争", limit=1)
        self.assertNotEqual(result.get("search_mode"), "multi_term")
    def test_multi_definitions_and_list_views_match_existing_shapes(self):
        defs = self.store.definitions_multi("ciel，白姬", offset=0, limit=5)
        self.assertEqual(defs["q"], "ciel，白姬")
        self.assertIn("total", defs)
        self.assertIn("has_more", defs)
        self.assertLessEqual(len(defs["items"]), 5)

        listing = self.store.list_view_multi("ciel，白姬", "", offset=0, limit=3)
        self.assertIn("highlight_terms", listing)
        self.assertIn("works", listing)
        self.assertIn("items", listing)
        self.assertLessEqual(len(listing["items"]), 3)

    def test_fsn_be_cleanup_document_is_absent(self):
        found = [(i, d) for i, d in enumerate(self.store.docs)
                 if d and (d.get("title") == "FSN BE整理" or d.get("file") == "非官方整理\\FSN BE整理.txt")]
        self.assertEqual(found, [])

    def test_single_occurrences_have_navigable_locations(self):
        result = self.store.list_view("真祖", "", 0, 300, "", None)
        self.assertTrue(result["items"])
        for item in result["items"]:
            self.assertTrue(item.get("path"))
            self.assertIn(item["jump"].get("kind"), ("viewer", "official"))

    def test_multi_occurrence_fragments_have_navigable_locations(self):
        result = self.store.list_view_multi("月,姬", "", 0, 200, "")
        self.assertTrue(result["items"])
        for item in result["items"]:
            self.assertTrue(item.get("path"))
            self.assertIn(item["jump"].get("kind"), ("viewer", "official"))

    def test_all_fgo_chapters_have_section_nodes(self):
        chapters = [node for key, node in self.store.nav.items()
                    if key.startswith("work:FGO||") and node.get("kind") == "official_chapter"]
        self.assertEqual(len(chapters), 394)
        self.assertTrue(all(node.get("section_count", 0) > 0 for node in chapters))

    def test_fgo_nav_exposes_section_level(self):
        route_key = "work:FGO||route:第一部（特异点F → 终局特异点）"
        route = self.store.story_node(route_key)
        self.assertTrue(route["children"])
        chapter = route["children"][0]
        self.assertEqual(chapter.get("kind"), "official_chapter")
        self.assertGreater(chapter.get("section_count", 0), 0)
        node = self.store.story_node(chapter["key"])
        self.assertFalse(node["chapters"])
        self.assertTrue(node["children"])
        self.assertTrue(all(item.get("kind") == "official_section" for item in node["children"]))
        self.assertTrue(all("section" in item and item.get("href") for item in node["children"]))
        self.assertEqual(node["children"][0]["name"], "第1节 燃烧的城市")
        self.assertEqual(len(node["children"]), 11)
        forbidden = {"战斗的理由", "御主的条件", "焦土的记忆", "无限复活／死亡"}
        self.assertFalse(forbidden & {item["name"] for item in node["children"]})

        sections = [node for key, node in self.store.nav.items()
                    if key.startswith("work:FGO||") and node.get("kind") == "official_section"]
        self.assertEqual(len(sections), 4034)
        self.assertTrue(all(node.get("href") for node in sections))

    def test_multi_occurrences_use_normal_length_and_fragment_counts(self):
        result = self.store.list_view_multi("真祖,死徒", "", 0, 200, "")
        self.assertGreater(result["total"], 0)
        self.assertEqual(result["total"], result["all_total"])
        self.assertEqual(result["total"], result["passages"])
        self.assertGreater(result["total"], result["docs"])
        self.assertLessEqual(max((len(item["snippet"]) for item in result["items"]), default=0), 800)
        level = result["multi_term"]["effective_level"]
        for item in result["items"]:
            self.assertGreaterEqual(len(item["matched_terms"]), level)


class MultiTermMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.groups = [
            {"variants": ["Ciel", "希耶尔"]},
            {"variants": ["白姬", "爱尔奎特·布伦史塔德"]},
        ]
        cls.pattern, cls.owners = server.compile_multi_term_pattern(cls.groups)

    def match(self, text):
        return server.match_multi_term_groups(text, self.pattern, self.owners)

    def test_group_synonyms_are_or_and_groups_are_and(self):
        positions, mask = self.match("希耶尔与白姬相见")
        self.assertEqual(mask, 0b11)
        self.assertEqual(len(positions), 2)

    def test_cross_language_synonym_combination_is_allowed(self):
        positions, mask = self.match("Ciel met 爱尔奎特·布伦史塔德")
        self.assertEqual(mask, 0b11)
        self.assertEqual(len(positions), 2)

    def test_one_group_alone_does_not_satisfy_joint_match(self):
        _positions, mask = self.match("只有 Ciel 出现")
        self.assertEqual(mask, 0b01)

    def test_english_synonym_uses_word_boundaries(self):
        _positions, mask = self.match("Cielo is not Ciel")
        self.assertEqual(mask, 0b01)






