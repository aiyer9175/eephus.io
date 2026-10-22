# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The headline eWAR label check's circularity guard, read ONCE
(docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md part 4).

    python tools/ewar_headline_label_guard.py --dry-run   # fixtures with nulls, no real data
    python tools/ewar_headline_label_guard.py --look      # THE LOOK: once; writes the record

The core label's guard (tools/ewar_core_label_guard.py, EWAR_CORE_LABEL_EPOCH_GATE.md part 4)
with the series changed: the same pairs, statistic, B, seeds, -0.02 margin, permuted twin and
club leg, scored on the headline label (published fWAR plus the frozen headline departures of
data/ewar_headline_label.json). The one difference in the club leg is the pitching side: the
part there is war + the label's pitching departure (the core label left pitchers on fWAR).

Part 4.5's structural check rides the record: on the registered frames the label carries no
departure, so G-1 must read gap 0 with its twin at gap 0 and no departing pair, and every G-2
outcome dT 0. Anything else is a contradiction of the registration: the record says so, the
switch is not cleared, and the run exits 4 (STOP, OWNER_QUESTION.md).

Reads only the frozen fWAR vintage, data/ewar_headline_label.json and the cached
Baseball-Reference stint frames and StatsAPI standings; never fetches; relates no dark
betting column to anything and reads no grade.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Callable, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import ewar_core_label_guard as C  # noqa: E402  (the registered statistics, reused unchanged)

GATE_DOC = "docs/efv-2026-10-22/EWAR_HEADLINE_LABEL_GATE.md"
RECORD = ROOT / "docs" / "efv-2026-10-22" / "ewar_headline_label_guard.json"
LAB_VERSION = "ewar_headline_label_guard/1"

HIT, PIT = C.HIT, C.PIT


# --------------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------------

class HeadlineInputs(C.GuardInputs):
    """The core guard's inputs with the label's departures read from the frozen headline
    label vintage (both sides on each series)."""

    def departures(self, series: str) -> dict:
        import ewar_headline_label
        return ewar_headline_label.departures(series=series)

    def label_meta(self) -> dict:
        import ewar_headline_label
        blob = ewar_headline_label.load()
        return {"vintage_id": blob.get("vintage_id"), "content_sha256": blob.get("content_sha256"),
                "fwar_vintage_id": blob.get("fwar_vintage_id"),
                "ewar_v3_sha256": blob.get("ewar_v3_sha256"),
                "file_sha256": C._sha_file(ewar_headline_label.OUT)}


class FixtureInputs(C.FixtureInputs):
    """The core fixtures with an optional planted pitching departure as well."""

    def __init__(self, noise: float = 0.0, pit_noise: float = 0.0, seed: int = 7, n_players: int = 120):
        super().__init__(noise=noise, seed=seed, n_players=n_players)
        if pit_noise:
            rng = np.random.default_rng(seed + 1)
            for y, blk in self._rows.items():
                for m in sorted(blk[PIT]):
                    self._deps.setdefault((m, y), {})["pit"] = float(rng.normal(0, pit_noise))


# --------------------------------------------------------------------------
# the club leg with the label on both sides
# --------------------------------------------------------------------------

def g2(rows: Mapping, deps: Mapping, bwar: Mapping, team_exp: Mapping, standings: Mapping,
       seasons, boot: int) -> dict:
    """The eBR gate's team guard (11.2.4) with frame = fWAR and part = the label on both
    sides (war + the label's departure on that side)."""
    import swar_targets as T
    ys = [int(y) for y in seasons]
    clubs = sorted({(y + 1, t) for y in ys for t in (standings.get(y + 1) or {})})
    if not clubs:
        raise C.GuardStop("the team guard has no club-season with standings")

    def num(v):
        x = C._f(v)
        return np.nan if x is None else x

    outcomes = {
        "runs_scored": np.array([num(standings[s][t].get("rs")) for s, t in clubs], float),
        "runs_allowed": np.array([-num(standings[s][t].get("ra")) for s, t in clubs], float),
        "run_differential": np.array([num(standings[s][t].get("rs")) - num(standings[s][t].get("ra"))
                                      for s, t in clubs], float),
        "wins": np.array([float(standings[s][t]["w"]) for s, t in clubs], float),
    }
    expo_key = {HIT: "pa", PIT: "ip"}
    players = sorted({m for y in ys for side in (HIT, PIT) for m in ((rows.get(y) or {}).get(side) or {})})
    nxt = {side: {(s, m): e for (sd, s, m), e in team_exp.items() if sd == side} for side in (HIT, PIT)}

    def mat(side: str, value_of) -> np.ndarray:
        vals, expo = {}, {}
        for y in ys:
            for m, r in ((rows.get(y) or {}).get(side) or {}).items():
                vals[(y, m)] = value_of(m, y, r)
                expo[(y, m)] = r.get(expo_key[side])
        return T.roster_matrix(vals, expo, nxt[side], players, clubs)

    bkey = {HIT: "bat", PIT: "pit"}
    mats = {}
    for side in (HIT, PIT):
        k = bkey[side]
        frame = mat(side, lambda m, y, r: r.get("war"))
        ref = mat(side, lambda m, y, r, k=k: (bwar.get((m, y)) or {}).get(k))
        part = mat(side, lambda m, y, r, k=k: None if r.get("war") is None
                   else r["war"] + (deps.get((m, y)) or {}).get(k, 0.0))
        mats[side] = {"frame": frame, "part": part, "ref": ref}
    g = T.team_guard(mats, outcomes, C.GUARD_OUTCOMES, clubs, boot=boot, seed=T.GUARD_SEED)
    g["seed"] = T.GUARD_SEED
    g["boot"] = boot
    g["holds"] = bool(g["non_inferior"] and not g["underpowered"])
    g["n_departing_cells"] = int(sum(1 for y in ys for side in (HIT, PIT)
                                     for m in ((rows.get(y) or {}).get(side) or {})
                                     if (deps.get((m, y)) or {}).get(bkey[side], 0.0) != 0.0))
    return g


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def structure_check(G1: dict, G2: dict) -> dict:
    """Part 4.5: the identity the registration states before the look."""
    twin = G1.get("twin") or {}
    dts = {name: o.get("dT") for name, o in (G2.get("outcomes") or {}).items()}
    out = {"g1_gap": G1.get("gap"), "g1_twin_gap": twin.get("gap"),
           "g1_n_pairs_departing": G1.get("n_pairs_departing"),
           "g2_n_departing_cells": G2.get("n_departing_cells"), "g2_dT": dts}
    out["holds"] = bool(G1.get("gap") == 0.0 and twin.get("gap") == 0.0
                        and G1.get("n_pairs_departing") == 0 and G2.get("n_departing_cells") == 0
                        and dts and all(v == 0.0 for v in dts.values()))
    return out


def run(inputs: C.GuardInputs, boot: int = C.BOOT, log: Callable = print, expect_identity: bool = True) -> dict:
    rows = inputs.season_rows()
    need = sorted({y for y in C.PREDICTOR_SEASONS} | {y + 1 for y in C.PREDICTOR_SEASONS})
    missing = [y for y in need if y not in rows]
    if missing:
        raise C.GuardStop(f"the vintage lacks seasons {missing}")
    deps = inputs.departures("headline")
    real = inputs.departures("realized")
    meta = inputs.label_meta()
    log(f"[guard] headline label {meta.get('vintage_id')}; predictor seasons {C.PREDICTOR_SEASONS}; "
        f"B {boot}; seed {C.SEED} (G-1), team guard seed per 11.2.4")
    twin = C.twin_departures(rows, deps, C.PREDICTOR_SEASONS, C.SEED)
    log("[guard] scoring began")
    G1 = C.g1(rows, deps, twin, C.PREDICTOR_SEASONS, C.MIN_PA, boot, C.SEED)
    log(f"[G-1] pairs {G1['n_pairs']} players {G1.get('n_players')} departing {G1.get('n_pairs_departing')} "
        f"gap {G1.get('gap')} lower {G1.get('lower')} sd {G1.get('sd')} => "
        f"{'NON-INFERIOR' if G1['non_inferior'] else 'not non-inferior'}; "
        f"twin gap {G1.get('twin', {}).get('gap')} lower {G1.get('twin', {}).get('lower')}")
    standings = inputs.standings([y + 1 for y in C.PREDICTOR_SEASONS])
    G2 = g2(rows, deps, inputs.bwar(), inputs.team_exposure(), standings, C.PREDICTOR_SEASONS, boot)
    for name, o in G2["outcomes"].items():
        log(f"[G-2] {name:16s} n {o['n_club_seasons']} dT {o['dT']} lower player {o['player'].get('lower')} "
            f"club {o['club'].get('lower')} => {'NON-INFERIOR' if o['non_inferior'] else 'not non-inferior'}")
    log(f"[G-2] guard {'NON-INFERIOR' if G2['non_inferior'] else 'NOT NON-INFERIOR'}"
        f"{' (underpowered)' if G2['underpowered'] else ''}; departing cells {G2['n_departing_cells']}")
    sec = {
        "rate_per_600pa": C.g1(rows, deps, twin, C.PREDICTOR_SEASONS, C.MIN_PA, boot, C.SEED, rate=True),
        "floor_200pa": C.g1(rows, deps, twin, C.PREDICTOR_SEASONS, C.MIN_PA_SECONDARY, boot, C.SEED),
        "realized_pitchers": C.g1_pitchers_realized(rows, real, C.R2_SEASONS, boot, C.SEED),
        "framing_rows": C.g1(rows, deps, twin, C.PREDICTOR_SEASONS, C.MIN_PA, boot, C.SEED,
                             subset=lambda p: abs(p["frm_runs"]) > C.FRAMING_RUNS_EPS),
    }
    for k, v in sec.items():
        log(f"[secondary] {k}: n {v.get('n_pairs')} gap {v.get('gap')} lower {v.get('lower')}")
    holds = bool(G1["non_inferior"] and G2["holds"])
    twin_also = bool(G1.get("twin", {}).get("non_inferior"))
    struct = structure_check(G1, G2)
    cleared = bool(holds and (struct["holds"] or not expect_identity))
    log(f"[guard] THE GUARD {'HOLDS' if holds else 'DOES NOT HOLD'}"
        + (" (the permuted twin is also NON-INFERIOR: G-1 cannot separate the label's change from a random "
           "change of the same size)" if (twin_also and G1["non_inferior"]) else ""))
    log(f"[guard] part 4.5 structure (identity on the registered frames): "
        f"{'as registered' if struct['holds'] else 'CONTRADICTED'}; switch "
        f"{'cleared' if cleared else 'NOT cleared'}")
    return {
        "schema": 1, "lab": LAB_VERSION, "registration": GATE_DOC,
        "label": meta, "inputs": inputs.input_meta(),
        "parameters": {"predictor_seasons": list(C.PREDICTOR_SEASONS), "min_pa": C.MIN_PA, "boot": boot,
                       "seed": C.SEED, "margin": C.MARGIN, "outcomes": [list(o) for o in C.GUARD_OUTCOMES],
                       "r2_seasons": list(C.R2_SEASONS), "min_ip": C.MIN_IP},
        "g1": G1, "g2": C._jsonable(G2), "secondary": sec, "structure": struct,
        "verdict": {"g1_non_inferior": G1["non_inferior"], "g2_non_inferior": G2["holds"],
                    "guard_holds": holds, "twin_also_non_inferior": twin_also,
                    "structure_as_registered": struct["holds"], "switch_cleared": cleared},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="fixtures with nulls; no real data, no write")
    g.add_argument("--look", action="store_true", help="THE LOOK: once, on real data; writes the record")
    ap.add_argument("--boot", type=int, default=None, help="dry run only")
    a = ap.parse_args(argv)
    if a.dry_run:
        for noise, pit in ((0.0, 0.0), (3.0, 0.0), (0.0, 3.0)):
            rec = run(FixtureInputs(noise=noise, pit_noise=pit), boot=a.boot or 200, expect_identity=False)
            json.dumps(C._jsonable(rec), allow_nan=True)
            print(f"[dry-run] planted departure sd bat {noise} pit {pit}: guard holds "
                  f"{rec['verdict']['guard_holds']}; structure as registered {rec['verdict']['structure_as_registered']}")
        return 0
    if a.boot is not None:
        print("--boot is fixed at the registered B on the look")
        return 2
    if RECORD.exists():
        print(f"REFUSED: {RECORD} exists; the look runs once")
        return 2
    started = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    try:
        rec = run(HeadlineInputs(), boot=C.BOOT)
    except C.GuardStop as e:
        print(f"STOP before scoring: {e}")
        return 3
    finished = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    rec = {"generated_at": finished, **rec}
    rec["run"] = {"started_at": started, "finished_at": finished, "git_head": C._git_head(),
                  "command": "python tools/ewar_headline_label_guard.py --look"}
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(C._jsonable(rec), indent=1, ensure_ascii=True, allow_nan=True) + "\n",
                      encoding="utf-8")
    print(f"written {RECORD}")
    if not rec["verdict"]["structure_as_registered"]:
        print("STOP: part 4.5's structure is contradicted; nothing flips (OWNER_QUESTION.md)")
        return 4
    return 0


if __name__ == "__main__":
    sys.exit(main())
