#!/usr/bin/env python3
"""
Lint-ONLY timing over a manifest — no dry-run repair.

A separately-measured "2.7-8 ms" lint-speed claim was measured by
`triage_real_assets.py` on 6 curated real assets (22k-65k faces) via an
external wall-clock wrapped tightly around `lint_file()` alone — never
including `repair()`. `batch_lint.py`'s `wall_ms` column is a DIFFERENT,
larger measurement (lint + dry-run repair combined; repair's decimation pass
dominates it) and is not comparable to the 6-asset claim. This script
reproduces the ORIGINAL measurement's shape (lint_file only) at the full
corpus's scale (2,313 assets, up to ~1M+ faces) so the two numbers can
honestly be compared, or the 6-asset number can be honestly scoped down to
"n=6" if the corpus disagrees with it.

Same resume/durability shape as `batch_lint.py`, for the same reason: a
process killed partway through 2,313 assets must not lose completed rows.

Terminal B (WORK):
    python scripts/measure_lint_timing.py \
        --manifest manifests/3d_arena_corpus.jsonl \
        --out results/lint_timing.jsonl

License: MIT.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batch_lint import (build_manifest_from_dir, load_manifest, load_result_rows,  # noqa: E402
                        ensure_trailing_newline, write_manifest)
from geometry_linter import Thresholds, lint_file  # noqa: E402


def load_completed_ids(out_path: Path) -> set[str]:
    return {r["asset_id"] for r in load_result_rows(out_path) if "asset_id" in r}


def process_one(entry: dict[str, str], thresholds: Thresholds) -> dict[str, Any]:
    """lint_file only. Never raises — a bad asset becomes an error row."""
    row: dict[str, Any] = {
        "asset_id": entry["asset_id"], "generator": entry.get("generator"),
    }
    t0 = time.perf_counter()
    try:
        cert = lint_file(entry["path"], thresholds)
    except Exception as exc:
        row["error"] = f"lint: {type(exc).__name__}: {exc}"
        row["lint_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        return row
    row["lint_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    row["faces"] = cert["geometry"]["faces"]
    row["verdict"] = cert["verdict"]
    return row


def percentile(sorted_vals: list[float], pct: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * pct
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, metavar="MANIFEST.jsonl",
                    help="asset_id/path/source/generator manifest; built from "
                         "--from-dir if it doesn't exist yet")
    ap.add_argument("--from-dir", default=None, metavar="DIR",
                    help="build the manifest from this directory (only used "
                         "when --manifest doesn't already exist)")
    ap.add_argument("--source", default="local", metavar="NAME")
    ap.add_argument("--out", required=True, metavar="RESULTS.jsonl")
    ap.add_argument("--max-polys", type=int, default=50_000)
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        if not args.from_dir:
            print(f"No manifest at {manifest_path} and no --from-dir given.",
                  file=sys.stderr)
            return 2
        entries = build_manifest_from_dir(Path(args.from_dir), args.source)
        write_manifest(manifest_path, entries)
        print(f"Built manifest: {len(entries)} asset(s) -> {manifest_path}")

    manifest = load_manifest(manifest_path)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_trailing_newline(out_path)
    completed = load_completed_ids(out_path)
    pending = [e for e in manifest if e["asset_id"] not in completed]

    print(f"Manifest: {len(manifest)} asset(s) - already done: {len(completed)} "
          f"- pending: {len(pending)}\n", flush=True)

    thresholds = Thresholds(max_polys=args.max_polys)
    with open(out_path, "a", encoding="utf-8") as out_fh:
        for i, entry in enumerate(pending):
            row = process_one(entry, thresholds)
            out_fh.write(json.dumps(row) + "\n")
            out_fh.flush()
            if i % 50 == 0 or i == len(pending) - 1:
                print(f"  [{i + 1}/{len(pending)}] {row['asset_id'][:48]:50s} "
                      f"{row.get('lint_ms', 'n/a')} ms", flush=True)

    all_rows = load_result_rows(out_path)
    ok = [r for r in all_rows if "error" not in r]
    errs = len(all_rows) - len(ok)
    times = sorted(r["lint_ms"] for r in ok)
    print(f"\nTotal: {len(all_rows)}  ok: {len(ok)}  errors: {errs}")
    if times:
        print(f"lint-only wall-clock: p50={percentile(times, 0.5):.2f} ms  "
              f"p90={percentile(times, 0.9):.2f} ms  "
              f"max={times[-1]:.2f} ms  min={times[0]:.2f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
