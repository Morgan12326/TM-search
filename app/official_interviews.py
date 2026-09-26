# -*- coding: utf-8 -*-
"""Build helpers for the official-answer and interview index."""

import re
from collections import defaultdict


QUESTION_RE = re.compile(
    r"(?m)^[ \t]*(?:[●◆■◇○〇]\s*)?"
    r"(?:(?:Q|Ｑ|q|ｑ|问|問|提问|問題|質問)\s*[：:])[ \t]*"
)
ANSWER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[AＡaａ]\s*[：:]|(?:答|回答)\s*[：:])[ \t]*"
)
MIN_CONTENT_CHARS = 2
PUNCT_RE = re.compile(r"[\s。！？!?，,、；;：:（）()《》〈〉「」『』\[\]【】…—\-]+")
PLACEHOLDER_QUESTIONS = {"奈", "武", "虚", "奈须", "奈須", "武内", "A", "Q", "答", "問"}


def _substantive(text):
    return len(PUNCT_RE.sub("", text or ""))


def _clean_answer(text):
    text = (text or "").strip()
    match = ANSWER_RE.match(text)
    if match:
        text = text[match.end():].strip()
    lines = text.splitlines()
    while lines and SEPARATOR_RE.match(lines[-1].strip()):
        lines.pop()
    return "\n".join(lines).strip()


SPEAKER_RE = re.compile(r"(?m)^[ \t]*(?P<speaker>[^：:\n]{1,20})[：:]")
SEPARATOR_RE = re.compile(r"^[\-—－━=]{4,}$")


def _speaker_counts(blocks):
    counts = defaultdict(int)
    for _order, text in blocks:
        for match in SPEAKER_RE.finditer(text or ""):
            speaker = match.group("speaker").strip()
            if not speaker or re.match(r"^(?:Q|Ｑ|q|ｑ|问|問|提问|問題|質問|A|Ａ|a|ａ)$", speaker):
                continue
            counts[speaker] += 1
    return counts


def _accepted_answer_boundary(text, question_start, match, speaker_counts):
    if match is None:
        return False
    speaker = match.group("speaker").strip()
    if not speaker or speaker.casefold().startswith(("http", "https")):
        return False
    if speaker.startswith(("A", "Ａ", "答", "回答")):
        return True
    question_text = text[question_start:match.start()].strip()
    return bool(re.search(r"[?？]", question_text)) or speaker_counts.get(speaker, 0) >= 2


def _slice_blocks(blocks, start_block, start_char, end_block, end_char):
    if start_block > end_block or (start_block == end_block and start_char >= end_char):
        return ""
    parts = []
    for index in range(start_block, end_block + 1):
        text = blocks[index][1]
        left = start_char if index == start_block else 0
        right = end_char if index == end_block else len(text)
        part = text[left:right].strip()
        if part:
            parts.append(part)
    return "\n".join(parts).strip()


def extract_qa_pairs(blocks):
    normalized = [(int(order), str(text or "")) for order, text in blocks]
    if not normalized:
        return []
    speaker_counts = _speaker_counts(normalized)

    questions = []
    for block_index, (_order, text) in enumerate(normalized):
        for match in QUESTION_RE.finditer(text):
            questions.append((block_index, match.start(), match.end()))
    if not questions:
        return []

    pairs = []
    for index, (block_index, _question_start, question_end) in enumerate(questions):
        next_question = questions[index + 1] if index + 1 < len(questions) else None
        text = normalized[block_index][1]
        explicit_answer = ANSWER_RE.search(text, question_end)
        generic_answer = SPEAKER_RE.search(text, question_end)
        same_block_answer = explicit_answer or generic_answer
        if generic_answer and not _accepted_answer_boundary(
                text, question_end, generic_answer, speaker_counts):
            continue
        if next_question and next_question[0] == block_index and next_question[1] < (
                same_block_answer.start() if same_block_answer else len(text)):
            same_block_answer = None

        if same_block_answer is not None:
            question_text = text[question_end:same_block_answer.start()].strip()
            answer_char = (same_block_answer.end() if same_block_answer is explicit_answer
                           else same_block_answer.start())
            answer_start = (block_index, answer_char)
            if next_question and next_question[0] == block_index:
                answer_limit = (block_index, next_question[1])
            else:
                answer_limit = (block_index, len(text))
        else:
            question_text = text[question_end:].strip()
            answer_start = (block_index + 1, 0)
            answer_limit = ((next_question[0], next_question[1]) if next_question
                            else (len(normalized) - 1, len(normalized[-1][1])))

        answer_text = ""
        if answer_start <= answer_limit:
            answer_text = _clean_answer(_slice_blocks(
                normalized, answer_start[0], answer_start[1],
                answer_limit[0], answer_limit[1],
            ))

        if (_substantive(question_text) < MIN_CONTENT_CHARS
                or _substantive(answer_text) < MIN_CONTENT_CHARS):
            continue

        end_block = answer_limit[0]
        if answer_limit[1] == 0 and end_block > answer_start[0]:
            end_block -= 1
        end_block = max(answer_start[0], min(end_block, len(normalized) - 1))
        pairs.append({
            "start": normalized[block_index][0],
            "end": normalized[end_block][0],
            "q": question_text,
            "a": answer_text,
        })
    return pairs


def build_answer_excerpt(answer, pattern, max_chars=420):
    """Return a compact answer excerpt around a match, or the first few turns."""
    text = str(answer or "").strip()
    if not text:
        return "", False
    lines = text.splitlines() or [text]
    match = pattern.search(text) if pattern is not None else None
    if match is not None:
        matched_line = text.count("\n", 0, match.start())
        start = max(0, matched_line - 2)
        end = min(len(lines), matched_line + 3)
    else:
        start = 0
        end = min(len(lines), 4)

    excerpt = "\n".join(lines[start:end]).strip()
    while len(excerpt) > max_chars and end - start > 1:
        if match is None:
            end -= 1
        elif matched_line - start >= end - matched_line - 1 and start < matched_line:
            start += 1
        elif end > matched_line + 1:
            end -= 1
        else:
            break
        excerpt = "\n".join(lines[start:end]).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rstrip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(lines) or len("\n".join(lines[start:end]).strip()) > len(excerpt) else ""
    return prefix + excerpt + suffix, (start > 0 or end < len(lines) or suffix)


def _valid_qa(q, a):
    q = str(q or "").strip()
    a = str(a or "").strip()
    if q in PLACEHOLDER_QUESTIONS:
        return False
    return _substantive(q) >= MIN_CONTENT_CHARS and _substantive(a) >= MIN_CONTENT_CHARS


def _qa_fingerprint(q, a):
    return (PUNCT_RE.sub("", str(q or "")).casefold(),
            PUNCT_RE.sub("", str(a or "")).casefold())


def _question_key(q):
    first_sentence = re.split(r"[?？。！!]", str(q or ""), maxsplit=1)[0]
    return PUNCT_RE.sub("", first_sentence).casefold()[:24]


def _locate_qa(blocks, q, a):
    q_plain = PUNCT_RE.sub("", q or "")
    a_plain = PUNCT_RE.sub("", a or "")
    a_head = a_plain[:24]
    if not q_plain or not a_head:
        return None
    for index, (order, text) in enumerate(blocks):
        if q_plain not in PUNCT_RE.sub("", text):
            continue
        nearby = blocks[index:index + 3]
        joined = PUNCT_RE.sub("", "".join(item[1] for item in nearby))
        if a_head not in joined:
            continue
        answer_order = int(order)
        for answer_order, answer_text in nearby:
            if a_head in PUNCT_RE.sub("", answer_text):
                answer_order = int(answer_order)
                break
        return int(order), answer_order
    return None


def _story_primary_docs(docs, story, blocks_by_doc):
    docs_by_id = {int(doc["id"]): doc for doc in docs}
    out = []
    order = 0
    for work in story.get("works", []):
        if work.get("work") != "访谈":
            continue
        for route in work.get("routes", []):
            for chapter in route.get("chapters", []):
                doc_id = int(chapter["doc"])
                doc = docs_by_id.get(doc_id)
                if doc is None:
                    continue
                out.append({
                    "doc": doc_id,
                    "work": work.get("work") or doc.get("work") or "",
                    "route": route.get("name") or "",
                    "chapter": chapter.get("title") or doc.get("title") or "",
                    "start": int(chapter.get("start") or 0),
                    "order": order,
                    "title": doc.get("title") or chapter.get("title") or "",
                    "kind": doc.get("kind") or "",
                })
                order += 1
    return out


def build_official_index(docs, story, story_blocks, qa_rows, interview_rows=None):
    docs = list(docs or [])
    story_blocks = list(story_blocks or [])
    qa_rows = list(qa_rows or [])

    blocks_by_doc = defaultdict(list)
    for doc_id, order, text in story_blocks:
        blocks_by_doc[int(doc_id)].append((int(order), str(text or "")))
    for rows in blocks_by_doc.values():
        rows.sort(key=lambda row: row[0])

    primary_docs = _story_primary_docs(docs, story, blocks_by_doc)
    primary_ids = {item["doc"] for item in primary_docs}
    order_by_doc = {item["doc"]: item["order"] for item in primary_docs}

    candidates = []
    for item in primary_docs:
        for pair in extract_qa_pairs(blocks_by_doc.get(item["doc"], [])):
            candidates.append({
                "doc": item["doc"], "start": pair["start"], "end": pair["end"],
                "q": pair["q"], "a": pair["a"], "source_kind": "extracted",
            })

    for row in qa_rows:
        try:
            doc_id = int(row.get("doc"))
        except (TypeError, ValueError):
            continue
        if doc_id not in primary_ids or not _valid_qa(row.get("q"), row.get("a")):
            continue
        located = _locate_qa(blocks_by_doc.get(doc_id, []), row.get("q"), row.get("a"))
        if located is None:
            continue
        start, end = located
        candidates.append({
            "doc": doc_id, "start": start, "end": end,
            "q": str(row.get("q") or "").strip(), "a": str(row.get("a") or "").strip(),
            "source_kind": "legacy",
        })

    deduped = {}
    for item in candidates:
        key = (item["doc"], _question_key(item["q"]))
        rank = (1 if item.get("source_kind") == "extracted" else 0,
                -int(item["start"]),
                len(item["q"]) + len(item["a"]),
                item["end"] - item["start"])
        if key not in deduped or rank > deduped[key][0]:
            deduped[key] = (rank, item)
    primary_qa = [item for _rank, item in deduped.values()]
    primary_qa.sort(key=lambda item: (order_by_doc.get(item["doc"], 10 ** 9),
                                      item["start"], item["doc"], item["q"]))

    docs_by_id = {int(doc["id"]): doc for doc in docs}
    supplements, seen_supplement = [], set()
    for row in qa_rows:
        try:
            doc_id = int(row.get("doc"))
        except (TypeError, ValueError):
            continue
        if doc_id in primary_ids or not _valid_qa(row.get("q"), row.get("a")):
            continue
        doc = docs_by_id.get(doc_id)
        if not doc:
            continue
        file_name = str(doc.get("file") or "")
        if doc.get("kind") not in ("访谈", "问答") or not file_name.startswith("设定本 访谈\\"):
            continue
        q = str(row.get("q") or "").strip()
        a = str(row.get("a") or "").strip()
        key = (doc_id,) + _qa_fingerprint(q, a)
        if key in seen_supplement:
            continue
        seen_supplement.add(key)
        supplements.append({
            "doc": doc_id, "start": 0, "end": 0, "q": q, "a": a,
            "source_kind": "supplement",
        })

    return {
        "version": 1,
        "primary_docs": primary_docs,
        "qa": primary_qa,
        "supplements": supplements,
        "stats": {
            "primary_docs": len(primary_docs),
            "qa": len(primary_qa),
            "supplements": len(supplements),
        },
    }

