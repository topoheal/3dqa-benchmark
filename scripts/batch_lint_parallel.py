#!/usr/bin/env python3
"""
Parallel driver over `batch_lint.py` — same measurement, N worker processes.

`docs/PUBLIC_BENCHMARK.md` step 2 (engineering section): the batch runner
(`batch_lint.py`) proved resumable single-process lint+dry-run-heal over a
manifest. At 2,313 assets and ~5.8 s/asset (measured on the 6-asset proof
run; dominated by dry-run decimation on FAIL assets, not `lint_file` itself)
serial execution extrapolates to ~3.7 hours. The core is stateless — no
shared mutable state between assets — so this parallelizes safely across OS
processes.

Design: deterministic sharding, not a shared queue. Every asset's shard is
`index_in_manifest % workers`, where the index comes from the manifest's
fixed sort order (`list_3d_arena_assets.py` sorts by generator then name).
That means a given asset always lands in the same shard file across re-runs,
regardless of which subset happened to be pending — so each shard file
inherits `batch_lint.py`'s existing resume-on-crash guarantee unmodified: no
new resume logic was written here, the existing 8 tests already cover it.

This script does NOT reimplement the lint+heal path. It shells out to
`batch_lint.py` once per shard (a tested, already-correct subprocess) and
waits for all of them, then concatenates the shard result files into one
merged output. Concatenation is safe because asset_ids are unique across
shards by construction.

Terminal B (WORK):
    python scripts/batch_lint_parallel.py --from-dir samples/real_ai \
        --manifest manifests/real_ai.jsonl --out results/real_ai.jsonl \
        --workers 8

Re-running after a partial run resumes automatically, per-shard.

License: MIT.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from batch_lint import build_manifest_from_dir, write_manifest, load_result_rows  # noqa: E402


def shard_path(out: Path, i: int) -> Path:
    return out.with_suffix(f".shard{i}{out.suffix}")


def shard_manifest_path(manifest: Path, i: int) -> Path:
    return manifest.with_suffix(f".shard{i}{manifest.suffix}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, metavar="MANIFEST.jsonl",
                    help="manifest path; built from --from-dir if it doesn't exist yet")
    ap.add_argument("--from-dir", default=None, metavar="DIR")
    ap.add_argument("--source", default="local", metavar="NAME")
    ap.add_argument("--out", required=True, metavar="RESULTS.jsonl",
                    help="final merged results file (produced by concatenating shards)")
    ap.add_argument("--max-polys", type=int, default=50_000)
    ap.add_argument("--workers", type=int, default=max(1, multiprocessing.cpu_count() - 1),
                    help="worker processes; default cpu_count - 1")
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        if not args.from_dir:
            print(f"No manifest at {manifest_path} and no --from-dir given.", file=sys.stderr)
            return 2
        entries = build_manifest_from_dir(Path(args.from_dir), args.source)
        if not entries:
            print(f"No supported assets in {args.from_dir}.", file=sys.stderr)
            return 2
        write_manifest(manifest_path, entries)
        print(f"Built manifest: {len(entries)} asset(s) -> {manifest_path}")

    manifest = [json.loads(line) for line in
                manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    workers = max(1, min(args.workers, len(manifest))) if manifest else 1
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    shards: list[list[dict]] = [[] for _ in range(workers)]
    for i, entry in enumerate(manifest):
        shards[i % workers].append(entry)

    procs = []
    shard_manifests = []
    shard_outs = []
    for i, entries in enumerate(shards):
        if not entries:
            continue
        sm = shard_manifest_path(manifest_path, i)
        so = shard_path(out_path, i)
        write_manifest(sm, entries)
        shard_manifests.append(sm)
        shard_outs.append(so)
        cmd = [sys.executable, str(ROOT / "scripts" / "batch_lint.py"),
               "--manifest", str(sm), "--out", str(so), "--max-polys", str(args.max_polys)]
        procs.append(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True))

    print(f"Manifest: {len(manifest)} asset(s) across {len(procs)} worker shard(s)\n")
    logs = [""] * len(procs)
    for i, p in enumerate(procs):
        out, _ = p.communicate()
        logs[i] = out or ""
        status = "ok" if p.returncode == 0 else f"exit {p.returncode}"
        print(f"--- shard {i} ({status}) ---")
        print(logs[i].rstrip())

    # A shard file can contain a truncated trailing line from a crash mid-write
    # (batch_lint.py's own resume already tolerates this — see load_result_rows
    # — by treating that asset_id as not-done and re-appending a fresh row later
    # in the same file). Reuse the same tolerant reader for the merge rather
    # than re-deriving the skip logic here.
    all_rows = []
    for so in shard_outs:
        all_rows.extend(load_result_rows(so))
    merged_lines = [json.dumps(r) for r in all_rows]
    out_path.write_text("\n".join(merged_lines) + ("\n" if merged_lines else ""), encoding="utf-8")
    ok = [r for r in all_rows if "error" not in r]
    failed_shards = sum(1 for p in procs if p.returncode != 0)
    print(f"\nMerged: {len(all_rows)} row(s) -> {out_path}  ·  failed shard processes: {failed_shards}")
    if ok:
        print(f"PASS: {sum(1 for r in ok if r['verdict']=='PASS')}/{len(ok)}  ·  "
              f"heal full: {sum(1 for r in ok if r.get('heal')=='full')}  ·  "
              f"heal partial: {sum(1 for r in ok if r.get('heal')=='partial')}  ·  "
              f"errors: {len(all_rows) - len(ok)}")
    return 1 if failed_shards else 0


if __name__ == "__main__":
    raise SystemExit(main())
