# -*- coding: utf-8 -*-
import unittest

from app import server


class RankingStore(server.Store):
    """复用 Store 的卡片方法，但不加载完整语料。"""

    def __init__(self, works):
        self.docs = {
            doc_id: {
                "id": doc_id,
                "title": "测试资料 %d" % doc_id,
                "work": work,
                "kind": "用语辞典",
                "file": "test-%d.txt" % doc_id,
            }
            for doc_id, work in works.items()
        }


def entry(doc_id, body, *, group="term:测试词条", translation_group=None,
          is_primary=False, is_meaning_primary=False, quality=0):
    translation_group = translation_group or ("translation:%d" % doc_id)
    return {
        "term": "测试词条",
        "display_term": "测试词条",
        "cat": "概念",
        "body": body,
        "doc": doc_id,
        "lang": "zh",
        "source_unit_id": "source:%d" % doc_id,
        "concept_id": group,
        "group_id": group,
        "translation_group_id": translation_group,
        "variant_id": "variant:%d" % doc_id,
        "authority": "official_source",
        "translation_kind": "direct",
        "is_primary": is_primary,
        "is_meaning_primary": is_meaning_primary,
        "definition_quality": quality,
        "source_refs": [],
        "conflict_flags": [],
    }


class DefinitionRankingTests(unittest.TestCase):
    def cards(self, entries, works):
        store = RankingStore(works)
        return store._group_entry_cards(entries, "exact")

    def test_covering_definition_becomes_primary(self):
        short = "这是测试词条的基础定义。它说明了起源、核心原理以及使用限制，并记录了最后的注意事项、使用条件和结果。"
        long = short + "补充资料进一步说明历史演变、例外条件、实例细节和不同作品中的差异，并补充常见误区、相关概念与具体案例。"
        cards = self.cards(
            [entry(1, short, is_primary=True), entry(2, long)],
            {1: "月姬", 2: "月姬"},
        )

        self.assertEqual(1, len(cards))
        self.assertEqual(long, cards[0]["body"])
        self.assertEqual(0, cards[0]["same_concept_count"])
        self.assertEqual([], cards[0]["same_concept"])

    def test_normal_version_becomes_primary_without_coverage(self):
        cards = self.cards(
            [
                entry(1, "正常版本只说明杯战的基本目的、参加者和胜负条件。", is_primary=True),
                entry(2, "特殊版本围绕月之圣杯展开电子空间中的淘汰机制，并讨论不同从者阵营的选择。"),
            ],
            {1: "FSN", 2: "FE"},
        )

        self.assertEqual("FSN", cards[0]["source"]["work"])
        self.assertEqual("FE", cards[0]["same_concept"][0]["source"]["work"])

    def test_normal_version_beats_covering_special_version(self):
        normal = "这是圣杯战争的基础定义。它说明了目的、参加者、规则和最终奖励，并记录常见例外、使用条件与结果。"
        special = normal + "特殊版本继续说明电子空间中的淘汰过程、不同阵营、隐藏规则以及多种结局条件。"
        cards = self.cards(
            [entry(1, normal, is_primary=True), entry(2, special)],
            {1: "FSN", 2: "FE"},
        )

        self.assertEqual("FSN", cards[0]["source"]["work"])
        self.assertEqual("FE", cards[0]["same_concept"][0]["source"]["work"])

    def test_normal_versions_follow_fsn_fz_fa_fsf(self):
        cards = self.cards(
            [
                entry(1, "FSN：说明圣杯战争的参加规则。"),
                entry(2, "FZ：记录第四次杯战的经过。"),
                entry(3, "FA：描述另一场大规模杯战。"),
                entry(4, "FSF：记录雪原市的特殊杯战。"),
            ],
            {1: "FSN", 2: "FZ", 3: "FA", 4: "FSF"},
        )

        self.assertEqual(
            ["FSN", "FZ", "FA", "FSF"],
            [cards[0]["source"]["work"]] + [card["source"]["work"] for card in cards[0]["same_concept"]],
        )

    def test_special_versions_precede_normal_versions_in_same_concept(self):
        cards = self.cards(
            [
                entry(1, "正常杯战说明从者、御主与圣杯之间的关系。", is_primary=True),
                entry(2, "FE：电子空间中的特殊杯战。"),
                entry(3, "FEX：月之圣杯后的特殊战争。"),
                entry(4, "FEXL：月之圣杯相关的新冲突。"),
            ],
            {1: "FSN", 2: "FE_CCC", 3: "FEX", 4: "FEXL"},
        )

        self.assertEqual("FSN", cards[0]["source"]["work"])
        self.assertEqual(
            ["FE_CCC", "FEX", "FEXL"],
            [card["source"]["work"] for card in cards[0]["same_concept"]],
        )

    def test_unknown_works_keep_existing_primary(self):
        cards = self.cards(
            [
                entry(1, "第一条资料说明魔术协会的历史与职责。", is_primary=False),
                entry(2, "第二条资料记录封印指定的执行过程与相关案例。", is_primary=True),
            ],
            {1: "其他", 2: "其他"},
        )

        self.assertIn("封印指定", cards[0]["body"])

    def test_near_identical_definitions_are_merged(self):
        first = "这是同一个词条的定义，它说明了起源、发展和结果，并补充相关人物与事件。"
        second = "这是同一个词条的定义， 它说明了起源、发展和结果，并补充相关人物与事件！"
        cards = self.cards([entry(1, first), entry(2, second)], {1: "月姬", 2: "月姬"})

        self.assertEqual(1, len(cards))
        self.assertEqual(0, cards[0]["same_concept_count"])

    def test_duplicate_prefers_normal_version(self):
        body = "这是同一个词条完全相同的定义，包含起源、机制、限制以及补充说明。"
        cards = self.cards(
            [entry(1, body, is_primary=True), entry(2, body)],
            {1: "FSN", 2: "FE"},
        )

        self.assertEqual(1, len(cards))
        self.assertEqual("FSN", cards[0]["source"]["work"])

    def test_similar_text_slightly_above_seventy_percent_is_merged(self):
        first = "甲" * 50 + "乙" * 20
        second = "甲" * 50 + "丙" * 20
        cards = self.cards([entry(1, first), entry(2, second)], {1: "月姬", 2: "月姬"})

        self.assertEqual(1, len(cards))
        self.assertEqual(0, cards[0]["same_concept_count"])

    def test_similar_text_below_seventy_percent_is_not_merged(self):
        first = "甲" * 45 + "乙" * 20
        second = "甲" * 45 + "丙" * 20
        cards = self.cards([entry(1, first), entry(2, second)], {1: "月姬", 2: "月姬"})

        self.assertEqual(1, len(cards))
        self.assertEqual(1, cards[0]["same_concept_count"])


class DefinitionRankingDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = server.Store()

    def test_fixed_field_prefers_comprehensive_readbook(self):
        cards, _canonical = self.store.ordered_definitions("固有结界")
        self.assertIn("月姬读本Plus Period", cards[0]["source"]["title"])
        visible_ids = [cards[0]["source"]["id"]] + [
            card["source"]["id"] for card in cards[0]["same_concept"]
        ]
        self.assertNotIn(718, visible_ids)

    def test_holy_grail_prefers_fsn_and_keeps_only_one_fsm_card(self):
        cards, _canonical = self.store.ordered_definitions("圣杯")
        primary = cards[0]
        visible_ids = [primary["source"]["id"]] + [
            card["source"]["id"] for card in primary["same_concept"]
        ]

        self.assertEqual(662, primary["source"]["id"])
        self.assertEqual("FSN", primary["source"]["work"])
        self.assertEqual(1, visible_ids.count(662))
        self.assertEqual("FE", primary["same_concept"][0]["source"]["work"])

    def test_forced_primary_cards_are_first(self):
        marple_cards, _canonical = self.store.ordered_definitions("空想具现化")
        self.assertEqual(825, marple_cards[0]["source"]["id"])

        short_query_cards, _canonical = self.store.ordered_definitions("直死之魔眼")
        self.assertEqual(828, short_query_cards[0]["source"]["id"])
        self.assertEqual("直死之魔眼", short_query_cards[0]["term"])

        exact_cards, _canonical = self.store.ordered_definitions("直死的魔眼")
        self.assertEqual(828, exact_cards[0]["source"]["id"])
    def test_short_name_contains_card_precedes_body_mentions(self):
        cards, _canonical = self.store.ordered_definitions("士郎")
        self.assertEqual("卫宫士郎", cards[0]["term"])
        self.assertEqual("contains", cards[0]["match"])
        body_positions = [index for index, card in enumerate(cards)
                          if card.get("match") == "body"]
        contains_positions = [index for index, card in enumerate(cards)
                              if card.get("match") == "contains"]
        self.assertTrue(contains_positions)
        self.assertTrue(body_positions)
        self.assertLess(max(contains_positions), min(body_positions))

    def test_common_short_names_keep_contains_bucket_before_body(self):
        for query in ("樱", "凛", "言峰"):
            cards, _canonical = self.store.ordered_definitions(query)
            body_positions = [index for index, card in enumerate(cards)
                              if card.get("match") == "body"]
            contains_positions = [index for index, card in enumerate(cards)
                                  if card.get("match") == "contains"]
            if contains_positions and body_positions:
                self.assertLess(max(contains_positions), min(body_positions), query)


    def test_old_design_cards_have_visible_prefix(self):
        cards, _canonical = self.store.ordered_definitions("死徒二十七祖")
        visible = [cards[0]] + list(cards[0].get("same_concept") or [])
        by_doc = {card["source"]["id"]: card for card in visible}

        self.assertTrue(by_doc[729]["body"].startswith("【旧设】"))
        self.assertTrue(by_doc[818]["body"].startswith("【旧设】"))

    def test_ruby_definition_typo_is_corrected(self):
        cards, _canonical = self.store.ordered_definitions("红宝石之星/蓝宝石之星")
        card = next(card for card in cards if card["source"]["id"] == 641)
        self.assertIn("红宝石自己", card["body"])
        self.assertNotIn("红白事", card["body"])

    def test_wiki_leaf_applies_old_design_prefix(self):
        view = self.store.wiki_leaf(self.store.leaf_of(828), 0, 500)
        item = next(item for item in view["items"] if item["term"] == "死徒二十七祖")
        self.assertEqual(828, item["source"]["id"])
        self.assertTrue(item["def"].startswith("【旧设】"))

    def test_grail_war_keeps_normal_primary_and_special_same_first(self):
        cards, _canonical = self.store.ordered_definitions("圣杯战争")
        self.assertEqual("FSN", cards[0]["source"]["work"])
        self.assertEqual("FE", cards[0]["same_concept"][0]["source"]["work"])

    def test_noble_phantasm_keeps_normal_primary_and_special_same_first(self):
        cards, _canonical = self.store.ordered_definitions("宝具")
        self.assertEqual("FSN", cards[0]["source"]["work"])
        self.assertEqual("FE", cards[0]["same_concept"][0]["source"]["work"])


if __name__ == "__main__":
    unittest.main()

