# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Served-payload equivalence for the port (PORT_SPEC.md Gate C, PORT_RUNBOOK.md).

Three commands:

    python tools/port_equivalence.py snapshot --root . --out ref.json
        Record every published payload (the nightly rsync's data set) with its
        sha256 and three canonical digests. Pages and assets are recorded by
        sha256 only; Gate C covers payloads, Gate B covers pages.

    python tools/port_equivalence.py compare --ref ref.json --root /target/tree
        Sort every payload into one category and exit 1 on any DIFFERENT,
        MISSING or EXTRA file:
          IDENTICAL   same bytes
          LINE_ENDINGS same bytes once CRLF reads as LF (a Windows checkout of
                      a tracked file against the Linux box's LF checkout)
          TIMESTAMP   equal once the stamp keys below are dropped
          FLOAT_REPR  equal once numbers compare as decimals (1.0 == 1)
          ORDERING    equal once every list is sorted
          DIFFERENT   anything else (run `diff` on the pair for the leaves)

    python tools/port_equivalence.py diff REF_FILE TARGET_FILE
        Every differing leaf path with both values, numbers compared as
        decimals at full precision, no tolerance.

    python tools/port_equivalence.py selftest FILE
        Positive control: perturbs one numeric leaf of a copy of FILE in its
        last serialized place and asserts `diff` reports exactly that leaf.

The published set is computed the way deploy/nightly-build.sh's rsync computes
it: data/*.json and data/*.js at depth one minus deploy/data_exclude.txt, plus
the per-player directories in PER_PLAYER_DIRS (pinned to the script's include
lines by test_port_equivalence.py).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The per-player directories deploy/nightly-build.sh's rsync includes.
PER_PLAYER_DIRS: tuple[str, ...] = (
    "pitch_plots", "player_detail", "debuts_full", "mgmt_decisions",
    "ledger_clubs", "franchise_clubs", "mlb_events", "mlbstats_player",
    "mlb_player_detail",
)
# Leaf keys that carry a write time, not a value (the TIMESTAMP category).
STAMP_KEYS: frozenset[str] = frozenset({
    "generated_at", "built_at", "checked_at", "written_at", "stamped_at",
    "updated_at", "last_updated", "run_at", "exported_at", "refreshed_at",
    "built", "generated",
})


def _lines(path: Path) -> list[str]:
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines()
            if x.strip() and not x.strip().startswith("#")]


def payload_files(root: Path) -> list[str]:
    """Module-relative posix paths of every published payload under data/."""
    excl = set(_lines(root / "deploy" / "data_exclude.txt"))
    data = root / "data"
    out = [p.relative_to(root).as_posix() for p in sorted(data.iterdir())
           if p.is_file() and p.suffix in (".json", ".js") and p.name not in excl]
    for d in PER_PLAYER_DIRS:
        base = data / d
        if base.is_dir():
            out += sorted(p.relative_to(root).as_posix()
                          for p in base.rglob("*") if p.is_file())
    return out


def page_files(root: Path) -> list[str]:
    out: list[str] = []
    for e in _lines(root / "deploy" / "publish_paths.txt"):
        p = root / e
        if p.is_dir():
            out += sorted(f.relative_to(root).as_posix() for f in p.rglob("*")
                          if f.is_file() and "__pycache__" not in f.parts)
        elif p.is_file():
            out.append(e)
    return out


def _strip(obj, *, numbers: bool, unordered: bool):
    if isinstance(obj, dict):
        return {k: _strip(v, numbers=numbers, unordered=unordered)
                for k, v in obj.items() if k not in STAMP_KEYS}
    if isinstance(obj, list):
        items = [_strip(v, numbers=numbers, unordered=unordered) for v in obj]
        if unordered:
            items.sort(key=lambda v: json.dumps(v, sort_keys=True, default=str))
        return items
    if numbers and isinstance(obj, Decimal):
        n = obj.normalize()
        return format(n, "f") if n == n.to_integral_value() else str(n)
    if isinstance(obj, Decimal):
        return "D:" + str(obj)
    return obj


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def _load(raw: bytes):
    return json.loads(raw.decode("utf-8"), parse_float=Decimal, parse_int=Decimal)


def fingerprint(path: Path) -> dict:
    raw = path.read_bytes()
    rec = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
           "sha256_lf": hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()}
    if path.suffix == ".json":
        try:
            obj = _load(raw)
        except ValueError:
            rec["parse_error"] = True
            return rec
        rec["canon_stamp"] = _digest(_strip(obj, numbers=False, unordered=False))
        rec["canon_num"] = _digest(_strip(obj, numbers=True, unordered=False))
        rec["canon_unordered"] = _digest(_strip(obj, numbers=True, unordered=True))
    return rec


def _sha_lf(path: Path) -> str:
    """sha256 with CRLF read as LF: a page is the same page on either checkout."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def snapshot(root: Path) -> dict:
    return {
        "root": str(root),
        "payloads": {rel: fingerprint(root / rel) for rel in payload_files(root)},
        "pages": {rel: {"sha256_lf": _sha_lf(root / rel)} for rel in page_files(root)},
    }


def categorize(ref: dict, new: dict) -> str:
    if ref["sha256"] == new["sha256"]:
        return "IDENTICAL"
    if "sha256_lf" in ref and ref["sha256_lf"] == new.get("sha256_lf"):
        return "LINE_ENDINGS"
    for key, cat in (("canon_stamp", "TIMESTAMP"), ("canon_num", "FLOAT_REPR"),
                     ("canon_unordered", "ORDERING")):
        if key in ref and ref.get(key) == new.get(key):
            return cat
    return "DIFFERENT"


def compare(ref_doc: dict, root: Path) -> dict:
    ref = ref_doc["payloads"]
    now = set(payload_files(root))
    cats: dict[str, list[str]] = {}
    for rel in sorted(ref):
        if rel not in now:
            cats.setdefault("MISSING", []).append(rel)
            continue
        cats.setdefault(categorize(ref[rel], fingerprint(root / rel)), []).append(rel)
    for rel in sorted(now - set(ref)):
        cats.setdefault("EXTRA", []).append(rel)
    pages_ref = ref_doc.get("pages", {})
    page_diff = sorted(rel for rel, r in pages_ref.items()
                       if not (root / rel).is_file()
                       or _sha_lf(root / rel) != r.get("sha256_lf"))
    return {"counts": {k: len(v) for k, v in sorted(cats.items())},
            "files": cats, "pages_differing": page_diff,
            "ok": not any(k in cats for k in ("DIFFERENT", "MISSING", "EXTRA"))}


def leaf_diff(a, b, path: str = "$", out: list | None = None, cap: int = 500) -> list:
    out = [] if out is None else out
    if len(out) >= cap:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append((f"{path}.{k}", a.get(k, "<absent>"), b.get(k, "<absent>")))
            else:
                leaf_diff(a[k], b[k], f"{path}.{k}", out, cap)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{path}.length", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            leaf_diff(x, y, f"{path}[{i}]", out, cap)
    elif a != b:
        out.append((path, a, b))
    return out


def diff_files(a: Path, b: Path) -> list:
    return leaf_diff(_load(a.read_bytes()), _load(b.read_bytes()))


def _first_numeric_leaf(obj, path="$", keys=()):
    """(printed path, key list, value) of the first numeric leaf, depth first."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            hit = _first_numeric_leaf(v, f"{path}.{k}", keys + (k,))
            if hit:
                return hit
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hit = _first_numeric_leaf(v, f"{path}[{i}]", keys + (i,))
            if hit:
                return hit
    elif isinstance(obj, Decimal):
        return path, keys, obj
    return None


def _set_leaf(obj, keys: tuple, value):
    cur = obj
    for k in keys[:-1]:
        cur = cur[k]
    cur[keys[-1]] = value


def selftest(path: Path) -> dict:
    """Positive control: one unit in the last serialized place of one leaf."""
    obj = _load(path.read_bytes())
    hit = _first_numeric_leaf(obj)
    if hit is None:
        return {"ok": False, "reason": "no numeric leaf"}
    leaf, keys, val = hit
    exp = val.as_tuple().exponent
    bumped = val + Decimal(1).scaleb(exp if isinstance(exp, int) else 0)
    obj2 = copy.deepcopy(obj)
    _set_leaf(obj2, keys, bumped)
    found = leaf_diff(obj, obj2)
    return {"leaf": leaf, "before": str(val), "after": str(bumped),
            "reported": [(p_, str(x), str(y)) for p_, x, y in found],
            "ok": len(found) == 1 and found[0][0] == leaf}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--root", type=Path, default=ROOT)
    s.add_argument("--out", type=Path, required=True)
    c = sub.add_parser("compare")
    c.add_argument("--ref", type=Path, required=True)
    c.add_argument("--root", type=Path, default=ROOT)
    c.add_argument("--out", type=Path, help="write the full report here")
    d = sub.add_parser("diff")
    d.add_argument("ref_file", type=Path)
    d.add_argument("target_file", type=Path)
    t = sub.add_parser("selftest")
    t.add_argument("file", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        snap = snapshot(a.root.resolve())
        a.out.write_text(json.dumps(snap, indent=0, sort_keys=True), encoding="utf-8")
        print(json.dumps({"payloads": len(snap["payloads"]), "pages": len(snap["pages"])}))
        return 0
    if a.cmd == "compare":
        res = compare(json.loads(a.ref.read_text(encoding="utf-8")), a.root.resolve())
        if a.out:
            a.out.write_text(json.dumps(res, indent=1), encoding="utf-8")
        print(json.dumps({"counts": res["counts"], "pages_differing": len(res["pages_differing"]),
                          "ok": res["ok"]}, indent=1))
        for cat in ("DIFFERENT", "MISSING", "EXTRA"):
            for rel in res["files"].get(cat, [])[:50]:
                print(cat, rel)
        return 0 if res["ok"] else 1
    if a.cmd == "diff":
        rows = diff_files(a.ref_file, a.target_file)
        for path, x, y in rows:
            print(f"{path}\t{x}\t{y}")
        print(f"{len(rows)} differing leaves (capped at 500)")
        return 0 if not rows else 1
    res = selftest(a.file)
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
