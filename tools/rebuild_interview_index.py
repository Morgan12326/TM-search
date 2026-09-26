# -*- coding: utf-8 -*-
"""Rebuild the official-answer and interview search index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.official_interviews import build_official_index


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_from_data_dir(data_dir):
    data_dir = Path(data_dir)
    entries = read_json(data_dir / "entries.json")
    story = read_json(data_dir / "story.json")
    story_blocks = read_json(data_dir / "story_blocks.json")
    return build_official_index(
        entries.get("docs") or [],
        story,
        story_blocks,
        entries.get("qa") or [],
        entries.get("interviews") or [],
    )


def write_index(data_dir, output_path=None):
    payload = build_from_data_dir(data_dir)
    target = Path(output_path) if output_path else Path(data_dir) / "official_interviews.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target, payload


def check_index(data_dir, output_path=None):
    payload = build_from_data_dir(data_dir)
    target = Path(output_path) if output_path else Path(data_dir) / "official_interviews.json"
    current = read_json(target)
    if current != payload:
        raise RuntimeError("official_interviews.json is out of date")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    parser.add_argument("--output")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if not args.write and not args.check:
        parser.error("choose --write or --check")
    if args.write:
        target, payload = write_index(args.data_dir, args.output)
        print("wrote %s: %s" % (target, json.dumps(payload["stats"], ensure_ascii=False)))
    if args.check:
        payload = check_index(args.data_dir, args.output)
        print("check passed: %s" % json.dumps(payload["stats"], ensure_ascii=False))


if __name__ == "__main__":
    main()
