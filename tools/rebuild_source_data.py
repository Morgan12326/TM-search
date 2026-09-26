# -*- coding: utf-8 -*-
"""Deterministic repair helpers for source-backed Type-Moon Search data."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.I)
MD_LINK_RE = re.compile(r"\[([^\]]{0,200})\]\((?:(?:https?://|www\.)[^)]+)\)", re.I)
HTML_LINK_RE = re.compile(r"<a\b[^>]*>(.*?)</a>", re.I | re.S)
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CHINESE_SIGNAL_CHARS = frozenset("的是了这這为為而就都也我你他她它们們说說到有在把被与與和跟对對从從将將能会會不没沒有么麼嗎呢吧啊")
CHINESE_PUNCTUATION = ("，", "；", "：", "。", "！", "？")

DDD_ROUTES = (
    ("Vol.1", (
        "1~~J the E.txt",
        "2~~HandS.(R).txt",
        "3~~HandS.(L).txt",
        "4~~formal hunt.txt",
        "5~~《DDD》 Vol.1 附录.txt",
    )),
    ("Vol.2", (
        "1 S.VS.S-1.txt",
        "2 S.VS.S-2.txt",
        "3 FOMALHAUT.txt",
        "4 Vt.in day dream.txt",
        "5 附录.txt",
    )),
    ("宙之外", ("宙之外.txt",)),
)

FE_CCC_ROOT = Path("原作文本") / "FE CCC"
FE_CCC_ROUTES = (
    "CCC C狐路线",
    "CCC 无铭ARHCER路线",
    "CCC 赤SABER路线",
    "CCC 金闪闪路线",
)


MB_ROOT = Path("原作文本") / "MB"
MB_ROUTE_ORDER = ("MB汉化", "MBAA", "MBAACC", "MBAC", "MBR")


def _natural_key(value):
    return [int(part) if part.isdigit() else part.casefold()
            for part in re.split(r"(\d+)", str(value))]


def _mb_source_root(source_roots):
    for root in source_roots:
        candidate = Path(root) / MB_ROOT
        if candidate.is_dir():
            return Path(root), candidate
    raise RuntimeError("MB source directory not found")


def _mb_files(root, source_root):
    return sorted(
        [p for p in root.rglob("*") if p.is_file() and "日文" not in p.parts],
        key=lambda p: _natural_key(str(p.relative_to(source_root))),
    )


def ensure_mb_entries(entries, source_roots):
    source_root, root = _mb_source_root(source_roots)
    docs_by_file = {d.get("file"): d for d in entries["docs"]}
    next_id = max((d.get("id", -1) for d in entries["docs"]), default=-1) + 1
    for path in _mb_files(root, source_root):
        relative = str(path.relative_to(source_root)).replace("/", "\\")
        if relative in docs_by_file:
            continue
        text = read_source_text(path)
        doc = {
            "id": next_id,
            "title": path.stem,
            "work": "月姬",
            "kind": "原作",
            "file": relative,
            "chars": len(text),
            "meta": {},
        }
        doc.update(_language_profile([text]))
        entries["docs"].append(doc)
        docs_by_file[relative] = doc
        next_id += 1
    return source_root, root, docs_by_file


def build_mb_work(entries, source_roots):
    source_root, root, docs_by_file = ensure_mb_entries(entries, source_roots)
    files = _mb_files(root, source_root)
    routes = []
    for route_name in MB_ROUTE_ORDER:
        rows = []
        for path in files:
            relative = path.relative_to(root)
            if not relative.parts or relative.parts[0] != route_name:
                continue
            file_key = str(path.relative_to(source_root)).replace("/", "\\")
            doc = docs_by_file[file_key]
            group = ""
            if route_name == "MB汉化" and len(relative.parts) > 2:
                group = re.sub(r"\s+", " ", relative.parts[1]).strip()
            rows.append({
                "title": doc["title"],
                "doc": doc["id"],
                "start": 0,
                "end": None,
                "group": group,
                "_file": file_key,
            })
        rows.sort(key=lambda chapter: (
            0 if not chapter["group"] else 1,
            _natural_key(chapter["group"]),
            _natural_key(Path(chapter["_file"]).name),
        ))
        chapters = []
        for chapter in rows:
            chapter = dict(chapter)
            chapter.pop("_file", None)
            chapters.append(chapter)
        routes.append({"name": route_name, "chapters": chapters, "chars": 0, "extra": False})
    return {"work": "MB", "routes": routes}


def upsert_mb_work(story, entries, source_roots):
    mb_work = build_mb_work(entries, source_roots)
    for index, work in enumerate(story["works"]):
        if work["work"] == "MB":
            story["works"][index] = mb_work
            return mb_work
    insert_at = next((i + 1 for i, work in enumerate(story["works"]) if work["work"] == "月姬"), 0)
    story["works"].insert(insert_at, mb_work)
    return mb_work


MONTH_CHAPTERS = {
    499: [
        "序章·涂鸦", "反转冲动1（上）", "反转冲动1（下）", "反转冲动2",
        "黑之兽1 (上)", "黑之兽1 （下）", "黑之兽2", "苍い咎迹",
        "直死の眼 1", "直死の眼 2", "死", "朱の红月 1", "朱の红月2",
        "凶ツ夜", "月世界", "Turn End 月姬", "Good End 黎明之月",
    ],
    513: ["序章", "反转冲动I", "反转冲动II", "黑兽I", "黑兽II", "朱い残滓I", "13．太阳"],
    511: [
        "第一章    反转冲动 I", "第二章    反转冲动 II", "第二章    反转冲动 III",
        "第四章    沉痛的伤痕 I", "第五章    静梦", "第六章    沉梦",
        "第七章    沉痛的伤痕 II", "第8日 午睡之梦", "第9日 吸血鬼",
        "第10日 热带夜", "第11日 望远镜 上", "第11日 望远镜 下",
        "第12日 上", "第12日 下", "Normal End 远方的葦切",
        "TRUE END 温暖的午睡",
    ],
    512: [
        "Opening", "プロローグ", "反転衝動I", "反転衝動II", "反転衝動III",
        "揺籃の庭", "殺人鬼I", "殺人鬼II", "透る爪痕", "死", "硝る躯I",
        "硝る躯II", "硝る躯III", "白昼夢", "金糸の繭", "まひるの月",
        "附录1 暗黒唇痕", "附录2 殺人貴", "附录3 ひなたのゆめ",
    ],
    510: ["序章 涂鸦", "反转冲动I", "反转冲动II", "反转冲动III", "日向の梦"],
    509: ["月蚀"],
}


@dataclass(frozen=True)
class LanguageRun:
    lang: str
    text: str


@dataclass(frozen=True)
class SourceBlock:
    text: str
    start: int
    end: int


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    return "\n".join(line.rstrip() for line in text.split("\n"))


def decode_bytes(raw: bytes) -> str:
    last_error = None
    for encoding in ("utf-8-sig", "utf-16", "gb18030"):
        try:
            return normalize_text(raw.decode(encoding))
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise UnicodeDecodeError("unknown", raw, 0, min(1, len(raw)), "unsupported source encoding")


def resolve_source_path(file_name: str, source_roots: Iterable[Path]) -> Path | None:
    if not file_name:
        return None
    for root in source_roots:
        direct = root / file_name
        if direct.exists():
            return direct
    return None


def _has_chinese_signal(text: str) -> bool:
    signals = sum(1 for char in text if char in CHINESE_SIGNAL_CHARS)
    return signals >= 2 or any(p in text for p in CHINESE_PUNCTUATION)


def classify_language(text: str) -> str:
    text = text or ""
    kana = len(KANA_RE.findall(text))
    han = len(HAN_RE.findall(text))
    if kana >= 2 and kana / float(max(1, kana + han)) > 0.10:
        return "ja"
    if han >= 4 and kana == 0:
        return "zh"
    if kana == 0 and _has_chinese_signal(text):
        return "zh"
    return "neutral"


def split_language_runs(text: str) -> list[LanguageRun]:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", normalize_text(text)) if block.strip()]
    runs: list[LanguageRun] = []
    for block in blocks:
        lines = block.splitlines()
        current = None
        buffer: list[str] = []

        def flush():
            nonlocal buffer
            if buffer and current is not None:
                value = "\n".join(buffer).strip()
                if value:
                    runs.append(LanguageRun(current, value))
            buffer = []

        for line in lines:
            lang = classify_language(line)
            if lang == "neutral":
                lang = current or "neutral"
            if current is None:
                current = lang
            elif lang != current:
                flush()
                current = lang
            buffer.append(line)
        flush()
    return runs


def remove_paired_japanese(runs: list[LanguageRun]) -> list[LanguageRun]:
    visible: list[LanguageRun] = []
    index = 0
    while index < len(runs):
        if runs[index].lang in ("ja", "neutral"):
            lookahead = index
            has_japanese = False
            while lookahead < len(runs) and runs[lookahead].lang in ("ja", "neutral"):
                has_japanese = has_japanese or runs[lookahead].lang == "ja"
                lookahead += 1
            if has_japanese and lookahead < len(runs) and runs[lookahead].lang == "zh":
                index = lookahead
                continue
        visible.append(runs[index])
        index += 1
    return visible


def split_source_blocks(text: str) -> list[SourceBlock]:
    text = normalize_text(text)
    blocks = []
    for match in re.finditer(r"[^\n](?:.*?)(?=\n\s*\n|\Z)", text, re.S):
        raw = match.group(0)
        stripped = raw.strip()
        if not stripped:
            continue
        left = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        blocks.append(SourceBlock(stripped, match.start() + left, match.start() + right))
    return blocks


def _load_json(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def extract_legacy_fsr_blocks(legacy_dir: Path, current_entries: dict):
    legacy_docs = {d["id"]: d for d in _load_json(legacy_dir / "entries.json")["docs"]}
    current_docs = {d["id"]: d for d in current_entries["docs"]}
    offsets = _load_json(legacy_dir / "offsets.json")
    corpus = (legacy_dir / "corpus.txt").read_text(encoding="utf-8")
    blocks = {}
    metadata = {}
    for doc_id in range(2, 103):
        old = legacy_docs.get(doc_id)
        current = current_docs.get(doc_id)
        if old is None or current is None:
            raise RuntimeError("legacy FSR doc id %d is missing" % doc_id)
        keys = ("title", "work", "kind", "file")
        if any(old.get(key) != current.get(key) for key in keys):
            raise RuntimeError("legacy FSR doc id %d metadata changed" % doc_id)
        rows = sorted((order, start, length) for start, length, doc_id_, order in offsets if doc_id_ == doc_id)
        extracted = [(order, corpus[start:start + length]) for order, start, length in rows]
        if not extracted or not any(text.strip() for _, text in extracted):
            raise RuntimeError("legacy FSR doc id %d has no text" % doc_id)
        blocks[doc_id] = extracted
        metadata[doc_id] = dict(current)
    return blocks, metadata


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    parser.add_argument("--legacy-data-dir", default=r"D:\codex\Projects\Output\发布归档\v1.1.6\型月搜索电脑版_v1.1.6\_internal\data")
    parser.add_argument("--source-root", action="append", default=[
        r"D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版",
        r"D:\型月\型月游戏文本设定访谈合集17版\入门级整理17版 - 副本",
    ])
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not any((args.audit, args.write, args.check)):
        parser.error("choose --audit, --write, or --check")
    data_dir = Path(args.data_dir).resolve()
    legacy_dir = Path(args.legacy_data_dir).resolve()
    entries = _load_json(data_dir / "entries.json")
    fsr_blocks, _ = extract_legacy_fsr_blocks(legacy_dir, entries)
    source_roots = [Path(p).resolve() for p in args.source_root]
    if args.audit:
        month_ids, ddd_ids, _, interview_ids = _target_doc_ids(entries, _load_json(data_dir / "story.json"))
        print("月姬 targets: %d" % len(month_ids))
        print("DDD targets: %d" % len(ddd_ids))
        print("FSR targets: %d" % len(fsr_blocks))
        print("访谈 targets: %d" % len(interview_ids))
    if args.write:
        result = write_repaired_data(data_dir, source_roots, legacy_dir)
        print("rebuilt: %s" % json.dumps(result, ensure_ascii=False))
    if args.check:
        check_repaired_data(data_dir, source_roots, legacy_dir)
        print("check passed")


def read_source_text(path: Path) -> str:
    return decode_bytes(path.read_bytes())


def sanitize_source_text(text: str) -> str:
    text = HTML_LINK_RE.sub(r"\1", str(text or ""))
    text = MD_LINK_RE.sub(r"\1", text)
    return URL_RE.sub("", text)


def _normalize_heading(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("\u3000", "")).strip().lower()


def heading_block_index(blocks: list[SourceBlock], title: str, start_at: int = 0) -> int:
    target = _normalize_heading(title)
    best = None
    for index, block in enumerate(blocks):
        if index < start_at:
            continue
        lines = block.text.splitlines()
        for line in lines:
            if _normalize_heading(line) == target:
                best = index
                break
        if best is not None:
            break
    if best is None:
        raise RuntimeError("heading not found in source: %s" % title)
    return best


def _feccc_source_root(source_roots):
    candidates = [Path(root) for root in source_roots
                  if (Path(root) / FE_CCC_ROOT).is_dir()]
    if not candidates:
        raise RuntimeError("FE CCC source directory not found")
    for root in reversed(candidates):
        if str(root).endswith("- 副本"):
            return root, root / FE_CCC_ROOT
    return candidates[-1], candidates[-1] / FE_CCC_ROOT


def _feccc_files(root):
    return sorted([p for p in root.rglob("*") if p.is_file()],
                  key=lambda p: _natural_key(str(p.relative_to(root))))


def ensure_feccc_entries(entries, source_roots):
    source_root, root = _feccc_source_root(source_roots)
    docs_by_file = {d.get("file"): d for d in entries["docs"]}
    next_id = max((d.get("id", -1) for d in entries["docs"]), default=-1) + 1
    for path in _feccc_files(root):
        relative = str(path.relative_to(source_root)).replace("/", "\\")
        if relative in docs_by_file:
            continue
        text = read_source_text(path)
        doc = {
            "id": next_id,
            "title": path.stem,
            "work": "FE",
            "kind": "原作",
            "file": relative,
            "chars": len(text),
            "meta": {},
        }
        doc.update(_language_profile([text]))
        entries["docs"].append(doc)
        docs_by_file[relative] = doc
        next_id += 1
    return source_root, root, docs_by_file


def build_feccc_work(entries, source_roots):
    source_root, root, docs_by_file = ensure_feccc_entries(entries, source_roots)
    files = _feccc_files(root)

    def chapter_for(path):
        relative = str(path.relative_to(source_root)).replace("/", "\\")
        doc = docs_by_file[relative]
        return {"title": doc["title"], "doc": doc["id"], "start": 0, "end": None,
                "_file": relative}

    root_chapters = []
    routes = []
    for route_name in FE_CCC_ROUTES:
        rows = []
        for path in files:
            relative = path.relative_to(root)
            if len(relative.parts) == 2 and relative.parts[0] == route_name:
                rows.append(chapter_for(path))
        rows.sort(key=lambda chapter: _natural_key(Path(chapter["_file"]).name))
        chapters = []
        for chapter in rows:
            chapter = dict(chapter)
            chapter.pop("_file", None)
            chapters.append(chapter)
        routes.append({"name": route_name, "chapters": chapters, "chars": 0, "extra": False})
    for route_name in ("玉藻前相关", "安徒生相关"):
        path = root / (route_name + ".txt")
        if not path.is_file():
            raise RuntimeError("FE CCC direct file missing: %s" % path)
        chapter = chapter_for(path)
        chapter.pop("_file", None)
        routes.append({"name": route_name, "chapters": [chapter], "chars": 0, "extra": False})
    return {"work": "FE_CCC", "root_chapters": root_chapters, "routes": routes}


def upsert_feccc_work(story, entries, source_roots):
    work = build_feccc_work(entries, source_roots)
    for index, existing in enumerate(story["works"]):
        if existing["work"] in ("FE", "FE_CCC"):
            story["works"][index] = work
            return work
    story["works"].insert(0, work)
    return work


def build_month_route(source_roots, entries, story):
    docs = {d["id"]: d for d in entries["docs"]}
    work = next(w for w in story["works"] if w["work"] == "月姬")
    route = next(r for r in work["routes"] if r["name"] == "月姬本篇")
    groups = {}
    for chapter in route["chapters"]:
        groups.setdefault(chapter["doc"], chapter.get("group", ""))
    chapters = []
    for doc_id, titles in MONTH_CHAPTERS.items():
        doc = docs[doc_id]
        path = resolve_source_path(doc.get("file", ""), source_roots)
        if path is None:
            raise RuntimeError("month source missing: %s" % doc.get("file"))
        blocks = split_source_blocks(read_source_text(path))
        starts = []
        cursor = 0
        for index, title in enumerate(titles):
            start = 0 if doc_id == 509 else heading_block_index(blocks, title, cursor)
            starts.append(start)
            cursor = start + 1
        for index, title in enumerate(titles):
            start = starts[index]
            end = starts[index + 1] if index + 1 < len(starts) else None
            chapters.append({"title": title, "doc": doc_id, "start": start, "end": end,
                             "group": groups.get(doc_id, "")})
    route["chapters"] = chapters
    return route


def build_ddd_work(source_roots, entries):
    docs = entries["docs"]
    by_file = {d.get("file"): d for d in docs}
    routes = []
    for route_name, file_names in DDD_ROUTES:
        chapters = []
        for file_name in file_names:
            matches = [d for path, d in by_file.items() if path and Path(path).name == file_name]
            if len(matches) != 1:
                raise RuntimeError("DDD source mapping failed for %s: %r" % (file_name, matches))
            doc = matches[0]
            if "[日]" in doc["file"]:
                raise RuntimeError("Japanese DDD source must be excluded: %s" % doc["file"])
            chapters.append({"title": Path(file_name).stem, "doc": doc["id"], "start": 0, "end": None})
        routes.append({"name": route_name, "chapters": chapters, "chars": 0, "extra": False})
    return {"work": "DDD", "routes": routes}


def build_fsr_routes(entries):
    docs = [d for d in entries["docs"] if 2 <= d["id"] <= 96]
    routes = []
    for route_name, lo, hi in (("正篇·盈月之仪", 53, 96), ("DLC", 2, 52)):
        selected = [d for d in docs if lo <= d["id"] <= hi]
        selected.sort(key=lambda d: int(d.get("meta", {}).get("剧情顺序") or d["id"]))
        chapters = []
        for doc in selected:
            meta = doc.get("meta", {})
            chapters.append({
                "title": meta.get("剧情段落") or doc["title"],
                "doc": doc["id"],
                "start": 0,
                "end": None,
                "group": meta.get("剧情章节") or "",
            })
        routes.append({"name": route_name, "chapters": chapters, "chars": 0, "extra": False})
    return routes
def _language_profile(texts):
    kana = sum(len(KANA_RE.findall(text)) for text in texts)
    han = sum(len(HAN_RE.findall(text)) for text in texts)
    ratio = kana / float(max(1, kana + han))
    if kana and not han:
        lang = "ja"
    elif kana and han:
        lang = "mixed"
    elif kana:
        lang = "ja"
    else:
        lang = "zh"
    return {"lang": lang, "ja_ratio": round(ratio, 3)}


def _target_doc_ids(entries, story):
    month_ids = set(MONTH_CHAPTERS)
    ddd_ids = set()
    for d in entries["docs"]:
        if d.get("work") == "DDD" and d.get("kind") == "原作" and "[日]" not in d.get("file", ""):
            ddd_ids.add(d["id"])
    fsr_ids = set(range(2, 103))
    interview_ids = set()
    for work in story["works"]:
        if work["work"] == "访谈":
            interview_ids.update(c["doc"] for r in work["routes"] for c in r["chapters"])
    return month_ids, ddd_ids, fsr_ids, interview_ids


def build_target_blocks(data_dir: Path, source_roots, legacy_dir: Path):
    entries = _load_json(data_dir / "entries.json")
    story = _load_json(data_dir / "story.json")
    old_fe_docs = {
        c["doc"] for work in story["works"] if work["work"] == "FE"
        for c in [chapter for r in work["routes"] for chapter in r["chapters"]]
    }
    ensure_mb_entries(entries, source_roots)
    upsert_mb_work(story, entries, source_roots)
    ensure_feccc_entries(entries, source_roots)
    upsert_feccc_work(story, entries, source_roots)
    docs = {d["id"]: d for d in entries["docs"]}
    month_ids, ddd_ids, fsr_ids, story_interview_ids = _target_doc_ids(entries, story)
    interview_ids = {
        d["id"] for d in entries["docs"]
        if d.get("kind") in ("访谈", "问答") and resolve_source_path(d.get("file", ""), source_roots)
    }
    all_targets = month_ids | ddd_ids | fsr_ids | interview_ids
    corpus_blocks = {}
    display_blocks = {}
    japanese_blocks = {}

    fsr_blocks, fsr_metadata = extract_legacy_fsr_blocks(legacy_dir, entries)
    for doc_id, rows in fsr_blocks.items():
        normalized = [(order, text) for order, text in rows]
        corpus_blocks[doc_id] = normalized
        if doc_id in range(2, 97):
            display_blocks[doc_id] = normalized
        docs[doc_id]["chars"] = sum(len(text) for _, text in normalized)

    for doc_id in month_ids | ddd_ids:
        doc = docs[doc_id]
        path = resolve_source_path(doc.get("file", ""), source_roots)
        if path is None:
            raise RuntimeError("target source missing: %s" % doc.get("file"))
        text = sanitize_source_text(read_source_text(path))
        blocks = [block.text for block in split_source_blocks(text)]
        rows = [(order, block) for order, block in enumerate(blocks)]
        corpus_blocks[doc_id] = rows
        display_blocks[doc_id] = rows
        docs[doc_id]["chars"] = sum(len(block) for block in blocks)

    for doc_id in interview_ids:
        doc = docs[doc_id]
        path = resolve_source_path(doc.get("file", ""), source_roots)
        if path is None:
            raise RuntimeError("interview source missing: %s" % doc.get("file"))
        raw_runs = split_language_runs(sanitize_source_text(read_source_text(path)))
        runs = remove_paired_japanese(raw_runs)
        if any(run.lang == "ja" for run in raw_runs):
            from language_blocks import looks_like_chinese_block
            first_chinese = next((index for index, run in enumerate(runs)
                                  if looks_like_chinese_block(run.text)), None)
            if first_chinese is not None:
                runs = runs[first_chinese:]
        corpus_rows = []
        visible_rows = []
        jp_rows = []
        for order, run in enumerate(runs):
            lang = "ja" if run.lang == "ja" else "zh"
            text = run.text.strip()
            if not text:
                continue
            corpus_rows.append((order, text))
            if lang == "ja":
                jp_rows.append((doc_id, order, text))
            else:
                visible_rows.append((doc_id, order, text))
        corpus_blocks[doc_id] = corpus_rows
        if visible_rows:
            display_blocks[doc_id] = [(order, text) for _, order, text in visible_rows]
        japanese_blocks[doc_id] = jp_rows
        docs[doc_id]["chars"] = sum(len(text) for _, text in corpus_rows)

    story_doc_ids = {c["doc"] for w in story["works"] for c in w.get("root_chapters", [])}
    story_doc_ids.update(c["doc"] for w in story["works"] for r in w["routes"] for c in r["chapters"])
    for doc_id in story_doc_ids:
        if doc_id in corpus_blocks:
            continue
        doc = docs.get(doc_id)
        path = resolve_source_path((doc or {}).get("file", ""), source_roots)
        if path is None:
            continue
        text = sanitize_source_text(read_source_text(path))
        corpus_rows = []
        visible_rows = []
        jp_rows = []
        for order, block in enumerate(split_source_blocks(text)):
            lang = classify_language(block.text)
            corpus_rows.append((order, block.text))
            if lang == "ja":
                jp_rows.append((doc_id, order, block.text))
            else:
                visible_rows.append((doc_id, order, block.text))
        corpus_blocks[doc_id] = corpus_rows
        if visible_rows:
            display_blocks[doc_id] = [(order, block) for _, order, block in visible_rows]
        japanese_blocks[doc_id] = jp_rows
        docs[doc_id]["chars"] = sum(len(block) for _, block in corpus_rows)
        all_targets.add(doc_id)

    for doc_id in all_targets:
        rows = corpus_blocks.get(doc_id, [])
        profile = _language_profile([text for _, text in rows])
        docs[doc_id].update(profile)
    removed_story_docs = old_fe_docs - story_doc_ids
    return entries, story, all_targets, corpus_blocks, display_blocks, japanese_blocks, removed_story_docs
def _rows_by_doc(rows):
    result = {}
    for doc_id, order, text in rows:
        result.setdefault(doc_id, []).append((order, text))
    for values in result.values():
        values.sort(key=lambda item: item[0])
    return result


def _write_json(path: Path, payload, pretty=False):
    temp_path = path.with_name(path.name + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    temp_path.replace(path)


def normalize_story_ranges(story, block_lists):
    for work in story["works"]:
        for route in work["routes"]:
            chapters = route["chapters"]
            last_by_doc = {}
            resolved = set()
            for index, chapter in enumerate(chapters):
                blocks = block_lists.get(chapter["doc"])
                if not blocks:
                    continue
                if sum(1 for item in chapters if item["doc"] == chapter["doc"]) == 1:
                    chapter["start"] = 0
                    chapter["end"] = None
                    resolved.add(index)
                    continue
                source_blocks = [SourceBlock(text, 0, 0) for text in blocks]
                try:
                    start = heading_block_index(source_blocks, chapter["title"],
                                                last_by_doc.get(chapter["doc"], 0))
                except RuntimeError:
                    continue
                chapter["start"] = start
                last_by_doc[chapter["doc"]] = start + 1
                resolved.add(index)
            for index in range(len(chapters) - 1, -1, -1):
                if index in resolved:
                    continue
                chapter = chapters[index]
                blocks = block_lists.get(chapter["doc"])
                if not blocks:
                    continue
                next_start = None
                for following in chapters[index + 1:]:
                    if following["doc"] == chapter["doc"]:
                        next_start = following["start"]
                        break
                if next_start is not None:
                    chapter["start"] = next_start
                elif chapter.get("start") is None or chapter["start"] >= len(blocks):
                    chapter["start"] = len(blocks) - 1
            for index, chapter in enumerate(chapters):
                if index + 1 < len(chapters) and chapters[index + 1]["doc"] == chapter["doc"]:
                    chapter["end"] = chapters[index + 1]["start"]
                else:
                    chapter["end"] = None
    return story


def assign_story_keys(story):
    for work in story["works"]:
        for index, chapter in enumerate(work.get("root_chapters", [])):
            chapter["key"] = "%s::root::%d" % (work["work"], index)
        for route in work["routes"]:
            for index, chapter in enumerate(route["chapters"]):
                chapter["key"] = "%s::%s::%d" % (work["work"], route["name"], index)
    return story


def update_story_manifests(story, entries, source_roots, block_lists):
    normalize_story_ranges(story, block_lists)
    for work in story["works"]:
        if work["work"] == "月姬":
            build_month_route(source_roots, entries, story)
        elif work["work"] == "DDD":
            replacement = build_ddd_work(source_roots, entries)
            work["routes"] = replacement["routes"]
        elif work["work"] == "FSR":
            work["routes"] = build_fsr_routes(entries)
    assign_story_keys(story)
    return story


def write_repaired_data(data_dir: Path, source_roots, legacy_dir: Path):
    entries, story, targets, overrides, display_blocks, japanese_blocks, removed_story_docs = build_target_blocks(
        data_dir, source_roots, legacy_dir
    )
    docs = entries["docs"]
    offsets = _load_json(data_dir / "offsets.json")
    story_rows = _load_json(data_dir / "story_blocks.json")
    jp_rows = _load_json(data_dir / "jp_blocks.json")
    recovered = _load_json(data_dir / "zh_recovered_blocks.json")

    current_offsets = {}
    for start, length, doc_id, order in offsets:
        current_offsets.setdefault(doc_id, []).append((order, start, length))
    for values in current_offsets.values():
        values.sort(key=lambda item: item[0])
    corpus = (data_dir / "corpus.txt").read_text(encoding="utf-8")

    blocks_by_doc = {}
    for doc in docs:
        doc_id = doc["id"]
        if doc_id in overrides:
            blocks_by_doc[doc_id] = list(overrides[doc_id])
        else:
            blocks_by_doc[doc_id] = [
                (order, corpus[start:start + length])
                for order, start, length in current_offsets.get(doc_id, [])
            ]

    ordered_blocks = []
    for doc in docs:
        doc_id = doc["id"]
        for order, text in sorted(blocks_by_doc.get(doc_id, []), key=lambda item: item[0]):
            text = text.strip("\n")
            if text:
                ordered_blocks.append((doc_id, order, text))

    recovered_rows = [row for row in recovered.get("blocks", []) if row["doc"] not in targets]
    for row in recovered_rows:
        text = row["text"].strip("\n")
        if text:
            ordered_blocks.append((row["doc"], row["order"], text))

    new_corpus = "\n".join(text for _, _, text in ordered_blocks)
    new_offsets = []
    cursor = 0
    for doc_id, order, text in ordered_blocks:
        new_offsets.append([cursor, len(text), doc_id, order])
        cursor += len(text) + 1
    new_recovered = {
        "version": 1,
        "base_corpus_length": len(new_corpus),
        "blocks": [],
    }

    current_story = _rows_by_doc(story_rows)
    for doc_id in targets | removed_story_docs:
        current_story.pop(doc_id, None)
    for doc_id, rows in display_blocks.items():
        current_story[doc_id] = [(order, text) for order, text in rows]
    new_story_rows = []
    for doc in docs:
        doc_id = doc["id"]
        for order, text in sorted(current_story.get(doc_id, []), key=lambda item: item[0]):
            new_story_rows.append([doc_id, order, text])

    current_jp = _rows_by_doc(jp_rows)
    for doc_id in targets | removed_story_docs:
        current_jp.pop(doc_id, None)
    for doc_id, rows in japanese_blocks.items():
        current_jp[doc_id] = [(order, text) for _, order, text in rows]
    new_jp_rows = []
    for doc in docs:
        doc_id = doc["id"]
        for order, text in sorted(current_jp.get(doc_id, []), key=lambda item: item[0]):
            new_jp_rows.append([doc_id, order, text])

    from language_blocks import looks_like_chinese_block
    moved_chinese = [row for row in new_jp_rows if looks_like_chinese_block(row[2])]
    if moved_chinese:
        new_jp_rows = [row for row in new_jp_rows if row not in moved_chinese]
        for doc_id, order, text in moved_chinese:
            if new_corpus:
                new_corpus += "\n"
            start = len(new_corpus)
            new_corpus += text
            new_offsets.append([start, len(text), doc_id, order])
        new_recovered["base_corpus_length"] = len(new_corpus)

    range_blocks = {doc_id: [text for _, text in rows] for doc_id, rows in display_blocks.items()}
    update_story_manifests(story, entries, source_roots, range_blocks)
    _write_json(data_dir / "entries.json", entries)
    _write_json(data_dir / "story.json", story, pretty=True)
    (data_dir / "corpus.txt.tmp").write_text(new_corpus, encoding="utf-8", newline="\n")
    (data_dir / "corpus.txt.tmp").replace(data_dir / "corpus.txt")
    _write_json(data_dir / "offsets.json", new_offsets)
    _write_json(data_dir / "story_blocks.json", new_story_rows)
    _write_json(data_dir / "jp_blocks.json", new_jp_rows)
    _write_json(data_dir / "zh_recovered_blocks.json", new_recovered, pretty=True)
    return {
        "corpus_chars": len(new_corpus),
        "offsets": len(new_offsets),
        "story_blocks": len(new_story_rows),
        "jp_blocks": len(new_jp_rows),
        "targets": len(targets),
    }


def check_repaired_data(data_dir: Path, source_roots, legacy_dir: Path):
    entries = _load_json(data_dir / "entries.json")
    story = _load_json(data_dir / "story.json")
    offsets = _load_json(data_dir / "offsets.json")
    corpus = (data_dir / "corpus.txt").read_text(encoding="utf-8")
    doc_ids = {d["id"] for d in entries["docs"]}
    assert all(doc_id in doc_ids for _, _, doc_id, _ in offsets)
    assert all(0 <= start and start + length <= len(corpus) for start, length, _, _ in offsets)
    month = next(w for w in story["works"] if w["work"] == "月姬")
    route = next(r for r in month["routes"] if r["name"] == "月姬本篇")
    assert len(route["chapters"]) == 65
    jade = [c for c in route["chapters"] if c["doc"] == 512]
    amber = [c for c in route["chapters"] if c["doc"] == 510]
    assert len(jade) == 19 and len(amber) == 5
    ddd = next(w for w in story["works"] if w["work"] == "DDD")
    assert [r["name"] for r in ddd["routes"]] == ["Vol.1", "Vol.2", "宙之外"]
    assert [len(r["chapters"]) for r in ddd["routes"]] == [5, 5, 1]
    current_blocks = _rows_by_doc(_load_json(data_dir / "story_blocks.json"))
    assert not any(w["work"] == "FE" for w in story["works"])
    for work in story["works"]:
        assert all(c.get("key") for c in work.get("root_chapters", []))
        for route in work["routes"]:
            assert route["chapters"]
            assert all(c.get("key") for c in route["chapters"])
    feccc = next(w for w in story["works"] if w["work"] == "FE_CCC")
    assert feccc["root_chapters"] == []
    assert [r["name"] for r in feccc["routes"]] == ["CCC C狐路线", "CCC 无铭ARHCER路线", "CCC 赤SABER路线", "CCC 金闪闪路线", "玉藻前相关", "安徒生相关"]
    assert [len(r["chapters"]) for r in feccc["routes"]] == [10, 9, 11, 12, 1, 1]
    feccc_docs = {c["doc"] for r in feccc["routes"] for c in r["chapters"]}
    assert all(not URL_RE.search(text) for doc_id, rows in current_blocks.items()
               if doc_id in feccc_docs for _, text in rows)
    fsr = next(w for w in story["works"] if w["work"] == "FSR")
    assert [len(r["chapters"]) for r in fsr["routes"]] == [44, 51]
    mb = next(w for w in story["works"] if w["work"] == "MB")
    assert [r["name"] for r in mb["routes"]] == ["MB汉化", "MBAA", "MBAACC", "MBAC", "MBR"]
    assert [len(r["chapters"]) for r in mb["routes"]] == [71, 28, 2, 24, 18]
    mb_docs = {c["doc"] for r in mb["routes"] for c in r["chapters"]}
    docs_by_id = {d["id"]: d for d in entries["docs"]}
    assert all("\\日文\\" not in docs_by_id[doc_id]["file"] for doc_id in mb_docs)
    current_blocks = _rows_by_doc(_load_json(data_dir / "story_blocks.json"))
    assert all(not URL_RE.search(text) for doc_id, rows in current_blocks.items()
               if doc_id in mb_docs for _, text in rows)
    fsr_blocks, _ = extract_legacy_fsr_blocks(legacy_dir, entries)
    current = current_blocks
    for doc_id, rows in fsr_blocks.items():
        if doc_id > 96:
            continue
        if doc_id not in current:
            raise AssertionError("FSR story overlay missing doc %d" % doc_id)
    return True

if __name__ == "__main__":
    main()






