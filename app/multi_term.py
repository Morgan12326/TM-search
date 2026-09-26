import bisect
# -*- coding: utf-8 -*-
"""Explicit multi-term AND search with progressive subset relaxation."""

import heapq
import re
from collections import defaultdict


MULTI_TERM_SPLIT_RE = re.compile(r"[,，;；|｜、\r\n]+")
OCC_PUNCT = "·・‧．."
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff66-\uff9f]")


def split_multi_terms(q):
    parts = [part.strip() for part in MULTI_TERM_SPLIT_RE.split(q or "")]
    parts = [part for part in parts if part]
    return parts if len(parts) >= 2 else []


def combination_membership_count(k):
    if k < 2:
        return 0
    return (1 << k) - 1 - k


def shortest_span(position_groups):
    groups = []
    for values in position_groups or []:
        values = sorted({int(value) for value in values})
        if not values:
            return None
        groups.append(values)
    if not groups:
        return None
    if len(groups) == 1:
        return 0
    heap = []
    current_max = -1
    for group_id, values in enumerate(groups):
        current_max = max(current_max, values[0])
        heapq.heappush(heap, (values[0], group_id, 0))
    best = None
    while heap:
        low, group_id, index = heapq.heappop(heap)
        span = current_max - low
        best = span if best is None else min(best, span)
        next_index = index + 1
        if next_index >= len(groups[group_id]):
            break
        next_pos = groups[group_id][next_index]
        current_max = max(current_max, next_pos)
        heapq.heappush(heap, (next_pos, group_id, next_index))
    return best


def first_matching_level(masks, max_level):
    for level in range(max_level, 0, -1):
        if any(int(mask).bit_count() >= level for mask in masks):
            return level
    return 0


class MultiTermEngine:
    """Store-aware engine kept outside server.py to keep the HTTP service thin."""

    def __init__(self, store, card_total_max, work_rank, occurrence_term_pattern):
        self.store = store
        self.card_total_max = card_total_max
        self.work_rank = work_rank
        self.occurrence_term_pattern = occurrence_term_pattern

    def _compile_pattern(self, groups):
        alternatives, owners = [], {}
        for group_id, group in enumerate(groups or []):
            variants = sorted(
                {str(value or "").strip() for value in (group.get("variants") or [])
                 if str(value or "").strip()},
                key=lambda value: (-len(value), value.casefold()),
            )
            for variant in variants:
                alternatives.append(self.occurrence_term_pattern(variant))
                normalized = re.sub(r"[·・‧．.\s]+", "", variant).casefold()
                owners.setdefault(normalized, set()).add(group_id)
        if not alternatives:
            return re.compile(r"(?!x)x"), owners
        return re.compile("|".join("(?:%s)" % value for value in alternatives), re.I), owners

    def _match(self, text, pattern, owners):
        positions = defaultdict(set)
        for match in pattern.finditer(text or ""):
            normalized = re.sub(r"[·・‧．.\s]+", "", match.group(0)).casefold()
            for group_id in owners.get(normalized, ()):
                positions[group_id].add(match.start())
        mask = 0
        for group_id in positions:
            mask |= 1 << group_id
        return {group_id: sorted(values) for group_id, values in positions.items()}, mask

    def _labels(self, unit, groups):
        return [groups[index]["input"] for index in range(len(groups))
                if unit["mask"] & (1 << index)]

    def _make_unit(self, kind, item, text, order, pattern, owners, group_count):
        positions, mask = self._match(text, pattern, owners)
        if not mask:
            return None
        span = shortest_span([positions[index] for index in range(group_count)
                              if positions.get(index)])
        return {"kind": kind, "item": item, "positions": positions,
                "mask": mask, "span": span, "order": order}

    def _expand_occurrence(self, unit, groups, level):
        """把一个段落命中拆成若干正常长度、且满足有效层级的片段。"""
        store = self.store
        item = unit["item"]
        doc_id, block, segment = item["doc"], item["block"], item["seg"]
        positions = unit["positions"]
        terms = [group["input"] for group in groups]
        out = []
        seen_windows = set()
        seen_texts = set()
        anchor_sets = [values[:20] for values in positions.values()]
        anchors = []
        for index in range(20):
            for values in anchor_sets:
                if index < len(values):
                    anchors.append(values[index])
        for anchor in anchors[:40]:
                s, e = store.snippet_window(anchor, "", terms=terms)
                inside = {}
                for group_id, group_positions in positions.items():
                    present = group_positions[bisect.bisect_left(group_positions, s):bisect.bisect_right(group_positions, e - 1)]
                    if present:
                        inside[group_id] = sorted(present)
                if len(inside) < level:
                    continue
                snippet = store.snippet_text(s, e, doc_id)
                window_key = (doc_id, block, s, e)
                text_key = (doc_id, block, re.sub(r"\s+", "", snippet))
                if window_key in seen_windows or text_key in seen_texts:
                    continue
                seen_windows.add(window_key)
                seen_texts.add(text_key)
                mask = 0
                for group_id in inside:
                    mask |= 1 << group_id
                span = shortest_span([inside[index] for index in range(len(groups))
                                      if inside.get(index)])
                out.append({
                    "kind": "occurrence",
                    "item": {"pos": min(pos for vals in inside.values() for pos in vals),
                             "seg": segment, "doc": doc_id, "block": block, "work": item["work"]},
                    "positions": inside,
                    "mask": mask,
                    "span": span,
                    "order": min(pos for vals in inside.values() for pos in vals),
                    "snippet": snippet,
                    "snippet_start": s,
                    "snippet_end": e,
                })
        if not out and positions:
            centers = [vals[0] for vals in positions.values() if vals]
            mid = (min(centers) + max(centers)) // 2
            s = max(0, mid - 200)
            e = min(len(store.corpus), mid + 200)
            snippet = store.snippet_text(s, e, doc_id)
            out.append({
                "kind": "occurrence",
                "item": {"pos": min(centers), "seg": segment, "doc": doc_id, "block": block, "work": item["work"]},
                "positions": positions,
                "mask": unit["mask"],
                "span": shortest_span([positions[index] for index in range(len(groups)) if positions.get(index)]),
                "order": min(centers),
                "snippet": snippet,
                "snippet_start": s,
                "snippet_end": e,
            })
        return out

    def analysis(self, q, scope=""):
        store = self.store
        cache_key = (q or "", scope or "")
        cached = store._multi_cache.get(cache_key)
        if cached is not None:
            return cached
        groups = store.multi_term_groups(q)
        if not groups:
            result = {"groups": [], "level": 0, "definitions": [],
                      "interviews": [], "qa": [], "occurrences": []}
            store._multi_cache = {cache_key: result}
            return result

        pattern, owners = self._compile_pattern(groups)
        group_count = len(groups)
        allow = store.scope_set(scope)
        definitions, interviews, qa = [], [], []

        for order, entry in enumerate(store.entries):
            if allow is not None and entry["doc"] not in allow:
                continue
            text = "\n".join(str(entry.get(key) or "") for key in
                             ("term", "source_term", "display_term", "body"))
            unit = self._make_unit("definition", entry, text, order,
                                   pattern, owners, group_count)
            if unit:
                definitions.append(unit)

        for order, item in enumerate(store.interviews):
            if allow is not None and item["doc"] not in allow:
                continue
            text = "\n".join([str(item.get("term") or ""), str(item.get("body") or "")])
            unit = self._make_unit("interview", item, text, order,
                                   pattern, owners, group_count)
            if unit:
                interviews.append(unit)

        for order, item in enumerate(store.qa):
            if allow is not None and item["doc"] not in allow:
                continue
            text = "\n".join([str(item.get("q") or ""), str(item.get("a") or "")])
            unit = self._make_unit("qa", item, text, order,
                                   pattern, owners, group_count)
            if unit:
                qa.append(unit)

        segment_occurrences = []
        segment_hits = {}
        for match in pattern.finditer(store.corpus):
            normalized = re.sub(r"[·・‧．.\s]+", "", match.group(0)).casefold()
            group_ids = owners.get(normalized, ())
            if not group_ids:
                continue
            segment = store.seg_of(match.start())
            if segment < 0:
                continue
            doc_id = store.offsets[segment][2]
            if allow is not None and doc_id not in allow:
                continue
            for group_id in group_ids:
                segment_hits.setdefault(segment, {}).setdefault(group_id, set()).add(match.start())

        for segment, by_group in segment_hits.items():
            positions = {group_id: sorted(values) for group_id, values in by_group.items()}
            mask = 0
            for group_id in positions:
                mask |= 1 << group_id
            _start, _length, doc_id, block = store.offsets[segment]
            segment_occurrences.append({
                "kind": "occurrence",
                "item": {"pos": min(values[0] for values in positions.values()),
                         "seg": segment, "doc": doc_id, "block": block,
                         "work": store.docs[doc_id]["work"]},
                "positions": positions,
                "mask": mask,
                "span": shortest_span([positions[index] for index in range(group_count)
                                       if positions.get(index)]),
                "order": segment,
            })

        all_units = definitions + interviews + qa + segment_occurrences
        level = first_matching_level([unit["mask"] for unit in all_units], group_count)
        if not level:
            result = {"groups": groups, "level": 0, "definitions": [],
                      "interviews": [], "qa": [], "occurrences": []}
        else:
            occurrences = []
            candidates = [unit for unit in segment_occurrences if unit["mask"].bit_count() >= level]
            for unit in candidates[:200]:
                occurrences.extend(self._expand_occurrence(unit, groups, level))
            result = {
                "groups": groups,
                "level": level,
                "definitions": [unit for unit in definitions if unit["mask"].bit_count() >= level],
                "interviews": [unit for unit in interviews if unit["mask"].bit_count() >= level],
                "qa": [unit for unit in qa if unit["mask"].bit_count() >= level],
                "occurrences": occurrences,
            }
        store._multi_cache = {cache_key: result}
        return result

    def _definition_cards(self, analysis, groups):
        store = self.store
        units = sorted(
            analysis["definitions"],
            key=lambda unit: (unit["span"], store._entry_rank(unit["item"]), unit["order"]),
        )
        matched_by_gid = {}
        for unit in units:
            entry = unit["item"]
            gid = entry.get("group_id") or entry.get("concept_id") or ("term:" + entry["term"])
            indexes = matched_by_gid.setdefault(gid, set())
            indexes.update(index for index in range(len(groups))
                           if unit["mask"] & (1 << index))
        cards = store._group_entry_cards([unit["item"] for unit in units], "multi")
        for card in cards:
            gid = card.get("group_id") or card.get("concept_id") or ("term:" + card.get("term", ""))
            card["matched_terms"] = [groups[index]["input"]
                                     for index in sorted(matched_by_gid.get(gid, set()))]
        return cards

    def _multi_occ(self, unit, groups):
        store = self.store
        item = unit["item"]
        labels = self._labels(unit, groups)
        base = store._occ(item, "", terms=labels)
        snippet = unit.get("snippet") or base["snippet"]
        base.update({
            "snippet": snippet,
            "paragraph": snippet,
            "span": unit["span"],
            "matched_terms": labels,
        })
        return base

    def search(self, q, limit=60, scope="", analysis=None):
        store = self.store
        requested = (q or "").strip()
        analysis = analysis or self.analysis(requested, scope)
        groups = analysis["groups"]
        level = analysis["level"]
        highlight_terms, seen = [], set()
        for group in groups:
            for value in group["variants"]:
                key = value.casefold()
                if key not in seen:
                    seen.add(key)
                    highlight_terms.append(value)

        notice = ""
        if not groups:
            notice = "没有找到可联合检索的词条组。"
        elif not level:
            notice = "没有找到任意两个词条同时出现的语料。"
        elif level < len(groups):
            notice = ("未找到同时包含全部 %d 个词条的语料，已放宽为任意 %d 个词条组共同出现。"
                      % (len(groups), level))

        result = {
            "q": requested,
            "requested_q": requested,
            "scope": scope,
            "scope_name": store.scope_name(scope),
            "alias": None,
            "alias_note": None,
            "normalization": [],
            "highlight_terms": highlight_terms,
            "match_mode": "multi_term",
            "search_mode": "multi_term",
            "scoped": bool(scope),
            "definitions": [],
            "interviews": [],
            "qa": [],
            "official_items": [],
            "official_total": 0,
            "official_counts": {"qa": 0, "pointer": 0, "supplement": 0},
            "official_has_more": False,
            "related": [],
            "classifications": [],
            "occurrences": [],
            "total": 0,
            "by_work": [],
            "by_work_segs": {},
            "by_work_docs": {},
            "docs": 0,
            "truncated": False,
            "defs_total": 0,
            "multi_term": {
                "requested_terms": [group["input"] for group in groups],
                "effective_level": level,
                "relaxed": bool(groups and level < len(groups)),
                "notice": notice,
            },
        }
        if not groups or not level:
            return result

        store._attach_official_preview(result, requested, scope, multi=True)
        cards = self._definition_cards(analysis, groups)
        result["defs_total"] = len(cards)
        result["definitions"] = cards[:self.card_total_max]

        interview_units = sorted(
            analysis["interviews"],
            key=lambda unit: (unit["span"], unit["item"]["doc"], unit["order"]),
        )
        for unit in interview_units[:8]:
            item = unit["item"]
            result["interviews"].append({
                "term": item.get("term") or "",
                "entry_type": item.get("entry_type") or "interview",
                "body": item.get("body") or "",
                "jp_body": item.get("jp_body"),
                "source": store.source(item["doc"]),
                "source_locator": item.get("source_locator") or {},
                "source_refs": item.get("source_refs") or [],
                "span": unit["span"],
                "matched_terms": self._labels(unit, groups),
            })

        qa_units = sorted(
            analysis["qa"],
            key=lambda unit: (unit["span"], unit["item"]["doc"], unit["order"]),
        )
        for unit in qa_units[:8]:
            item = unit["item"]
            result["qa"].append({
                "q": item["q"],
                "a": item["a"],
                "truncated": item.get("truncated", False),
                "source": store.source(item["doc"]),
                "span": unit["span"],
                "matched_terms": self._labels(unit, groups),
            })

        occurrence_units = sorted(
            analysis["occurrences"],
            key=lambda unit: (unit["span"], self.work_rank(unit["item"]["work"]),
                              unit["item"]["doc"], unit["item"]["block"], unit.get("order", 0)),
        )
        work_hits, work_docs = {}, {}
        for unit in occurrence_units:
            work = unit["item"]["work"]
            work_hits[work] = work_hits.get(work, 0) + 1
            work_docs.setdefault(work, set()).add(unit["item"]["doc"])
        result["total"] = len(occurrence_units)
        result["raw_total"] = len(occurrence_units)
        result["docs"] = len({unit["item"]["doc"] for unit in occurrence_units})
        result["by_work"] = sorted(work_hits.items(), key=lambda pair: self.work_rank(pair[0]))
        result["by_work_segs"] = dict(work_hits)
        result["by_work_docs"] = {work: len(values) for work, values in work_docs.items()}
        result["truncated"] = len(occurrence_units) > limit
        result["occurrences"] = [
            self._multi_occ(unit, groups) for unit in occurrence_units[:limit]
        ]
        return result

    def definitions_view(self, q, scope="", offset=0, limit=20):
        store = self.store
        analysis = self.analysis(q, scope)
        groups = analysis["groups"]
        cards = self._definition_cards(analysis, groups) if analysis["level"] else []
        highlight_terms, seen = [], set()
        for group in groups:
            for value in group["variants"]:
                key = value.casefold()
                if key not in seen:
                    seen.add(key)
                    highlight_terms.append(value)
        notice = ""
        if groups and not analysis["level"]:
            notice = "没有找到任意两个词条同时出现的语料。"
        elif groups and analysis["level"] < len(groups):
            notice = ("未找到同时包含全部 %d 个词条的语料，已放宽为任意 %d 个词条组共同出现。"
                      % (len(groups), analysis["level"]))
        offset = max(int(offset), 0)
        limit = max(min(int(limit), 100), 1)
        return {
            "q": q,
            "scope": scope,
            "scope_name": store.scope_name(scope),
            "search_mode": "multi_term",
            "highlight_terms": highlight_terms,
            "total": len(cards),
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < len(cards),
            "items": cards[offset:offset + limit],
            "multi_term": {
                "requested_terms": [group["input"] for group in groups],
                "effective_level": analysis["level"],
                "relaxed": bool(groups and analysis["level"] < len(groups)),
                "notice": notice,
            },
        }

    def list_view(self, q, work="", offset=0, limit=50, scope=""):
        store = self.store
        analysis = self.analysis(q, scope)
        groups = analysis["groups"]
        units = sorted(
            analysis["occurrences"] if analysis["level"] else [],
            key=lambda unit: (unit["span"], self.work_rank(unit["item"]["work"]),
                              unit["item"]["doc"], unit["item"]["block"], unit.get("order", 0)),
        )
        scoped = units
        items = [unit for unit in scoped if unit["item"]["work"] == work] if work else scoped
        offset = max(int(offset), 0)
        limit = max(min(int(limit), 200), 1)
        page = items[offset:offset + limit]
        work_hits, work_docs = {}, {}
        for unit in scoped:
            item = unit["item"]
            work_hits[item["work"]] = work_hits.get(item["work"], 0) + 1
            work_docs.setdefault(item["work"], set()).add(item["doc"])
        highlight_terms, seen = [], set()
        for group in groups:
            for value in group["variants"]:
                key = value.casefold()
                if key not in seen:
                    seen.add(key)
                    highlight_terms.append(value)
        current_docs = len({unit["item"]["doc"] for unit in items})
        notice = ""
        if groups and not analysis["level"]:
            notice = "没有找到任意两个词条同时出现的语料。"
        elif groups and analysis["level"] < len(groups):
            notice = ("未找到同时包含全部 %d 个词条的语料，已放宽为任意 %d 个词条组共同出现。"
                      % (len(groups), analysis["level"]))
        return {
            "q": q,
            "requested_q": q,
            "work": work,
            "offset": offset,
            "scope": scope,
            "scope_name": store.scope_name(scope),
            "search_mode": "multi_term",
            "highlight_terms": highlight_terms,
            "total": len(items),
            "all_total": len(scoped),
            "passages": len(items),
            "docs": current_docs,
            "truncated": False,
            "works": [[name, work_hits[name], work_hits[name], len(work_docs[name])]
                      for name in sorted(work_hits, key=self.work_rank)],
            "items": [
                dict(self._multi_occ(unit, groups), n=unit["mask"].bit_count())
                for unit in page
            ],
            "has_more": offset + limit < len(items),
            "multi_term": {
                "requested_terms": [group["input"] for group in groups],
                "effective_level": analysis["level"],
                "relaxed": bool(groups and analysis["level"] < len(groups)),
                "notice": notice,
            },
        }
