# -*- coding: utf-8 -*-
"""Recover Chinese blocks that were previously stored as untranslated Japanese."""
import argparse
import json
import os
import re


KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
CHINESE_SIGNAL_CHARS = frozenset(
    "的是了这這为為而就都也我你他她它们們说說到有在把被与與和跟对對从從将將能会會不没沒有么麼嗎呢吧啊"
)
CHINESE_PUNCTUATION = ("，", "；", "：")


def looks_like_chinese_block(text):
    """Conservatively identify prose that is Chinese rather than Japanese."""
    text = text or ""
    han = len(HAN_RE.findall(text))
    kana = len(KANA_RE.findall(text))
    if han < 8:
        return False
    kana_ratio = kana / float(han + kana)
    if kana_ratio > 0.18:
        return False
    signals = sum(1 for char in text if char in CHINESE_SIGNAL_CHARS)
    strong_punctuation = any(char in text for char in CHINESE_PUNCTUATION)
    if kana_ratio <= 0.08:
        return signals >= 2 or (signals >= 1 and strong_punctuation and han >= 12)
    return signals >= 6 and strong_punctuation and han >= 20


def build_recovery(jp_rows, base_corpus_length):
    """Split Japanese-block rows into recovered Chinese rows and remaining rows."""
    recovered = []
    remaining = []
    for row in jp_rows:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("invalid jp_blocks row: %r" % (row,))
        doc_id, order, text = row
        if not isinstance(doc_id, int) or not isinstance(order, int) or not isinstance(text, str):
            raise ValueError("invalid jp_blocks row types: %r" % (row,))
        target = recovered if looks_like_chinese_block(text) else remaining
        if target is recovered:
            recovered.append({"doc": doc_id, "order": order, "text": text})
        else:
            remaining.append([doc_id, order, text])
    return {
        "version": 1,
        "base_corpus_length": int(base_corpus_length),
        "blocks": recovered,
    }, remaining


def load_recovered_blocks(data_dir):
    """Load and validate the optional recovered-Chinese sidecar."""
    path = os.path.join(data_dir, "zh_recovered_blocks.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("unsupported zh_recovered_blocks.json version")
    base_length = payload.get("base_corpus_length")
    blocks = payload.get("blocks")
    if not isinstance(base_length, int) or not isinstance(blocks, list):
        raise ValueError("invalid zh_recovered_blocks.json header")
    normalized = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("invalid recovered block: %r" % (block,))
        doc_id, order, text = block.get("doc"), block.get("order"), block.get("text")
        if not isinstance(doc_id, int) or not isinstance(order, int) or not isinstance(text, str):
            raise ValueError("invalid recovered block: %r" % (block,))
        normalized.append({"doc": doc_id, "order": order, "text": text})
    return {"version": 1, "base_corpus_length": base_length, "blocks": normalized}


def _write_json(path, payload, pretty=False):
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8", newline="\n") as handle:
        if pretty:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        else:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
    os.replace(temp_path, path)


def write_recovery(data_dir):
    corpus_path = os.path.join(data_dir, "corpus.txt")
    jp_path = os.path.join(data_dir, "jp_blocks.json")
    with open(corpus_path, encoding="utf-8") as handle:
        corpus_length = len(handle.read())
    with open(jp_path, encoding="utf-8") as handle:
        jp_rows = json.load(handle)
    recovery, remaining = build_recovery(jp_rows, corpus_length)
    _write_json(os.path.join(data_dir, "zh_recovered_blocks.json"), recovery, pretty=True)
    _write_json(jp_path, remaining)
    return recovery, remaining


def check_recovery(data_dir):
    corpus_path = os.path.join(data_dir, "corpus.txt")
    jp_path = os.path.join(data_dir, "jp_blocks.json")
    with open(corpus_path, encoding="utf-8") as handle:
        corpus_length = len(handle.read())
    with open(jp_path, encoding="utf-8") as handle:
        jp_rows = json.load(handle)
    recovery = load_recovered_blocks(data_dir)
    if recovery is None:
        raise AssertionError("zh_recovered_blocks.json is missing")
    if recovery["base_corpus_length"] != corpus_length:
        raise AssertionError("recovery baseline does not match corpus.txt")
    recovered_rows = [(b["doc"], b["order"], b["text"]) for b in recovery["blocks"]]
    remaining_rows = [(d, o, t) for d, o, t in jp_rows]
    if len(recovered_rows + remaining_rows) != len(set(recovered_rows + remaining_rows)):
        raise AssertionError("recovered and remaining rows overlap or contain duplicates")
    if any(not looks_like_chinese_block(text) for _, _, text in recovered_rows):
        raise AssertionError("recovered list contains a non-Chinese row")
    if any(looks_like_chinese_block(text) for _, _, text in remaining_rows):
        raise AssertionError("jp_blocks.json still contains Chinese prose")
    return len(recovered_rows), len(remaining_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
    parser.add_argument("--write", action="store_true", help="rewrite jp_blocks.json and create the sidecar")
    parser.add_argument("--check", action="store_true", help="validate an existing recovery partition")
    args = parser.parse_args()
    if args.write:
        recovery, remaining = write_recovery(args.data_dir)
        print("recovered %d blocks; %d remain Japanese" % (len(recovery["blocks"]), len(remaining)))
    if args.check:
        recovered, remaining = check_recovery(args.data_dir)
        print("checked %d recovered blocks and %d Japanese blocks" % (recovered, remaining))
    if not args.write and not args.check:
        parser.error("choose --write or --check")


if __name__ == "__main__":
    main()
