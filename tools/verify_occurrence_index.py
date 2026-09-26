# -*- coding: utf-8 -*-
"""Independent cross-check for occurrence locations and reader round-trips."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import server
from tools.rebuild_occurrence_index import _load_json, _location_index, _find_location


def _check_jump(store, jump, doc_id, order):
    if not isinstance(jump, dict):
        return False, "missing jump"
    kind = jump.get("kind")
    if kind == "official":
        chapter = store.official_chapter(jump.get("work"), int(jump.get("id")))
        if not chapter:
            return False, "missing official chapter"
        section = int(jump.get("section", -1))
        if section < 0 or section >= len(chapter["chapters"]):
            return False, "official section out of range"
        return True, ""
    if kind == "viewer":
        chapter_key = jump.get("chapter")
        if chapter_key:
            info = store.story_chapter_by_key.get(chapter_key)
            if not info:
                return False, "missing story chapter key"
            _work, route, index = info
            chapter = route["chapters"][index]
            if int(chapter["doc"]) != int(doc_id):
                return False, "story chapter document mismatch"
        if doc_id not in store.doc_span:
            return False, "viewer document has no readable span"
        return True, ""
    return False, "unknown jump kind"


def verify(data_dir: Path, source_roots, legacy_data_dir: Path):
    del source_roots, legacy_data_dir
    old_data = server.store.DATA
    server.store.DATA = str(data_dir)
    try:
        store = server.Store()
        locations = _load_json(data_dir / "occurrence_locations.json")
        by_doc = _location_index(locations)
        errors = []
        checked_blocks = 0
        for doc_id, rows in store.doc_index.items():
            for order, _start, _length in rows:
                checked_blocks += 1
                location = _find_location(by_doc, doc_id, order)
                if not location:
                    errors.append({"doc": doc_id, "order": order, "error": "missing location"})
                    continue
                ok, reason = _check_jump(store, location.get("jump"), doc_id, order)
                if not ok:
                    errors.append({"doc": doc_id, "order": order, "path": location.get("path"), "error": reason})
                if not location.get("path"):
                    errors.append({"doc": doc_id, "order": order, "error": "empty path"})

        checked_locations = 0
        for row in locations:
            checked_locations += 1
            ok, reason = _check_jump(store, row.get("jump"), int(row["doc"]), int(row["start"]))
            if not ok:
                errors.append({"doc": row["doc"], "start": row["start"], "path": row.get("path"), "error": reason})

        official_docs = set()
        for work in store.story_works:
            for chapter in work.get("root_chapters", []):
                official_docs.add(int(chapter["doc"]))
            for route in work.get("routes", []):
                for chapter in route.get("chapters", []):
                    official_docs.add(int(chapter["doc"]))
        by_doc_rows = {}
        for doc_id, order, text in _load_json(data_dir / "story_blocks.json"):
            by_doc_rows.setdefault(int(doc_id), []).append((int(order), text))
        with_jp = {}
        for doc_id, order, text in _load_json(data_dir / "jp_blocks.json"):
            with_jp.setdefault(int(doc_id), []).append((int(order), text))
        missing_story_text = sorted(
            doc_id for doc_id in official_docs
            if not by_doc_rows.get(doc_id) and not with_jp.get(doc_id)
        )
        if missing_story_text:
            errors.append({"error": "story chapters missing visible/japanese text", "docs": missing_story_text[:20]})

        # Verify every official FGO chapter still has a section-level jump.
        expected_fgo = set()
        for part in _load_json(data_dir / "fgo_story.json"):
            for chapter in part.get("chapters", []):
                expected_fgo.add(int(chapter["war_id"]))
        active_fgo = {int(row["jump"]["id"]) for row in locations
                      if row.get("jump", {}).get("kind") == "official"
                      and row["jump"].get("work") == "FGO"}
        excluded = _load_json(data_dir / "occurrence_exclusions.json").get("items", [])
        docs = {int(doc["id"]): doc for doc in _load_json(data_dir / "entries.json")["docs"]}
        for item in excluded:
            evidence = item.get("evidence") or {}
            if evidence.get("war_id") is not None:
                active_fgo.add(int(evidence["war_id"]))
                continue
            doc = docs.get(int(item.get("doc", -1)), {})
            if doc.get("official") and doc.get("work") == "FGO":
                match = re.search(r"(?:^|[\\/])(\d+)_", str(doc.get("file") or ""))
                if match:
                    war_id = int(match.group(1))
                    active_fgo.add(401 if war_id == 400 else war_id)
        missing_fgo = sorted(expected_fgo - active_fgo)
        if missing_fgo:
            errors.append({"error": "FGO chapters missing official jump", "chapters": missing_fgo})

        for text in (data_dir / "corpus.txt").read_text(encoding="utf-8").splitlines():
            if re.search(r"(?i)https?://|www\.|<a\b|\[[^\]]+\]\((?:https?://|www\.)[^)]+\)", text):
                errors.append({"error": "link remains in corpus", "text": text[:120]})
                break

        return {
            "documents": len(store.doc_index),
            "checked_blocks": checked_blocks,
            "checked_locations": checked_locations,
            "story_chapters": len(official_docs),
            "official_fgo_chapters": len(active_fgo),
            "errors": errors,
        }
    finally:
        server.store.DATA = old_data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(ROOT / "data"))
    parser.add_argument("--source-root", action="append", default=[
        r"D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版",
        r"D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版 - 副本",
    ])
    parser.add_argument("--legacy-data-dir", default=r"D:\codex\Projects\Output\发布归档\v1.1.6\型月搜索电脑版_v1.1.6\_internal\data")
    args = parser.parse_args(argv)
    report = verify(Path(args.data_dir).resolve(), [Path(x) for x in args.source_root], Path(args.legacy_data_dir))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
