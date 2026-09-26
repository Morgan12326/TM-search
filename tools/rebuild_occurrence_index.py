# -*- coding: utf-8 -*-
"""Rebuild and verify the occurrence index used by the search UI."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    from .rebuild_source_data import (
        _language_profile,
        read_source_text,
        resolve_source_path,
        sanitize_source_text,
        split_source_blocks,
    )
except ImportError:  # Direct execution: python tools/rebuild_occurrence_index.py
    from rebuild_source_data import (
        _language_profile,
        read_source_text,
        resolve_source_path,
        sanitize_source_text,
        split_source_blocks,
    )

KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
HTML_LINK_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>")
MD_LINK_RE = re.compile(r"\[([^\]]{0,240})\]\((?:(?:https?://|www\.)[^)]+)\)", re.I)
URL_RE = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"“”]+")
SCRIPT_MARK_RE = re.compile(r"(?m)^\s*(?:\*define|numalias\b|mov\s+\$msgline|textgosub\b)")
NOISE_LINE_RE = re.compile(
    r"^\s*(?:出处|来源|原文|网址|链接|译者|翻译|录入|校对|扫图|修图|发布|资源|原帖|转载|作者)\s*[:：]"
)
CONTROL_LINE_RE = re.compile(
    r"^\s*(?:[-=*#_;・·—]{4,}|(?:goto|return|if|mov|numalias|effect|textgosub|ruby|select|"
    r"clickstr|menusetwindow|menuselectcolor|savenumber|savename)\b)",
    re.I,
)
SCRIPT_STRING_RE = re.compile(r'"([^"\n]+)"')
CHINESE_SIGNALS = frozenset(
    "的是了这這为為而就都也我你他她它们們说說到有在把被与與和跟对對从從将將能会會不没沒有么麼嗎呢吧啊"
)
CHINESE_PUNCT = ("，", "；", "：", "。", "！", "？")

WORK_SHORT = {
    "Fate/stay night": "FSN",
    "Fate/hollow ataraxia": "FHA",
    "Fate/Grand Order": "FGO",
    "Fate/Zero": "FZ",
    "Fate/Apocrypha": "FA",
    "Fate/EXTRA 系列": "FE",
    "Fate/EXTELLA": "FEX",
    "Fate/EXTELLA LINK": "FEXL",
    "Fate/strange fake": "FSF",
    "Fate/Samurai Remnant": "FSR",
    "Fate/Prototype 系列": "FP",
    "Fate/kaleid liner・Koha Ace": "FKL",
    "月姬R（蓝月之玻）": "月姬R",
    "其他": "未归类资料",
}
LABEL_SHORT = {
    "序章（共通）": "序章",
    "Saber线（Fate）": "Saber线",
    "远坂凛线（UBW）": "UBW线",
    "间桐樱线（Heaven's Feel）": "HF线",
    "主线：复仇者与巴泽特": "主线",
    "第一部（特异点F → 终局特异点）": "第一部",
    "1.5 亚种特异点": "1.5部",
    "第二部（Lostbelt）": "第二部",
    "奏章（Ordeal Call）": "奏章",
    "活动剧情（按实装年份）": "活动",
    "幕间物语（按职阶）": "幕间",
}
DATA_FILES = (
    "entries.json", "story.json", "corpus.txt", "offsets.json",
    "story_blocks.json", "jp_blocks.json", "zh_recovered_blocks.json",
    "occurrence_locations.json", "occurrence_exclusions.json",
    "occurrence_source_manifest.json",
)


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload, pretty=False):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    temp.replace(path)


def _normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"[\s　]+", "", value).casefold()


def normalize_for_match(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"[\s\u3000]+", "", text)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_label(value: str) -> str:
    value = str(value or "").strip()
    return LABEL_SHORT.get(value, WORK_SHORT.get(value, value))


def _script_dialogue(raw: str) -> str:
    out = []
    for match in SCRIPT_STRING_RE.finditer(raw):
        value = match.group(1).replace("_", "").strip()
        if not value or re.search(r"(?i)\.(?:png|jpg|jpeg|bmp|wav|ogg|mp3|cur|txt)$", value):
            continue
        out.append(value)
    return "\n".join(out)


def clean_occurrence_text(text: str) -> str:
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if SCRIPT_MARK_RE.search(text):
        text = _script_dialogue(text)
    else:
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = HTML_LINK_RE.sub(r"\1", text)
        text = MD_LINK_RE.sub(r"\1", text)
        text = HTML_TAG_RE.sub("", text)
        text = URL_RE.sub("", text)
    text = text.replace("\ufeff", "").replace("\u200b", "")
    text = "".join(ch for ch in text if ch == "\n" or ord(ch) >= 32)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\u3000]+", " ", line).strip()
        if not line or NOISE_LINE_RE.search(line) or CONTROL_LINE_RE.search(line):
            continue
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _line_language(line: str):
    kana = len(KANA_RE.findall(line))
    han = len(HAN_RE.findall(line))
    if not kana and not han and not re.search(r"[A-Za-z0-9]", line):
        return None
    if kana:
        ratio = kana / float(max(1, kana + han))
        if ratio >= 0.18:
            return "ja"
    if han:
        return "zh"
    return "neutral"


def split_visible_and_japanese(text: str):
    cleaned = clean_occurrence_text(text)
    if not cleaned:
        return "", ""
    visible, japanese = [], []
    current = None
    for line in cleaned.splitlines():
        lang = _line_language(line)
        if lang in (None, "neutral"):
            lang = current or "zh"
        current = lang
        (japanese if lang == "ja" else visible).append(line)
    return "\n".join(visible).strip(), "\n".join(japanese).strip()

def build_story_locations(story: dict, block_orders):
    locations = {}
    for work in story.get("works", []):
        work_name = work.get("work") or ""
        groups = []
        if work.get("root_chapters"):
            groups.append({"name": work_name, "chapters": work.get("root_chapters", [])})
        groups.extend(work.get("routes", []))
        for route in groups:
            route_name = route.get("name") or ""
            for chapter in route.get("chapters") or []:
                doc_id = int(chapter["doc"])
                start = int(chapter.get("start") or 0)
                end = chapter.get("end")
                end = int(end) if end is not None else None
                path = [short_label(work_name)]
                route_label = short_label(route_name)
                if route_label and route_label != path[-1]:
                    path.append(route_label)
                group = short_label(chapter.get("group") or "")
                if group and group not in path:
                    path.append(group)
                title = str(chapter.get("title") or "").strip()
                if title and title not in path:
                    path.append(title)
                jump = {
                    "kind": "viewer", "doc": doc_id, "start": start,
                    "end": end, "chapter": chapter.get("key"),
                }
                for order in block_orders.get(doc_id, []):
                    if order < start or (end is not None and order >= end):
                        continue
                    locations.setdefault((doc_id, order), {"path": path, "jump": jump})
    return locations


def build_official_chapter(part: dict, chapter: dict, doc_id: int):
    work = "月姬R" if str(part.get("part", "")).startswith("月姬R") else "FGO"
    rows, locations = [], []
    order = 0
    for section_index, section in enumerate(chapter.get("chapters") or []):
        for line in section.get("lines") or []:
            text = clean_occurrence_text(line.get("t") or "")
            if not text:
                continue
            rows.append((order, text))
            path = [short_label(work)]
            part_label = short_label(part.get("part") or "")
            if part_label and part_label not in path:
                path.append(part_label)
            group = short_label(chapter.get("group") or "")
            if group and group not in path:
                path.append(group)
            title = str(chapter.get("title") or "").strip()
            if title and title not in path:
                path.append(title)
            section_title = str(section.get("title") or "").strip()
            if section_title and section_title not in path:
                path.append(section_title)
            locations.append({
                "path": path,
                "jump": {"kind": "official", "work": work, "id": int(chapter["war_id"]),
                         "section": section_index},
            })
            order += 1
    return rows, locations


def _first_int_prefix(path_value: str):
    match = re.search(r"(?:^|[\\/])(\d+)_", str(path_value or ""))
    return int(match.group(1)) if match else None


def _official_authority(entries, fgo_story, tsukihime_story):
    fgo_parts = []
    for part in fgo_story:
        for chapter in part.get("chapters", []):
            fgo_parts.append((part, chapter))
    fgo_by_war = {int(chapter["war_id"]): (part, chapter) for part, chapter in fgo_parts}
    fgo_candidates = defaultdict(list)
    tsuk_by_title = {}
    for part in tsukihime_story:
        for chapter in part.get("chapters", []):
            tsuk_by_title[(part.get("part"), _normalize_key(chapter.get("title")))] = (part, chapter)
            tsuk_by_title[_normalize_key(chapter.get("title"))] = (part, chapter)

    for doc in entries["docs"]:
        if not doc.get("official"):
            continue
        doc_id = int(doc["id"])
        work = doc.get("work")
        if work == "FGO":
            prefix = _first_int_prefix(doc.get("file"))
            target = 401 if prefix == 400 else prefix
            if target in fgo_by_war:
                fgo_candidates[target].append((doc_id, doc, prefix))
        elif work == "月姬R":
            part_name = (doc.get("meta") or {}).get("分部")
            found = tsuk_by_title.get((part_name, _normalize_key(doc.get("title")))) or \
                tsuk_by_title.get(_normalize_key(doc.get("title")))
            if found:
                key = ("tsuki", int(found[1]["war_id"]))
                fgo_candidates[key].append((doc_id, doc, None))

    selected, excluded = {}, []
    for target, candidates in fgo_candidates.items():
        if isinstance(target, tuple):
            part, chapter = tsuk_by_title.get(
                ((candidates[0][1].get("meta") or {}).get("分部"), _normalize_key(candidates[0][1].get("title")))
            ) or tsuk_by_title.get(_normalize_key(candidates[0][1].get("title")))
        else:
            part, chapter = fgo_by_war[target]
            exact = [candidate for candidate in candidates if candidate[2] == target]
            chosen = exact[0] if exact else sorted(candidates, key=lambda item: item[0])[0]
            for candidate in candidates:
                if candidate[0] != chosen[0]:
                    excluded.append({
                        "doc": candidate[0], "title": candidate[1].get("title"),
                        "reason": "duplicate_official_chapter",
                        "canonical_docs": [chosen[0]],
                        "evidence": {"war_id": target, "duplicate_prefix": candidate[2]},
                    })
            selected[chosen[0]] = (part, chapter)
            continue
        chosen = sorted(candidates, key=lambda item: item[0])[0]
        for candidate in candidates:
            if candidate[0] != chosen[0]:
                excluded.append({
                    "doc": candidate[0], "title": candidate[1].get("title"),
                    "reason": "duplicate_official_chapter",
                    "canonical_docs": [chosen[0]], "evidence": {"war_id": chapter["war_id"]},
                })
        selected[chosen[0]] = (part, chapter)
    return selected, excluded

def _doc_definitions(entries, doc_id):
    rows = []
    for order, entry in enumerate(entries.get("entries", [])):
        if entry.get("doc") != doc_id:
            continue
        body = clean_occurrence_text(entry.get("body") or "")
        if body:
            rows.append((order, body))
    return rows


def _known_merge_exclusion(doc, source_text, story):
    title = str(doc.get("title") or "")
    file_name = str(doc.get("file") or "")
    if "合并文本" not in title and "合并文本" not in file_name:
        return None
    work = doc.get("work")
    route_fragment = ""
    if work == "月姬" and "歌月十夜" in (title + file_name):
        route_fragment = "歌月十夜"
    elif work == "FSN" and "UBW" in (title + file_name).upper():
        route_fragment = "远坂凛线（UBW）"
    elif work == "FSN" and "HF" in (title + file_name).upper():
        route_fragment = "间桐樱线（Heaven's Feel）"
    elif work == "FSN" and "fate" in file_name.casefold():
        route_fragment = "Saber线（Fate）"
    elif work == "FHA":
        route_fragment = "主线"
    if not route_fragment:
        return None
    canonical = []
    for item in story.get("works", []):
        if item.get("work") != work:
            continue
        for route in item.get("routes", []):
            if route_fragment in route.get("name", ""):
                canonical.extend(int(chapter["doc"]) for chapter in route.get("chapters", []))
    if not canonical:
        return None
    is_script = bool(SCRIPT_MARK_RE.search(source_text or ""))
    return {
        "doc": int(doc["id"]), "title": title,
        "reason": "raw_merged_script" if is_script else "verified_merged_text",
        "canonical_docs": canonical,
        "evidence": {"work": work, "route": route_fragment,
                     "canonical_chapters": len(canonical), "source_is_script": is_script},
    }


def merge_source_modes(existing, current):
    modes = dict(existing or {})
    modes.update(current or {})
    return modes


def merge_exclusions(preferred, existing):
    merged = []
    seen = set()
    for item in list(preferred or []) + list(existing or []):
        doc_id = int(item.get("doc", -1))
        if doc_id in seen:
            continue
        seen.add(doc_id)
        merged.append(item)
    return merged


def source_mode_for_doc(manifest, doc_id, doc):
    modes = (manifest or {}).get("modes") or {}
    mode = modes.get(str(doc_id))
    if mode:
        return mode
    return "official" if doc.get("official") else None


def build_bundle(data_dir: Path, source_roots, legacy_data_dir: Path):
    del legacy_data_dir
    entries = _load_json(data_dir / "entries.json")
    story = _load_json(data_dir / "story.json")
    old_offsets = _load_json(data_dir / "offsets.json")
    old_story_rows = _load_json(data_dir / "story_blocks.json")
    old_corpus = (data_dir / "corpus.txt").read_text(encoding="utf-8")
    fgo_story = _load_json(data_dir / "fgo_story.json")
    tsukihime_story = _load_json(data_dir / "tsukihime_r.json")
    source_manifest_path = data_dir / "occurrence_source_manifest.json"
    source_manifest = _load_json(source_manifest_path) if source_manifest_path.exists() else {"version": 1, "modes": {}}
    docs_by_id = {int(doc["id"]): doc for doc in entries["docs"]}
    corpus_doc_ids = {int(row[2]) for row in old_offsets}
    old_story = defaultdict(dict)
    for doc_id, order, text in old_story_rows:
        old_story[int(doc_id)][int(order)] = text

    official_selected, discovered_excluded = _official_authority(entries, fgo_story, tsukihime_story)
    exclusion_path = data_dir / "occurrence_exclusions.json"
    existing_excluded = _load_json(exclusion_path).get("items", []) if exclusion_path.exists() else []
    excluded = merge_exclusions(discovered_excluded, existing_excluded)
    excluded_ids = {int(item["doc"]) for item in excluded}
    visible, japanese, locations = defaultdict(list), defaultdict(list), {}
    source_modes = defaultdict(Counter)

    for doc_id in sorted(corpus_doc_ids):
        doc = docs_by_id.get(doc_id)
        if doc is None or doc_id in excluded_ids:
            continue
        if doc_id in official_selected:
            part, chapter = official_selected[doc_id]
            rows, row_locations = build_official_chapter(part, chapter, doc_id)
            for index, (order, text) in enumerate(rows):
                visible[doc_id].append((order, text))
                locations[(doc_id, order)] = row_locations[index]
            source_modes[doc_id]["official"] += 1
            continue

        source_text, source_path = "", resolve_source_path(doc.get("file", ""), source_roots)
        if source_path is not None:
            source_text = sanitize_source_text(read_source_text(source_path))
            merge_exclusion = _known_merge_exclusion(doc, source_text, story)
            if merge_exclusion and doc_id not in excluded_ids:
                excluded.append(merge_exclusion)
                excluded_ids.add(doc_id)
                continue

        mode = source_mode_for_doc(source_manifest, doc_id, doc)
        if mode == "definitions":
            definition_rows = _doc_definitions(entries, doc_id)
            if definition_rows:
                visible[doc_id].extend(definition_rows)
                source_modes[doc_id]["definitions"] += 1
                continue
        elif mode == "legacy_slice":
            rows = sorted((int(row[3]), int(row[1]), int(row[0])) for row in old_offsets
                          if int(row[2]) == doc_id)
            for order, length, start in rows:
                text = clean_occurrence_text(old_corpus[start:start + length])
                if text:
                    visible[doc_id].append((order, text))
            source_modes[doc_id]["legacy_slice"] += 1
            continue
        elif mode == "source_file" or (mode is None and source_text and doc_id not in old_story):
            if source_text:
                for order, block in enumerate(split_source_blocks(source_text)):
                    visible_text, jp_text = split_visible_and_japanese(block.text)
                    if visible_text:
                        visible[doc_id].append((order, visible_text))
                    if jp_text:
                        japanese[doc_id].append((order, jp_text))
                source_modes[doc_id]["source_file"] += 1
                continue

        if mode == "story_overlay" or (mode is None and doc_id in old_story):
            for order, text in sorted(old_story.get(doc_id, {}).items()):
                visible_text, jp_text = split_visible_and_japanese(text)
                if visible_text:
                    visible[doc_id].append((order, visible_text))
                if jp_text:
                    japanese[doc_id].append((order, jp_text))
            if visible.get(doc_id) or japanese.get(doc_id):
                source_modes[doc_id]["story_overlay"] += 1
                continue

        if source_text:
            for order, block in enumerate(split_source_blocks(source_text)):
                visible_text, jp_text = split_visible_and_japanese(block.text)
                if visible_text:
                    visible[doc_id].append((order, visible_text))
                if jp_text:
                    japanese[doc_id].append((order, jp_text))
            source_modes[doc_id]["source_file"] += 1
            continue

        definition_rows = _doc_definitions(entries, doc_id)
        if definition_rows:
            visible[doc_id].extend(definition_rows)
            source_modes[doc_id]["definitions"] += 1
            continue

        rows = sorted((int(row[3]), int(row[1]), int(row[0])) for row in old_offsets if int(row[2]) == doc_id)
        for order, length, start in rows:
            text = clean_occurrence_text(old_corpus[start:start + length])
            if text:
                visible[doc_id].append((order, text))
        source_modes[doc_id]["legacy_slice"] += 1
    story_ids = set()
    for work in story.get("works", []):
        story_ids.update(int(c["doc"]) for c in work.get("root_chapters", []))
        for route in work.get("routes", []):
            story_ids.update(int(c["doc"]) for c in route.get("chapters", []))

    hashes = defaultdict(list)
    for doc_id, rows in visible.items():
        flattened = normalize_for_match("\n".join(text for _, text in sorted(rows)))
        if flattened:
            hashes[_sha256_text(flattened)].append(doc_id)
    for digest, ids in hashes.items():
        if len(ids) < 2:
            continue
        story_matches = [doc_id for doc_id in ids if doc_id in story_ids]
        keep = story_matches[0] if story_matches else min(ids)
        for doc_id in ids:
            if doc_id == keep or (story_matches and doc_id in story_matches):
                continue
            excluded.append({
                "doc": doc_id, "title": docs_by_id[doc_id].get("title"),
                "reason": "exact_duplicate_text", "canonical_docs": [keep],
                "evidence": {"sha256": digest},
            })
            excluded_ids.add(doc_id)
            visible.pop(doc_id, None)
            japanese.pop(doc_id, None)

    visible_orders = {doc_id: sorted(order for order, _ in rows) for doc_id, rows in visible.items()}
    story_locations = build_story_locations(story, visible_orders)
    for key, location in story_locations.items():
        locations.setdefault(key, location)

    for doc_id, rows in visible.items():
        doc = docs_by_id[doc_id]
        fallback = {
            "path": [short_label(doc.get("work") or ""), str(doc.get("title") or "")],
            "jump": {"kind": "viewer", "doc": doc_id, "start": None, "end": None, "chapter": None},
        }
        for order, _text in rows:
            locations.setdefault((doc_id, order), fallback)

    location_rows = []
    for doc_id in sorted(visible):
        ordered = sorted(visible[doc_id])
        start_index = 0
        while start_index < len(ordered):
            order, _text = ordered[start_index]
            location = locations[(doc_id, order)]
            path, jump = list(location["path"]), dict(location["jump"])
            end_index = start_index + 1
            while end_index < len(ordered):
                next_order, _next_text = ordered[end_index]
                next_location = locations[(doc_id, next_order)]
                if next_order != ordered[end_index - 1][0] + 1 or next_location["path"] != path or next_location["jump"] != jump:
                    break
                end_index += 1
            location_rows.append({
                "doc": doc_id, "start": order, "end": ordered[end_index - 1][0] + 1,
                "path": path, "jump": jump,
            })
            start_index = end_index

    story_rows, jp_rows = [], []
    for doc in entries["docs"]:
        doc_id = int(doc["id"])
        for order, text in sorted(visible.get(doc_id, [])):
            story_rows.append([doc_id, order, text])
        for order, text in sorted(japanese.get(doc_id, [])):
            jp_rows.append([doc_id, order, text])
        if doc_id in corpus_doc_ids:
            doc["chars"] = sum(len(text) for _, text in visible.get(doc_id, [])) + sum(
                len(text) for _, text in japanese.get(doc_id, [])
            )
            doc.update(_language_profile(
                [text for _, text in visible.get(doc_id, [])] +
                [text for _, text in japanese.get(doc_id, [])]
            ))

    stats = {
        "corpus_docs": len(corpus_doc_ids), "visible_docs": len(visible),
        "visible_blocks": len(story_rows), "japanese_docs": len(japanese),
        "japanese_blocks": len(jp_rows), "official_docs": len(official_selected),
        "story_docs": len(story_ids & set(visible)),
        "fallback_docs": sum(1 for mode in source_modes.values() if "legacy_slice" in mode),
        "excluded_docs": len(excluded),
    }
    return {
        "version": 1, "entries": entries, "story": story, "story_rows": story_rows,
        "jp_rows": jp_rows, "locations": location_rows, "excluded": excluded,
        "stats": stats, "source_modes": source_modes,
    }

def write_bundle(data_dir: Path, bundle):
    backup_dir = data_dir.parent / "temp" / ("occurrence-sync-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name in DATA_FILES:
        source = data_dir / name
        if source.exists():
            shutil.copy2(source, backup_dir / name)

    story_rows, jp_rows = bundle["story_rows"], bundle["jp_rows"]
    ordered = []
    for doc in bundle["entries"]["docs"]:
        doc_id = int(doc["id"])
        for row in story_rows:
            if int(row[0]) == doc_id:
                ordered.append((doc_id, int(row[1]), row[2]))
    ordered.sort(key=lambda item: (item[0], item[1]))
    corpus = "\n".join(text for _, _, text in ordered)
    offsets, cursor = [], 0
    for doc_id, order, text in ordered:
        offsets.append([cursor, len(text), doc_id, order])
        cursor += len(text) + 1

    try:
        _write_json(data_dir / "entries.json", bundle["entries"])
        _write_json(data_dir / "story_blocks.json", story_rows)
        _write_json(data_dir / "jp_blocks.json", jp_rows)
        (data_dir / "corpus.txt.tmp").write_text(corpus, encoding="utf-8", newline="\n")
        (data_dir / "corpus.txt.tmp").replace(data_dir / "corpus.txt")
        _write_json(data_dir / "offsets.json", offsets)
        _write_json(data_dir / "occurrence_locations.json", bundle["locations"], pretty=True)
        _write_json(data_dir / "occurrence_exclusions.json", {"version": 1, "items": bundle["excluded"]}, pretty=True)
        current_modes = {str(doc_id): next(iter(counter))
                         for doc_id, counter in bundle.get("source_modes", {}).items()}
        manifest_path = data_dir / "occurrence_source_manifest.json"
        old_manifest = _load_json(manifest_path) if manifest_path.exists() else {"modes": {}}
        manifest_modes = merge_source_modes(old_manifest.get("modes"), current_modes)
        _write_json(manifest_path, {"version": 1, "modes": manifest_modes}, pretty=True)
        _write_json(data_dir / "zh_recovered_blocks.json",
                    {"version": 1, "base_corpus_length": len(corpus), "blocks": []}, pretty=True)
        check_data(data_dir)
    except Exception:
        for name in DATA_FILES:
            source = backup_dir / name
            if source.exists():
                shutil.copy2(source, data_dir / name)
        raise
    return backup_dir


def _location_index(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row["doc"])].append(row)
    by_doc = {}
    for doc_id, values in grouped.items():
        values.sort(key=lambda item: int(item["start"]))
        by_doc[doc_id] = {
            "starts": [int(row["start"]) for row in values],
            "rows": values,
        }
    return by_doc


def _find_location(by_doc, doc_id, order):
    group = by_doc.get(int(doc_id))
    if not group:
        return None
    starts, rows = group["starts"], group["rows"]
    index = bisect.bisect_right(starts, int(order)) - 1
    if index < 0:
        return None
    row = rows[index]
    return row if int(row["start"]) <= int(order) < int(row["end"]) else None


def _contains_link_or_control(text: str):
    return bool(URL_RE.search(text) or HTML_TAG_RE.search(text) or MD_LINK_RE.search(text) or CONTROL_LINE_RE.search(text))


def _strong_chinese_like(text: str):
    kana, han = len(KANA_RE.findall(text)), len(HAN_RE.findall(text))
    if han < 4:
        return False
    ratio = kana / float(max(1, kana + han))
    signals = sum(1 for char in text if char in CHINESE_SIGNALS)
    punct = any(char in text for char in CHINESE_PUNCT)
    return ratio <= 0.08 and (signals >= 2 or (signals >= 1 and punct))


def missing_official_chapters(all_ids, active_ids, excluded):
    covered = set(int(value) for value in active_ids)
    for item in excluded:
        if item.get("reason") == "duplicate_official_chapter":
            war_id = (item.get("evidence") or {}).get("war_id")
            if war_id is not None:
                covered.add(int(war_id))
    return set(int(value) for value in all_ids) - covered


def check_data(data_dir: Path):
    entries = _load_json(data_dir / "entries.json")
    corpus = (data_dir / "corpus.txt").read_text(encoding="utf-8")
    offsets = _load_json(data_dir / "offsets.json")
    blocks = _load_json(data_dir / "story_blocks.json")
    jp_blocks = _load_json(data_dir / "jp_blocks.json")
    locations = _load_json(data_dir / "occurrence_locations.json")
    excluded = _load_json(data_dir / "occurrence_exclusions.json")["items"]
    docs = {int(doc["id"]): doc for doc in entries["docs"]}
    excluded_ids = {int(item["doc"]) for item in excluded}

    assert len(blocks) == len(offsets), "story_blocks and offsets differ"
    for row, offset in zip(blocks, offsets):
        doc_id, order, text = int(row[0]), int(row[1]), row[2]
        start, length, off_doc, off_order = offset
        assert doc_id == int(off_doc) and order == int(off_order), "offset identity mismatch"
        assert corpus[start:start + length] == text, "corpus and story block mismatch"
        assert not _contains_link_or_control(text), (doc_id, order, text[:120])

    for doc_id, _order, text in jp_blocks:
        assert not _strong_chinese_like(text), (doc_id, text[:120])
        assert not URL_RE.search(text), (doc_id, text[:120])

    assert not (set(int(row[2]) for row in offsets) & excluded_ids), "excluded document remains searchable"
    by_doc = _location_index(locations)
    for doc_id, order, _text in blocks:
        record = _find_location(by_doc, doc_id, order)
        assert record, (doc_id, order)
        assert record["path"] and isinstance(record["jump"], dict), (doc_id, order)

    fgo_chapters = set()
    for part in _load_json(data_dir / "fgo_story.json"):
        for chapter in part.get("chapters", []):
            fgo_chapters.add(int(chapter["war_id"]))
    official_ids = set()
    for record in locations:
        jump = record["jump"]
        if jump.get("kind") == "official" and jump.get("work") == "FGO":
            official_ids.add(int(jump["id"]))
    official_exclusions = []
    for item in excluded:
        item = dict(item)
        evidence = dict(item.get("evidence") or {})
        doc = docs.get(int(item.get("doc", -1)))
        if doc and doc.get("official") and doc.get("work") == "FGO":
            war_id = _first_int_prefix(doc.get("file"))
            if war_id == 400:
                war_id = 401
            if war_id is not None:
                evidence.setdefault("war_id", war_id)
                item["reason"] = "duplicate_official_chapter"
        item["evidence"] = evidence
        official_exclusions.append(item)
    missing = missing_official_chapters(fgo_chapters, official_ids, official_exclusions)
    assert not missing, "missing official FGO chapters: %s" % sorted(missing)[:10]
    return {
        "documents": len(set(int(row[2]) for row in offsets)), "blocks": len(blocks),
        "japanese_blocks": len(jp_blocks), "locations": len(locations),
        "excluded": len(excluded), "official_fgo_chapters": len(official_ids),
    }

def audit(data_dir: Path, source_roots, legacy_data_dir: Path):
    return build_bundle(data_dir, source_roots, legacy_data_dir)["stats"]


def build_arg_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--data-dir", default=str(root / "data"))
    parser.add_argument("--source-root", action="append", default=[
        r"D:\\型月\\型月游戏文本设定访谈合集17版\\入门级整理17版",
        r"D:\\型月\\型月游戏文本设定访谈合集17版\\入门级整理17版 - 副本",
    ])
    parser.add_argument("--legacy-data-dir", default=r"D:\\codex\\Projects\\Output\\发布归档\\v1.1.6\\型月搜索电脑版_v1.1.6\\_internal\\data")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    return parser


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    data_dir = Path(args.data_dir).resolve()
    sources = [Path(path).resolve() for path in args.source_root]
    if args.audit:
        print(json.dumps(audit(data_dir, sources, Path(args.legacy_data_dir)), ensure_ascii=False, indent=2))
    elif args.write:
        bundle = build_bundle(data_dir, sources, Path(args.legacy_data_dir))
        backup = write_bundle(data_dir, bundle)
        print(json.dumps({"backup": str(backup), "check": check_data(data_dir), "stats": bundle["stats"]},
                         ensure_ascii=False, indent=2))
    elif args.check:
        print(json.dumps(check_data(data_dir), ensure_ascii=False, indent=2))
    else:
        parser.error("choose --audit, --write, or --check")


__all__ = [
    "clean_occurrence_text", "split_visible_and_japanese", "short_label",
    "build_story_locations", "build_official_chapter", "build_bundle",
    "check_data", "write_bundle", "build_arg_parser", "missing_official_chapters", "source_mode_for_doc", "merge_exclusions", "merge_source_modes",
]


if __name__ == "__main__":
    main()
