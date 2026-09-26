# -*- coding: utf-8 -*-
"""Fetch, normalize, and import the Fate/strange Fake story archive."""
from __future__ import annotations

import argparse
import hashlib
import html
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

WORK = "FSF"
SOURCE_MID = "3493084864186368"
SOURCE_LABEL = "Bilibili 2022 连续中文转载（与台湾角川中文版用字一致）"
ARTICLE_IDS = {
    1: (20201893, 20202012, 20202097),
    2: (20276269, 20277806, 20277809),
    3: (20277813, 20277817, 20277821),
    4: (20306426, 20306410, 20306434),
    5: (20306446, 20306453, 20329431),
    6: (20329439, 20329452, 20329455, 20329462),
    7: (20355823, 20355829, 20355834),
}
DOC_IDS = {1: 301, 2: 302, 3: 303, 4: 299}
PROTOTYPE_DOC = 300
PROTOTYPE_ROUTE = "《Fate/states night》"
VOLUME_RE = re.compile(r"^第[一二三四五六七八九十百零〇0-9]+卷(?:[\s　]+|$)")
HEADING_RE = re.compile(
    r"^(?:序(?:章)?(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]+)?|"
    r"(?:第)?[一二三四五六七八九十百零〇0-9]+章|"
    r"间章|幕间|序章|接续章|余章|尾声|终章|后记)"
)
URL_RE = re.compile(r"(?i)(?:https?://|www\.)\S+")
BOILERPLATE_RE = re.compile(
    r"^(?:作者|插画|譯者|译者|录入|转载|搬运|原帖|简介|封面|彩页)[:：]?\s*$"
)


class _BlockParser(HTMLParser):
    BLOCK_TAGS = {"h1", "h2", "h3", "p", "blockquote"}
    SKIP_TAGS = {"script", "style", "figure", "svg", "video", "audio"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self.skip_depth = 0
        self.block_tag = None
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "img":
            return
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "br" and self.block_tag:
            self.buffer.append("\n")
        elif tag in self.BLOCK_TAGS and self.block_tag is None:
            self.block_tag = tag
            self.buffer = []

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br" and self.block_tag and not self.skip_depth:
            self.buffer.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag == self.block_tag:
            text = html.unescape("".join(self.buffer))
            kind = "heading" if tag in {"h1", "h2", "h3"} else "paragraph"
            for part in _clean_block(text, kind):
                self.blocks.append({"kind": kind, "text": part})
            self.block_tag = None
            self.buffer = []

    def handle_data(self, data):
        if not self.skip_depth and self.block_tag:
            self.buffer.append(data)


def _normalize_line(value: str) -> str:
    value = html.unescape(value or "")
    value = value.replace("\u00a0", " ").replace("\u3000", " ")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t\f\v]+", " ", value).strip()


def _clean_block(text: str, kind: str) -> list[str]:
    result = []
    for line in _normalize_line(text).splitlines():
        line = _normalize_line(line)
        if not line or BOILERPLATE_RE.match(line) or URL_RE.fullmatch(line):
            continue
        if kind == "heading":
            line = VOLUME_RE.sub("", line).strip()
            if not line or line == "目录":
                continue
        result.append(line)
    return result


def extract_blocks(source_html: str) -> list[dict]:
    parser = _BlockParser()
    parser.feed(source_html or "")
    parser.close()
    return [block for block in parser.blocks if block["text"].strip()]


def _chapter_heading(value: str) -> bool:
    title = VOLUME_RE.sub("", value).strip()
    match = HEADING_RE.match(title)
    if not match:
        return False
    suffix = title[match.end():]
    return not suffix or suffix[0].isspace() or suffix[0] in "（(〔【[「『：:「\"'"


def _canonical_chapter_title(value: str) -> str:
    return VOLUME_RE.sub("", _normalize_line(value)).strip()


def _volume_toc(blocks: list[dict]) -> tuple[list[str], int]:
    candidates = []
    for index, block in enumerate(blocks):
        if block["kind"] != "paragraph" or not VOLUME_RE.match(block["text"]):
            continue
        title = _canonical_chapter_title(block["text"])
        if title and not _excluded_section_title(title):
            candidates.append((index, title))
    if not candidates:
        return [], -1
    runs = []
    current = [candidates[0]]
    for item in candidates[1:]:
        if item[0] == current[-1][0] + 1:
            current.append(item)
        else:
            runs.append(current)
            current = [item]
    runs.append(current)
    run = max(runs, key=len)
    return [title for _, title in run], run[-1][0]


def _excluded_section_title(value: str) -> bool:
    title = _canonical_chapter_title(value)
    return title.startswith("解说") or title.startswith("插画") or title.startswith("插图")


def _article_blocks(article: dict) -> list[dict]:
    return extract_blocks(article.get("html", ""))


def assemble_volume(volume: int, articles: list[dict]) -> tuple[list[dict], list[dict], list[str]]:
    first_blocks = _article_blocks(articles[0]) if articles else []
    toc_titles, toc_end = _volume_toc(first_blocks)
    expected = set(toc_titles)
    chapters = []
    current = None
    audits = []

    def start_chapter(title: str):
        nonlocal current
        if current and current["title"] == title:
            return
        current = {"title": title, "paragraphs": []}
        chapters.append(current)

    def expected_heading(text: str) -> str | None:
        title = _canonical_chapter_title(text)
        if expected:
            for candidate in sorted(expected, key=len, reverse=True):
                if title == candidate:
                    return candidate
                suffix = title[len(candidate):] if title.startswith(candidate) else ""
                if suffix and suffix[0] in "（(：:「『【[":
                    return candidate
        if _chapter_heading(title):
            return title
        return None

    for article_index, article in enumerate(articles):
        blocks = _article_blocks(article)
        start_index = 0
        if article_index == 0:
            if toc_titles:
                start_index = next(
                    (index for index in range(toc_end + 1, len(blocks))
                     if _canonical_chapter_title(blocks[index]["text"]) == toc_titles[0]),
                    len(blocks),
                )
            if start_index >= len(blocks):
                start_index = next(
                    (index for index, block in enumerate(blocks)
                     if block["kind"] == "heading" and _chapter_heading(block["text"])),
                    len(blocks),
                )
        parsed_chars = 0
        excluded_chars = 0
        first_title = None
        last_title = None
        skip_section = False
        for block in blocks[start_index:]:
            text = block["text"].strip()
            if _excluded_section_title(text):
                skip_section = True
                excluded_chars += len(text)
                continue
            title = expected_heading(text)
            if title is not None:
                skip_section = False
                start_chapter(title)
                first_title = first_title or title
                last_title = title
                parsed_chars += len(text)
            elif skip_section:
                excluded_chars += len(text)
                continue
            elif current is not None:
                current["paragraphs"].append(text)
                first_title = first_title or current["title"]
                last_title = current["title"]
                parsed_chars += len(text)
        audits.append({
            "article_id": article.get("article_id"),
            "api_words": article.get("words"),
            "parsed_chars": parsed_chars,
            "excluded_chars": excluded_chars,
            "covered_chars": parsed_chars + excluded_chars,
            "first_chapter": first_title,
            "last_chapter": last_title,
        })

    if toc_titles:
        found = [chapter["title"] for chapter in chapters]
        missing = [title for title in toc_titles if title not in found]
        if missing:
            raise ValueError(f"volume {volume} missing TOC chapters: {missing}")

    for index, audit in enumerate(audits):
        words = audit.get("api_words")
        if not words:
            continue
        tolerance = 0.07 if index == 0 else 0.02
        delta = abs(audit["covered_chars"] - words) / max(1, words)
        audit["delta_ratio"] = round(delta, 6)
        if delta > tolerance:
            raise ValueError(
                "article coverage mismatch: volume %s cv%s parsed=%s words=%s ratio=%.3f"
                % (volume, audit["article_id"], audit["covered_chars"], words, delta)
            )

    result = []
    for chapter in chapters:
        text = "\n".join(part for part in chapter["paragraphs"] if part.strip()).strip()
        if text:
            result.append({"title": chapter["title"], "text": text})
    if not result:
        raise ValueError(f"volume {volume} produced no chapters")
    return result, audits, toc_titles


def build_volume_chapters(volume: int, articles: list[dict]) -> list[dict]:
    chapters, _audits, _toc = assemble_volume(volume, articles)
    return chapters

PROTOTYPE_HEADING_RE = re.compile(r"^(?:序章|ACT[1-6]\s+\S+|尾声\s+Player|后记)$", re.I)


def build_prototype_segments(rows: list[tuple[int, str]]) -> tuple[list[tuple[int, str]], list[dict]]:
    ordered = [(int(order), text) for order, text in sorted(rows, key=lambda item: item[0])]
    start = next((i for i, (_, text) in enumerate(ordered) if text.strip() == "序章"), None)
    if start is None:
        raise ValueError("prototype start chapter not found")
    afterword = next((i for i in range(start, len(ordered))
                      if ordered[i][1].strip() == "后记"), None)
    if afterword is None:
        raise ValueError("prototype afterword not found")
    end = len(ordered)
    for i in range(afterword + 1, len(ordered)):
        text = ordered[i][1].strip()
        if text.startswith("附录") or text.startswith("森井"):
            end = i
            break
    selected = ordered[start:end]
    blocks = list(enumerate(text for _, text in selected))
    chapters = []
    current = None
    for index, (_, text) in enumerate(blocks):
        title = text.strip()
        if PROTOTYPE_HEADING_RE.match(title):
            current = {"title": title, "start": index, "end": None}
            chapters.append(current)
    for i, chapter in enumerate(chapters):
        chapter["end"] = chapters[i + 1]["start"] if i + 1 < len(chapters) else None
    return blocks, chapters
def _article_url(article_id: int) -> str:
    return f"https://www.bilibili.com/read/cv{article_id}/"


def _make_opener():
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                         "AppleWebKit/537.36 Chrome/126 Safari/537.36")]
    try:
        opener.open("https://www.bilibili.com/", timeout=20).read(512)
    except Exception:
        pass
    return opener


_CURL_CFFI_SESSION = None


def _article_result(article_id: int, data: dict) -> dict:
    content_html = data.get("content") or ""
    return {
        "article_id": article_id,
        "url": _article_url(article_id),
        "title": data.get("title") or "",
        "publish_time": data.get("publish_time"),
        "words": int(data.get("words") or 0),
        "content_sha256": hashlib.sha256(content_html.encode("utf-8")).hexdigest(),
        "html": content_html,
    }


def _fetch_article_browser_tls(article_id: int):
    """Use curl_cffi's browser TLS fingerprint when available."""
    global _CURL_CFFI_SESSION
    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        return None
    if _CURL_CFFI_SESSION is None:
        _CURL_CFFI_SESSION = curl_requests.Session(impersonate="chrome")
        try:
            _CURL_CFFI_SESSION.get("https://www.bilibili.com/", timeout=20)
        except Exception:
            pass
    response = _CURL_CFFI_SESSION.get(
        f"https://api.bilibili.com/x/article/view?id={article_id}",
        headers={"Referer": _article_url(article_id)},
        timeout=30,
    )
    return response.json()


def fetch_article(article_id: int, opener=None, retries: int = 8) -> dict:
    opener = opener or _make_opener()
    url = f"https://api.bilibili.com/x/article/view?id={article_id}"
    headers = {"Referer": _article_url(article_id)}
    last_error = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers=headers)
            payload = json.load(opener.open(request, timeout=30))
            if payload.get("code") == 0 and payload.get("data"):
                return _article_result(article_id, payload["data"])
            last_error = RuntimeError(f"Bilibili cv{article_id}: {payload.get('code')} {payload.get('message')}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            last_error = exc
        try:
            payload = _fetch_article_browser_tls(article_id)
        except Exception as exc:
            payload = None
            last_error = exc
        if payload and payload.get("code") == 0 and payload.get("data"):
            return _article_result(article_id, payload["data"])
        if attempt + 1 < retries:
            time.sleep(min(30, 5 * (attempt + 1)))
    raise RuntimeError(str(last_error) if last_error else f"failed to fetch cv{article_id}")


def build_manifest(cache_dir: Path | None = None, pause: float = 1.5) -> dict:
    cache_dir = cache_dir or Path("temp") / "fsf-source-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    opener = _make_opener()
    volumes = []
    for volume, article_ids in ARTICLE_IDS.items():
        articles = []
        for article_id in article_ids:
            cache_path = cache_dir / f"cv{article_id}.json"
            if cache_path.exists():
                article = json.loads(cache_path.read_text(encoding="utf-8"))
                if article.get("html"):
                    articles.append(article)
                    continue
            article = fetch_article(article_id, opener=opener)
            cache_path.write_text(json.dumps(article, ensure_ascii=False, separators=(",", ":")),
                                  encoding="utf-8", newline="\n")
            time.sleep(pause)
            articles.append(article)
        chapters, audits, toc = assemble_volume(volume, articles)
        article_rows = []
        for article, audit in zip(articles, audits):
            row = {k: v for k, v in article.items() if k != "html"}
            row.update(audit)
            article_rows.append(row)
        volumes.append({
            "volume": volume,
            "doc_id": DOC_IDS.get(volume),
            "articles": article_rows,
            "toc": toc,
            "chapters": chapters,
            "chars": sum(len(chapter["text"]) for chapter in chapters),
        })
    return {
        "version": 1,
        "work": WORK,
        "source_mid": SOURCE_MID,
        "source_label": SOURCE_LABEL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "volumes": volumes,
        "excluded": [
            {"volume": 8, "reason": "暂无公开可验证的可靠中文连续全文"},
            {"volume": 9, "reason": "现有公开版本均为机翻或 AI 翻译，未达到收录标准"},
        ],
    }


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload, pretty=False):
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    temp.replace(path)


def _chapter_blocks(chapter: dict) -> list[str]:
    blocks = [chapter["title"]]
    blocks.extend(part.strip() for part in re.split(r"\n\s*\n", chapter["text"]) if part.strip())
    return blocks


def _find_existing_fsf_work(story: dict) -> dict | None:
    return next((work for work in story.get("works", []) if work.get("work") == WORK), None)


def volume_file_key(volume: int) -> str:
    return f"剧情大全\\FSF\\第{volume}卷.txt"


def resolve_volume_doc_id(docs: list[dict], volume: int, requested=None) -> int | None:
    if requested is not None:
        return int(requested)
    key = volume_file_key(volume)
    matches = [int(doc["id"]) for doc in docs
               if doc.get("work") == WORK and doc.get("kind") == "原作" and doc.get("file") == key]
    return min(matches) if matches else None


def stale_fsf_doc_ids(docs: list[dict], target_ids: set[int]) -> set[int]:
    stale = set()
    for doc in docs:
        if doc.get("work") != WORK or doc.get("kind") != "原作":
            continue
        if re.fullmatch(r"剧情大全\\FSF\\第[0-9]+卷\.txt", doc.get("file", "")):
            if int(doc["id"]) not in target_ids:
                stale.add(int(doc["id"]))
    return stale


def find_prototype_route(work: dict) -> dict | None:
    names = {"fake states night", "原型企划《fake states night》", "原型企划《Fake/states night》（与第1卷同源，非重复）", PROTOTYPE_ROUTE}
    return next((route for route in work.get("routes", [])
                 if route.get("name") in names), None)


def apply_manifest(data_dir: Path, manifest: dict) -> dict:
    entries_path = data_dir / "entries.json"
    story_path = data_dir / "story.json"
    offsets_path = data_dir / "offsets.json"
    story_blocks_path = data_dir / "story_blocks.json"
    jp_blocks_path = data_dir / "jp_blocks.json"
    recovered_path = data_dir / "zh_recovered_blocks.json"
    corpus_path = data_dir / "corpus.txt"

    entries = _load_json(entries_path)
    story = _load_json(story_path)
    offsets = _load_json(offsets_path)
    story_rows = _load_json(story_blocks_path)
    jp_rows = _load_json(jp_blocks_path)
    corpus = corpus_path.read_text(encoding="utf-8")

    docs = entries["docs"]
    docs_by_id = {doc["id"]: doc for doc in docs}
    next_id = max((doc.get("id", -1) for doc in docs), default=-1) + 1

    old_work = _find_existing_fsf_work(story)
    if not old_work:
        raise RuntimeError("FSF story work not found")
    if not find_prototype_route(old_work):
        raise RuntimeError("prototype fake states night route not found")

    current_blocks = {}
    for start, length, doc_id, order in offsets:
        current_blocks.setdefault(doc_id, []).append((order, corpus[start:start + length]))
    for rows in current_blocks.values():
        rows.sort(key=lambda item: item[0])

    prototype_blocks, prototype_chapters = build_prototype_segments(current_blocks[PROTOTYPE_DOC])
    for chapter in prototype_chapters:
        chapter["doc"] = PROTOTYPE_DOC
    current_blocks[PROTOTYPE_DOC] = prototype_blocks
    prototype = {
        "name": PROTOTYPE_ROUTE,
        "chapters": prototype_chapters,
        "chars": sum(len(text) for _, text in prototype_blocks),
        "extra": False,
        "order": 0,
    }
    prototype_doc = docs_by_id.get(PROTOTYPE_DOC)
    if prototype_doc is None:
        raise RuntimeError("prototype document not found")
    prototype_meta = dict(prototype_doc.get("meta") or {})
    prototype_meta.update({
        "说明": "2008 愚人节原型《Fake/states night》",
        "关系": "与第1卷共享早期序章素材，但为不同篇幅与结构的原型文本",
    })
    prototype_doc.update({
        "title": "Fake/states night 原型",
        "work": WORK,
        "kind": "原作",
        "file": "剧情大全\\FSF\\Fake-states-night.txt",
        "chars": sum(len(text) for _, text in prototype_blocks),
        "meta": prototype_meta,
    })

    target_doc_ids = {PROTOTYPE_DOC}
    routes = [prototype]
    for volume in manifest["volumes"]:
        volume_no = int(volume["volume"])
        doc_id = volume.get("doc_id") or DOC_IDS.get(volume_no)
        if doc_id is None:
            doc_id = resolve_volume_doc_id(docs, volume_no)
        if doc_id is None:
            doc_id = next_id
            next_id += 1
        target_doc_ids.add(doc_id)
        blocks = []
        for chapter in volume["chapters"]:
            blocks.extend(_chapter_blocks(chapter))
        current_blocks[doc_id] = list(enumerate(blocks))
        chapters = []
        cursor = 0
        for chapter in volume["chapters"]:
            count = len(_chapter_blocks(chapter))
            chapters.append({
                "title": chapter["title"],
                "doc": doc_id,
                "start": cursor,
                "end": cursor + count if chapter is not volume["chapters"][-1] else None,
            })
            cursor += count
        routes.append({
            "name": f"第{volume_no}卷",
            "chapters": chapters,
            "chars": sum(len(text) for _, text in current_blocks[doc_id]),
            "extra": False,
            "order": volume_no,
        })
        meta = {
            "卷": f"第{volume_no}卷",
            "来源": manifest["source_label"],
            "来源文章": "、".join(f"cv{a['article_id']}" for a in volume["articles"]),
            "抓取时间": manifest.get("generated_at", ""),
        }
        doc = docs_by_id.get(doc_id)
        if doc is None:
            doc = {"id": doc_id, "meta": {}}
            docs.append(doc)
        doc.update({
            "title": f"Fate/strange Fake 第{volume_no}卷",
            "work": WORK,
            "kind": "原作",
            "file": volume_file_key(volume_no),
            "chars": sum(len(text) for _, text in current_blocks[doc_id]),
            "meta": meta,
            "lang": "zh",
            "ja_ratio": 0.0,
        })
        docs_by_id[doc_id] = doc

    stale_ids = stale_fsf_doc_ids(docs, target_doc_ids)
    if stale_ids:
        docs[:] = [doc for doc in docs if int(doc["id"]) not in stale_ids]
        for doc_id in stale_ids:
            docs_by_id.pop(doc_id, None)
            current_blocks.pop(doc_id, None)

    for route in routes:
        for index, chapter in enumerate(route["chapters"]):
            chapter["key"] = f"{WORK}::{route['name']}::{index}"

    new_work = {"work": WORK, "routes": routes,
                "chapters": sum(len(route["chapters"]) for route in routes)}
    story["works"] = [new_work if work.get("work") == WORK else work for work in story["works"]]

    ordered_blocks = []
    for doc in sorted(docs, key=lambda item: item.get("id", -1)):
        for order, text in sorted(current_blocks.get(doc["id"], []), key=lambda item: item[0]):
            text = str(text).strip("\n")
            if text:
                ordered_blocks.append((doc["id"], order, text))
    new_corpus = "\n".join(text for _, _, text in ordered_blocks)
    new_offsets = []
    cursor = 0
    for doc_id, order, text in ordered_blocks:
        new_offsets.append([cursor, len(text), doc_id, order])
        cursor += len(text) + 1

    current_story = {}
    for doc_id, order, text in story_rows:
        current_story.setdefault(doc_id, []).append((order, text))
    for doc_id in target_doc_ids | stale_ids:
        current_story.pop(doc_id, None)
    for doc_id in target_doc_ids:
        current_story[doc_id] = current_blocks[doc_id]
    new_story_rows = []
    for doc in sorted(docs, key=lambda item: item.get("id", -1)):
        for order, text in sorted(current_story.get(doc["id"], []), key=lambda item: item[0]):
            new_story_rows.append([doc["id"], order, text])

    new_jp_rows = [row for row in jp_rows if row[0] not in target_doc_ids | stale_ids]
    recovered = _load_json(recovered_path)
    recovered["base_corpus_length"] = len(new_corpus)

    _write_json(entries_path, entries)
    _write_json(story_path, story, pretty=True)
    temp_corpus = corpus_path.with_name(corpus_path.name + ".tmp")
    temp_corpus.write_text(new_corpus, encoding="utf-8", newline="\n")
    temp_corpus.replace(corpus_path)
    _write_json(offsets_path, new_offsets)
    _write_json(story_blocks_path, new_story_rows)
    _write_json(jp_blocks_path, new_jp_rows)
    _write_json(recovered_path, recovered, pretty=True)
    return {"volumes": len(manifest["volumes"]),
            "chapters": sum(len(volume["chapters"]) for volume in manifest["volumes"]),
            "story_blocks": len(new_story_rows),
            "corpus_chars": len(new_corpus)}


def check_data(data_dir: Path, manifest: dict) -> dict:
    entries = _load_json(data_dir / "entries.json")
    story = _load_json(data_dir / "story.json")
    rows = _load_json(data_dir / "story_blocks.json")
    docs = {doc["id"]: doc for doc in entries["docs"]}
    work = _find_existing_fsf_work(story)
    if not work:
        raise AssertionError("FSF story work missing")
    expected_names = [PROTOTYPE_ROUTE] + [f"第{i}卷" for i in range(1, 8)]
    names = [route["name"] for route in work["routes"]]
    if names != expected_names:
        raise AssertionError(f"unexpected FSF routes: {names}")
    by_doc = {}
    for doc_id, order, text in rows:
        by_doc.setdefault(doc_id, []).append((order, text))
    seen = set()
    for volume in manifest["volumes"]:
        route = next(route for route in work["routes"] if route["name"] == f"第{volume['volume']}卷")
        if [c["title"] for c in route["chapters"]] != [c["title"] for c in volume["chapters"]]:
            raise AssertionError(f"chapter manifest mismatch in volume {volume['volume']}")
        for chapter in route["chapters"]:
            if chapter["doc"] not in docs:
                raise AssertionError(f"missing doc {chapter['doc']}")
            footprint = (chapter["doc"], chapter.get("start"), chapter.get("end"), chapter["title"])
            if footprint in seen:
                raise AssertionError(f"duplicate chapter: {footprint}")
            seen.add(footprint)
            start = chapter.get("start") or 0
            end = chapter.get("end")
            selected = [text for order, text in by_doc.get(chapter["doc"], [])
                        if order >= start and (end is None or order < end)]
            if not selected or not any(text.strip() for text in selected):
                raise AssertionError(f"empty chapter: {route['name']} {chapter['title']}")
    return {"routes": len(names), "volumes": len(manifest["volumes"]),
            "chapters": sum(len(route["chapters"]) for route in work["routes"][1:])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default_app = Path(__file__).resolve().parent
    default_root = default_app.parent
    parser.add_argument("--manifest", default=str(default_app / "fsf_story_sources.json"))
    parser.add_argument("--data-dir", default=str(default_root / "data"))
    parser.add_argument("--cache-dir", default=str(default_root / "temp" / "fsf-source-cache"))
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not any((args.fetch, args.write, args.check)):
        parser.error("choose --fetch, --write, or --check")
    manifest_path = Path(args.manifest).resolve()
    data_dir = Path(args.data_dir).resolve()
    if args.fetch:
        manifest = build_manifest(Path(args.cache_dir).resolve())
        _write_json(manifest_path, manifest, pretty=True)
        print(json.dumps({"manifest": str(manifest_path),
                          "volumes": len(manifest["volumes"]),
                          "chapters": sum(len(v["chapters"]) for v in manifest["volumes"])},
                         ensure_ascii=False))
    if args.write:
        manifest = _load_json(manifest_path)
        result = apply_manifest(data_dir, manifest)
        print(json.dumps(result, ensure_ascii=False))
    if args.check:
        manifest = _load_json(manifest_path)
        print(json.dumps(check_data(data_dir, manifest), ensure_ascii=False))


if __name__ == "__main__":
    main()