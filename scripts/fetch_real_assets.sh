#!/usr/bin/env bash
# Fetch REAL generative-AI 3D exports for sanitizer tuning / the public
# benchmark corpus (docs/PUBLIC_BENCHMARK.md).
#
# Source: the "3D Arena" dataset (MIT-licensed) — real outputs from production
# image-to-3D generators, published by HF staff for model comparison:
#   https://huggingface.co/datasets/3d-arena/3d-arena
# No account or token needed; these are public direct-download URLs.
#
# The manifest is built programmatically over the HF tree API
# (scripts/list_3d_arena_assets.py) rather than hand-curated — it walks every
# generator directory under outputs/ and keeps only formats this engine can
# ingest (batch_lint.py's SUFFIXES: .glb/.gltf/.obj/.ply/.stl), which as of
# 2026-07-31 is 2,313 files / 21.8 GB across 23 generators (docs/PUBLIC_BENCHMARK.md).
#
# SAFE BY DEFAULT: this script only lists the manifest and prints the disk
# estimate. It downloads nothing unless you pass --download.
#
# The assets land in samples/real_ai_corpus/ which is GIT-IGNORED — we tune
# against them, we do NOT redistribute them in this repo.
#
# NOT samples/real_ai/: that directory holds the original hand-curated 6-asset
# baseline `tests/test_per_target_heal.py` hard-globs with assertions
# calibrated to exactly those 6 ("all must pass, nothing introduced"). Pulling
# the full corpus into that same directory once turned 2 tests into ~3,800
# parametrized cases, most of which legitimately "fail" against the general
# population (the census itself shows nowhere near 100% heal-with-zero-
# regressions) — not a code regression, just the wrong population hitting a
# narrowly-calibrated assertion. Keeping the full corpus in its own directory
# is what prevents that recurring on every future re-run.
#
# Terminal B (WORK):
#   ./scripts/fetch_real_assets.sh                        # dry run: manifest + size estimate only
#   ./scripts/fetch_real_assets.sh --download             # actually pull the full corpus (~22 GB)
#   ./scripts/fetch_real_assets.sh --download --jobs 4    # concurrent downloads (default 4)
#   ./scripts/fetch_real_assets.sh --download --generator TripoSR --generator Meshy-5
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/samples/real_ai_corpus"
MANIFEST="$ROOT/manifests/3d_arena_corpus.jsonl"
BASE="https://huggingface.co/datasets/3d-arena/3d-arena/resolve/main"
PYTHON="$ROOT/.venv/bin/python3"
[ -x "$PYTHON" ] || PYTHON="python3"

DOWNLOAD=0
JOBS=4
GENERATOR_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --download) DOWNLOAD=1; shift ;;
    --jobs) JOBS="$2"; shift 2 ;;
    --generator) GENERATOR_ARGS+=(--generator "$2"); shift 2 ;;
    --manifest) MANIFEST="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

echo "Querying HF tree API and building manifest -> $MANIFEST" >&2
"$PYTHON" "$ROOT/scripts/list_3d_arena_assets.py" --manifest "$MANIFEST" ${GENERATOR_ARGS[@]+"${GENERATOR_ARGS[@]}"}

if [ "$DOWNLOAD" -ne 1 ]; then
  cat >&2 <<EOF

Dry run only — nothing downloaded. Re-run with --download to pull the corpus
listed above into $OUT (git-ignored).
EOF
  exit 0
fi

command -v jq >/dev/null 2>&1 || { echo "jq is required for --download (manifest parsing)" >&2; exit 1; }

mkdir -p "$OUT"
COUNT=$(wc -l < "$MANIFEST" | tr -d ' ')
echo
echo "Downloading $COUNT files -> $OUT ($JOBS concurrent; measured aggregate "
echo "bandwidth on this connection only scales ~1.2x with concurrency, it is"
echo "not per-connection throttled, so this is a modest win, not a multiplier)"

download_one() {
  local gen="$1" name="$2" remote="$3"
  local dest="$OUT/${gen}__${name}"
  if [ -s "$dest" ]; then
    echo "  = ${gen}/${name} (already present)"
    return 0
  fi
  echo "  + ${gen}/${name}"
  curl -fsSL --retry 3 -o "$dest" "$BASE/${remote}?download=true"
}
export -f download_one
export OUT BASE

jq -r '[.generator, .name, .remote_path] | @tsv' "$MANIFEST" \
  | xargs -P "$JOBS" -L 1 bash -c 'download_one "$@"' _

echo
echo "Done. $(ls "$OUT" | wc -l | tr -d ' ') files in $OUT"
cat <<'EOF'

Next (Terminal B):
  python scripts/batch_lint_parallel.py --from-dir samples/real_ai_corpus \
      --manifest manifests/real_ai_corpus.jsonl --out results/real_ai_corpus.jsonl --workers 5
Or drop any single file onto the dashboard (Terminal A must be running uvicorn).
EOF
