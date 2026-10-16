# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The inputs and the per-season assembly of eWAR's pitching bases S2b and R2
(docs/ebr-2026-09-30/EBR_GATE.md part 11.3), called by tools/build_swar.py.

The formulas live in pitch_basis.py (pure). This file reads caches only, never
fetches and never writes: the Savant expected-stats pitcher cache, the StatsAPI
season fielding feed (per club), and the play-by-play runner record
(.cache/pbp_runners, with the corpus's pitcher of record and its substitution
events). A season the runner record lacks (2016, 2017, 2020) takes RA* = R, the
two runner terms dropped, as part 11.2.1 says, and the census says so.

It relates nothing to any next-season quantity: every number here is a
same-season construction.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Optional

import pitch_basis as PB
import swar

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache"
SAVANT_DIR = CACHE / "savant_mlb"
RUNNER_DIR = CACHE / "pbp_runners"
CORPUS_DIR = CACHE / "pbp_corpus"

#: Tolerance of the runner accounting (11.3.1 invariant 4), in runs.
RUNS_TOL = 1e-6


class PitchBasisStop(RuntimeError):
    """A precondition or invariant of part 11.3 failed: nothing is written."""


# --------------------------------------------------------------------------
# readers (caches only)
# --------------------------------------------------------------------------

def read_savant_pitcher(season: int) -> dict[int, tuple[float, float]]:
    """{mlbam: (woba, est_woba)} from the expected-stats pitcher cache. A season
    2016 or later without the cache stops the build (never a refetch)."""
    path = SAVANT_DIR / f"expected_pitcher_{int(season)}.csv"
    if not path.exists():
        raise PitchBasisStop(f"Savant pitcher cache {season}: {path.name} is not cached")
    out = {}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    for r in csv.DictReader(io.StringIO(text)):
        try:
            out[int(r["player_id"])] = (float(r["woba"]), float(r["est_woba"]))
        except (TypeError, ValueError, KeyError):
            continue
    return out


def read_fielding_by_team(season: int) -> dict[int, dict[str, dict[str, float]]]:
    """{mlbam: {position: {team id: innings}}} from the StatsAPI season fielding
    feed's per-club splits (the replica's fresher cache of that feed)."""
    import fwar_replica_eval as R
    out: dict = {}
    for s in R._splits(R.fielding_path(int(season))):
        pid = (s.get("player") or {}).get("id")
        pos = (s.get("position") or {}).get("abbreviation")
        team = (s.get("team") or {}).get("id")
        if pid is None or not pos or team is None:
            continue
        inn = R._ip((s.get("stat") or {}).get("innings"))
        byp = out.setdefault(int(pid), {}).setdefault(pos, {})
        byp[str(team)] = byp.get(str(team), 0.0) + inn
    return out


def read_runner_record(season: int):
    """(plays, runners, pitcher of record, substitutions) DataFrames of one
    season, or None when the record lacks the season."""
    y = int(season)
    paths = (RUNNER_DIR / "plays" / str(y) / f"pa-{y}.parquet",
             RUNNER_DIR / "runners" / str(y) / f"runners-{y}.parquet",
             CORPUS_DIR / "plays" / str(y) / f"plays-{y}.parquet",
             CORPUS_DIR / "events" / str(y) / f"events-{y}.parquet")
    if not all(p.exists() for p in paths):
        return None
    import pandas as pd
    plays = pd.read_parquet(paths[0], columns=[
        "game_pk", "half", "inning", "at_bat_index", "batter_id", "scheduled_innings",
        "outs_before", "outs_after", "on_first", "on_second", "on_third", "runner_placed"])
    runners = pd.read_parquet(paths[1], columns=[
        "game_pk", "at_bat_index", "runner_id", "is_batter", "end", "is_out", "is_scoring"])
    pitchers = pd.read_parquet(paths[2], columns=["game_pk", "at_bat_index", "pitcher_id"])
    events = pd.read_parquet(paths[3], columns=[
        "game_pk", "event_type", "player_id", "replaced_player_id", "is_substitution"])
    return plays, runners, pitchers, events


# --------------------------------------------------------------------------
# the runner terms of one season
# --------------------------------------------------------------------------

def _i(v) -> Optional[int]:
    try:
        if v is None or v != v:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def season_runner_terms(record) -> tuple[dict, dict, dict]:
    """({pitcher: {ir, irs, bq, bqs, e_ir, e_bq}}, p_s table {(base, outs): p},
    census) from one season's runner record."""
    import ebr
    plays, runners, pitchers, events = record
    plays = plays.merge(pitchers, on=["game_pk", "at_bat_index"], how="left")
    plays = plays.sort_values(["game_pk", "at_bat_index"], kind="mergesort").reset_index(drop=True)
    no_pitcher = int(plays["pitcher_id"].isna().sum())

    # scorers and batter-runners reaching, per (game, plate appearance)
    sc = runners[runners["is_scoring"].fillna(False).astype(bool)]
    scorers: dict = {}
    for g, a, rid in zip(sc["game_pk"].tolist(), sc["at_bat_index"].tolist(), sc["runner_id"].tolist()):
        if _i(rid) is not None:
            scorers.setdefault((int(g), int(a)), []).append(int(rid))
    bat = runners[runners["is_batter"].fillna(False).astype(bool)]
    out_b = set()
    on_b = set()
    for g, a, rid, end, io_ in zip(bat["game_pk"].tolist(), bat["at_bat_index"].tolist(),
                                   bat["runner_id"].tolist(), bat["end"].tolist(), bat["is_out"].tolist()):
        if _i(rid) is None:
            continue
        key = (int(g), int(a), int(rid))
        if bool(io_):
            out_b.add(key)
        elif end is not None and str(end) not in ("None", "nan", "<NA>"):
            on_b.add(key)

    # pinch runners: a substitute runner takes the replaced runner's owner
    sub = events[events["is_substitution"].fillna(False).astype(bool)
                 & (events["event_type"] == "offensive_substitution")]
    subs_by_game: dict = {}
    for g, pid, rep in zip(sub["game_pk"].tolist(), sub["player_id"].tolist(), sub["replaced_player_id"].tolist()):
        if _i(pid) is not None and _i(rep) is not None:
            subs_by_game.setdefault(int(g), {})[int(pid)] = int(rep)

    # the p_s table on the fit set of part 2.3
    fit = ebr.fit_mask(plays)
    starts = []
    acc: dict = {}
    missing_owner = 0
    halves = 0
    keys = plays["game_pk"].astype(str) + "|" + plays["inning"].astype(str) + "|" + plays["half"].astype(str)
    cols = {c: plays[c].tolist() for c in ("game_pk", "at_bat_index", "pitcher_id", "outs_before",
                                           "on_first", "on_second", "on_third", "batter_id")}
    fitl = list(fit)
    order: dict = {}
    walks: list = []
    for i, k in enumerate(keys.tolist()):
        order.setdefault(k, []).append(i)
    for idx in order.values():
        halves += 1
        g = int(cols["game_pk"][idx[0]])
        # (runner -> scoring plate appearances) in this half
        score_at: dict = {}
        for i in idx:
            for rid in scorers.get((g, int(cols["at_bat_index"][i])), ()):
                score_at.setdefault(rid, []).append(int(cols["at_bat_index"][i]))
        seq = []
        for i in idx:
            a = int(cols["at_bat_index"][i])
            o = _i(cols["outs_before"][i])
            o = 0 if o is None else min(2, max(0, o))
            bases = (_i(cols["on_first"][i]), _i(cols["on_second"][i]), _i(cols["on_third"][i]))
            if fitl[i]:
                for b, rid in zip(PB.BASES, bases):
                    if rid is not None:
                        starts.append((b, o, any(x >= a for x in score_at.get(rid, ()))))
            pit = _i(cols["pitcher_id"][i])
            if pit is None:
                continue
            batter = _i(cols["batter_id"][i])
            reached = (batter is not None and (g, a, batter) in on_b and (g, a, batter) not in out_b)
            seq.append(PB.Play(ab=a, pitcher=pit, outs=o, bases=bases, batter=batter if batter is not None else -1,
                               reached=reached, scorers=tuple(scorers.get((g, a), ()))))
        walks.append({"seq": seq, "game": g})
    p = PB.p_table(starts)
    for meta in walks:
        r = PB.half_runner_terms(meta["seq"], p, acc, subs_by_game.get(meta["game"]))
        missing_owner += r["missing_owner"]
    census = {"halves": halves, "plays_without_pitcher": no_pitcher,
              "runners_without_owner": missing_owner, "p_cells": len(p)}
    return acc, p, census


# --------------------------------------------------------------------------
# one season's S2b and R2 rows
# --------------------------------------------------------------------------

def _num(v, default=0.0) -> float:
    try:
        f = float(v)
        return default if f != f else f
    except (TypeError, ValueError):
        return default


def pitch_line(mid: int, stat: dict, ip: float) -> PB.PitchLine:
    return PB.PitchLine(
        mlbam=int(mid), ip=float(ip), tbf=_num(stat.get("battersFaced")), ab=_num(stat.get("atBats")),
        h=_num(stat.get("hits")), doub=_num(stat.get("doubles")), trip=_num(stat.get("triples")),
        hr=_num(stat.get("homeRuns")), bb=_num(stat.get("baseOnBalls")),
        ibb=_num(stat.get("intentionalWalks")), hbp=_num(stat.get("hitByPitch")),
        sf=_num(stat.get("sacFlies")), so=_num(stat.get("strikeOuts")), r=_num(stat.get("runs")))


def season_rows(season: int, inp, K: dict, hitters: list, pitchers: list, chain: dict,
                sp_pool, rp_pool, nopp: set, k_consts=None) -> dict:
    """S2b (both home-run variants) and R2 for every pitcher row of one season,
    plus the raw terms, RA*, RA9*, the runner terms and the census. `k_consts`
    overrides (K_CQ, K_BAB, K_LOB); None reads pitch_basis's frozen constants."""
    k_cq, k_bab, k_lob = k_consts if k_consts is not None else PB.constants()
    W, scale = K["woba_weights"], K["woba_scale"]
    counts = inp.pitching_counts(season)
    savant = inp.savant_pitcher(season)
    fbt = inp.fielding_by_team(season)
    record = inp.runner_record(season)

    lines = {}
    for r in pitchers:
        st = (counts.get(r.mlbam) or {}).get("stat") or {}
        lines[r.mlbam] = pitch_line(r.mlbam, st, r.ip)
    inside = [ln for m, ln in lines.items() if m not in nopp and ln.ip > 0]
    lg = PB.league(inside, W)

    # the clubs' fielding runs, shared by batters faced
    fld = {h.mlbam: float(h.fld or 0.0) for h in hitters}
    fld_frm = {h.mlbam: float(h.fld or 0.0) + float(h.frm or 0.0) for h in hitters}
    # each fielder's innings per club, summed over positions, pitching left out
    field_inn = {}
    for m, byp in fbt.items():
        tot: dict = {}
        for p, byt in byp.items():
            if p == "P":
                continue
            for t, x in byt.items():
                tot[t] = tot.get(t, 0.0) + x
        field_inn[m] = tot
    pit_inn = {m: dict(byp.get("P") or {}) for m, byp in fbt.items()}
    club_fld = PB.club_runs(fld, field_inn)
    club_ff = PB.club_runs(fld_frm, field_inn)
    shares = PB.pitcher_shares({m: ln.tbf for m, ln in lines.items()}, pit_inn)
    club_bf: dict = {}
    for m, byt in shares.items():
        for t, b in byt.items():
            club_bf[t] = club_bf.get(t, 0.0) + b

    if record is not None:
        acc, ptab, rcensus = season_runner_terms(record)
    else:
        acc, ptab, rcensus = {}, {}, {"halves": 0, "plays_without_pitcher": 0,
                                      "runners_without_owner": 0, "p_cells": 0}

    rows: dict = {}
    raw_b: dict = {v: {} for v in swar.HR_VARIANTS}
    dw_real: dict = {}
    ip_map = {r.mlbam: r.ip for r in pitchers}
    for r in pitchers:
        ln = lines[r.mlbam]
        a = chain.get(r.mlbam)
        rt = acc.get(r.mlbam) or PB._blank()
        ras = PB.ra_star(ln.r, rt["bqs"], rt["e_bq"], rt["irs"], rt["e_ir"])
        d = PB.woba_denominator(ln)
        sv = savant.get(r.mlbam)
        x = PB.savant_gap_runs(sv[1] if sv else None, sv[0] if sv else None, d, scale)
        f_b = PB.defense_share(shares.get(r.mlbam) or {}, club_fld, club_bf)
        f_r = PB.defense_share(shares.get(r.mlbam) or {}, club_ff, club_bf)
        row = {"ra_star": ras, "runner_terms": dict(rt) if record is not None else None,
               "savant": sv is not None, "fld_share": f_b, "fld_frm_share": f_r,
               "ra9_star": None, "terms": {}}
        skip = a is None or r.mlbam in nopp or r.ip <= 0
        if not skip:
            row["ra9_star"] = PB.ra9_star(ras, a["pf"], ln.tbf, f_r, a["ip"])
        for v in swar.HR_VARIANTS:
            if skip:
                raw_b[v][r.mlbam] = 0.0
                row["terms"][v] = None
                continue
            tgt = swar.blend_target(swar.start_share(a["start_ip"], a["ip"]), sp_pool, rp_pool)
            m_tilde = swar.shrunk_counts(r, tgt, v)
            t = PB.terms(ln, W, lg, scale, m_tilde["hr"], x, f_b, ras)
            gr = PB.blend_runs(t, k_cq, k_bab, k_lob)
            df = PB.dfip_blend(swar.dfip(r, m_tilde), gr, r.ip)
            raw_b[v][r.mlbam] = swar.dwar0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], a["pf"],
                                          a["fip"], df, K["lg_ra9"], K["lg_era"], a["gm"])
            row["terms"][v] = {"cq": t["cq"], "bab": t["bab"], "lob": t["lob"], "c": t["c"],
                               "n": t["n"], "g": gr, "dfip_b": df}
        if skip:
            dw_real[r.mlbam] = 0.0
        else:
            actual = swar.pitcher_war0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"],
                                       swar.pfipr9(a["fip"], a["pf"], K["lg_ra9"], K["lg_era"]), a["gm"])
            real = swar.pitcher_war0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], row["ra9_star"], a["gm"])
            dw_real[r.mlbam] = real - actual
        rows[r.mlbam] = row
    delta_b = {v: PB.repin(raw_b[v], ip_map, nopp) for v in swar.HR_VARIANTS}
    delta_r = PB.repin(dw_real, ip_map, nopp)
    for m, row in rows.items():
        row["blend"] = {v: {"dwar0": raw_b[v][m], "delta": delta_b[v][m]} for v in swar.HR_VARIANTS}
        row["realized"] = {"dwar0": dw_real[m], "delta": delta_r[m]}

    # -- the accounting checks (11.3.1 invariants 2 to 4; 11.2.8)
    checks = {"zero_sum": {}, "runner_accounting": PB.accounting_gap(acc) if acc else None}
    for v in swar.HR_VARIANTS:
        s = sum(delta_b[v].values())
        checks["zero_sum"][PB.BLEND_PREFIX + v] = s
        if abs(s) > 1e-9:
            raise PitchBasisStop(f"{season} S2b {v}: re-pinned Delta sums to {s!r}, not 0")
        if any(delta_b[v][m] != 0.0 for m in nopp if m in delta_b[v]):
            raise PitchBasisStop(f"{season} S2b {v}: a nopp row carries a non-zero Delta")
    s = sum(delta_r.values())
    checks["zero_sum"][PB.REALIZED_KEY] = s
    if abs(s) > 1e-9:
        raise PitchBasisStop(f"{season} R2: re-pinned Delta sums to {s!r}, not 0")
    if acc:
        gap = checks["runner_accounting"]
        if abs(gap["e_bq_minus_e_ir"]) > RUNS_TOL or abs(gap["irs_minus_bqs"]) > RUNS_TOL:
            raise PitchBasisStop(f"{season}: the runner terms do not net to zero ({gap})")
        r_sum = sum(lines[m].r for m in acc if m in lines)
        ras_sum = sum(rows[m]["ra_star"] for m in acc if m in rows)
        checks["ra_star_minus_r_over_tracked_pitchers"] = ras_sum - r_sum
    ir_pbp = sum(v["ir"] for v in acc.values())
    irs_pbp = sum(v["irs"] for v in acc.values())
    ir_api = sum(_num(((counts.get(m) or {}).get("stat") or {}).get("inheritedRunners")) for m in lines)
    irs_api = sum(_num(((counts.get(m) or {}).get("stat") or {}).get("inheritedRunnersScored")) for m in lines)
    census = {
        "pb_runner_record": 1 if record is not None else 0,
        "pb_savant_rows": sum(1 for r in rows.values() if r["savant"]),
        "pb_without_club_innings": sum(1 for m in lines if not (shares.get(m) or {})),
        "pb_runners_without_owner": int(rcensus["runners_without_owner"]),
        "pb_plays_without_pitcher": int(rcensus["plays_without_pitcher"]),
        "pb_ir_pbp": int(ir_pbp), "pb_irs_pbp": int(irs_pbp),
        "pb_ir_statsapi": int(ir_api), "pb_irs_statsapi": int(irs_api),
    }
    return {"rows": rows, "checks": checks, "census": census,
            "league": {"lc": lg.lc, "h": lg.h, "r_per_d": lg.r_per_d, "lg_woba": lg.lg_woba},
            "p_table": {f"{b}|{o}": v for (b, o), v in sorted(ptab.items())},
            "constants": {"k_cq": k_cq, "k_bab": k_bab, "k_lob": k_lob}}
