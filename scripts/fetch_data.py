# -*- coding: utf-8 -*-
"""Download and install the runtime data archive for Type-Moon Search."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEST = ROOT / "data"
REQUIRED_FILES = (
    "corpus.txt",
    "entries.json",
    "offsets.json",
    "story.json",
    "story_blocks.json",
    "fgo_story.json",
    "occurrence_locations.json",
    "official_interviews.json",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_extract(archive: Path, target: Path) -> None:
    target = target.resolve()
    with zipfile.ZipFile(archive) as bundle:
        total = sum(info.file_size for info in bundle.infolist())
        if total > 1024 * 1024 * 1024:
            raise RuntimeError("data archive expands beyond 1 GiB")
        for info in bundle.infolist():
            destination = (target / info.filename).resolve()
            if target != destination and target not in destination.parents:
                raise RuntimeError(f"unsafe archive entry: {info.filename}")
        bundle.extractall(target)


def install_data(source: Path, dest: Path, force: bool) -> None:
    if dest.exists() and any(p.name != "README.md" for p in dest.iterdir()) and not force:
        raise FileExistsError(f"{dest} already contains data; use --force to overwrite")
    dest.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name == "README.md":
            continue
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and install Type-Moon Search data")
    parser.add_argument("--url", default=os.environ.get("TM_SEARCH_DATA_URL", ""))
    parser.add_argument("--sha256", default=os.environ.get("TM_SEARCH_DATA_SHA256", ""))
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--force", action="store_true", help="overwrite existing data files")
    args = parser.parse_args()

    if not args.url or not args.sha256:
        parser.error("provide --url and --sha256, or set TM_SEARCH_DATA_URL and TM_SEARCH_DATA_SHA256")

    expected = args.sha256.strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        parser.error("--sha256 must be a 64-character hexadecimal SHA-256 value")

    with tempfile.TemporaryDirectory(prefix="tm-search-data-") as tmp:
        temp = Path(tmp)
        archive = temp / "data.zip"
        print(f"downloading: {args.url}")
        with urllib.request.urlopen(args.url, timeout=120) as response, archive.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)

        actual = sha256_file(archive)
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch\n expected: {expected}\n actual:   {actual}")

        extracted = temp / "extracted"
        extracted.mkdir()
        safe_extract(archive, extracted)
        candidates = list(extracted.iterdir())
        if len(candidates) == 1 and candidates[0].is_dir() and candidates[0].name == "data":
            source = candidates[0]
        else:
            source = extracted

        install_data(source, args.dest.resolve(), args.force)
        missing = [name for name in REQUIRED_FILES if not (args.dest / name).is_file()]
        if missing:
            raise RuntimeError("missing required data files: " + ", ".join(missing))

    print(f"data installed to: {args.dest.resolve()}")
    print("SHA-256 verified")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
