# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Pitch rates on the three MLB Stats boards (plan Part 8, PM-03; owner asks 17 and 20).

The board-side join of pitch_rates.py, which owns every definition used here
(innings are outs / 3, the pooled league anchors, PAR, team PAR). This module
only says WHICH line each board row reads and WHICH rows make a club:

  * Starters board: the pitcher's line in his starts (StatsAPI's "sp" role
    line), against the league's starts line for the season.
  * Relievers board: his line in relief (the "rp" role line), against the
    league's relief line.
  * Hitters board: his season line (pitches seen over PA), against every
    non-pitcher's line for the season.
  * When the season's role split is missing or fails its batters-faced parity,
    pitch_rates falls back to season lines; a row on that fallback is stamped
    role_line_basis = "season_line_fallback", and its per-start or per-relief
    figures print only when the season line IS that role's line (every game a
    start, or no start at all).
  * Team units ride the boards' club-today basis: the rows that name the club
    are the rows Offense+, Rotation+ and Bullpen+ are built from. Team PAR is
    pitch_rates.team_par over the clubs on the board, so the clubs average 100.

New row keys only, appended after every existing key, and only while
pitch_rates.SERVE_PITCH_RATES is True. ip_per_gs is never touched: the starts-only
length rides as sp_ip_per_gs. A player with no pitch count gets every new key as
None, never zero.

Starters: p_ip, p_bf, par, par_delta, pit_per_gs, sp_ip_per_gs, role_line_basis.
Relievers: p_ip, p_bf, par, par_delta, pit_per_g, role_line_basis.
Hitters: p_pa, par, par_delta, pit.
Teams: rot_p_ip, rot_par, rot_pit_per_gs; pen_p_ip, pen_par; lineup_p_pa, lineup_par.
"""

from __future__ import annotations

from typing import Optional

import pitch_rates as PR

SP_ROW_KEYS = ("p_ip", "p_bf", "par", "par_delta", "pit_per_gs", "sp_ip_per_gs",
               "role_line_basis")
RP_ROW_KEYS = ("p_ip", "p_bf", "par", "par_delta", "pit_per_g", "role_line_basis")
HIT_ROW_KEYS = ("p_pa", "par", "par_delta", "pit")
SP_TEAM_KEYS = ("rot_p_ip", "rot_par", "rot_pit_per_gs")
RP_TEAM_KEYS = ("pen_p_ip", "pen_par")
HIT_TEAM_KEYS = ("lineup_p_pa", "lineup_par")
PAYLOAD_KEY = "pitch_rates"

TEAM_PAR_NOTE = ("Team PAR: 100 x the club's rate / the unweighted mean of the club "
                 "rates on this board, so the clubs average 100")


def serving() -> bool:
    """Read at call time, so a test or a one-process preview can set the flag."""
    return bool(PR.SERVE_PITCH_RATES)


def _r(v, nd: int):
    return None if v is None else round(float(v), nd)


def _pos(v) -> Optional[float]:
    f = PR._num(v)
    return f if f is not None and f > 0 else None


def season_context(season: int, fetch: bool = True) -> dict:
    """The league anchors and the player lines for one MLB season, read once
    per export. `fetch` lets pitch_rates refresh the season's role split on its
    own TTL (the current season only; past seasons are cached for good)."""
    lr = PR.league_rates("MLB", int(season), fetch=fetch)
    lines = PR.player_lines(int(season), "MLB", fetch=fetch)
    return {"season": int(season), "league": lr, "lines": lines}


# --------------------------------------------------------------------------- #
# Pitchers
# --------------------------------------------------------------------------- #
def _pitcher_line(ctx: dict, mlbam, role: str) -> tuple[Optional[dict], Optional[str]]:
    """(line, basis) for one board row: the role line when the season reads
    off the role split, else the season line, stamped as the fallback."""
    try:
        pl = ctx["lines"].get(int(mlbam))
    except (TypeError, ValueError):
        return None, None
    pit = (pl or {}).get("pit")
    if not pit:
        return None, None
    if ctx["league"]["basis"] == PR.BASIS_ROLE and pit.get(role):
        return pit[role], PR.BASIS_ROLE
    sl = pit.get("season_line")
    if not sl:
        return None, None
    return sl, PR.BASIS_FALLBACK


def _role_pure(line: dict, role: str) -> bool:
    """A season line that IS the role line: every game a start (sp), or no
    start at all (rp)."""
    g, gs = PR._num(line.get("g")) or 0, PR._num(line.get("gs")) or 0
    return g > 0 and (gs == g if role == "sp" else gs == 0)


def _pitcher_values(ctx: dict, mlbam, role: str) -> dict:
    keys = SP_ROW_KEYS if role == "sp" else RP_ROW_KEYS
    out = {k: None for k in keys}
    line, basis = _pitcher_line(ctx, mlbam, role)
    lr = ctx["league"]
    if line is None or lr["pitching_status"] != "usable" or line.get("missing_np"):
        return out
    np_ = _pos(line.get("np"))
    outs = _pos(line.get("outs"))
    if np_ is None or outs is None:
        return out
    anchor = (lr.get(role) or {}).get("p_ip")
    rate = PR.p_ip(np_, outs)
    out["p_ip"] = _r(rate, 2)
    out["p_bf"] = _r(PR.p_bf(np_, line.get("bf")), 3)
    out["par"] = PR.par(rate, anchor)
    out["par_delta"] = _r(PR.par_delta(rate, anchor), 2)
    out["role_line_basis"] = basis
    per_ok = basis == PR.BASIS_ROLE or _role_pure(line, role)
    if role == "sp":
        gs = _pos(line.get("gs"))
        out["pit_per_gs"] = _r(PR._ratio(np_, gs), 1) if per_ok and gs else None
        out["sp_ip_per_gs"] = _r(outs / 3.0 / gs, 2) if per_ok and gs else None
    else:
        g = _pos(line.get("g"))
        out["pit_per_g"] = _r(PR._ratio(np_, g), 1) if per_ok and g else None
    return out


def stamp_pitcher_rows(rows: list[dict], ctx: dict, role: str) -> dict:
    """Append the role's row keys to every board row; return the counts."""
    n = n_fb = 0
    for row in rows:
        vals = _pitcher_values(ctx, row.get("mlbam"), role)
        row.update(vals)
        if vals["p_ip"] is not None:
            n += 1
            if vals["role_line_basis"] == PR.BASIS_FALLBACK:
                n_fb += 1
    return {"rows": len(rows), "stamped": n, "season_line_fallback": n_fb}


def stamp_pitcher_teams(teams: list[dict], rows: list[dict], ctx: dict, role: str) -> int:
    """Rotation (sp) or bullpen (rp) units: the role lines of the board rows
    that name the club, pooled. A member with no usable line is skipped, never
    counted as zero."""
    lean, gs_acc = [], {}
    for row in rows:
        club = row.get("team") or ""
        if not club:
            continue
        line, basis = _pitcher_line(ctx, row.get("mlbam"), role)
        if line is None or line.get("missing_np"):
            continue
        if basis != PR.BASIS_ROLE and not _role_pure(line, role):
            continue
        np_, outs = _pos(line.get("np")), _pos(line.get("outs"))
        if np_ is None or outs is None:
            continue
        lean.append({"team_id": club, "np": np_, "outs": outs})
        if role == "sp" and _pos(line.get("gs")):
            a = gs_acc.setdefault(club, [0.0, 0.0])
            a[0] += np_
            a[1] += _pos(line.get("gs"))
    usable = ctx["league"]["pitching_status"] == "usable"
    rates = PR.team_unit_rates(lean, "rotation" if role == "sp" else "bullpen") if usable else {}
    clubs = [t.get("team") for t in teams if t.get("team")]
    tp = PR.team_par({c: rates.get(c) for c in clubs})
    n = 0
    for t in teams:
        c = t.get("team")
        rate = rates.get(c)
        par_v = PR.par(tp.get(c), 100.0) if tp.get(c) is not None else None
        if role == "sp":
            a = gs_acc.get(c) if usable else None
            t["rot_p_ip"] = _r(rate, 2)
            t["rot_par"] = par_v
            t["rot_pit_per_gs"] = _r(a[0] / a[1], 1) if a and a[1] else None
        else:
            t["pen_p_ip"] = _r(rate, 2)
            t["pen_par"] = par_v
        n += rate is not None
    return n


# --------------------------------------------------------------------------- #
# Hitters
# --------------------------------------------------------------------------- #
def _hitter_values(np_raw, pa_raw, anchor, usable: bool) -> dict:
    out = {k: None for k in HIT_ROW_KEYS}
    np_, pa = _pos(np_raw), _pos(pa_raw)
    if not usable or np_ is None or pa is None:
        return out
    rate = PR.p_pa(np_, pa)
    out["p_pa"] = _r(rate, 3)
    out["par"] = PR.par(rate, anchor)
    out["par_delta"] = _r(PR.par_delta(rate, anchor), 3)
    out["pit"] = int(np_)
    return out


def stamp_hitter_rows(rows: list[dict], np_by_id: dict, ctx: dict) -> dict:
    """P/PA on the season line. `np_by_id` maps mlbam to the pitches seen on
    the board's own season row (hitter_export's NP field)."""
    lr = ctx["league"]
    usable = lr["tracking"] == "usable"
    anchor = (lr.get("hit") or {}).get("p_pa")
    n = 0
    for row in rows:
        mid = row.get("mlbam")
        np_raw = np_by_id.get(int(mid)) if mid is not None else None
        vals = _hitter_values(np_raw, row.get("pa"), anchor, usable)
        row.update(vals)
        n += vals["p_pa"] is not None
    return {"rows": len(rows), "stamped": n}


def stamp_hitter_teams(teams: list[dict], rows: list[dict], np_by_id: dict,
                       pos_by_id: dict, ctx: dict) -> int:
    """Lineup units: the hitter rows that name the club, pitches over PA pooled
    (pitchers' bats left out, as pitch_rates.team_unit_rates defines it)."""
    lean = []
    for row in rows:
        mid, club = row.get("mlbam"), row.get("team") or ""
        if mid is None or not club:
            continue
        np_ = _pos(np_by_id.get(int(mid)))
        pa = _pos(row.get("pa"))
        if np_ is None or pa is None:
            continue
        lean.append({"team_id": club, "np": np_, "pa": pa, "pos": pos_by_id.get(int(mid))})
    usable = ctx["league"]["tracking"] == "usable"
    rates = PR.team_unit_rates(lean, "lineup") if usable else {}
    clubs = [t.get("team") for t in teams if t.get("team")]
    tp = PR.team_par({c: rates.get(c) for c in clubs})
    n = 0
    for t in teams:
        c = t.get("team")
        rate = rates.get(c)
        t["lineup_p_pa"] = _r(rate, 3)
        t["lineup_par"] = PR.par(tp.get(c), 100.0) if tp.get(c) is not None else None
        n += rate is not None
    return n


# --------------------------------------------------------------------------- #
# The payload block
# --------------------------------------------------------------------------- #
def _anchor_block(ctx: dict, side: str) -> dict:
    lr = ctx["league"]
    blk = lr.get(side) or {}
    if side == "hit":
        anchors = {"p_pa": _r(blk.get("p_pa"), 4)}
        status = lr["tracking"]
        basis = "every non-pitcher's season line, pooled"
    else:
        anchors = {"p_ip": _r(blk.get("p_ip"), 4), "p_bf": _r(blk.get("p_bf"), 4)}
        if side == "sp":
            anchors["pit_per_gs"] = _r(blk.get("pit_per_gs"), 2)
            anchors["sp_ip_per_gs"] = _r(blk.get("sp_ip_per_gs"), 3)
        else:
            anchors["pit_per_g"] = _r(blk.get("pit_per_g"), 2)
        status = lr["pitching_status"]
        basis = lr["basis"]
    return {"season": ctx["season"], "role": side, "anchors": anchors,
            "anchor_n": blk.get("n"), "status": status, "basis": basis}


def payload_block(ctx: dict, side: str, as_of: str, n: dict,
                  n_teams: Optional[int] = None) -> dict:
    """The live board's pitch_rates block: anchors, counts, season, basis, as_of."""
    out = {"as_of": as_of, **_anchor_block(ctx, side), "n": dict(n),
           "definitions": {
               "innings": "outs / 3; a line of 6.1 is 19 outs",
               "par": "round(100 x rate / league rate for the role and season), "
                      "nearest; 100 = average, not inverted, uncoloured",
               "par_delta": "rate minus the league rate, in pitches",
               "team_par": TEAM_PAR_NOTE,
               "team_basis": "club today: the board rows that name the club, the "
                             "membership of Offense+, Rotation+ and Bullpen+",
           }}
    if n_teams is not None:
        out["n"]["teams_stamped"] = n_teams
    return out


def history_block(per_season: dict, as_of: str) -> dict:
    """The history payload's block: each season against its own anchor."""
    return {"as_of": as_of,
            "basis": "each season's rows against that season's own league anchor",
            "seasons": per_season}


def history_season(ctx: dict, side: str, n: dict) -> dict:
    return {**_anchor_block(ctx, side), "n": dict(n)}


# --------------------------------------------------------------------------- #
# The served-artifact contract (read by the three boards' contract tests)
# --------------------------------------------------------------------------- #
_SIDES = {"sp": ("starters", SP_ROW_KEYS, SP_TEAM_KEYS, "p_ip", "rot_par"),
          "rp": ("relievers", RP_ROW_KEYS, RP_TEAM_KEYS, "p_ip", "pen_par"),
          "hit": ("hitters", HIT_ROW_KEYS, HIT_TEAM_KEYS, "p_pa", "lineup_par")}


# Half a point of rounding, plus the served rate's own rounding (P/IP to 2
# places moves PAR by at most 0.03; P/PA to 3 places by at most 0.02).
PAR_TOL = 0.55


def check_board(doc: dict, side: str) -> list[str]:
    """Problems with a served board's pitch-rate keys, [] when it is clean.

    No block: no row or team carries a new key (the dark build). A block: every
    row and team carries every new key; a rate is None or positive; PAR is the
    nearest point of 100 x rate / anchor (within the served rounding); the
    starts-only length never exceeds ip_per_gs; the clubs' team PAR averages
    100 within the integer rounding."""
    list_key, row_keys, team_keys, rate_key, team_par_key = _SIDES[side]
    rows, teams = doc.get(list_key) or [], doc.get("teams") or []
    bad: list[str] = []
    blk = doc.get(PAYLOAD_KEY)
    if blk is None:
        for r in rows:
            if set(row_keys) & set(r):
                bad.append(f"row {r.get('mlbam')} carries a pitch-rate key with no block")
        for t in teams:
            if set(team_keys) & set(t):
                bad.append(f"team {t.get('team')} carries a pitch-rate key with no block")
        return bad
    anchor = (blk.get("anchors") or {}).get(rate_key)
    for r in rows:
        missing = [k for k in row_keys if k not in r]
        if missing:
            bad.append(f"row {r.get('mlbam')} lacks {missing}")
            continue
        rate = r[rate_key]
        if rate is None:
            if r["par"] is not None:
                bad.append(f"row {r.get('mlbam')} has PAR with no rate")
            continue
        if not isinstance(rate, float) or rate <= 0:
            bad.append(f"row {r.get('mlbam')} {rate_key} {rate!r}")
        if not isinstance(r["par"], int):
            bad.append(f"row {r.get('mlbam')} par {r['par']!r}")
        elif anchor and abs(r["par"] - 100.0 * rate / anchor) > PAR_TOL:
            bad.append(f"row {r.get('mlbam')} par {r['par']} vs {100.0 * rate / anchor:.2f}")
        if side == "sp" and r.get("sp_ip_per_gs") is not None and r.get("ip_per_gs") is not None:
            if r["sp_ip_per_gs"] > r["ip_per_gs"] + 0.011:
                bad.append(f"row {r.get('mlbam')} sp_ip_per_gs above ip_per_gs")
    pars = []
    for t in teams:
        missing = [k for k in team_keys if k not in t]
        if missing:
            bad.append(f"team {t.get('team')} lacks {missing}")
        elif t[team_par_key] is not None:
            pars.append(t[team_par_key])
    if pars and abs(sum(pars) / len(pars) - 100.0) > 0.5:
        bad.append(f"team PAR averages {sum(pars) / len(pars):.2f}, not 100")
    return bad
