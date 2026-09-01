# The State of AI-Generated 3D Assets — a public census

> ### ⚠️ The figures that were published in this file have been retracted.
>
> This report was generated on **2026-08-01**. A re-lint on **2026-08-17**
> (FINDING-7) superseded the heal rates, and three open findings undermine the
> per-generator defect-rate table that used to appear here. Those numbers have
> been removed rather than left standing.
>
> **The current census is published and versioned at
> [topoheal.com/census/](https://topoheal.com/census/)** — with the method, the
> per-generator table, an explicit list of the columns that are withheld and
> why, CSV and JSON downloads, and a citation block.

## Attribution

All assets analyzed come from the [**3D Arena**](https://huggingface.co/datasets/3d-arena/3d-arena)
dataset on Hugging Face, dataset-level licensed **MIT**. This repo does not
redistribute the assets themselves (`manifests/3d_arena_corpus.jsonl` lists
their remote paths; `scripts/fetch_real_assets.sh` re-downloads them from the
original source) only the measurements taken over them. Full credit for
the underlying generative outputs and the dataset's curation goes to the 3D
Arena project and the individual generator teams whose outputs it hosts.

## Reproducing it

This repo keeps the corpus manifests, the runner and the raw result artifacts.
See [REPRODUCE.md](REPRODUCE.md). The engine ships as the `3dqa` package:

    pip install 3dqa

## Why no numbers are restated here

A figure that lives in two places goes stale in one of them, and this project
has shipped two stale numbers exactly that way. Everything quantitative lives
at [topoheal.com/census/](https://topoheal.com/census/), which is generated
from its source CSV and verified against it on every build, so it cannot drift.

---

**Topoheal** — geometry inspection, non-destructive repair and certification
for 3D assets. [topoheal.com](https://topoheal.com)
