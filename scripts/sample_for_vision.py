#!/usr/bin/env python3
"""
Deterministic stratified sample for the vision-backed pass.

`docs/PUBLIC_BENCHMARK.md`: geometry-only runs over the full corpus ($0), but
the vision pass (`--vision claude`, one model call per asset) only ever runs
over "a stratified sample of ~30-50, chosen to span generators and defect
classes" — reported as its own scope, never conflated with the full-corpus
census. This script picks that sample from the full geometry-lint results,
seeded so the selection is reproducible from the same inputs.

Stratification: each asset's stratum is (generator, primary_defect_class),
where primary_defect_class is the alphabetically-first defect class it has
(matching aggregate_results.py's DEFECT_CLASSES), or "clean" if it's a PASS
with none. Sampling round-robins one asset per stratum, in sorted stratum
order, cycling until N is reached or every stratum is exhausted — this
maximizes generator x defect-class coverage before ever taking a second
asset from the same stratum, which is what "span generators and defect
classes" actually requires (a pure random sample would just reproduce the
corpus's own generator/defect skew).

Output: a manifest of the chosen asset_ids, and — because
`verify_real_assets.py` takes a flat `--dir` of assets, not a manifest —
symlinks into `--link-dir` (default `samples/vision_sample/`) so it can be
pointed there directly without copying multi-hundred-MB files.

Terminal B (WORK):
    python scripts/sample_for_vision.py --results results/real_ai_corpus.jsonl \
        --n 40 --seed 42 --link-dir samples/vision_sample \
        --out-manifest manifests/vision_sample.jsonl

License: MIT.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batch_lint import load_result_rows  # noqa: E402
from aggregate_results import classify  # noqa: E402


def primary_defect_class(row: dict[str, Any]) -> str:
    if "error" in row:
        return "lint_error"
    classes = sorted(classify(row))
    return classes[0] if classes else "clean"


def stratified_sample(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    strata: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        key = (r.get("generator") or "unknown", primary_defect_class(r))
        strata.setdefault(key, []).append(r)

    rng = random.Random(seed)
    for members in strata.values():
        rng.shuffle(members)

    ordered_keys = sorted(strata.keys())
    chosen: list[dict[str, Any]] = []
    cursors = {k: 0 for k in ordered_keys}
    while len(chosen) < n and any(cursors[k] < len(strata[k]) for k in ordered_keys):
        for k in ordered_keys:
            if len(chosen) >= n:
                break
            if cursors[k] < len(strata[k]):
                chosen.append(strata[k][cursors[k]])
                cursors[k] += 1
    return chosen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, metavar="RESULTS.jsonl")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--source-dir", default=str(ROOT / "samples" / "real_ai_corpus"),
                    help="directory the original assets live in (asset_id == filename there)")
    ap.add_argument("--link-dir", default=str(ROOT / "samples" / "vision_sample"))
    ap.add_argument("--out-manifest", required=True, type=Path)
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    rows = load_result_rows(Path(args.results))
    rows = [r for r in rows if "error" not in r]  # a lint error has no asset to render
    if not rows:
        print("No usable rows in --results.", file=sys.stderr)
        return 2

    chosen = stratified_sample(rows, args.n, args.seed)

    link_dir = Path(args.link_dir)
    link_dir.mkdir(parents=True, exist_ok=True)
    source_dir = Path(args.source_dir)
    missing = []
    for r in chosen:
        src = source_dir / r["asset_id"]
        dst = link_dir / r["asset_id"]
        if not src.is_file():
            missing.append(str(src))
            continue
        if dst.is_symlink() or dst.exists():
            dst.unlink()
        dst.symlink_to(src.resolve())

    args.out_manifest.parent.mkdir(parents=True, exist_ok=True)
    args.out_manifest.write_text(
        "\n".join(json.dumps({
            "asset_id": r["asset_id"], "generator": r.get("generator"),
            "verdict": r.get("verdict"), "stratum_defect_class": primary_defect_class(r),
        }) for r in chosen) + "\n", encoding="utf-8")

    by_gen: dict[str, int] = {}
    by_class: dict[str, int] = {}
    for r in chosen:
        by_gen[r.get("generator") or "unknown"] = by_gen.get(r.get("generator") or "unknown", 0) + 1
        by_class[primary_defect_class(r)] = by_class.get(primary_defect_class(r), 0) + 1

    print(f"Sampled {len(chosen)} asset(s) -> {link_dir} (manifest: {args.out_manifest})")
    print(f"Generators covered: {len(by_gen)}  ·  defect classes covered: {len(by_class)}")
    print(f"By generator: {dict(sorted(by_gen.items()))}")
    print(f"By defect class: {dict(sorted(by_class.items()))}")
    if missing:
        print(f"WARNING: {len(missing)} asset(s) not found on disk, skipped: {missing[:5]}...",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
