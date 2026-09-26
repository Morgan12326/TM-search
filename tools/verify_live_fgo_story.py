# -*- coding: utf-8 -*-
"""Verify the live service actually serves the repaired FGO story reader."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.server import SERVER_BUILD


class LiveCheckError(RuntimeError):
    pass


def fetch_json(base_url: str, path: str, params=None):
    url = base_url.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            if response.status != 200:
                raise LiveCheckError(f"{path} returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LiveCheckError(f"{path} returned HTTP {exc.code}: {body[:120]}") from exc


def check(condition, message):
    if not condition:
        raise LiveCheckError(message)


def verify(base_url: str):
    status = fetch_json(base_url, "/api/status")
    check(status.get("build") == SERVER_BUILD,
          f"running service build {status.get('build')!r} != {SERVER_BUILD!r}; restart required")

    tree = fetch_json(base_url, "/api/story/tree")["tree"]
    fgo = next((child for top in tree for child in top.get("children", [])
                if child.get("key") == "work:FGO"), None)
    check(fgo is not None, "FGO is missing from /api/story/tree")
    check(fgo.get("chapters") == 394,
          f"FGO chapter count is {fgo.get('chapters')!r}, expected 394")

    root = fetch_json(base_url, "/api/story/node", {"key": "work:FGO"})
    check(root.get("children"), "FGO route list is empty")
    route = fetch_json(base_url, "/api/story/node", {"key": root["children"][0]["key"]})
    first = (route.get("children") or [None])[0]
    check(first is not None, "first FGO route has no chapters")
    check(first.get("official") == "FGO", "FGO chapter card is missing official metadata")
    check(first.get("id") == 100, f"first FGO chapter id is {first.get('id')!r}, expected 100")
    check(first.get("section_count") == 11,
          f"first FGO section count is {first.get('section_count')!r}, expected 11")

    official = fetch_json(base_url, "/api/official/chapter", {"work": "FGO", "id": 100})
    legacy = fetch_json(base_url, "/api/fgo/chapter", {"id": 100})
    for label, chapter in (("official", official), ("legacy", legacy)):
        check(chapter.get("title") == "特异点F 燃烧污染都市 冬木",
              f"{label} endpoint returned the wrong title")
        check(len(chapter.get("chapters") or []) == 11,
              f"{label} endpoint did not return 11 sections")
        check(chapter.get("lines") == 1028,
              f"{label} endpoint returned {chapter.get('lines')!r} lines, expected 1028")
        check("啾……啾……" in chapter["chapters"][0]["lines"][0]["t"],
              f"{label} endpoint first line does not contain expected text")

    search = fetch_json(base_url, "/api/search", {"q": "啾……啾……", "limit": 50})
    occurrence = next((item for item in search.get("occurrences", [])
                       if item.get("jump") == {
                           "kind": "official", "work": "FGO", "id": 100, "section": 0,
                       }), None)
    check(occurrence is not None, "search result has no official jump to FGO id=100 section=0")
    target = official["chapters"][occurrence["jump"]["section"]]
    check("啾……啾……" in "\n".join(line["t"] for line in target.get("lines", [])),
          "official jump target section does not contain the searched text")

    return {
        "build": status["build"],
        "fgo_chapters": fgo["chapters"],
        "first_chapter": official["title"],
        "first_sections": len(official["chapters"]),
        "first_lines": official["lines"],
        "occurrence_jump": occurrence["jump"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args(argv)
    try:
        result = verify(args.base_url)
    except Exception as exc:  # noqa: BLE001 - CLI should report the exact failed check
        print(f"FAIL: {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("PASS: live FGO story reader verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
