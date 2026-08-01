#!/usr/bin/env python3
"""
Aggregate `batch_lint.py` / `batch_lint_parallel.py` results into the census
tables `docs/PUBLIC_BENCHMARK.md` asks for.

Writes JSON (full detail, overall + per-generator) and CSV (the per-generator
table — the most quotable artifact of the whole exercise, per the doc). The
report is regenerated from these files, not hand-written, so a re-run over a
bigger corpus or a re-lint after a bug fix always reproduces the same numbers
from the same inputs.

Defect classes map 1:1 onto `geometry_linter.py`'s actual finding codes (not
re-derived — reading the codes off the linter is what keeps this honest if a
check is ever renamed). "Over budget" is measured against `unity_mobile`'s
30,000-triangle cap specifically (`qa_profiles.BUILTIN_PROFILES`), independent
of whatever `--max-polys` the lint run itself used — this is the doc's
"distance from spec" number, not the linter's own pass/fail line.

Terminal B (WORK):
    python scripts/aggregate_results.py --results results/real_ai.jsonl \
        --out-json results/aggregate.json --out-csv results/aggregate_by_generator.csv

License: MIT.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batch_lint import load_result_rows  # noqa: E402
from qa_profiles import BUILTIN_PROFILES  # noqa: E402

UNITY_MOBILE_TRI_CAP = BUILTIN_PROFILES["unity_mobile"]["geometry"]["max_triangles"]

# code -> defect class, straight off geometry_linter.py's Finding.code values.
# Matches docs/PUBLIC_BENCHMARK.md's headline list exactly: "not watertight,
# non-manifold, UVs missing, inverted normals, floating debris, over budget,
# vertex-colour-only". "over_budget" here is the linter's own POLY_COUNT_EXCEEDED
# check (against whatever --max-polys the lint run used) — a DIFFERENT number
# from `over_unity_mobile_budget` below, which is the doc's separate "distance
# from spec" metric measured against unity_mobile's 30k cap specifically,
# regardless of what --max-polys this run configured. Do not conflate the two.
DEFECT_CLASSES: dict[str, set[str]] = {
    "not_watertight": {"UNCLOSED_HOLES"},
    "non_manifold": {"NON_MANIFOLD_EDGES", "MANIFOLD_NO_EDGES"},
    "uv_missing": {"UV_MISSING"},
    "inverted_normals": {"NORMALS_INVERTED"},
    "inconsistent_normals": {"NORMALS_INCONSISTENT"},
    "floating_debris": {"FLOATING_GEOMETRY"},
    "over_budget": {"POLY_COUNT_EXCEEDED"},
    "vertex_color_only": {"VERTEX_COLOR_ONLY"},
}


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    f, c = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def classify(row: dict[str, Any]) -> set[str]:
    codes = set(row.get("errors") or []) | set(row.get("warnings") or [])
    return {cls for cls, member_codes in DEFECT_CLASSES.items() if codes & member_codes}


def summarize_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One group's row = one generator, or the whole corpus. Rates are
    fractions of `n_ok` (lint-errored assets are reported separately and
    excluded from rate denominators — they were never linted, so they carry
    no defect signal one way or the other)."""
    errored = [r for r in rows if "error" in r]
    ok = [r for r in rows if "error" not in r]
    n = len(ok)
    summary: dict[str, Any] = {"n_assets": len(rows), "n_lint_errors": len(errored), "n_ok": n}
    if n == 0:
        return summary

    summary["pass_rate"] = sum(1 for r in ok if r["verdict"] == "PASS") / n
    for cls in DEFECT_CLASSES:
        summary[f"defect_{cls}"] = sum(1 for r in ok if cls in classify(r)) / n

    faces = sorted(r["faces"] for r in ok)
    summary["faces_median"] = percentile(faces, 0.5)
    summary["faces_p90"] = percentile(faces, 0.9)
    summary["unity_mobile_triangle_cap"] = UNITY_MOBILE_TRI_CAP
    summary["over_unity_mobile_budget"] = sum(1 for f in faces if f > UNITY_MOBILE_TRI_CAP) / n

    fails = [r for r in ok if r["verdict"] == "FAIL"]
    if fails:
        nf = len(fails)
        summary["n_fail"] = nf
        summary["heal_full"] = sum(1 for r in fails if r.get("heal") == "full") / nf
        summary["heal_partial"] = sum(1 for r in fails if r.get("heal") == "partial") / nf
        summary["heal_none"] = sum(1 for r in fails if r.get("heal") == "no") / nf
        summary["heal_errored"] = sum(
            1 for r in fails if isinstance(r.get("heal"), str) and r["heal"].startswith("ERROR")) / nf
    summary["n_introduced_regressions"] = sum(1 for r in ok if r.get("introduced"))

    timings = sorted(r["wall_ms"] for r in ok if "wall_ms" in r)
    if timings:
        summary["wall_ms_p50"] = percentile(timings, 0.5)
        summary["wall_ms_p90"] = percentile(timings, 0.9)
        summary["wall_ms_max"] = timings[-1]
    return summary


def error_histogram(rows: list[dict[str, Any]]) -> dict[str, int]:
    """What could not even be MEASURED, and why — distinct from the repair
    taxonomy (which is about defects that WERE measured but not fixed). A
    lint error is not a defect finding; it means the file fell outside what
    this engine's mesh-based checks can assess at all (a real example found
    at corpus scale: some 404_GEN .ply exports are raw point clouds with no
    face topology — `trimesh.load` returns a PointCloud, not a Trimesh/Scene,
    and `lint_file` correctly refuses to fabricate a mesh verdict for it).
    Buckets on the error string with the per-file path/name stripped, so
    e.g. 50 different corrupt filenames with the same root cause collapse
    into one bucket instead of 50."""
    counts: dict[str, int] = {}
    for r in rows:
        err = r.get("error")
        if not err:
            continue
        counts[err] = counts.get(err, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def unfixable_histogram(rows: list[dict[str, Any]]) -> dict[str, int]:
    """The failure taxonomy: what dry-run repair could not fix, and how
    often. `docs/PUBLIC_BENCHMARK.md` asks for this as its own reported
    item, distinct from the defect prevalence table."""
    counts: dict[str, int] = {}
    for r in rows:
        if "error" in r:
            continue
        for code in r.get("unfixable") or []:
            counts[code] = counts.get(code, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True, nargs="+", metavar="RESULTS.jsonl",
                    help="one or more results files (e.g. a merged full-corpus file "
                         "and a separate vision-sample results file)")
    ap.add_argument("--out-json", required=True, type=Path)
    ap.add_argument("--out-csv", required=True, type=Path,
                    help="per-generator table, the headline artifact")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    rows: list[dict[str, Any]] = []
    for p in args.results:
        rows.extend(load_result_rows(Path(p)))
    if not rows:
        print("No rows found in --results.", file=sys.stderr)
        return 2

    by_generator: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_generator.setdefault(r.get("generator") or "unknown", []).append(r)

    overall = summarize_group(rows)
    out = {
        "overall": overall,
        "by_generator": {gen: summarize_group(grs) for gen, grs in sorted(by_generator.items())},
        "unfixable_taxonomy": unfixable_histogram(rows),
        "lint_error_taxonomy": error_histogram(rows),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    fieldnames = ["generator"] + list(overall.keys())
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, restval="")
        w.writeheader()
        w.writerow({"generator": "OVERALL", **overall})
        for gen, s in out["by_generator"].items():
            w.writerow({"generator": gen, **s})

    print(f"Wrote {args.out_json} and {args.out_csv}")
    print(f"Assets: {len(rows)}  ·  generators: {len(by_generator)}  ·  "
          f"lint errors: {overall['n_lint_errors']}")
    print(f"Overall PASS rate: {overall.get('pass_rate', 0):.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
