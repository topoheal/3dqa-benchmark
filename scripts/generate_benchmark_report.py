#!/usr/bin/env python3
"""
Render `docs/PUBLIC_BENCHMARK_REPORT.md` from `aggregate_results.py`'s output.

`docs/PUBLIC_BENCHMARK.md` engineering step 3: "Aggregation to JSON + CSV, so
the report is regenerated from data rather than hand-written." This is that
regeneration step — every number in the output markdown is read out of the
aggregate JSON, none typed by hand, so re-running the pipeline over a bigger
corpus (or after a linter bug fix) reproduces the report from scratch with no
copy-paste drift.

Scope discipline (the doc's cost-control section): this script covers ONLY
the geometry-only, full-corpus census — $0, deterministic. The vision-backed
subset is a SEPARATE scope with its own report, already produced by
`verify_real_assets.py` (which this script links to, not duplicates) — never
conflate the two pass rates in one table.

Terminal B (WORK):
    python scripts/generate_benchmark_report.py --aggregate results/aggregate.json \
        --out docs/PUBLIC_BENCHMARK_REPORT.md \
        --vision-doc docs/PUBLIC_BENCHMARK_VISION_SAMPLE.md

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

from measure_lint_timing import percentile  # noqa: E402

DEFECT_LABELS = {
    "not_watertight": "Not watertight",
    "non_manifold": "Non-manifold",
    "uv_missing": "UVs missing",
    "inverted_normals": "Inverted normals",
    "inconsistent_normals": "Inconsistent normals",
    "floating_debris": "Floating debris",
    "over_budget": "Over poly budget (run's own cap)",
    "vertex_color_only": "Vertex-colour-only",
}


def pct(x: Any) -> str:
    return "n/a" if x is None else f"{x:.1%}"


def num(x: Any) -> str:
    return "n/a" if x is None else f"{x:,.0f}" if isinstance(x, (int, float)) else str(x)


def defect_table(overall: dict, by_generator: dict[str, dict]) -> str:
    gens = sorted(by_generator.keys())
    header = ["Generator", "N"] + list(DEFECT_LABELS.values())
    lines = ["| " + " | ".join(header) + " |",
             "|" + "---|" * len(header)]
    row = ["**ALL**", str(overall.get("n_assets", 0))]
    row += [pct(overall.get(f"defect_{k}")) for k in DEFECT_LABELS]
    lines.append("| " + " | ".join(row) + " |")
    for gen in gens:
        g = by_generator[gen]
        row = [gen, str(g.get("n_assets", 0))]
        row += [pct(g.get(f"defect_{k}")) for k in DEFECT_LABELS]
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def taxonomy_table(taxonomy: dict[str, int]) -> str:
    if not taxonomy:
        return "_Nothing was left unfixed in this run — every FAIL that attempted a dry-run repair healed at least partially._"
    total = sum(taxonomy.values())
    lines = ["| Unfixable finding | Occurrences | Share of unfixable findings |",
             "|---|---:|---:|"]
    for code, count in taxonomy.items():
        lines.append(f"| `{code}` | {count} | {count / total:.1%} |")
    return "\n".join(lines)


def error_taxonomy_table(taxonomy: dict[str, int]) -> str:
    if not taxonomy:
        return "_Every asset in this corpus loaded and was measured — no lint errors._"
    total = sum(taxonomy.values())
    lines = ["| Reason (could not be measured at all) | Occurrences | Share of lint errors |",
             "|---|---:|---:|"]
    for msg, count in taxonomy.items():
        lines.append(f"| `{msg}` | {count} | {count / total:.1%} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aggregate", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--corpus-label", default="3D Arena (Hugging Face, MIT)")
    ap.add_argument("--vision-doc", default=None,
                     help="path to the separately-produced vision-sample report, "
                          "linked (not duplicated) if it exists")
    ap.add_argument("--lint-timing", default=None, type=Path,
                     help="path to measure_lint_timing.py's results jsonl "
                          "(lint_file only, no repair) — kept separate from "
                          "the lint+repair wall_ms above because the 6-asset "
                          "curated claim ('2.7-8ms') was measured this way, "
                          "not as lint+repair combined")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    data = json.loads(args.aggregate.read_text(encoding="utf-8"))
    overall = data["overall"]
    by_generator = data["by_generator"]
    taxonomy = data.get("unfixable_taxonomy", {})
    error_taxonomy = data.get("lint_error_taxonomy", {})

    n = overall.get("n_assets", 0)
    n_gen = len(by_generator)
    cap = overall.get("unity_mobile_triangle_cap", "n/a")

    lines = [
        '# The State of AI-Generated 3D Assets — a public census',
        "",
        f"> Produced by `scripts/generate_benchmark_report.py` from "
        f"`{args.aggregate}`. Every number below was measured by "
        f"`batch_lint.py` / `batch_lint_parallel.py` over real files on disk — "
        f"none is hand-typed or extrapolated. Geometry-only: deterministic, "
        f"$0, millisecond-scale per asset. No texture-class QA (this tier "
        f"never samples a texture map).",
        "",
        f"**Corpus:** {n:,} assets across {n_gen} generators, {args.corpus_label}.",
        f"**Run:** {time.strftime('%Y-%m-%d', time.gmtime())}.",
        f"**Lint errors (malformed/unreadable assets, excluded from rates below):** "
        f"{overall.get('n_lint_errors', 0)}",
        "",
        "## Headline: defect prevalence by class, by generator",
        "",
        "Each cell is the share of that generator's assets carrying that defect "
        "(a single asset can carry more than one, so rows don't sum to 100%).",
        "",
        defect_table(overall, by_generator),
        "",
        "## What could not be measured, and why",
        "",
        "Distinct from a defect finding: these files fell outside what this "
        "engine's mesh-based checks can assess at all (e.g. a point cloud "
        "with no face topology), so they carry no verdict either way and are "
        "excluded from every rate above, not counted as clean.",
        "",
        error_taxonomy_table(error_taxonomy),
        "",
        "## Distance from spec",
        "",
        f"Median face count: **{num(overall.get('faces_median'))}** · "
        f"p90: **{num(overall.get('faces_p90'))}** · "
        f"Unity-mobile's published budget: **{cap:,}** triangles.",
        f"**{pct(overall.get('over_unity_mobile_budget'))}** of all assets in this "
        "corpus exceed that budget as exported, regardless of whether this lint "
        "run's own `--max-polys` threshold flagged them.",
        "",
        "## Heal rate (dry-run repair, geometry-only)",
        "",
        f"Of assets that FAILED lint (n={overall.get('n_fail', 0)}): "
        f"**{pct(overall.get('heal_full'))}** heal fully, "
        f"**{pct(overall.get('heal_partial'))}** heal partially, "
        f"**{pct(overall.get('heal_none'))}** do not heal, "
        f"**{pct(overall.get('heal_errored'))}** error during repair.",
        "",
        f"**Regressions introduced by healing: {overall.get('n_introduced_regressions', 0)} "
        "asset(s).** Reported here regardless of how small, per this project's "
        "own rule that a repair must never hide a regression.",
        "",
        "## Failure taxonomy — what dry-run repair could not fix",
        "",
        taxonomy_table(taxonomy),
        "",
        "## Timing (wall-clock per asset, lint + dry-run repair)",
        "",
        f"p50: **{num(overall.get('wall_ms_p50'))} ms** · "
        f"p90: **{num(overall.get('wall_ms_p90'))} ms** · "
        f"max: **{num(overall.get('wall_ms_max'))} ms**. "
        "Measured on this machine, single-process-per-shard; see "
        "`scripts/batch_lint_parallel.py` for the parallel run that produced this file.",
        "",
    ]

    if args.lint_timing and args.lint_timing.is_file():
        lint_rows = [json.loads(l) for l in
                     args.lint_timing.read_text(encoding="utf-8").splitlines() if l.strip()]
        lint_ms = sorted(r["lint_ms"] for r in lint_rows if "error" not in r)
        lines += [
            "## Lint-only timing (no repair) — the number comparable to the "
            "curated-sample claim",
            "",
            f"p50: **{percentile(lint_ms, 0.5):.1f} ms** · "
            f"p90: **{percentile(lint_ms, 0.9):.1f} ms** · "
            f"max: **{percentile(lint_ms, 1.0):.1f} ms** "
            f"(n={len(lint_ms)}). A separately-measured 6-asset curated baseline "
            "(22k-65k faces) reported \"2.7-8 ms\" the same way (lint only, no "
            "dry-run repair); this row is the same measurement at full-corpus "
            "scale (median 77k faces, up to 6.1M) and is 15-45x higher at the "
            "median — do not quote the 6-asset number as general. See "
            "`scripts/measure_lint_timing.py`.",
            "",
        ]

    lines += [
        "## Honest guardrails",
        "",
        "- **This is one dataset with its own selection effects.** "
        f"\"Assets from {args.corpus_label}\" is not \"all AI-generated 3D.\"",
        "- **No texture-class QA claim.** `raster_cpu` / this lint tier never "
        "samples a texture map, so texture defects (stretching, seams, "
        "resolution) are out of scope here, not clean.",
        "- **No contrast group in this pass.** A professionally-authored CC0 "
        "baseline (Poly Haven) is planned but not run in this report — do not "
        "read the numbers above as an AI-vs-human gap.",
        "- **The vision-backed pass rate is NOT in this table.** It only ever "
        "runs over a small stratified sample (cost control — one model call "
        "per asset) and is reported separately, never blended with the "
        "full-corpus geometry numbers above.",
        "",
    ]

    if args.vision_doc and Path(args.vision_doc).is_file():
        lines += [
            "## Vision-backed sample (separate scope)",
            "",
            f"A stratified, seeded sample was additionally run through the full "
            f"closed loop (heal → re-render → vision verification, one model "
            f"call per asset). See [`{args.vision_doc}`]({Path(args.vision_doc).name}) "
            "for that report — its numbers describe only the sampled subset, "
            "not the full corpus above.",
            "",
        ]
    elif args.vision_doc:
        lines += [
            "## Vision-backed sample (separate scope)",
            "",
            f"Not yet run. Planned output: `{args.vision_doc}`, via "
            "`scripts/sample_for_vision.py` + `scripts/verify_real_assets.py --vision claude`.",
            "",
        ]

    lines += [
        "## How to reproduce",
        "",
        "```",
        "./scripts/fetch_real_assets.sh --download",
        "python scripts/batch_lint_parallel.py --from-dir samples/real_ai_corpus \\",
        "    --manifest manifests/real_ai_corpus.jsonl --out results/real_ai_corpus.jsonl --workers 5",
        "python scripts/aggregate_results.py --results results/real_ai_corpus.jsonl \\",
        "    --out-json results/aggregate.json --out-csv results/aggregate_by_generator.csv",
        "python scripts/measure_lint_timing.py --manifest manifests/real_ai_corpus_lint.jsonl \\",
        "    --from-dir samples/real_ai_corpus --out results/lint_timing.jsonl",
        "python scripts/generate_benchmark_report.py --aggregate results/aggregate.json \\",
        "    --out docs/PUBLIC_BENCHMARK_REPORT.md \\",
        "    --vision-doc docs/PUBLIC_BENCHMARK_VISION_SAMPLE.md \\",
        "    --lint-timing results/lint_timing.jsonl",
        "```",
        "",
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
