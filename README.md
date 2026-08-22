# The State of AI-Generated 3D Assets, a public census

> Produced by `scripts/generate_benchmark_report.py` from `results/aggregate.json`. Every number below was measured by `batch_lint.py` / `batch_lint_parallel.py` over real files on disk — none is hand-typed or extrapolated. Geometry-only: deterministic, $0, millisecond-scale per asset. No texture-class QA (this tier never samples a texture map).

**Corpus:** 2,307 assets across 23 generators, 3D Arena (Hugging Face, MIT).
**Run:** 2026-08-01.
**Lint errors (malformed/unreadable assets, excluded from rates below):** 303

## Attribution

All assets analyzed here come from the [**3D Arena**](https://huggingface.co/datasets/3d-arena/3d-arena)
dataset on Hugging Face, dataset-level licensed **MIT**. This repo does not
redistribute the assets themselves (`manifests/3d_arena_corpus.jsonl` lists
their remote paths; `scripts/fetch_real_assets.sh` re-downloads them from the
original source) only the measurements taken over them. Full credit for
the underlying generative outputs and the dataset's curation goes to the 3D
Arena project and the individual generator teams whose outputs it hosts.

## Headline: defect prevalence by class, by generator

Each cell is the share of that generator's assets carrying that defect (a single asset can carry more than one, so rows don't sum to 100%).

| Generator | N | Not watertight | Non-manifold | UVs missing | Inverted normals | Inconsistent normals | Floating debris | Over poly budget (run's own cap) | Vertex-colour-only |
|---|---|---|---|---|---|---|---|---|---|
| **ALL** | 2307 | 40.1% | 9.7% | 39.7% | 0.0% | 1.8% | 4.7% | 61.9% | 14.9% |
| 3DTopia-XL | 101 | 36.6% | 0.0% | 0.0% | 0.0% | 1.0% | 21.8% | 48.5% | 0.0% |
| 404_GEN | 101 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| Hi3DGen | 101 | 29.7% | 0.0% | 100.0% | 0.0% | 0.0% | 1.0% | 100.0% | 0.0% |
| Hunyuan3D-2 | 101 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| Hunyuan3D-2.1 | 101 | 2.0% | 2.0% | 0.0% | 0.0% | 0.0% | 3.0% | 0.0% | 0.0% |
| IM-MA | 101 | 84.2% | 53.5% | 100.0% | 0.0% | 4.0% | 16.8% | 0.0% | 100.0% |
| InstantMesh | 101 | 10.9% | 2.0% | 100.0% | 0.0% | 14.9% | 13.9% | 82.2% | 0.0% |
| LGM | 101 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| MeshFormer | 93 | 26.9% | 0.0% | 100.0% | 0.0% | 0.0% | 1.1% | 100.0% | 0.0% |
| Meshy-5 | 98 | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 86.7% | 0.0% |
| Meshy-6 | 101 | 99.0% | 0.0% | 0.0% | 0.0% | 0.0% | 1.0% | 100.0% | 0.0% |
| Real3D | 101 | 100.0% | 44.6% | 100.0% | 0.0% | 0.0% | 2.0% | 99.0% | 100.0% |
| SAM-3D-Objects-3DGS | 101 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |
| SF3D | 101 | 3.0% | 3.0% | 0.0% | 0.0% | 0.0% | 1.0% | 1.0% | 0.0% |
| SPAR3D | 101 | 1.0% | 1.0% | 0.0% | 0.0% | 0.0% | 1.0% | 7.9% | 0.0% |
| Strawb3rry | 101 | 15.8% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 99.0% | 0.0% |
| Strawberrry | 101 | 37.6% | 4.0% | 0.0% | 0.0% | 0.0% | 1.0% | 44.6% | 0.0% |
| TRELLIS | 100 | 60.0% | 0.0% | 0.0% | 0.0% | 0.0% | 3.0% | 4.0% | 0.0% |
| TRELLIS.2-4B | 101 | 91.1% | 14.9% | 0.0% | 0.0% | 5.0% | 6.9% | 100.0% | 0.0% |
| TripoSG | 101 | 39.6% | 32.7% | 100.0% | 0.0% | 0.0% | 5.9% | 100.0% | 0.0% |
| TripoSR | 97 | 100.0% | 14.4% | 100.0% | 0.0% | 0.0% | 8.2% | 69.1% | 100.0% |
| Unique3D | 101 | 49.5% | 6.9% | 100.0% | 0.0% | 11.9% | 4.0% | 100.0% | 0.0% |
| Zaohaowu3D | 101 | 14.9% | 13.9% | 0.0% | 0.0% | 0.0% | 2.0% | 100.0% | 0.0% |

## What could not be measured, and why

Distinct from a defect finding: these files fell outside what this engine's mesh-based checks can assess at all (e.g. a point cloud with no face topology), so they carry no verdict either way and are excluded from every rate above, not counted as clean.

| Reason (could not be measured at all) | Occurrences | Share of lint errors |
|---|---:|---:|
| `lint: ValueError: Unsupported load result type: PointCloud` | 303 | 100.0% |

## Distance from spec

Median face count: **77,402** · p90: **618,085** · Unity-mobile's published budget: **30,000** triangles.
**79.8%** of all assets in this corpus exceed that budget as exported, regardless of whether this lint run's own `--max-polys` threshold flagged them.

## Heal rate (dry-run repair, geometry-only)

Of assets that FAILED lint (n=1501): **45.0%** heal fully, **49.8%** heal partially, **5.1%** do not heal, **0.0%** error during repair.

**Regressions introduced by healing: 454 asset(s).** Reported here regardless of how small, per this project's own rule that a repair must never hide a regression.

## Failure taxonomy, what dry-run repair could not fix

| Unfixable finding | Occurrences | Share of unfixable findings |
|---|---:|---:|
| `UNCLOSED_HOLES` | 577 | 88.1% |
| `NON_MANIFOLD_EDGES` | 55 | 8.4% |
| `FLOATING_GEOMETRY` | 15 | 2.3% |
| `NORMALS_INCONSISTENT` | 7 | 1.1% |
| `POLY_COUNT_EXCEEDED` | 1 | 0.2% |

## Timing (wall-clock per asset, lint + dry-run repair)

p50: **15,458 ms** · p90: **45,358 ms** · max: **450,462 ms**. Measured on this machine, single-process-per-shard; see `scripts/batch_lint_parallel.py` for the parallel run that produced this file.

## Lint-only timing (no repair), the number comparable to the curated-sample claim

p50: **128.6 ms** · p90: **1294.3 ms** · max: **32061.5 ms** (n=2004). A separately-measured 6-asset curated baseline (22k-65k faces) reported "2.7-8 ms" the same way (lint only, no dry-run repair); this row is the same measurement at full-corpus scale (median 77k faces, up to 6.1M) and is 15-45x higher at the median — do not quote the 6-asset number as general. See `scripts/measure_lint_timing.py`.

## Honest guardrails

- **This is one dataset with its own selection effects.** "Assets from 3D Arena (Hugging Face, MIT)" is not "all AI-generated 3D."
- **No texture-class QA claim.** `raster_cpu` / this lint tier never samples a texture map, so texture defects (stretching, seams, resolution) are out of scope here, not clean.
- **No contrast group in this pass.** A professionally-authored CC0 baseline (Poly Haven) is planned but not run in this report — do not read the numbers above as an AI-vs-human gap.
- **The vision-backed pass rate is NOT in this table.** It only ever runs over a small stratified sample (cost control — one model call per asset) and is reported separately, never blended with the full-corpus geometry numbers above.

## Vision-backed sample (separate scope)

A stratified, seeded sample was additionally run through the full closed loop (heal → re-render → vision verification, one model call per asset). See [`docs/PUBLIC_BENCHMARK_VISION_SAMPLE.md`](PUBLIC_BENCHMARK_VISION_SAMPLE.md) for that report — its numbers describe only the sampled subset, not the full corpus above.

## How to reproduce

See `REPRODUCE.md` for the full walkthrough. Short version:

```
python3 -m venv .venv && source .venv/bin/activate
pip install "3dqa[repair,fast]"          # the published package this runner depends on

./scripts/fetch_real_assets.sh --download                     # ~22 GB, one-time
python scripts/batch_lint_parallel.py --from-dir samples/real_ai_corpus \
    --manifest manifests/real_ai_corpus.jsonl --out results/real_ai_corpus.jsonl --workers 5
python scripts/measure_lint_timing.py --manifest manifests/real_ai_corpus_lint.jsonl \
    --from-dir samples/real_ai_corpus --out results/lint_timing.jsonl
python scripts/aggregate_results.py --results results/real_ai_corpus.jsonl \
    --out-json results/aggregate.json --out-csv results/aggregate_by_generator.csv
python scripts/generate_benchmark_report.py --aggregate results/aggregate.json \
    --out README.md \
    --vision-doc PUBLIC_BENCHMARK_VISION_SAMPLE.md \
    --lint-timing results/lint_timing.jsonl
```

This runner imports `geometry_linter`/`repair_engine`/`qa_profiles` from the
installed `3dqa` package, nothing in this repo needs private source, which
is the whole point of publishing it this way.
