#!/usr/bin/env python3
"""
Enumerate the full 3D Arena corpus over the HF tree API — no download.

`docs/PUBLIC_BENCHMARK.md` step 1: `fetch_real_assets.sh`'s hand-curated
6-entry FILES array doesn't scale to "the full corpus". This replaces it with
a programmatic listing: paginate the HF tree API
(`/api/datasets/3d-arena/3d-arena/tree/main/outputs?recursive=true`) — it
returns 50 entries per page and a `Link: rel="next"` cursor, not the whole
tree in one call — and keep only files this engine can ingest today (the same
`SUFFIXES` `batch_lint.py` already uses to filter a local directory, imported
rather than re-declared so the two lists cannot drift).

Writes a download manifest (JSON Lines: generator, name, remote path, size)
and prints a count/size summary. Never downloads a file — that is
`fetch_real_assets.sh`'s job, over the manifest this produces.

Terminal B (WORK):
    python scripts/list_3d_arena_assets.py --manifest manifests/3d_arena_corpus.jsonl

License: MIT.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batch_lint import SUFFIXES  # noqa: E402 — single source of truth for ingestable formats

API_BASE = "https://huggingface.co/api/datasets/3d-arena/3d-arena/tree/main/outputs"
DOWNLOAD_BASE = "https://huggingface.co/datasets/3d-arena/3d-arena/resolve/main"
PAGE_LIMIT = 100
LINK_NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')


def fetch_page(url: str) -> tuple[list[dict[str, Any]], str | None]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read())
        link = resp.headers.get("Link", "")
    m = LINK_NEXT_RE.search(link)
    next_url = m.group(1) if m else None
    return body, next_url


def walk_tree() -> list[dict[str, Any]]:
    """All entries under outputs/, following pagination to exhaustion."""
    entries: list[dict[str, Any]] = []
    url = f"{API_BASE}?recursive=true&expand=true&limit={PAGE_LIMIT}"
    seen_urls: set[str] = set()
    while url and url not in seen_urls:
        seen_urls.add(url)
        page, url = fetch_page(url)
        entries.extend(page)
    return entries


def build_manifest(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per ingestable file: generator, name, remote path, size."""
    rows = []
    for e in entries:
        if e.get("type") != "file":
            continue
        path = e["path"]  # e.g. "outputs/TripoSR/a_bird.glb"
        parts = path.split("/", 2)
        if len(parts) != 3:
            continue  # not two levels deep (outputs/<generator>/<file>) — skip
        _, generator, name = parts
        if Path(name).suffix.lower() not in SUFFIXES:
            continue
        rows.append({
            "generator": generator,
            "name": name,
            "remote_path": path,
            "size_bytes": e.get("size", 0),
        })
    rows.sort(key=lambda r: (r["generator"], r["name"]))
    return rows


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def summarize(rows: list[dict[str, Any]]) -> str:
    total_bytes = sum(r["size_bytes"] for r in rows)
    by_ext: dict[str, list[int]] = {}
    by_gen: dict[str, list[int]] = {}
    for r in rows:
        ext = Path(r["name"]).suffix.lower()
        by_ext.setdefault(ext, []).append(r["size_bytes"])
        by_gen.setdefault(r["generator"], []).append(r["size_bytes"])

    lines = []
    lines.append(f"Generators: {len(by_gen)}")
    lines.append(f"Ingestable files (suffixes {sorted(SUFFIXES)}): {len(rows)}")
    lines.append(f"Total download size: {total_bytes / 1e9:.1f} GB ({total_bytes:,} bytes)")
    lines.append("")
    lines.append("By format:")
    for ext, sizes in sorted(by_ext.items(), key=lambda kv: -sum(kv[1])):
        lines.append(f"  {ext:<6} {len(sizes):>5} files  {sum(sizes) / 1e9:>7.2f} GB")
    lines.append("")
    lines.append("By generator (sorted by count):")
    for gen, sizes in sorted(by_gen.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"  {gen:<20} {len(sizes):>5} files  {sum(sizes) / 1e6:>8.1f} MB")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=ROOT / "manifests" / "3d_arena_corpus.jsonl")
    ap.add_argument("--generator", action="append", default=None,
                     help="Restrict to this generator (repeatable). Default: all.")
    args = ap.parse_args()

    entries = walk_tree()
    rows = build_manifest(entries)
    if args.generator:
        wanted = set(args.generator)
        rows = [r for r in rows if r["generator"] in wanted]

    write_manifest(args.manifest, rows)
    print(f"Manifest written: {args.manifest} ({len(rows)} rows)\n", file=sys.stderr)
    print(summarize(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
