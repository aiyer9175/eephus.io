# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The pitch-rate sidecar and its no-outcome probes (owner ask 19; Q10_10; plan Part 8
lane pitch_metrics, pitch_metrics.md s7).

WHAT IT WRITES. data/_labs/efv_pitch_rate_features.json, keyed (side, list vintage,
player): the column efv_pitch_rate_features builds (ppa_rel for hitters, pbf_rel for
pitchers) on every lv_dev row (efv_vintage_frame, development vintages 2011 to 2019)
that has a block. A row of the frame with no entry has no block; a consumer imputes it
at the has-block TRAIN mean (efv_pitch_rate_features.impute_at_train_mean) and emits
no absence flag. The pinned matrices are never read or written, so their sha256 pins do
not move.

THE STEPS (pitch_metrics.md s7, each a probe in data/xfv_arm_ledger.json through
tools/efv_arm_ledger.py):

    (a) coverage by (V, side), counts only            PM19:coverage.<col>:<side>
    (b) the balance probe (W3 > 0 share by has-block)  NOT BUILT HERE (see below)
    (c) the DS-06 admission                            Q10_11's, never this tool's
    (d) descriptive correlations with obp_rel, k_rel   PM19:corr.<col>:<side>
        and bb_rel (the closed D-1:bb_rel:hit arm's
        column), no outcome

Step (b) reads an outcome split tied to V2's candidate blocks. Under the owner's PM-Q4
answer (b), Q10_11's amendment to docs/efv-v2/EFV_V2_GATE.md s4.2 commits before any
read of W3 here; until it has, this tool holds no code that reads a label, and the
task stops after (a) and (d).

NEVER READ: list vintages 2020 and 2021 (R-LV; efv_vintage_frame's guard raises) and
every row whose effective debut year is 2025 or later (R-VM; dropped before any count,
the number dropped reported). No WAR, label or outcome module is imported. Nothing is
grouped or summarised by consensus-FV level (docs/PROSPECT_ANCHOR_GATE.md); no table of
P/PA, P/BF or PAR by grade.

Run:  python tools/efv_pitch_rate_sidecar.py [--dry-run]
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_pitch_rate_features as PR  # noqa: E402
import efv_vintage_frame as F  # noqa: E402

OUT = ROOT / "data" / "_labs" / "efv_pitch_rate_features.json"
SCHEMA = "efv_pitch_rate_features/1"
TASK = "Q10_10_EFV_PITCH_RATE_SIDECAR"
#: The other pre-V MiLB rate columns each side's column is correlated with (step d).
#: Hitters: obp_rel and k_rel (V2 skill candidates) and bb_rel (the closed D-1 arm).
#: Pitchers carry no obp_rel on their block.
CORR_WITH = {"hit": ("obp_rel", "k_rel", "bb_rel"), "pit": ("k_rel", "bb_rel")}
CLOSED_ARM = "D-1:bb_rel:hit"
#: Row fields in the compact rows block.
ROW_FIELDS = ("value", "exposure", "seasons")


def _guards() -> dict:
    pins = F.reserved_vm_pins()
    if pins:
        raise F.ReservedFrameError("; ".join(pins))
    bad = sorted(set(F.DEV_VINTAGES) & set(F.RESERVED_LV))
    if bad or max(F.DEV_VINTAGES) >= min(F.RESERVED_LV):
        raise F.ReservedFrameError(f"a development vintage reaches the reserved range: {bad}")
    return {"reserved_lv": sorted(F.RESERVED_LV),
            "r_vm_first_debut_year": F.R_VM_FIRST_DEBUT_YEAR,
            "vintages_read": list(F.DEV_VINTAGES), "reserved_vm_pins": pins}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def is_rvm(row: dict) -> bool:
    """True for a frame row whose effective debut year is R_VM_FIRST_DEBUT_YEAR or
    later (the frame's own debut field, placeholder days already moved to the season
    start). Such a row is dropped before any count."""
    dd = str(row.get("debut_date") or "")
    return dd[:4].isdigit() and int(dd[:4]) >= F.R_VM_FIRST_DEBUT_YEAR


def build(frames: dict | None = None, source: PR.RateSource | None = None) -> dict:
    """The sidecar document. `frames` ({side: {V: rows}}) is for tests; None builds the
    lv_dev frames with efv_vintage_frame.build_frame at each side's own MiLB floor."""
    guards = _guards()
    source = source or PR.RateSource()
    universe = None
    feats: dict = {s: {} for s in F.SIDES}
    milb: dict = {s: {} for s in F.SIDES}
    dropped = {s: 0 for s in F.SIDES}
    for V in F.DEV_VINTAGES:
        F.guard_score_request(V, purpose="pitch rate sidecar")
        for side in F.SIDES:
            if frames is not None:
                rows = list((frames.get(side) or {}).get(V) or [])
            else:
                if universe is None:
                    universe = F.load_universe()
                rows = F.build_frame(side, V, universe=universe, sidecars=False)
            keep = [r for r in rows if not is_rvm(r)]
            dropped[side] += len(rows) - len(keep)
            feats[side][V] = PR.attach(keep, source)
            milb[side][V] = {r["player_key"]: (r.get("milb") or {}) for r in keep}

    cov = PR.coverage(feats)
    corr: dict = {}
    for side in F.SIDES:
        col = PR.column_name(side)
        corr[side] = {"column": col}
        for other in CORR_WITH[side]:
            pairs = []
            for V, fs in sorted(feats[side].items()):
                for f in fs:
                    m = milb[side][V].get(f["player_key"]) or {}
                    if not f["has_block"] or not m or m.get("rates_missing"):
                        continue
                    y = m.get(other)
                    if y is None:
                        continue
                    pairs.append((V, f["value"], float(y)))
            corr[side][other] = PR.correlations(pairs)
        if side == "pit":
            corr[side]["obp_rel"] = "not on the pitcher block"

    rows_out: dict = {}
    for side in F.SIDES:
        for V, fs in sorted(feats[side].items()):
            blk = {f["player_key"]: [round(f["value"], 6), f["exposure"], f["seasons"]]
                   for f in sorted(fs, key=lambda f: f["player_key"]) if f["has_block"]}
            rows_out.setdefault(side, {})[str(V)] = blk

    probes: dict = {}
    for side in F.SIDES:
        col = PR.column_name(side)
        sv = [cov[f"{side}:{V}"] for V in F.DEV_VINTAGES]
        tag = f"PM19:coverage.{col}:{side}"
        probes[tag] = {"tag": tag, "step": "a", "verdict": "COUNTED", "reads_outcome": False,
                       "rows": sum(b["rows"] for b in sv),
                       "has_block": sum(b["has_block"] for b in sv),
                       "rvm_rows_dropped": dropped[side]}
        tag = f"PM19:corr.{col}:{side}"
        probes[tag] = {"tag": tag, "step": "d", "verdict": "DESCRIPTIVE",
                       "reads_outcome": False,
                       "spearman": {o: corr[side][o]["spearman"] for o in CORR_WITH[side]},
                       "n": {o: corr[side][o]["n"] for o in CORR_WITH[side]}}

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "produced_by": "tools/efv_pitch_rate_sidecar.py",
        "task": TASK,
        "owner_ask": ("19 (2026-09-30): calculate P/IP, P/PA and PAR relative to each "
                      "level for prospects, and check if any can be used as a driver "
                      "for eFV"),
        "registration_path": ("PM-Q4 answer (b), add to V2 now: Q10_11's amendment to "
                              "EFV_V2_GATE.md s4.2 commits before step (b) reads W3"),
        "role": "development sidecar; adjudicates nothing; no served number",
        "frame": "lv_dev",
        "guards": guards,
        "definition": {
            "columns": dict(PR.COLUMNS), "rates": dict(PR.RATES),
            "d": "ln(rate / pooled anchor of the same level-season (and role, pitchers))",
            "weight": "exposure (PA hitters, majority-role BF pitchers)",
            "shrink": f"total exposure / (total exposure + {PR.K_SHRINK:g})",
            "hit_min_pa": PR.HIT_MIN_PA, "pit_min_bf": PR.PIT_MIN_BF,
            "max_seasons": PR.MAX_SEASONS, "first_season": PR.FIRST_SEASON,
            "levels": list(PR.LEVELS),
            "usable_only": "pitch_rates tracking guard: untracked or partial level-seasons "
                           "give no rate and no anchor",
            "id": "the row's outcome-blind mlbam_id (efv_identity, DS-03)",
            "missing": "no entry; impute at the has-block TRAIN mean; no absence flag "
                       "in any head (DS-04, bug B3)",
            "sign_predicted": None,
        },
        "inputs": {
            "pitch_rates.py": _sha(ROOT / "pitch_rates.py"),
            "efv_pitch_rate_features.py": _sha(ROOT / "efv_pitch_rate_features.py"),
            "efv_vintage_frame.py": _sha(ROOT / "efv_vintage_frame.py"),
            "efv_identity.py": _sha(ROOT / "efv_identity.py"),
            "line_cache": ".cache/pitch_rates (read only, never fetched)",
            "milb_floor": {s: F.lv_milb_floor(s) for s in F.SIDES},
        },
        "steps": {
            "a": "run: coverage by (V, side), counts only",
            "b": ("not run: the balance probe reads W3 and waits for Q10_11's amendment "
                  "to EFV_V2_GATE.md s4.2 (PM-Q4 (b)); no label is read by this tool"),
            "c": "Q10_11_EFV_PITCH_RATE_ADMISSION (the DS-06 admission), not this tool",
            "d": "run: descriptive correlations, no outcome",
        },
        "rvm_rows_dropped": dropped,
        "coverage": cov,
        "correlations": corr,
        "closed_arm_compared": CLOSED_ARM,
        "row_fields": list(ROW_FIELDS),
        "rows": rows_out,
        "probes": probes,
        "n_probes": len(probes),
    }


def write(doc: dict, path: Path = OUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(doc, indent=1) + "\n").encode("utf-8"))


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    doc = build()
    for k, blk in doc["coverage"].items():
        print(f"  {k:9s} rows {blk['rows']:5d}  id {blk['id_resolved']:5d}  "
              f"block {blk['has_block']:5d}  share {blk['has_block_share']}  "
              f"lines {blk['lines_by_level']}")
    print(f"R-VM rows dropped: {doc['rvm_rows_dropped']}")
    for side, blk in doc["correlations"].items():
        for other in CORR_WITH[side]:
            c = blk[other]
            print(f"  {blk['column']} x {other}: n {c['n']}  pearson {c['pearson']}  "
                  f"spearman {c['spearman']}")
    if "--dry-run" not in argv:
        write(doc)
        print(f"wrote {OUT.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
