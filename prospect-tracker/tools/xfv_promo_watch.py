# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Forward-registered promoted-pitcher watchlist (eFV 3.3 F-WATCH).

The eFV board systematically PROMOTES a class of pitchers above scout
consensus (xfv_minus_consensus >= +2 on fringe consensus grades). The
side-fairness investigation could not adjudicate whether that promotion
channel is signal or model-flattery from the survivorship-censored
debuted-only eval pool. This module settles it FORWARD, the
editorial_eval.py way: freeze today's treatment cohort with matched
controls and a pre-registered kill rule, then score it only when the
windows close. ZERO output change to any published number - the
artifact is model-internal (deploy/data_exclude.txt) and nothing on the
site reads it.

  COHORT     live (kind=active) PITCHERS with
             xfv_minus_consensus >= +2.0 AND consensus_fv <= 45.33 AND
             model grade >= 45.0 (n=144 on the 2026-07-14 build).
             GRADE-GATE NOTE: the registration text named
             xfv_grade_quantile >= 45.0 but registered "expected
             n~=144"; on the frozen build the quantile field yields
             n=36 while the model grade xfv_grade >= 45.0 reproduces
             n=144 exactly. The cohort is frozen on xfv_grade (the
             count-pinned reading); the 36 rows that also clear the
             quantile gate carry the strict-quantile tag so both
             readings stay adjudicable.
  TAGS       C-RP (RP-designated position: RP/SIRP/MIRP/LIRP),
             deep-consensus (site consensus overall_rank > 1000),
             C-KBB (elite K + bad BB: k_rel >= +0.05 AND
             bb_rel >= +0.01 vs level norms), strict-quantile.
  CONTROLS   5x per treated arm: non-promoted (xfv_minus_consensus
             < +2.0) live pitchers matched on consensus FV (+/-2.5),
             age (+/-2.0y), and level (level_rank +/-1), greedy
             nearest-neighbor without replacement (reuse only on pool
             exhaustion, counted).
  PARITY     identically-defined promoted HITTERS (same thresholds,
             side=H), with their own 5x matched hitter controls -
             separates "the model promotes fringe arms badly" from
             "the model promotes fringe players badly".
  h1 HIT     (6-12mo window, opens 2027-01-15, closes 2027-07-15)
             scout re-evaluation ONLY: consensus FV >= freeze FV
             + 2.5, OR new-source pickup (more sources publish an FV
             than at freeze), OR top-100 entry (any source, none
             pre-freeze). Dropped-from-all-lists (no snapshot from any
             source in the 210 days before scoring) = explicit miss.
             Level advancement and BB% regression are recorded
             DESCRIPTIVE ONLY - both are regression-biased for a
             cohort selected on production over consensus.
  h2 HIT     (24mo, 2028-07-15) MLB debut; supersedes h1 as the
             primary outcome once closed.
  KILL RULE  adjudicate once >= 25 treated / >= 75 controls have
             matured; treated hit rate must beat control hit rate at
             bootstrap P >= 0.90 (2000 reps, seed 7) or the promotion
             channel is flagged for shrinkage (owner decision,
             registry records it).

HONESTY GUARDS (the editorial_eval pattern):
  * freeze happens ONCE - if the artifact exists the module refuses to
    re-freeze (a re-drawn cohort is not a forward test).
  * adjudication refuses to score before the h1 window opens AND the
    kill-rule minimums are met; before that it only reports pending.

Run: python tools/xfv_promo_watch.py [--out DIR]
  first run  -> freezes data/xfv_promo_watch.json
  later runs -> pending report until 2027-01-15, then adjudication is
                appended under "adjudications" (cohort block untouched).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
from datetime import date
from pathlib import Path

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[1]
# XFV_PROMO_DATA lets a lab run read the real inputs while writing the
# artifact elsewhere (--out); production leaves it unset.
DATA_DIR = Path(os.environ.get("XFV_PROMO_DATA", str(REPO / "data")))
OUT_NAME = "xfv_promo_watch.json"

SPEC = {
    "registered_at": "2026-07-15",
    "lane": "efv-3.3-fwatch",
    "cohort_rule": {
        "kind": "active",
        "xfv_minus_consensus_min": 2.0,
        "consensus_fv_max": 45.33,
        "grade_gate": {"field": "xfv_grade", "min": 45.0,
                       "registered_field": "xfv_grade_quantile",
                       "note": "registration text said xfv_grade_quantile but "
                               "pinned expected n~=144; xfv_grade reproduces "
                               "144 exactly (quantile reading = 36, kept as "
                               "the strict-quantile tag)"},
    },
    "tags": {
        "C-RP": "position in {RP, SIRP, MIRP, LIRP} (generic 'P' is NOT "
                "RP-designated)",
        "deep-consensus": "site consensus overall_rank > 1000 at freeze",
        "C-KBB": "milb k_rel >= +0.05 AND bb_rel >= +0.01 (elite K, bad BB "
                 "vs level norms, latest MiLB season)",
        "strict-quantile": "also clears xfv_grade_quantile >= 45.0 (the "
                           "literal registration reading)",
    },
    "controls": {
        "ratio": 5,
        "pool": "kind=active same-side players with xfv_minus_consensus "
                "< +2.0 (non-promoted), never in either treated cohort",
        "match": "consensus_fv +/-2.5, age_now +/-2.0y, level_rank +/-1; "
                 "greedy nearest by normalized distance, without "
                 "replacement (reuse only on exhaustion, counted)",
    },
    "h1": {
        "window_opens": "2027-01-15",
        "window_closes": "2027-07-15",
        "primary": "scout re-evaluation ONLY: consensus FV >= freeze FV "
                   "+ 2.5, OR new-source FV pickup vs freeze n_sources, OR "
                   "top-100 entry (any source; none pre-freeze)",
        "explicit_miss": "dropped-from-all-lists: no snapshot from any "
                         "source in the 210 days before the scoring date",
        "descriptive_only": ["level advancement vs frozen level_rank",
                             "BB% regression vs frozen bb_rel"],
    },
    "h2": {
        "matures": "2028-07-15",
        "primary": "MLB debut by maturity (debut supersedes h1)",
    },
    "kill_rule": {
        "min_matured_treated": 25,
        "min_matured_controls": 75,
        "test": "bootstrap P(treated hit rate > control hit rate) >= 0.90",
        "bootstrap": {"reps": 2000, "seed": 7},
        "on_fail": "promotion channel flagged for shrinkage (owner "
                   "decision, registry records it)",
    },
    "output_guarantee": "zero change to any published number; artifact is "
                        "listed in deploy/data_exclude.txt",
}

FV_TOL, AGE_TOL, LEVEL_TOL = 2.5, 2.0, 1
DROP_DAYS = 210
RP_POS = {"RP", "SIRP", "MIRP", "LIRP"}


# ---------------------------------------------------------------- inputs

def _load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _inputs():
    xfv = _load("xfv.json")
    mats = {"P": {r["player_key"]: r
                  for r in _load("xfv_live_pitcher_matrix.json")},
            "H": {r["player_key"]: r
                  for r in _load("xfv_live_hitter_matrix.json")}}
    ts = {p["player_key"]: p for p in _load("timeseries.json")["players"]}
    return xfv, mats, ts


def _passes(v: dict) -> bool:
    r = SPEC["cohort_rule"]
    # bughunt SCORE d (2026-07-23): the backgrade contributes prior-anchored
    # kind=="active" rows (xfv_provisional, no pro track record) to xfv.json;
    # their grade is a consensus-anchored PRIOR, not a model read, so they must
    # not enter the promo-watch cohort.
    return (v.get("kind") == "active"
            and not v.get("xfv_provisional")
            and (v.get("xfv_minus_consensus") is not None
                 and v["xfv_minus_consensus"] >= r["xfv_minus_consensus_min"])
            and (v.get("consensus_fv") is not None
                 and v["consensus_fv"] <= r["consensus_fv_max"])
            and (v.get("xfv_grade") is not None
                 and v["xfv_grade"] >= r["grade_gate"]["min"]))


def _tags(pk: str, v: dict, mat: dict, ts_row: dict, side: str) -> list[str]:
    tags = []
    milb = (mat or {}).get("milb") or {}
    if side == "P":
        if str((mat or {}).get("position") or "").upper() in RP_POS:
            tags.append("C-RP")
        k_rel, bb_rel = milb.get("k_rel"), milb.get("bb_rel")
        if k_rel is not None and bb_rel is not None \
                and k_rel >= 0.05 and bb_rel >= 0.01:
            tags.append("C-KBB")
    rank = (ts_row or {}).get("overall_rank")
    if rank is not None and rank > 1000:
        tags.append("deep-consensus")
    if (v.get("xfv_grade_quantile") or 0) >= 45.0:
        tags.append("strict-quantile")
    return tags


# ------------------------------------------------------------- baselines

def _consensus_state_asof(con, player_key: str, asof: str):
    """(median FV across sources' latest <= asof, n_sources,
    latest snapshot date across sources)."""
    rows = con.execute(
        """SELECT source, fv FROM snapshots s
           WHERE player_key = ? AND fv IS NOT NULL AND snapshot_date <= ?
             AND snapshot_date = (SELECT MAX(snapshot_date) FROM snapshots
                                  WHERE player_key = s.player_key
                                    AND source = s.source
                                    AND fv IS NOT NULL
                                    AND snapshot_date <= ?)""",
        (player_key, asof, asof)).fetchall()
    vals = sorted(float(r["fv"]) for r in rows)
    n = len(vals)
    med = None
    if n:
        med = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    last = con.execute(
        "SELECT MAX(snapshot_date) d FROM snapshots "
        "WHERE player_key = ? AND snapshot_date <= ?",
        (player_key, asof)).fetchone()
    return med, n, (last["d"] if last else None)


def _had_top100(con, player_key: str, before: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM snapshots WHERE player_key=? AND rank IS NOT NULL "
        "AND rank <= 100 AND snapshot_date < ? LIMIT 1",
        (player_key, before)).fetchone())


def _top100_inside(con, player_key: str, start: str, end: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM snapshots WHERE player_key=? AND rank IS NOT NULL "
        "AND rank <= 100 AND snapshot_date >= ? AND snapshot_date <= ? "
        "LIMIT 1", (player_key, start, end)).fetchone())


def _baseline(con, pk: str, v: dict, mat: dict, ts_row: dict,
              freeze: str) -> dict:
    milb = (mat or {}).get("milb") or {}
    fv_med, n_src, last_snap = _consensus_state_asof(con, pk, freeze)
    return {
        "player_key": pk,
        "side": v.get("side"),
        "position": (mat or {}).get("position"),
        "consensus_fv": v.get("consensus_fv"),
        "consensus_fv_snapshot_median": fv_med,
        "n_sources": n_src,
        "last_snapshot_date": last_snap,
        "had_top100_pre": _had_top100(con, pk, freeze),
        "xfv_grade": v.get("xfv_grade"),
        "xfv_grade_quantile": v.get("xfv_grade_quantile"),
        "xfv_minus_consensus": v.get("xfv_minus_consensus"),
        "age_now": (mat or {}).get("age_now"),
        "milb_level": milb.get("milb_level"),
        "level_rank": milb.get("level_rank"),
        "k_rel": milb.get("k_rel"),
        "bb_rel": milb.get("bb_rel"),
        "overall_rank": (ts_row or {}).get("overall_rank"),
        "debut_date": (ts_row or {}).get("debut_date"),
    }


# --------------------------------------------------------------- matching

def _match_controls(treated: list[dict], pool: list[dict]) -> dict:
    """Greedy 5-NN without replacement on (fv, age, level_rank)."""
    taken: set[str] = set()
    out, reused = {}, 0
    for t in sorted(treated, key=lambda r: r["player_key"]):
        cands = []
        for c in pool:
            if (t["consensus_fv"] is None or c["consensus_fv"] is None
                    or abs(c["consensus_fv"] - t["consensus_fv"]) > FV_TOL):
                continue
            if (t["age_now"] is not None and c["age_now"] is not None
                    and abs(c["age_now"] - t["age_now"]) > AGE_TOL):
                continue
            if (t["level_rank"] is not None and c["level_rank"] is not None
                    and abs(c["level_rank"] - t["level_rank"]) > LEVEL_TOL):
                continue
            d = (abs(c["consensus_fv"] - t["consensus_fv"]) / FV_TOL
                 + (abs(c["age_now"] - t["age_now"]) / AGE_TOL
                    if None not in (c["age_now"], t["age_now"]) else 1.0)
                 + (abs(c["level_rank"] - t["level_rank"])
                    if None not in (c["level_rank"], t["level_rank"])
                    else 1.0))
            cands.append((d, c["player_key"]))
        cands.sort()
        fresh = [pk for _, pk in cands if pk not in taken][:5]
        if len(fresh) < 5:                       # exhaustion fallback
            for _, pk in cands:
                if pk in fresh:
                    continue
                fresh.append(pk)
                reused += 1
                if len(fresh) == 5:
                    break
        taken.update(fresh)
        out[t["player_key"]] = fresh
    return {"map": out, "reused": reused}


# ----------------------------------------------------------------- freeze

def freeze(out_dir: Path, persist: bool = True) -> dict:
    import storage
    xfv, mats, ts = _inputs()
    bp = xfv["by_player"]
    freeze_date = date.today().isoformat()
    build = xfv["meta"].get("generated_at")

    cohorts, controls = {}, {}
    with storage.connect() as con:
        for side, label in (("P", "treated_pitchers"), ("H", "parity_hitters")):
            mat = mats[side]
            rows = []
            for pk, v in sorted(bp.items()):
                if v.get("side") != side or not _passes(v):
                    continue
                b = _baseline(con, pk, v, mat.get(pk), ts.get(pk), freeze_date)
                b["tags"] = _tags(pk, v, mat.get(pk), ts.get(pk), side)
                rows.append(b)
            treated_keys = {r["player_key"] for r in rows}
            pool = []
            for pk, m in sorted(mat.items()):
                v = bp.get(pk) or {}
                if pk in treated_keys or v.get("kind") != "active":
                    continue
                d = v.get("xfv_minus_consensus")
                if d is not None and d >= SPEC["cohort_rule"]["xfv_minus_consensus_min"]:
                    continue                     # promoted -> not a control
                milb = m.get("milb") or {}
                pool.append({"player_key": pk,
                             "consensus_fv": v.get("consensus_fv"),
                             "age_now": m.get("age_now"),
                             "level_rank": milb.get("level_rank")})
            m = _match_controls(rows, pool)
            ctrl_keys = sorted({pk for lst in m["map"].values() for pk in lst})
            ctrl_rows = []
            for pk in ctrl_keys:
                v = bp.get(pk) or {}
                ctrl_rows.append(_baseline(con, pk, v, mat.get(pk),
                                           ts.get(pk), freeze_date))
            cohorts[label] = rows
            controls[label] = {"match_map": m["map"],
                               "reused_matches": m["reused"],
                               "rows": ctrl_rows}

    def tag_counts(rows):
        c = {}
        for r in rows:
            for t in r["tags"]:
                c[t] = c.get(t, 0) + 1
        return c

    out = {
        "generated_at": freeze_date,
        "frozen": True,
        "source_build": build,
        "spec": SPEC,
        "counts": {
            "treated_pitchers": len(cohorts["treated_pitchers"]),
            "parity_hitters": len(cohorts["parity_hitters"]),
            "controls_pitchers": len(controls["treated_pitchers"]["rows"]),
            "controls_hitters": len(controls["parity_hitters"]["rows"]),
            "tags_pitchers": tag_counts(cohorts["treated_pitchers"]),
            "tags_hitters": tag_counts(cohorts["parity_hitters"]),
        },
        "maturation": {"h1_opens": SPEC["h1"]["window_opens"],
                       "h1_closes": SPEC["h1"]["window_closes"],
                       "h2": SPEC["h2"]["matures"]},
        "cohorts": cohorts,
        "controls": controls,
        "adjudications": [],
    }
    if persist:
        path = out_dir / OUT_NAME
        path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("froze %s (%d treated / %d parity)", path,
                 out["counts"]["treated_pitchers"],
                 out["counts"]["parity_hitters"])
    return out


# ------------------------------------------------------------ adjudicate

def _score_h1(con, base: dict, freeze_date: str, asof: str) -> bool | None:
    """Pre-registered h1 rule. None = unscoreable (no FV baseline)."""
    fv0 = base.get("consensus_fv_snapshot_median")
    if fv0 is None:
        fv0 = base.get("consensus_fv")
    fv_now, n_now, last = _consensus_state_asof(con, base["player_key"], asof)
    dropped = (last is None or
               (date.fromisoformat(asof) - date.fromisoformat(last)).days
               > DROP_DAYS)
    if fv_now is not None and fv0 is not None and fv_now >= fv0 + 2.5:
        return True
    if n_now > (base.get("n_sources") or 0):
        return True
    if not base.get("had_top100_pre") and _top100_inside(
            con, base["player_key"], freeze_date, asof):
        return True
    if dropped:
        return False                             # explicit miss
    if fv_now is None and fv0 is None:
        return None
    return False


def _boot_p(t_hits: list[int], c_hits: list[int],
            reps: int = 2000, seed: int = 7) -> float:
    rng = random.Random(seed)
    wins = 0
    for _ in range(reps):
        ts_ = [t_hits[rng.randrange(len(t_hits))] for _ in t_hits]
        cs_ = [c_hits[rng.randrange(len(c_hits))] for _ in c_hits]
        if sum(ts_) / len(ts_) > sum(cs_) / len(cs_):
            wins += 1
    return wins / reps


def adjudicate(out_dir: Path, persist: bool = True) -> dict:
    import storage
    path = out_dir / OUT_NAME
    art = json.loads(path.read_text(encoding="utf-8"))
    today = date.today()
    opens = date.fromisoformat(art["maturation"]["h1_opens"])
    if today < opens:
        log.info("promo watch pending: h1 opens %s (%d days away) - "
                 "no scoring", opens, (opens - today).days)
        return {"pending": True, "h1_opens": opens.isoformat(),
                "days_remaining": (opens - today).days}
    horizon = "h2" if today >= date.fromisoformat(
        art["maturation"]["h2"]) else "h1"
    asof = today.isoformat()
    freeze_date = art["generated_at"]
    result = {"scored_at": asof, "horizon": horizon, "arms": {}}
    debuted = None
    if horizon == "h2":
        # debuted players leave timeseries' active list; the durable
        # debut signal is xfv.json by_player kind flipping to "debuted"
        # (plus timeseries debut_date for anyone still listed).
        bp = _load("xfv.json")["by_player"]
        ts = _load("timeseries.json")["players"]
        ts_debut = {p["player_key"]: p.get("debut_date") for p in ts}
        debuted = {pk for pk, v in bp.items()
                   if v.get("kind") == "debuted"} | {
                       pk for pk, d in ts_debut.items() if d}
    with storage.connect() as con:
        for label in ("treated_pitchers", "parity_hitters"):
            if horizon == "h2":
                # debut supersedes h1: hit = MLB debut by maturity
                # (all cohort players were undebuted at freeze)
                def h2_hit(b):
                    return b["player_key"] in debuted
                t_hits = [h2_hit(b) for b in art["cohorts"][label]]
                c_hits = [h2_hit(b)
                          for b in art["controls"][label]["rows"]]
            else:
                t_hits = [_score_h1(con, b, freeze_date, asof)
                          for b in art["cohorts"][label]]
                c_hits = [_score_h1(con, b, freeze_date, asof)
                          for b in art["controls"][label]["rows"]]
            t = [int(x) for x in t_hits if x is not None]
            c = [int(x) for x in c_hits if x is not None]
            kr = art["spec"]["kill_rule"]
            eligible = (len(t) >= kr["min_matured_treated"]
                        and len(c) >= kr["min_matured_controls"])
            block = {"n_treated": len(t), "n_controls": len(c),
                     "treated_hits": sum(t), "control_hits": sum(c),
                     "treated_rate": round(sum(t) / len(t), 4) if t else None,
                     "control_rate": round(sum(c) / len(c), 4) if c else None,
                     "kill_rule_eligible": eligible}
            if eligible:
                p = _boot_p(t, c, kr["bootstrap"]["reps"],
                            kr["bootstrap"]["seed"])
                block["boot_p_treated_gt_control"] = round(p, 4)
                block["verdict"] = ("clears" if p >= 0.90
                                    else "flag-for-shrinkage")
            result["arms"][label] = block
    art["adjudications"].append(result)
    if persist:
        path.write_text(json.dumps(art, indent=1), encoding="utf-8")
        log.info("adjudication appended to %s", path)
    return result


# ------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DATA_DIR),
                    help="artifact directory (default: repo data/)")
    args = ap.parse_args()
    out_dir = Path(args.out)
    path = out_dir / OUT_NAME
    if path.exists():
        rep = adjudicate(out_dir)
        print(json.dumps(rep, indent=1))
    else:
        rep = freeze(out_dir)
        print(json.dumps({"frozen": True, "counts": rep["counts"],
                          "maturation": rep["maturation"]}, indent=1))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
