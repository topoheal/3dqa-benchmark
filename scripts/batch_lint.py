#!/usr/bin/env python3
"""
Batch geometry-only lint + dry-run heal over a manifest, with resume-on-failure.

`docs/PUBLIC_BENCHMARK.md` step 1 (engineering section): `triage_real_assets.py`
already proves the per-asset shape (lint + dry-run repair) over six assets held
in memory for one process lifetime — fine at 6, not survivable at hundreds or
thousands. This script is the same measurement restructured around a durable
manifest and an append-only, resumable results file, so a crash (or an OOM'd
asset, or a Ctrl-C) at asset 900 does not discard the first 899.

No vision, no rendering — `geometry_linter.lint_file` + `repair_engine.repair`
(dry-run) only, exactly as `docs/PUBLIC_BENCHMARK.md`'s cost-control section
specifies for a full-corpus census: deterministic, $0, millisecond-scale.

Two independent survival mechanisms, matching the two ways a batch run over
hundreds of untrusted assets actually dies:
  1. Per-asset try/except — one malformed asset raises a Python exception,
     recorded as an error row, the run continues. (Doesn't catch a hard
     interpreter crash — see 2.)
  2. Append-only results file, fsync'd after every asset, with the manifest
     loop skipping any asset_id already present on start — survives the
     WHOLE PROCESS dying (OOM-killed, Ctrl-C, power loss), because nothing
     is held in memory that isn't already durable on disk.

Manifest schema (JSON Lines, one object per line):
    {"asset_id": str, "path": str, "source": str, "generator": str}

Terminal B (WORK):
    python scripts/batch_lint.py --from-dir samples/real_ai \
        --manifest manifests/real_ai.jsonl --out results/real_ai.jsonl

Re-running the same command after a partial run resumes automatically —
completed asset_ids in --out are skipped, not re-processed.

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

from geometry_linter import Thresholds, lint_file  # noqa: E402
from repair_engine import repair  # noqa: E402

SUFFIXES = {".glb", ".gltf", ".obj", ".ply", ".stl"}


def build_manifest_from_dir(src: Path, source: str) -> list[dict[str, str]]:
    """One manifest entry per supported asset in `src`, sorted for determinism.
    Parses the `{Generator}__{name}.ext` convention `fetch_real_assets.sh`
    already writes; falls back to the bare filename when a file doesn't
    follow it, so this never raises on an unexpected name."""
    entries = []
    for p in sorted(src.glob("*")):
        if p.suffix.lower() not in SUFFIXES:
            continue
        stem = p.stem
        generator = stem.split("__", 1)[0] if "__" in stem else "unknown"
        entries.append({
            "asset_id": p.name,
            "path": str(p.resolve()),
            "source": source,
            "generator": generator,
        })
    return entries


def load_manifest(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def write_manifest(path: Path, entries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


def load_result_rows(path: Path) -> list[dict[str, Any]]:
    """All syntactically valid rows in a results file. A truncated/corrupt
    trailing line (the exact shape a mid-write crash leaves behind) is
    skipped, not fatal — every consumer of a results file (the resume check,
    the end-of-run summary, the aggregator) must agree on this tolerance, or
    a crash that resume already recovered from re-surfaces as a crash in
    whichever reader didn't skip the stale corrupt line still sitting in the
    file (it's never rewritten — only appended past)."""
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def ensure_trailing_newline(path: Path) -> None:
    """A results file truncated mid-write (a crash) can end without a
    trailing newline. Appending onto that with `open(path, "a")` — the
    resume path's normal write — concatenates the next row directly onto
    the garbage tail instead of starting a new line, corrupting that one
    row into unparseable garbage too. Since that row can never register as
    "done" (its own id lives inside a line that fails to parse), the asset
    would be silently recomputed and silently re-lost on every subsequent
    run, forever. Pre-empt it once, before any appending happens."""
    if not path.is_file() or path.stat().st_size == 0:
        return
    with open(path, "rb") as f:
        f.seek(-1, 2)
        if f.read(1) != b"\n":
            with open(path, "a", encoding="utf-8") as f2:
                f2.write("\n")


def load_completed_ids(out_path: Path) -> set[str]:
    """Asset IDs already recorded in a prior (possibly interrupted) run —
    the resume mechanism. That one asset behind a corrupt line is simply
    re-processed, which is always safe since nothing here mutates the input
    asset."""
    return {r["asset_id"] for r in load_result_rows(out_path) if "asset_id" in r}


def _metric(cert: dict, check: str, key: str, default=None):
    for f in cert["findings"]:
        if f["check"] == check:
            return f["metrics"].get(key, default)
    return default


def process_one(entry: dict[str, str], thresholds: Thresholds) -> dict[str, Any]:
    """Lint + dry-run heal one asset. Never raises — a bad asset becomes an
    error row, not a dead batch."""
    row: dict[str, Any] = {
        "asset_id": entry["asset_id"], "source": entry.get("source"),
        "generator": entry.get("generator"),
    }
    t0 = time.perf_counter()
    try:
        cert = lint_file(entry["path"], thresholds)
    except Exception as exc:
        row["error"] = f"lint: {type(exc).__name__}: {exc}"
        row["wall_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        return row

    row["verdict"] = cert["verdict"]
    row["faces"] = cert["geometry"]["faces"]
    row["vertices"] = cert["geometry"]["vertices"]
    row["is_watertight"] = cert["geometry"]["is_watertight"]
    row["errors"] = [f["code"] for f in cert["findings"]
                     if not f["passed"] and f["severity"] == "error"]
    row["warnings"] = [f["code"] for f in cert["findings"]
                       if not f["passed"] and f["severity"] == "warning"]
    row["has_uv"] = _metric(cert, "uv_coordinates", "has_uv")
    row["debris_faces"] = _metric(cert, "floating_clusters", "debris_faces")
    row["visual_kind"] = _metric(cert, "appearance", "visual_kind")

    if row["verdict"] == "PASS":
        row["heal"] = "n/a"
        row["wall_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
        return row

    try:
        rep = repair(entry["path"], thresholds=thresholds, dry_run=True)
        row["fixed"] = rep["repair"]["fixed"]
        row["unfixable"] = [u["code"] for u in rep["repair"]["unfixable"]]
        row["introduced"] = rep["repair"]["introduced"]
        row["heal"] = ("full" if rep["verdict"] == "PASS"
                       else ("partial" if rep["repair"]["fixed"] else "no"))
    except Exception as exc:
        row["heal"] = f"ERROR {type(exc).__name__}: {exc}"

    row["wall_ms"] = round((time.perf_counter() - t0) * 1000.0, 1)
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, metavar="MANIFEST.jsonl",
                    help="manifest path; built from --from-dir if it doesn't exist yet")
    ap.add_argument("--from-dir", default=None, metavar="DIR",
                    help="build the manifest from this directory (only used "
                         "when --manifest doesn't already exist)")
    ap.add_argument("--source", default="local", metavar="NAME",
                    help="source label recorded on each manifest entry built "
                         "from --from-dir (e.g. 3d_arena)")
    ap.add_argument("--out", required=True, metavar="RESULTS.jsonl",
                    help="append-only results file; resumed automatically if present")
    ap.add_argument("--max-polys", type=int, default=50_000)
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    manifest_path = Path(args.manifest)
    if not manifest_path.is_file():
        if not args.from_dir:
            print(f"No manifest at {manifest_path} and no --from-dir given.",
                  file=sys.stderr)
            return 2
        entries = build_manifest_from_dir(Path(args.from_dir), args.source)
        if not entries:
            print(f"No supported assets in {args.from_dir}.", file=sys.stderr)
            return 2
        write_manifest(manifest_path, entries)
        print(f"Built manifest: {len(entries)} asset(s) -> {manifest_path}")

    manifest = load_manifest(manifest_path)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    ensure_trailing_newline(out_path)
    completed = load_completed_ids(out_path)
    pending = [e for e in manifest if e["asset_id"] not in completed]

    print(f"Manifest: {len(manifest)} asset(s) · already done: {len(completed)} "
          f"· pending: {len(pending)}\n")
    if not pending:
        print("Nothing to do — every manifest entry is already in the results file.")
        return 0

    thresholds = Thresholds(max_polys=args.max_polys)
    processed = 0
    with open(out_path, "a", encoding="utf-8") as out_fh:
        for entry in pending:
            row = process_one(entry, thresholds)
            out_fh.write(json.dumps(row) + "\n")
            out_fh.flush()
            processed += 1
            if "error" in row:
                print(f"  {row['asset_id'][:48]:50s} ERROR {row['error'][:60]}")
            else:
                print(f"  {row['asset_id'][:48]:50s} {row['verdict']:8s} "
                      f"heal={row['heal']:<8} {row['faces']:>8,}f  "
                      f"{row['wall_ms']:.1f} ms")

    all_rows = load_result_rows(out_path)
    ok = [r for r in all_rows if "error" not in r]
    print(f"\nProcessed this run: {processed}  ·  total in {out_path}: {len(all_rows)}")
    print(f"PASS: {sum(1 for r in ok if r['verdict']=='PASS')}/{len(ok)}  ·  "
          f"heal full: {sum(1 for r in ok if r.get('heal')=='full')}  ·  "
          f"heal partial: {sum(1 for r in ok if r.get('heal')=='partial')}  ·  "
          f"errors: {len(all_rows) - len(ok)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
