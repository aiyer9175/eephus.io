# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-03 balance probe on the text family's missingness indicator (EFV3_B2;
SP/efv3/LANE_B.md F-B12 and the text rule in s3).

"Has a scouting report" could proxy "was on a top list", which proxies the outcome, so
report_absent is tested for label balance exactly as tools/efv_identity_balance.py tests
milb_absent: on the list-vintage frame F-LV, development vintages FIRST_TEXT_VINTAGE to
2019 (the vintages with contemporaneous text; 2011 and 2012 carry no text by rule), the
W3 > 0 share and the R3 share of the rows with the indicator against the rows without,
by side, and the indicator's partial coefficient in a linear probability model of
W3 > 0 on the within-(side, vintage) consensus percentile (a quadratic) and vintage
effects, with a player-clustered bootstrap CI95 (B_BAL draws). BALANCED when the CI95
covers zero. On a side where report_absent is not BALANCED the text column is offered
to the timing head only (efv_text_features.offered_columns).

The verdicts, the coverage receipt by (side, vintage) and the registration counts are
written under the key "text" of data/efv_identity_balance.json; every other key of that
receipt is left byte for byte (the identity tool's own output). No progress row, no
ledger row: the columns are scored only by the screening lab.

This tool joins the labels; the builder (efv_text_features.py) never sees them.
NEVER READ: list vintages 2020 and 2021 (the guard raises) and every player whose
effective debut year is 2025 or later (dropped before any statistic, count reported).
Nothing is grouped by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md).

Run:  python tools/efv_text_balance.py [--dry-run]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_identity_balance as IB  # noqa: E402
import efv_labels as L  # noqa: E402
import efv_text_features as T  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

OUT = T.BALANCE_PATH
SEED = IB.SEED
B_BAL = IB.B_BAL
VINTAGES: tuple[int, ...] = tuple(v for v in F.DEV_VINTAGES if v >= T.FIRST_TEXT_VINTAGE)
INDICATOR = "report_absent"
#: VERIFY_round1.md b19: Pipeline reports naming a later year, by snapshot year,
#: counted independently of laneB_coverage.json.
REGISTRATION = {
    "later_year_by_snapshot_year": {
        "2011": [128, 152], "2012": [278, 453], "2013": [8, 696], "2014": [13, 676],
        "2015": [19, 993], "2016": [25, 997], "2017": [31, 996], "2018": [31, 995],
        "2019": [27, 995]},
    "report_rows": 22127, "median_chars": 1431,
    "source": "SP/efv3/VERIFY_round1.md b19 (verify_text_r1.py)",
}


def build_rows(universe=None, war=None, reports=None) -> tuple[list[dict], dict, dict]:
    """(probe rows, receipt, text rows by side) on VINTAGES, R-VM players dropped."""
    universe = universe if universe is not None else F.load_universe()
    war = war if war is not None else L.war_seasons_table()
    rows, receipt = [], {"frame_rows": 0, "no_consensus": 0, "label_none": 0,
                         "dropped_rvm_players": 0, "vintages": list(VINTAGES)}
    rvm_keys = set()
    by_side: dict[str, dict[int, list[dict]]] = {}
    for side in F.SIDES:
        by_side[side] = T.text_rows(side, VINTAGES, universe=universe, reports=reports)
        for V, frame in sorted(by_side[side].items()):
            receipt["frame_rows"] += len(frame)
            labs = L.labels_for_frame(frame, universe=universe, war=war)
            for r, lab in zip(frame, labs):
                if lab.get("debut_year") is not None and \
                        int(lab["debut_year"]) >= F.R_VM_FIRST_DEBUT_YEAR:
                    rvm_keys.add(r["player_key"])
                    continue
                c = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
                if c is None:
                    receipt["no_consensus"] += 1
                    continue
                if lab.get("w3") is None:
                    receipt["label_none"] += 1
                    continue
                rows.append({"pk": r["player_key"], "V": V, "side": side, "fv": float(c),
                             "w3": float(lab["w3"]), "r3": lab.get("r3"),
                             INDICATOR: float(r[INDICATOR])})
    receipt["dropped_rvm_players"] = len(rvm_keys)
    receipt["rows_scored"] = len(rows)
    return rows, receipt, by_side


def balance(rows: list[dict], rng: np.random.Generator) -> dict:
    """The identity tool's balance formula on the one text indicator."""
    out: dict = {}
    for side in F.SIDES:
        d = [r for r in rows if r["side"] == side]
        u = IB._within([r["fv"] for r in d], [r["V"] for r in d])
        ypos = np.array([float(r["w3"] > 0) for r in d])
        r3 = np.array([np.nan if r["r3"] is None else float(r["r3"]) for r in d])
        vs = sorted({r["V"] for r in d})
        dummies = np.column_stack([[float(r["V"] == v) for r in d] for v in vs[1:]]) \
            if len(vs) > 1 else np.zeros((len(d), 0))
        cl = IB._clusters([r["pk"] for r in d])
        x = np.array([r[INDICATOR] for r in d])
        n1 = int(x.sum())
        blk = {"n": len(d), "n_with": n1, "n_without": len(d) - n1}
        if n1 == 0 or n1 == len(d):
            blk.update({"verdict": "CONSTANT", "partial": None, "ci95": None})
            out[side] = {INDICATOR: blk}
            continue
        m1, m0 = x == 1, x == 0
        blk["w3_pos_share_with"] = round(float(ypos[m1].mean()), 4)
        blk["w3_pos_share_without"] = round(float(ypos[m0].mean()), 4)
        blk["w3_pos_gap"] = round(float(ypos[m1].mean() - ypos[m0].mean()), 4)
        ok = ~np.isnan(r3)
        if (ok & m1).any() and (ok & m0).any():
            blk["r3_share_with"] = round(float(r3[ok & m1].mean()), 4)
            blk["r3_share_without"] = round(float(r3[ok & m0].mean()), 4)
        X = np.column_stack([np.ones(len(d)), u, u ** 2, dummies, x])

        def coef(ix):
            b, *_ = np.linalg.lstsq(X[ix], ypos[ix], rcond=None)
            return float(b[-1])
        point = coef(np.arange(len(d)))
        draws = []
        for _ in range(B_BAL):
            pick = rng.integers(0, len(cl), len(cl))
            ix = np.concatenate([cl[j] for j in pick])
            if x[ix].min() == x[ix].max():
                continue
            draws.append(coef(ix))
        lo, hi = (float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5)))
        blk.update({"partial": round(point, 4), "ci95": [round(lo, 4), round(hi, 4)],
                    "B_used": len(draws),
                    "verdict": "BALANCED" if lo <= 0 <= hi else "IMBALANCED"})
        out[side] = {INDICATOR: blk}
    return out


def text_block(bal: dict, receipt: dict, coverage: dict, commit: str | None) -> dict:
    # the same rule efv_text_features.offered_columns reads back off this block
    offered = {side: [T.column_name(h, side) for h in
                      (T.COLUMN_HEADS if bal[side][INDICATOR]["verdict"] == "BALANCED"
                       else ("time",))]
               for side in F.SIDES}
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_text_balance.py",
        "builder": "efv_text_features.py",
        "role": "development",
        "adjudicates": "nothing; the DS-03 missingness receipt for the text family",
        "frame": (f"lv_dev (F-LV, list vintages {VINTAGES[0]} to {VINTAGES[-1]}), "
                  f"W3 on the {L.provider()} label"),
        "label": {"provider": L.provider(), "resolved_through": L.resolved_through()},
        "guards": {"reserved_lv": sorted(F.RESERVED_LV),
                   "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
                   "reserved_vm_pins": F.reserved_vm_pins(),
                   "vintages_read": list(VINTAGES),
                   "dropped_vintages": list(T.DROPPED_VINTAGES)},
        "code": {"commit": commit, "builder_sha256": IB._sha(ROOT / "efv_text_features.py"),
                 "tool_sha256": IB._sha(Path(__file__))},
        "rows": receipt,
        "indicator": {INDICATOR: "no in-window report text on the row after the "
                                 "vintage rule and the anachronism filter"},
        "balance": bal,
        "offered_columns": offered,
        "coverage": coverage,
        "settings": {"min_df": T.MIN_DF, "ridge_alpha": T.RIDGE_ALPHA,
                     "min_report_chars": T.MIN_REPORT_CHARS,
                     "token_pattern": T.TOKEN_PATTERN},
        "registration": REGISTRATION,
        "not_in_efv_progress": ("the text columns are scored only by the screening "
                                "lab; this probe writes no progress row and no ledger "
                                "row"),
        "seed": SEED, "B": B_BAL,
    }


def merge_text_key(path: Path, block: dict) -> None:
    """Write `block` under BALANCE_KEY of the receipt at `path`, every other key and
    the file's own line ending kept. Idempotent."""
    raw = path.read_bytes()
    nl = "\r\n" if b"\r\n" in raw else "\n"
    doc = json.loads(raw.decode("utf-8"))
    doc[T.BALANCE_KEY] = block
    text = json.dumps(doc, indent=1) + "\n"
    path.write_bytes(text.replace("\n", nl).encode("utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    for V in VINTAGES:
        F.guard_score_request(V, purpose="text balance")
    rng = np.random.default_rng(SEED)
    rows, receipt, by_side = build_rows()
    coverage = T.coverage_receipt(by_side)
    bal = balance(rows, rng)
    try:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
    except OSError:
        commit = None
    block = text_block(bal, receipt, coverage, commit)
    print(json.dumps({"rows": receipt, "balance": bal, "offered": block["offered_columns"],
                      "coverage": coverage["by_side_vintage"], "sources": coverage["sources"]},
                     indent=1))
    if "--dry-run" not in argv:
        merge_text_key(OUT, block)
        print(f"wrote key {T.BALANCE_KEY!r} of {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
