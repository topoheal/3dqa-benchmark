# Reproducing this census

Everything in `README.md` was measured, not estimated, by the scripts in this
repo running against the published `3dqa` PyPI package — not against any
private source. You do not need access to this project's engineering repo to
reproduce any number here.

## 1. Environment

```
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install "3dqa[repair,fast]"
```

`3dqa[repair,fast]` pulls in everything the runner needs for full auto-heal
(quadric decimation, UV unwrap, hole-filling) and the fast connected-components
path. `pip show 3dqa` should report the same version this census was run
against — check the top of `README.md` for the run date, and
[the PyPI project page](https://pypi.org/project/3dqa/) for release history.

## 2. Fetch the corpus

```
./scripts/fetch_real_assets.sh                 # dry run: manifest + size estimate, downloads nothing
./scripts/fetch_real_assets.sh --download      # ~22 GB, one-time, from Hugging Face directly
```

This downloads real outputs from the [3D Arena](https://huggingface.co/datasets/3d-arena/3d-arena)
dataset (MIT) — no account or token needed. Assets land in
`samples/real_ai_corpus/` (gitignored — this repo does not redistribute
third-party assets, only measurements over them).

## 3. Run the census

```
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

All four commands are resumable — interrupt and re-run any of them and
already-completed assets are skipped, not reprocessed
(`batch_lint.py`/`measure_lint_timing.py`'s append-only results files).

`--workers 5` matches what this machine used; scale to your own core count.
Wall-clock time depends heavily on the corpus's own face-count distribution
(see README.md's timing section) — expect hours, not minutes, for the full
2,300+ asset corpus on a single machine.

## 4. Compare

Diff your `results/aggregate.json` against the one already committed in this
repo. They should match exactly on every count (defect prevalence, heal
rates, regression counts) — this is deterministic, geometry-only computation,
no randomness anywhere in this path. Timing numbers (`wall_ms`, the
lint-only percentiles) will differ by machine; everything else should not.

If your numbers disagree on anything other than timing, that is either a
`3dqa` version mismatch (pin the version from `README.md`'s run date) or a
real bug — please open an issue with your `results/aggregate.json` attached.

## 5. The vision-backed sample (partial reproduction only)

`manifests/vision_sample.jsonl` lists exactly which 40 assets were sampled
and how (`scripts/sample_for_vision.py`, deterministic/seeded — you can
re-run the sampling step yourself against your own `results/real_ai_corpus.jsonl`
to confirm the same 40 assets get selected). Re-running the actual vision
pass (render + Claude API call per asset) requires the closed-loop verifier,
which is not part of the published `3dqa` package or this repo — that scope
is intentionally kept separate (see `PUBLIC_BENCHMARK_VISION_SAMPLE.md`'s own
notes on run-to-run variance in that layer).

## What's NOT reproducible from this repo alone

- **Timing numbers** are machine-specific by nature — reproduce the
  *relationship* (lint-only vs. lint+repair, percentile shape), not the exact
  milliseconds.
- **The vision-backed sample's exact pass/fail counts** — see step 5 above.
- **The engine's internal implementation** — `geometry_linter`/`repair_engine`
  are consumed here as an installed dependency, by design (see this repo's
  own `LICENSE` for what governs the runner vs. what governs the package).
