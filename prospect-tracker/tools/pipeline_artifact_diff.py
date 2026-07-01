# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""pipeline_artifact_diff.py — before/after output-diff harness for run_monthly.

The deferred runtime optimizations (skip the redundant GRPO retrain, elide the
double timeseries/xfv/trade export on the monthly->daily rebuild chain, etc.)
must be PROVEN output-neutral before shipping: the committed rule is that a
runtime finding needs before/after diffs of timeseries / xfv / trade, not just a
faster wall clock. This tool captures a stable, timestamp-independent content
fingerprint of the key pipeline artifacts so two runs can be compared.

Usage:
    # baseline (current pipeline)
    python tools/pipeline_artifact_diff.py snapshot before
    # ... apply the optimization, re-run the pipeline ...
    python tools/pipeline_artifact_diff.py snapshot after
    # prove the artifacts are byte-identical (ignoring generated-at timestamps)
    python tools/pipeline_artifact_diff.py diff before after
        -> exit 0 if every artifact matches, 1 if any content changed.

Fingerprints are written under data/_artifact_fingerprints/<label>.json and are
git-ignored scratch (safe to delete). Volatile metadata keys (generated_at, run
summaries, freshness stamps) are stripped before hashing so an unchanged run does
not read as "changed" merely because the clock advanced.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAP_DIR = DATA / "_artifact_fingerprints"

# The substantive pipeline outputs a runtime optimization must not perturb.
# `content_key` (when set) narrows the hash to the meaningful sub-document so an
# outer metadata reshuffle doesn't mask a real change (and vice versa).
ARTIFACTS = [
    {"file": "timeseries.json",   "content_key": "players"},
    {"file": "xfv.json",          "content_key": None},
    {"file": "trade_values.json", "content_key": None},
    {"file": "grpo_scores.json",  "content_key": "all_scores"},
    {"file": "milb_translation.json", "content_key": None},
]

# Metadata field names stripped (recursively) before hashing — they legitimately
# change every run and would otherwise swamp a real content diff.
VOLATILE_KEYS = frozenset({
    "generated_at", "generated_from", "inserted_at", "built_at", "as_of",
    "timestamp", "data_freshness", "run", "run_summary",
})


def _strip_volatile(obj):
    """Recursively drop volatile metadata keys so the hash reflects only content."""
    if isinstance(obj, dict):
        return {k: _strip_volatile(v) for k, v in obj.items()
                if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip_volatile(x) for x in obj]
    return obj


def fingerprint_file(path: Path, content_key: str | None = None) -> dict | None:
    """Return {sha256, canon_len} for `path`, or None if it is missing/unreadable.
    Hashes the canonical (sorted, volatile-stripped) JSON of the whole document,
    or just document[content_key] when given."""
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"error": str(exc)}
    if content_key is not None and isinstance(doc, dict):
        doc = doc.get(content_key)
    canon = json.dumps(_strip_volatile(doc), sort_keys=True,
                       separators=(",", ":"), default=str)
    return {"sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
            "canon_len": len(canon)}


def snapshot(label: str, data_dir: Path = DATA) -> dict:
    """Fingerprint every known artifact under `data_dir` and persist the result."""
    result = {}
    for spec in ARTIFACTS:
        fp = fingerprint_file(data_dir / spec["file"], spec["content_key"])
        result[spec["file"]] = fp if fp is not None else {"missing": True}
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"{label}.json").write_text(
        json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")
    return result


def _load_snapshot(label: str) -> dict:
    path = SNAP_DIR / f"{label}.json"
    if not path.exists():
        raise SystemExit(f"no snapshot '{label}' at {path} — run `snapshot {label}` first")
    return json.loads(path.read_text(encoding="utf-8"))


def diff(label_a: str, label_b: str) -> int:
    """Compare two snapshots. Returns 0 if all artifacts match, 1 otherwise."""
    a, b = _load_snapshot(label_a), _load_snapshot(label_b)
    changed = False
    for spec in ARTIFACTS:
        f = spec["file"]
        fa, fb = a.get(f, {"missing": True}), b.get(f, {"missing": True})
        if fa == fb:
            state = "same" if not fa.get("missing") else "absent"
            print(f"  [=] {f:<26} {state}")
        else:
            changed = True
            print(f"  [~] {f:<26} CHANGED  {label_a}={fa.get('sha256', fa)[:12] if isinstance(fa.get('sha256'), str) else fa}"
                  f"  {label_b}={fb.get('sha256', fb)[:12] if isinstance(fb.get('sha256'), str) else fb}")
    verdict = "IDENTICAL (output-neutral)" if not changed else "DIFFERENCES FOUND"
    print(f"\n{label_a} vs {label_b}: {verdict}")
    return 1 if changed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot", help="fingerprint current artifacts under a label")
    s.add_argument("label")
    d = sub.add_parser("diff", help="compare two snapshots")
    d.add_argument("label_a")
    d.add_argument("label_b")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        res = snapshot(args.label)
        n = sum(1 for v in res.values() if "sha256" in v)
        print(f"snapshot '{args.label}': fingerprinted {n}/{len(ARTIFACTS)} artifacts "
              f"-> {SNAP_DIR / (args.label + '.json')}")
        return 0
    return diff(args.label_a, args.label_b)


if __name__ == "__main__":
    sys.exit(main())
