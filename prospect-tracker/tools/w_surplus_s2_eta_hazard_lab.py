# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""W-SURPLUS S2 (2026-07-24 cycle): eta-hazard-lite - 40-man selection shave.

FROZEN PROTOCOL (registered docs/efv-2026-07-24/GATES.md W-SURPLUS S2; this
header is written BEFORE the one gate attempt runs; constants below are the
a-priori choices and are not tuned):

SUBSTRATE  .cache/mlb_transactions tx_YYYY_MM.json.gz (2015-01 .. 2026-07).
           Selection event = typeCode "SE" ("selected the contract of ...",
           the 40-man add). Index: person.id -> EARLIEST SE date.
ID MAP     mlbam per cohort player: debuts.json ident first (debuted players),
           else the player_photos table (board players incl. censored actives).
           Source mix reported; rows without any mlbam can never flag.
COHORT     eta_backtest.build_cohort() rows, vintages 2018-2023 (the accepted
           eval protocol; nothing re-derived).
STOP-D     selection-date coverage = share of DEBUTED rows whose player has an
           SE event dated <= debut_date (debut_date from debuts.json; when the
           exact date is missing, <= Dec 31 of the debut year). STOP if < 0.60.
FEATURE    on40_at_snapshot = earliest SE date <= the row's vintage snapshot
           date. The hazard shave applies ONLY to on40 rows.
FIT        forward-chained per vintage Y on on40 DEBUTED rows from vintages
           < Y: per-level shave a_lv = clip(shrink * median(pred - actual),
           0, CAP) with shrink = n/(n+K); FROZEN: CAP = 1.0, K = 10,
           MIN_N = 8; POOLED (all-level) fallback when a level cell has
           n < MIN_N but the pooled on40 pool has n >= MIN_N.
SCORING    candidate = the LIVE estimate_eta path with fortyman_adj passed for
           on40 rows (eta.py hook, default-OFF); champion = the same rows'
           unmodified build_cohort preds. Identical rows both sides.
GATE       forward-chained debuted MAE improves AND within-1yr share improves
           (pooled, all debuted rows). Marginal = FAIL.
GUARDRAIL  |overdue_candidate - overdue_champion| <= 120 on censored-active
           rows (aligned with the accepted KM drift +101 / bias-shave +99).
           DISCLOSED STRUCTURAL LIMIT: censored actives can only flag when
           player_photos carries their mlbam; the flag-source mix quantifies
           how much of the guardrail is exercised.
ARTIFACT   data/eta_hazard_eval.json (lane-owned). NOTHING flips on by
           default; the live wiring is a wave-D decision.

Run: python tools/w_surplus_s2_eta_hazard_lab.py
"""

from __future__ import annotations

import gzip
import json
import statistics
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import eta_backtest as eb                                            # noqa: E402
import storage                                                       # noqa: E402
from eta import estimate_eta                                         # noqa: E402

TX_DIR = ROOT / ".cache" / "mlb_transactions"
OUT_PATH = ROOT / "data" / "eta_hazard_eval.json"

STOP_D_FLOOR = 0.60
CAP = 1.0
SHRINK_K = 10
MIN_N = 8
OVERDUE_GUARDRAIL = 120


def build_selection_index() -> dict[int, str]:
    """person.id (mlbam) -> earliest SE transaction date, whole substrate."""
    idx: dict[int, str] = {}
    files = sorted(TX_DIR.glob("tx_*.json.gz"))
    for fp in files:
        try:
            rows = json.load(gzip.open(fp, "rt", encoding="utf-8"))["transactions"]
        except (OSError, ValueError, KeyError):
            continue
        for r in rows:
            if r.get("typeCode") != "SE":
                continue
            pid = (r.get("person") or {}).get("id")
            d = r.get("date") or r.get("effectiveDate")
            if not pid or not d:
                continue
            pid = int(pid)
            if pid not in idx or d < idx[pid]:
                idx[pid] = d
    return idx, len(files)


def mlbam_map(ident: dict) -> tuple[dict[str, int], dict[str, str]]:
    """player_key -> mlbam. debuts.json ident first, else player_photos."""
    m: dict[str, int] = {}
    src: dict[str, str] = {}
    for k, info in ident.items():
        if info.get("mlbam"):
            m[k] = int(info["mlbam"])
            src[k] = "debuts"
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, mlbam_id FROM player_photos "
                             "WHERE mlbam_id IS NOT NULL AND player_key IS NOT NULL"):
            if r["player_key"] not in m:
                try:
                    m[r["player_key"]] = int(r["mlbam_id"])
                    src[r["player_key"]] = "photos"
                except (TypeError, ValueError):
                    continue
    return m, src


def _fit_shave(train_on40_deb: list[dict]) -> dict:
    """{level: shave} + {'_pooled': shave} from on40 debuted train rows."""
    out: dict[str, float] = {}
    pooled = [r["pred"] - r["actual"] for r in train_on40_deb]
    if len(pooled) >= MIN_N:
        a = (len(pooled) / (len(pooled) + SHRINK_K)) * statistics.median(pooled)
        out["_pooled"] = max(0.0, min(CAP, a))
    for lv in {r["level"] for r in train_on40_deb if r["level"]}:
        rs = [r["pred"] - r["actual"] for r in train_on40_deb if r["level"] == lv]
        if len(rs) >= MIN_N:
            a = (len(rs) / (len(rs) + SHRINK_K)) * statistics.median(rs)
            out[lv] = max(0.0, min(CAP, a))
    return out


def main() -> None:
    sel_idx, n_files = build_selection_index()
    rows, acct = eb.build_cohort()
    listings, cs, bio, debut_year, ident = eb._load_inputs()
    id_map, id_src = mlbam_map(ident)
    today_year = date.today().year

    # --- STOP-D coverage on the debuted cohort ---
    deb = [r for r in rows if r["outcome"] == "debuted"]
    covered = 0
    have_id = 0
    for r in deb:
        mm = id_map.get(r["player_key"])
        if mm is None:
            continue
        have_id += 1
        sel = sel_idx.get(mm)
        if sel is None:
            continue
        dd = (ident.get(r["player_key"]) or {}).get("debut_date")
        bound = dd if dd else f"{r['actual']}-12-31"
        if sel <= bound:
            covered += 1
    coverage = covered / len(deb) if deb else 0.0
    stop_d = coverage < STOP_D_FLOOR

    out = {
        "lane": "W-SURPLUS S2 eta-hazard-lite (2026-07-24 cycle)",
        "registration": "docs/efv-2026-07-24/GATES.md W-SURPLUS S2",
        "generated_at": date.today().isoformat(),
        "frozen_constants": {"cap": CAP, "shrink_k": SHRINK_K, "min_n": MIN_N,
                             "stop_d_floor": STOP_D_FLOOR,
                             "overdue_guardrail": OVERDUE_GUARDRAIL},
        "substrate": {"tx_files": n_files, "selection_events_indexed": len(sel_idx)},
        "accounting": acct,
        "coverage": {"debuted_rows": len(deb), "with_mlbam": have_id,
                     "with_selection_le_debut": covered,
                     "share": round(coverage, 4)},
    }

    if stop_d:
        out["verdict"] = "STOP-D"
        out["note"] = ("selection-date coverage below the 0.60 floor; "
                       "gate arms never ran (data phase halt)")
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print(json.dumps(out, indent=1))
        return

    # --- feature flags at the vintage snapshot ---
    flag_src = {"debuts": 0, "photos": 0}
    for r in rows:
        mm = id_map.get(r["player_key"])
        sel = sel_idx.get(mm) if mm is not None else None
        r["_on40"] = bool(sel and sel <= r["date"])
        if r["_on40"]:
            flag_src[id_src.get(r["player_key"], "photos")] = \
                flag_src.get(id_src.get(r["player_key"], "photos"), 0) + 1
    on40_rows = [r for r in rows if r["_on40"]]
    on40_deb = [r for r in on40_rows if r["outcome"] == "debuted"]
    on40_cens = [r for r in on40_rows if r["outcome"] == "censored_active"]

    # --- forward-chained fit + candidate rescore through the LIVE hook ---
    cand_pred: dict[int, int] = {}
    shaves_by_vintage: dict[int, dict] = {}
    for vy in eb.VINTAGE_YEARS:
        train = [r for r in on40_deb if r["vintage"] < vy]
        shave = _fit_shave(train)
        shaves_by_vintage[vy] = shave
        if not shave:
            continue
        for i, r in enumerate(rows):
            if r["vintage"] != vy or not r["_on40"]:
                continue
            a = shave.get(r["level"], shave.get("_pooled"))
            if a is None or a <= 0.0:
                continue
            res = estimate_eta(current_level=r["level"], age=r["age"],
                               is_pitcher=r["is_pitcher"], fv=r["fv"],
                               stats=r.get("srow"), snapshot_date=r.get("date"),
                               fortyman_adj=a)
            if res.eta_year is not None:
                cand_pred[i] = r["vintage"] + (res.eta_year - today_year)

    # --- gate scoring: pooled debuted rows, champion vs candidate ---
    champ_pairs, cand_pairs = [], []
    slice_champ, slice_cand = [], []
    movers = []
    for i, r in enumerate(rows):
        if r["outcome"] != "debuted":
            continue
        cp = r["pred"]
        kp = cand_pred.get(i, cp)
        champ_pairs.append((cp, r["actual"]))
        cand_pairs.append((kp, r["actual"]))
        if i in cand_pred:
            slice_champ.append((cp, r["actual"]))
            slice_cand.append((kp, r["actual"]))
            if kp != cp:
                movers.append({"player_key": r["player_key"],
                               "vintage": r["vintage"], "level": r["level"],
                               "fv": r["fv"], "champion_pred": cp,
                               "candidate_pred": kp, "actual": r["actual"]})
    champ = eb._score(champ_pairs)
    cand = eb._score(cand_pairs)
    sl_champ = eb._score(slice_champ)
    sl_cand = eb._score(slice_cand)

    # --- overdue guardrail on censored actives ---
    ov_champ = sum(1 for r in rows if r["outcome"] == "censored_active"
                   and r["pred"] <= eb.LAST_FULL_SEASON)
    ov_cand = 0
    for i, r in enumerate(rows):
        if r["outcome"] != "censored_active":
            continue
        p = cand_pred.get(i, r["pred"])
        if p <= eb.LAST_FULL_SEASON:
            ov_cand += 1
    ov_delta = ov_cand - ov_champ

    mae_ok = cand.get("mae", 9e9) < champ.get("mae", 0)
    w1_ok = cand.get("within_1y", 0) > champ.get("within_1y", 1)
    guard_ok = abs(ov_delta) <= OVERDUE_GUARDRAIL
    verdict = "PASS" if (mae_ok and w1_ok and guard_ok) else "FAIL"

    # shippable table: full-window fit (what wave D would wire) - descriptive
    shippable = _fit_shave(on40_deb)

    out.update({
        "flags": {"on40_rows": len(on40_rows), "on40_debuted": len(on40_deb),
                  "on40_censored_active": len(on40_cens),
                  "flag_source_mix": flag_src},
        "shaves_by_vintage": {str(k): v for k, v in shaves_by_vintage.items()},
        "pooled_debuted": {"champion": champ, "candidate": cand},
        "on40_slice_debuted": {"champion": sl_champ, "candidate": sl_cand},
        "overdue_guardrail": {"champion": ov_champ, "candidate": ov_cand,
                              "delta": ov_delta, "bar_abs": OVERDUE_GUARDRAIL,
                              "pass": bool(guard_ok),
                              "disclosure": ("censored actives flag only via "
                                             "player_photos mlbam; see "
                                             "flag_source_mix")},
        "bars": {"pooled_mae_improves": {"champion": champ.get("mae"),
                                         "candidate": cand.get("mae"),
                                         "pass": bool(mae_ok)},
                 "pooled_within_1y_improves": {"champion": champ.get("within_1y"),
                                               "candidate": cand.get("within_1y"),
                                               "pass": bool(w1_ok)},
                 "overdue_within_120": {"delta": ov_delta,
                                        "pass": bool(guard_ok)}},
        "verdict": verdict,
        "shippable_full_window_shave": shippable,
        "example_movers": movers[:12],
        "default_state": "OFF (eta.py fortyman_adj=None; live wiring is wave-D)",
    })
    OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("coverage", "flags", "bars", "verdict",
                                          "shaves_by_vintage",
                                          "shippable_full_window_shave",
                                          "overdue_guardrail")}, indent=1))
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
