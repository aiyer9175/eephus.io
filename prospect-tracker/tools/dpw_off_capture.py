# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""OFF byte-identity capture for the $/WAR path build (VAL_5, DESIGN_v2 section 9).

Two subcommands, both read-only over the repository:

  snapshot --out <dir>   extract the dollar fields of every priced payload and
                         copy the two series files whole into <dir>, which must
                         lie OUTSIDE the repository
  diff <a> <b>           compare two snapshots: dollar fields of the priced
                         payloads, and the two series files byte for byte;
                         exit 1 when anything differs

The build commit runs the same exporter chain at the pre-change HEAD and with
the build applied (flag OFF), on the same calendar day, on the same database,
with the FanGraphs drop folder empty, and quotes the diff. Artifact identity is
proven here, never in pytest (pytest must not regenerate artifacts).

A "dollar field" is a numeric leaf whose key names money (usd, _mm, surplus,
npv, value, dpw, rational, salary, guarantee, aav, price, cost, payroll, deal,
cash, sur...). Every other numeric leaf is counted and reported separately,
so pipeline noise outside the priced fields is visible without gating.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

PRICED = ["mlb_projections.json", "fa_class.json", "fa_class_2028.json", "fa_class_2029.json",
          "xfv.json", "trade_values.json", "timeseries.json", "ledger_board.json",
          "franchise_board.json"]
PRICED_GLOBS = ["ledger_clubs/*.json", "franchise_clubs/*.json"]
WHOLE = ["fa_meta.json", "fa_dpw_series.json"]

MONEY = re.compile(
    r"(usd|Usd|USD|_mm$|_mm_|Mm$|surplus|Surplus|^sur$|^sur[A-Z_]|npv|Npv|NPV|value|Value|"
    r"dpw|Dpw|rational|Rational|salary|Salary|^sal[A-Z_]|guar|Guar|aav|AAV|Aav|price|Price|"
    r"cost|Cost|payroll|Payroll|deal|Deal|cash|Cash|money|dollar|Dollar|level_usd)")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _walk(node, path: str, key: str, out_money: dict, out_other: dict) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _walk(v, f"{path}/{k}", str(k), out_money, out_other)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}[{i}]", key, out_money, out_other)
    elif isinstance(node, bool) or node is None or isinstance(node, str):
        return
    elif isinstance(node, (int, float)):
        (out_money if MONEY.search(key) else out_other)[path] = node


def _priced_files() -> list[Path]:
    files = [DATA / n for n in PRICED]
    for g in PRICED_GLOBS:
        files += sorted(DATA.glob(g))
    return files


def snapshot(out: Path) -> dict:
    out = out.resolve()
    if ROOT in out.parents or out == ROOT:
        raise SystemExit(f"refusing to write inside the repository: {out}")
    out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"priced": {}, "whole": {}}
    for p in _priced_files():
        rel = p.relative_to(DATA).as_posix()
        if not p.exists():
            manifest["priced"][rel] = None
            continue
        doc = json.loads(p.read_text(encoding="utf-8"))
        money: dict = {}
        other: dict = {}
        _walk(doc, "", "", money, other)
        dst = out / "priced" / (rel.replace("/", "__"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps({"money": money, "other": other}, separators=(",", ":")),
                       encoding="utf-8")
        manifest["priced"][rel] = {"sha256": _sha(p), "n_money": len(money), "n_other": len(other)}
    for n in WHOLE:
        p = DATA / n
        if p.exists():
            shutil.copyfile(p, out / ("whole__" + n))
            manifest["whole"][n] = _sha(p)
        else:
            manifest["whole"][n] = None
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def diff(a: Path, b: Path, show: int = 20) -> int:
    ma = json.loads((a / "manifest.json").read_text(encoding="utf-8"))
    mb = json.loads((b / "manifest.json").read_text(encoding="utf-8"))
    bad = 0
    lines = []
    for n in WHOLE:
        if ma["whole"].get(n) != mb["whole"].get(n):
            bad += 1
            lines.append(f"WHOLE {n}: sha {ma['whole'].get(n)} -> {mb['whole'].get(n)}")
        else:
            lines.append(f"WHOLE {n}: byte-identical ({ma['whole'].get(n)})")
    for rel in sorted(set(ma["priced"]) | set(mb["priced"])):
        ea, eb = ma["priced"].get(rel), mb["priced"].get(rel)
        if ea is None or eb is None:
            if ea != eb:
                bad += 1
                lines.append(f"PRICED {rel}: present {ea is not None} -> {eb is not None}")
            continue
        fa = json.loads((a / "priced" / rel.replace("/", "__")).read_text(encoding="utf-8"))
        fb = json.loads((b / "priced" / rel.replace("/", "__")).read_text(encoding="utf-8"))
        dm = [k for k in set(fa["money"]) | set(fb["money"]) if fa["money"].get(k) != fb["money"].get(k)]
        do = [k for k in set(fa["other"]) | set(fb["other"]) if fa["other"].get(k) != fb["other"].get(k)]
        bad += len(dm)
        lines.append(f"PRICED {rel}: {len(fa['money'])} dollar fields, {len(dm)} differ; "
                     f"{len(fa['other'])} other numeric fields, {len(do)} differ (not gated)")
        for k in sorted(dm)[:show]:
            lines.append(f"   $ {k}: {fa['money'].get(k)} -> {fb['money'].get(k)}")
    print("\n".join(lines))
    print(f"RESULT: {'EMPTY' if bad == 0 else f'{bad} difference(s)'}")
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--out", required=True)
    d = sub.add_parser("diff")
    d.add_argument("a")
    d.add_argument("b")
    args = ap.parse_args(argv)
    if args.cmd == "snapshot":
        m = snapshot(Path(args.out))
        print(json.dumps({k: (v or {}).get("n_money") if isinstance(v, dict) else v
                          for k, v in m["priced"].items()}, indent=1))
        print(json.dumps(m["whole"], indent=1))
        return 0
    return diff(Path(args.a), Path(args.b))


if __name__ == "__main__":
    sys.exit(main())
