# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Alchemy Lab - the sidecar export (data/pal.json).

Assembles the role-conversion board from reachable, mostly-bulk sources
(FanGraphs is 403-blocked, so no Stuff+/role-split scrapes):

  ROLE + rates    bullpen_export.load_season_pitching(year) - StatsAPI season
                  pitching 2018-2026 (GS/G/IP -> role; K%/BB%).
  ARSENAL         pybaseball.statcast_pitcher_arsenal_stats(year) - per-pitch
                  usage / whiff / xwOBA / hard-hit, ONE bulk call per season.
  VELOCITY        pybaseball.statcast_pitcher_pitch_arsenal(year) - avg velo per
                  pitch, bulk.
  PLATOON         StatsAPI sitCodes=vl,vr - OPS-against by batter hand, one
                  leaderboard-style call per pitcher (NOT a feed walk).
  REM+ projection rem_plus (display-only relief projection for SP->RP arms).

Produces three sections (RP->SP candidates, SP->RP candidates, conversion
history) plus a backtest scorecard. The backtest is a SIGN CHECK, not a weight
fitter: the observed conversion sample is tiny and selection-biased, so the fit
weights are frozen priors and we report Spearman rho (pre-conversion fit vs the
held-the-role label) with a caveat, plus where converters fall in the full-pool
fit distribution. The relief K% bump used by the REM+ projection is MEASURED from
the converters themselves.

BASIS STAMP (2026-09-06). The backtest block now names the WAR series it was
computed on (`backtest.war_basis`, whatever war_source.DEFAULT_PROVIDER served
this run) and carries the pre-registered per-direction gate verdict out of
data/pal_eval.json together with the series THAT was measured on
(`backtest.gate`). It does NOT re-run the gate on the served series and it
refuses to claim that it has: as of this stamp the live rhos are eWAR v2
(+0.025 RP->SP, +0.278 SP->RP, data/pal.json) and the gate is bWAR (-0.2062 /
+0.2916, data/pal_eval.json generated_at 2026-07-15). Nothing in this file
fits, scores or re-gates a direction; docs/e3-rp-sp-closure.md forbids
re-gating RP->SP by expanding the event set.

Run: `python pal_export.py`. Wired into run_monthly (best-effort). NETWORK-GATED:
nothing fetches at import; any pull failure logs and degrades (a null component
just drops from the renormalized blend) rather than aborting."""
from __future__ import annotations

import concurrent.futures as cf
import functools
import json
import logging
import os
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import bullpen_export as be
import pal_conversion as pc
import rem_plus
from pal_conversion import PalArm

_log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


@functools.lru_cache(maxsize=1)
def _efv_index() -> tuple:
    """({player_key: xfv_grade}, frozenset of floor keys) off data/xfv.json, in one
    parse. A floor key carries xfv_grade_is_floor: the outcome map returned its
    lowest knot, so its 20.0 is the bottom of the scale and not a resolved level.
    Both empty when the artifact is absent, so callers fall back to consensus."""
    try:
        x = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, frozenset()
    by = x.get("by_player") if isinstance(x, dict) else None
    if not isinstance(by, dict):
        return {}, frozenset()
    grades = {k: v.get("xfv_grade") for k, v in by.items()
              if isinstance(v, dict) and v.get("xfv_grade") is not None}
    floor = frozenset(k for k, v in by.items()
                      if k in grades and v.get("xfv_grade_is_floor") is True)
    return grades, floor


def _efv_by_key() -> dict:
    """{player_key: xfv_grade} off data/xfv.json - the site-wide grade."""
    return _efv_index()[0]


def _efv_floor_keys() -> frozenset:
    """player_keys whose eFV grade is the outcome map's floor (xfv_grade_is_floor)."""
    return _efv_index()[1]


OUT_PATH = DATA_DIR / "pal.json"
EVAL_PATH = DATA_DIR / "pal_eval.json"

HISTORY_YEARS = [2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026]  # 2020 kept out of pairs
CAND_MIN_IP = 20.0
STATSAPI = "https://statsapi.mlb.com/api/v1"

#: What each declared war_source provider measures, in one line, for the payload
#: stamp. war_source.py is the authority on the ids; this is display text only.
_WAR_SERIES = {
    "bwar": ("bWAR: the Baseball-Reference run frame, pitchers priced on the "
             "runs they actually allowed"),
    "ewar_v2": ("eWAR v2: the Baseball-Reference run frame with pitching "
                "re-priced on FIP within role (fielding unchanged pending SDR; "
                "position players match bWAR except in seasons they also pitched)"),
    "ewar_merged": "eWAR merged (declared, not servable)",
}

#: The provider load_bref_pitcher_war() actually READ in this process. None
#: until it runs, and it stays None when the pull fails or when a harness
#: substitutes its own loader (tools/pal_backtest_lab.py does), so the payload
#: stamp can never name a WAR series this build did not read.
_WAR_PROVIDER: Optional[str] = None


def _num(v):
    return be._num(v)


# --------------------------------------------------------------------------- #
# data pulls (network-gated)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=16)
def load_arsenal(year: int) -> dict:
    """{mlbam: [ {pitch, usage(0-1), whiff(0-1), est_woba, hard_hit(0-1)} ]}."""
    try:
        import pybaseball as pyb
        df = pyb.statcast_pitcher_arsenal_stats(int(year))
    except Exception as e:
        _log.warning("arsenal_stats(%s) failed: %s", year, e)
        return {}
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            pid = r.get("player_id")
            if pid is None:
                continue
            out.setdefault(int(pid), []).append({
                "pitch": r.get("pitch_type"),
                "usage": (_num(r.get("pitch_usage")) or 0) / 100.0,
                "whiff": (_num(r.get("whiff_percent")) or 0) / 100.0,
                "est_woba": _num(r.get("est_woba")),
                "hard_hit": (_num(r.get("hard_hit_percent")) or 0) / 100.0,
            })
    except Exception as e:
        _log.warning("arsenal parse(%s) failed: %s", year, e)
    return out


@functools.lru_cache(maxsize=16)
def load_velo(year: int) -> dict:
    """{mlbam: top-fastball avg velo}."""
    try:
        import pybaseball as pyb
        df = pyb.statcast_pitcher_pitch_arsenal(int(year))
    except Exception as e:
        _log.warning("pitch_arsenal velo(%s) failed: %s", year, e)
        return {}
    out: dict = {}
    fb_cols = ["ff_avg_speed", "si_avg_speed", "fc_avg_speed"]
    try:
        for r in df.to_dict("records"):
            pid = r.get("pitcher")
            if pid is None:
                continue
            vs = [_num(r.get(c)) for c in fb_cols if _num(r.get(c)) is not None]
            if vs:
                out[int(pid)] = round(max(vs), 1)
    except Exception as e:
        _log.warning("velo parse(%s) failed: %s", year, e)
    return out


def _platoon_one(pid_year):
    pid, year = pid_year
    import urllib.request as U
    url = (f"{STATSAPI}/people/{pid}/stats?stats=statSplits&sitCodes=vl,vr"
           f"&group=pitching&season={year}&gameType=R")
    try:
        req = U.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with U.urlopen(req, timeout=20) as r:
            d = json.load(r)
        vals, tbf = {}, {}
        for s in d.get("stats", []):
            for sp in (s.get("splits") or []):
                code = (sp.get("split") or {}).get("code")
                st = sp.get("stat") or {}
                ops = _num(st.get("ops"))
                if code in ("vl", "vr") and ops is not None:
                    vals[code] = ops
                    tbf[code] = _num(st.get("battersFaced"))
        mt = (min(tbf["vl"], tbf["vr"]) if tbf.get("vl") is not None and tbf.get("vr") is not None else None)
        return pid, vals.get("vl"), vals.get("vr"), mt
    except Exception:
        return pid, None, None, None


def load_platoon(pid_years: list, workers: int = 12) -> dict:
    """{(mlbam, year): (ops_vl, ops_vr)} for a set of (pid, year) pairs."""
    out: dict = {}
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_platoon_one, py): py for py in pid_years}
        for fut in cf.as_completed(futs):
            pid, year = futs[fut]
            try:
                _pid, vl, vr, mt = fut.result()
                out[(pid, year)] = (vl, vr, mt)
            except Exception:
                out[(pid, year)] = (None, None, None)
    return out


@functools.lru_cache(maxsize=16)
def load_pitch_hand(season: int) -> dict:
    """{mlbam: 'L'|'R'} for every MLB pitcher, one bulk call (reverse platoon)."""
    try:
        data = be._get_json("sports/1/players", {"season": int(season)})
    except Exception as e:
        _log.warning("pitchHand fetch failed: %s", e)
        return {}
    out = {}
    for p in data.get("people", []):
        ph = (p.get("pitchHand") or {}).get("code")
        if p.get("id") and ph:
            out[int(p["id"])] = ph
    return out


@functools.lru_cache(maxsize=1)
def load_bref_pitcher_war() -> dict:
    """{year: {mlbam: WAR}} - pitcher WAR by season on the war_source default
    provider (eWAR v2 from the 2026-09 epoch: Baseball-Reference run frame with
    pitching re-priced on FIP within role), summed across in-season stints
    (traded pitchers), for the "WAR produced by conversion" read. One bulk pull
    (war_source.stint_frame('pit'); the explicit 'bwar' provider would be the raw
    pybaseball.bwar_pitch input); best-effort, {} on any failure so the
    history still renders without the WAR column.

    RECORDS the provider it read into the module global _WAR_PROVIDER, which is
    what stamps the served payload. The name of this function is now a lie about
    its own default (it has said 'bref' since the bWAR days); the stamp is there
    so a reader of data/pal.json never has to trust the name."""
    global _WAR_PROVIDER
    try:
        import war_source
        provider = war_source.DEFAULT_PROVIDER
        df = war_source.stint_frame("pit")
    except Exception as e:  # noqa: BLE001
        _log.warning("bref pitcher WAR unavailable: %s", e)
        return {}
    _WAR_PROVIDER = provider
    out: dict = {}
    try:
        for r in df.to_dict("records"):
            mid, yr, war = r.get("mlb_ID"), r.get("year_ID"), r.get("WAR")
            if mid is None or yr is None or war is None:
                continue
            try:
                mid_i, yr_i, war_f = int(float(mid)), int(yr), float(war)
            except (TypeError, ValueError):
                continue
            out.setdefault(yr_i, {})
            out[yr_i][mid_i] = out[yr_i].get(mid_i, 0.0) + war_f
    except Exception as e:  # noqa: BLE001
        _log.warning("bref pitcher WAR parse failed: %s", e)
        return {}
    return out


def load_player_links() -> dict:
    """{mlbam: link} from data/player_links.json (mlbam <-> prospx key)."""
    try:
        d = json.loads((DATA_DIR / "player_links.json").read_text(encoding="utf-8"))
        return {e["mlbam"]: e for e in (d.get("byKey") or {}).values() if e.get("mlbam")}
    except Exception:
        return {}


@functools.lru_cache(maxsize=1)
def _graduated_player_keys() -> frozenset:
    """player_keys of prospects with an MLB debut on record (data/debuts.json).
    A HARD MLB-graduation gate for the prospect watch: anyone here has reached the
    majors and is no longer a conversion-watch prospect. Empty set on any failure
    (never crash the export)."""
    try:
        d = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
    except Exception as e:
        _log.warning("debuts.json unavailable for graduation gate: %s", e)
        return frozenset()
    return frozenset(e.get("player_key") for e in d if e.get("player_key"))


def load_prospect_pitchers(exclude_keys: Optional[set] = None) -> list:
    """Prospect pitcher pool with 20-80 scout tool grades. Best-effort: needs the
    prospect DB, so degrades to [] where it is absent (tests / no DB).

    A hard MLB-graduation gate drops anyone with an MLB debut on record
    (data/debuts.json) or with meaningful MLB service (`exclude_keys`, player_keys
    the caller resolves from career MLB innings via player_links). This catches
    established MLB pitchers whose prospect record was never marked debuted
    (e.g. NPB/KBO arrivals like Kodai Senga) that the status signal alone misses."""
    graduated = set(_graduated_player_keys())
    if exclude_keys:
        graduated |= set(exclude_keys)
    try:
        from storage import load_all_snapshots
        from consensus import build_timeseries, _is_pitcher_pos, ADOPT_NORMALIZED_CONSENSUS
        ts = build_timeseries(load_all_snapshots(), normalize=ADOPT_NORMALIZED_CONSENSUS)
    except Exception as e:
        _log.warning("prospect pool load unavailable: %s", e)
        return []
    out = []
    for p in ts:
        try:
            if p.player_key in graduated:
                continue    # hard MLB-graduation gate (debuted or meaningful MLB service)
            if getattr(p, "status", "") != "active" or not _is_pitcher_pos(p.position):
                continue
            pt = p.points[-1] if getattr(p, "points", None) else None
            tools = (getattr(pt, "tools_consensus", None) or getattr(pt, "tools", None) or {}) if pt else {}
            keys = list(pc.PROSPECT_TOOL_KEYS) + ["cmd"]
            tools = {k: _num(tools.get(k)) for k in keys if _num(tools.get(k)) is not None}
            if not tools:
                continue
            # fvE = the site-wide eFV grade; fv stays as the consensus close so
            # the card can fall back where eFV abstains. Serving only fv meant
            # an unlabeled consensus number under a bare "FV" label.
            # fvE_is_floor rides with it: the card names a floor grade as the
            # scale floor instead of printing 20 as if it were a level.
            efv = _efv_by_key().get(p.player_key)
            out.append({"player_key": p.player_key, "name": p.player_name, "org": p.org,
                        "position": p.position, "fv": _r(getattr(p, "fv_close", None), 1),
                        "fvE": _r(efv, 1),
                        "fvE_is_floor": efv is not None and p.player_key in _efv_floor_keys(),
                        "tools": tools})
        except Exception:
            continue
    return out


MLB_SERVICE_IP = 50.0   # career MLB innings that mark a pitcher as graduated


def _mlb_service_keys(by_pid: dict, links: dict) -> set:
    """player_keys of pitchers with meaningful career MLB innings (>= MLB_SERVICE_IP
    across the loaded seasons), resolved from their MLBAM id via player_links. The
    service half of the prospect-watch graduation gate (backstops debuts.json for
    foreign-league arrivals the debut tracker never marked)."""
    keys = set()
    for mlbam, byyr in by_pid.items():
        try:
            tot = sum(be.ip_to_float(r.get("IP")) for r in byyr.values())
        except Exception:
            continue
        if tot < MLB_SERVICE_IP:
            continue
        lk = links.get(mlbam)
        if lk and lk.get("key"):
            keys.add(lk["key"])
    return keys


# --------------------------------------------------------------------------- #
# W3 PAL-XRV (docs/wills-2026-07-23/GATES.md section W3) - default OFF:
#   EEPHUS_PAL_XRV       ARM-1: per-type AAA aStuff+ blended into the stuff
#                        reads (pal_conversion.stuff_read) for covered arms.
#   EEPHUS_PAL_XRV_RECO  ARM-2: pitch-add family holes ranked by league-mean
#                        per-type xRV (display only; independent of ARM-1 so
#                        the recommender can ship under COVERAGE-STARVED).
# --------------------------------------------------------------------------- #
AAA_STUFF_PATH = DATA_DIR / "stuff_plus_aaa.json"


@functools.lru_cache(maxsize=1)
def _load_aaa_stuff():
    """(players, league_xrv_by_type) from the AAA aStuff+ sidecar; ({}, {})
    best-effort - a missing/old sidecar degrades to the incumbent paths."""
    try:
        d = json.loads(AAA_STUFF_PATH.read_text(encoding="utf-8"))
        return (d.get("players") or {},
                (d.get("meta") or {}).get("league_xrv_by_type") or {})
    except Exception as e:                                     # noqa: BLE001
        _log.warning("stuff_plus_aaa sidecar unavailable: %s", e)
        return {}, {}


def aaa_coverage(players: dict, mlbam: int, season: int) -> Optional[dict]:
    """The W3 coverage gate: the pitcher's AAA aStuff+ by_type rows, ONLY when
    his sidecar season is the scored season or the prior one with >=
    pal_conversion.PAL_XRV_MIN_PITCHES pitches. None otherwise (the arm stays
    on the incumbent stuff read byte-identically - clause P3)."""
    row = (players or {}).get(str(mlbam))
    if not row or not row.get("by_type"):
        return None
    if row.get("season") not in (season, season - 1):
        return None
    if (row.get("n_pitches") or 0) < pc.PAL_XRV_MIN_PITCHES:
        return None
    return row["by_type"]


def _prospect_role(pos: Optional[str]) -> Optional[str]:
    pos = (pos or "").upper()
    if "SP" in pos:
        return "SP"
    if "RP" in pos or "IRP" in pos or "CL" in pos:
        return "RP"
    return None


def _was_starter(by_pid: dict, mlbam: int, cur_season: int) -> bool:
    """Did this pitcher hold a starting role in a prior MLB season (>= ~half a
    rotation turn)? The free MLB-history half of the starter-pedigree signal."""
    for y, r in by_pid.get(mlbam, {}).items():
        if y >= cur_season:
            continue
        if pc.role_of(r.get("G"), r.get("GS"), r.get("IP")) == "SP" and be.ip_to_float(r.get("IP")) >= 40:
            return True
    return False


# --------------------------------------------------------------------------- #
# arm assembly
# --------------------------------------------------------------------------- #
def build_arm(row: dict, arsenal: dict, velo: dict, platoon: dict, year: int) -> PalArm:
    mlbam = row["mlbam"]
    tbf = _num(row.get("BF")) or 0
    so = _num(row.get("SO")) or 0
    bb = _num(row.get("BB")) or 0
    ipf = be.ip_to_float(row.get("IP"))
    er = _num(row.get("ER")) or 0
    plat = platoon.get((mlbam, year)) or (None, None, None)
    return PalArm(
        mlbam=mlbam, name=row.get("name", ""), team=row.get("team", ""), season=year,
        role=pc.role_of(row.get("G"), row.get("GS"), row.get("IP")) or "",
        g=_num(row.get("G")) or 0, gs=_num(row.get("GS")) or 0, ip=ipf, tbf=tbf,
        k_pct=(so / tbf) if tbf else None, bb_pct=(bb / tbf) if tbf else None,
        era=(er * 9.0 / ipf) if ipf else None,
        arsenal=arsenal.get(mlbam, []), fb_velo=velo.get(mlbam),
        ops_vl=plat[0], ops_vr=plat[1], platoon_tbf=(plat[2] if len(plat) > 2 else None),
    )


# --------------------------------------------------------------------------- #
# backtest helpers
# --------------------------------------------------------------------------- #
def _spearman(xs, ys):
    n = len(xs)
    if n < 4:
        return None
    def _ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n)) ** 0.5
    vy = sum((ry[i] - my) ** 2 for i in range(n)) ** 0.5
    return None if vx == 0 or vy == 0 else cov / (vx * vy)


def _war_basis(war_by_year: dict, stamped: str) -> dict:
    """Which WAR series produced the history WAR column and the war_delta rhos
    in THIS build, and on what date. Pure labelling: it reads the global the
    loader set and computes nothing about the model.

    THREE states, and they are three different statements:
      available False               the pull failed, so every war_delta rho in
                                    the block is None by construction rather
                                    than by measurement.
      available, provider_known F   WAR rows are here but this process never ran
                                    the loader (a substituted one, e.g. the
                                    lab's cache), so the series is UNLABELLED
                                    and must not be named.
      available, provider_known T   the normal path; `series` names it."""
    provider = _WAR_PROVIDER
    return {
        "provider": provider,
        "series": _WAR_SERIES.get(provider),
        "source": "war_source.stint_frame('pit') on war_source.DEFAULT_PROVIDER",
        "stamped": stamped,
        "n_seasons": len(war_by_year),
        "available": bool(war_by_year),
        "provider_known": provider is not None,
    }


def _eval_gate(live_provider: Optional[str]) -> Optional[dict]:
    """The PRE-REGISTERED per-direction gate verdict, carried out of
    data/pal_eval.json into the served payload.

    THIS READS AN ARTIFACT. It does not re-run the gate, re-fit a weight or
    re-score an event: tools/pal_backtest_lab.py owns that harness, and
    docs/e3-rp-sp-closure.md forbids re-gating RP->SP by expanding the event
    set. The carry exists because the page has to be able to name the verdict
    AND the WAR series the verdict was measured on, and as of 2026-09-06 those
    are two different series: the eval artifact is generated_at 2026-07-15 and
    its primary_outcome names bWAR (rho -0.2062 / +0.2916), while the live rhos
    beside it come from war_source.DEFAULT_PROVIDER, eWAR v2 since the
    2026-09-03 epoch (rho +0.025 / +0.278 in data/pal.json).

    Returns None when the artifact is missing, unreadable or carries no
    per-direction block; the page then says the verdict is unavailable instead
    of asserting one."""
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    dirs_in = j.get("per_direction")
    if not isinstance(dirs_in, dict) or not dirs_in:
        return None
    # The eval has no provider field (it predates the epoch), so read the basis
    # off its own primary_outcome wording rather than assuming one.
    low = str(j.get("primary_outcome") or "").lower()
    basis = "ewar_v2" if "ewar" in low else ("bwar" if "bwar" in low else None)
    out_dirs: dict = {}
    rule = None
    for d, v in dirs_in.items():
        if not isinstance(v, dict):
            continue
        g = v.get("gate") or {}
        rule = rule or g.get("rule")
        best = v.get("best_baseline")
        out_dirs[d] = {
            "pass": g.get("pass"),
            "n_gate": v.get("n_gate"),
            "rho_fit_war_delta": v.get("rho_fit_war_delta"),
            "best_baseline": best,
            "best_baseline_rho": (v.get("baseline_rho_war_delta") or {}).get(best),
            "gap_lo95": (v.get("gap_ci_vs_best") or {}).get("lo95"),
        }
    if not out_dirs:
        return None
    return {
        "artifact": "data/pal_eval.json",
        "generated_at": j.get("generated_at"),
        "basis_provider": basis,
        "basis_series": _WAR_SERIES.get(basis),
        "rule": rule,
        "same_basis_as_live": bool(basis) and basis == live_provider,
        "per_direction": out_dirs,
        "note": ("Carried from the eval artifact, never re-run here. A direction "
                 "with pass=false ships as a structural screen: its FIT ordering "
                 "is not validated against realized WAR change."),
    }


def _basis_sentence(war_basis: dict, gate: Optional[dict]) -> str:
    """One sentence naming the WAR series under the live rhos and the series the
    gate verdict was measured on, so a reader can never take the two for one
    measurement. Derived from the stamps, so it cannot go stale on its own."""
    if not war_basis.get("available"):
        live = ("WAR outcomes are UNAVAILABLE in this build (the WAR pull failed), so "
                "every war_delta rho above is null by construction, not by measurement.")
    elif not war_basis.get("provider_known"):
        live = ("WAR outcomes are present but UNLABELLED: this build did not run the "
                "loader that records the series (a substituted loader), so the rhos "
                "above cannot be attributed to a WAR provider.")
    else:
        live = ("WAR outcomes are on " + (war_basis.get("series")
                                          or str(war_basis.get("provider")))
                + ", stamped " + str(war_basis.get("stamped")) + ".")
    if not gate:
        return live + (" No gate verdict is available: data/pal_eval.json is missing "
                       "or carries no per-direction block.")
    out = (live + " The pre-registered gate (data/pal_eval.json, "
           + str(gate.get("generated_at")) + ") ran on "
           + (gate.get("basis_series") or str(gate.get("basis_provider"))
              or "an unlabelled WAR series") + ".")
    if (war_basis.get("available") and war_basis.get("provider_known")
            and not gate.get("same_basis_as_live")):
        out += (" It has NOT been re-run on the series above, so the rhos and the "
                "verdicts beside them are not the same measurement.")
    return out


def _build_rem_pool(rows_2026: list, arsenal, velo, platoon) -> rem_plus.Pool:
    relievers = be.build_relievers(rows_2026, {}, {})
    pool = [r for r in relievers if rem_plus.is_true_reliever(r)]
    for r in pool:
        rem_plus.derive_rates(r)
    return rem_plus.build_pool(pool)


# --------------------------------------------------------------------------- #
# prospect role-mismatch watch: the staging bound (2026-07-30, owner decision)
# --------------------------------------------------------------------------- #
# The watch used to be "every mismatch at FV >= 40, sorted by FV, capped at 150",
# with the cap a bare default argument that was never written into data/pal.json and
# never named in the copy. That is a SILENT truncation, and the list sits at 123
# today: one source, or the owed position-seam reconciliation below, puts it through
# the cap without anybody being told.
#
# It is now STAGED: ranked by mismatch SEVERITY, floored at a severity threshold, and
# bounded by a named cap, with all three numbers emitted into the payload and stated
# in the /pal/ copy. The unbounded set stays in the payload under `prospect_watch_all`
# for anyone who wants it (and it is what the prospx pitcher-card chip joins against,
# so no player loses their chip to the staging).
#
# WHY 10.0, and why it is not tuned. `starter_shape`'s SWING band is
# [SHAPE_RP_MAX, SHAPE_SP_MIN] = [40, 60], twenty points wide, centred on 50. The
# threshold asks a flagged arm to sit at least HALF THAT BAND past its own boundary,
# i.e. shape <= 30 for a starter that profiles in relief, or >= 70 for a reliever that
# could start. That is a structural bound read off the band the model already defines,
# in the SFF_MOVE_CAP_FV tradition of a round a-priori bound rather than a number
# fitted to a metric. It is NOT a backtested severity: nothing here is backtested,
# which is why the copy calls the whole surface a descriptive screen.
#
# WHY NO SECOND CONFIRMING SIGNAL. The owner's decision offered "and/or require a
# second confirming signal". There is no admissible one:
#   * MiLB USAGE (role_usage.current_season_pitching) is CIRCULAR for exactly the
#     population that motivated the staging. Those rows' position labels were
#     themselves derived from that usage line by usage_position_override, so usage
#     would confirm itself.
#   * AAA aStuff+ is genuinely independent, but it is AAA-only and this watch is
#     bottom-heavy (99 of 123 entries at FV <= 44), so coverage on the flagged arms is
#     near zero. It is also behind a default-off env flag.
#   * arsenal_depth and cmd are the two INPUTS to starter_shape, so neither is
#     independent of the severity being staged.
# A severity threshold on the one continuous quantity the model produces is therefore
# the honest design, and the absence of a confirmer is recorded rather than papered
# over with a correlated one.
PROSPECT_WATCH_FV_MIN = 40.0        # pre-existing product floor, now named
PROSPECT_WATCH_MARGIN_MIN = 10.0    # half the 20-point SWING band (pc.SHAPE_SWING_BAND)
PROSPECT_WATCH_CAP = 60             # bounded slice; spotlights.TOP_N precedent


def build_prospect_watch_all(prospects: list) -> list:
    """EVERY role mismatch at or above the FV floor, ranked by severity. No cap.

    This is the unbounded set the payload keeps under `prospect_watch_all`, and it is
    what the prospx pitcher-card chip joins against, so staging the /pal/ list does not
    silently strip a player's role-conversion read off their card."""
    watch = []
    for p in prospects:
        rf = pc.prospect_role_fit(p.get("tools"), p.get("position"))
        if not rf["mismatch"] or (p.get("fv") or 0) < PROSPECT_WATCH_FV_MIN:
            continue
        # fvE RIDES ALONG. assets/pal.js reads `p.fvE != null ? Math.round(p.fvE)
        # : fCeil(p.fv)`, and this entry never carried fvE, so the eFV branch was
        # dead on 202 of 202 rows and the card always showed the consensus close.
        # load_prospect_pitchers has resolved the eFV grade all along; it was
        # dropped here, one line from the surface that wanted it.
        watch.append({"player_key": p.get("player_key"), "name": p["name"],
                      "org": p.get("org"), "position": p.get("position"),
                      "fv": p.get("fv"), "fvE": p.get("fvE"),
                      "fvE_is_floor": bool(p.get("fvE_is_floor")) and p.get("fvE") is not None,
                      "tools": p.get("tools"), **rf})
    # Severity first (the owner's ranking), FV as the tiebreak, name as the stable
    # third key: starter_shape is quantized hard enough that ties are the norm, and
    # without a deterministic third key the served order would follow pool order.
    watch.sort(key=lambda x: (-(x.get("mismatch_margin") or 0.0),
                              -(x.get("fv") or 0), x.get("name") or ""))
    return watch


def build_prospect_watch(prospects: list, cap: int = PROSPECT_WATCH_CAP,
                         margin_min: float = PROSPECT_WATCH_MARGIN_MIN) -> list:
    """The /pal/ prospect conversion watch: the role MISMATCHES worth a look (a
    scouted starter that profiles as a reliever, or vice versa), gated to real
    prospects (FV >= PROSPECT_WATCH_FV_MIN), STAGED at a severity threshold and
    bounded by a visible cap. Shape-only (scout tools, no MiLB stuff physics).

    Each entry carries `player_key` so a consumer (prospx pitcher cards) can join
    the role-fit read back onto its own prospect board by the canonical prospect
    key -- the reason this is a named helper rather than an inline loop."""
    full = build_prospect_watch_all(prospects)
    watch = [w for w in full if (w.get("mismatch_margin") or 0.0) >= margin_min]
    return watch[:cap]


# SEVERITY BANDS on the same structural ruler the threshold already uses. The
# SWING band is 20 points wide, so a mismatch sitting a FULL band width past its
# own boundary is a different object from one sitting the minimum half-band past
# it, and the card printed both as the same plain sentence. The cuts are the band
# read in quarters: full / three-quarter / half (the existing floor). Nothing here
# is fitted, and nothing here is a probability - it is the one continuous quantity
# the shape model produces, banded on its own units.
PROSPECT_WATCH_SEVERITY = (
    ("severe", 1.00, "a full swing band past the boundary"),
    ("marked", 0.75, "three quarters of the band past the boundary"),
    ("modest", 0.50, "half the band past the boundary, the listing floor"),
)


def prospect_watch_severity_cuts(margin_min: float = PROSPECT_WATCH_MARGIN_MIN) -> list:
    """[{key, min_margin, label}] biggest first. `margin_min` is passed through so
    a caller that moves the listing floor cannot leave the bottom band claiming a
    cut the export is not applying."""
    out = []
    for key, frac, label in PROSPECT_WATCH_SEVERITY:
        cut = round(pc.SHAPE_SWING_BAND * frac, 1)
        out.append({"key": key, "min_margin": max(cut, margin_min) if key == "modest" else cut,
                    "label": label})
    return out


def _severity_of(margin, cuts: list):
    m = _num(margin)
    if m is None:
        return None
    for c in cuts:
        if m >= c["min_margin"]:
            return c["key"]
    return None


def prospect_watch_rule(full: list, watch: list,
                        margin_min: float = PROSPECT_WATCH_MARGIN_MIN,
                        cap: int = PROSPECT_WATCH_CAP,
                        pool: Optional[list] = None) -> dict:
    """The bound, made visible in the payload. Every number the /pal/ copy states
    comes from here, so the surface can never claim a bound it is not applying.

    `pool` adds the COVERAGE half of that promise. A mismatch needs a stated role
    for the shape to disagree with, and 691 of the 1,875 pool pitchers (36.9%)
    carry a position of RHP, LHP or P, which states handedness and no role. They
    are structurally unable to appear on this list, correctly, and 326 of them
    clear the FV floor. The copy said "1,875 prospect pitchers scanned" and left
    that unsaid, which reads as a screen of the whole pool."""
    qualified = [w for w in full if (w.get("mismatch_margin") or 0.0) >= margin_min]
    just_outside = [w for w in full if (w.get("mismatch_margin") or 0.0) < margin_min]
    best_outside = max((w.get("mismatch_margin") or 0.0) for w in just_outside) if just_outside else None
    cuts = prospect_watch_severity_cuts(margin_min)
    for c in cuts:
        c["n"] = sum(1 for w in watch
                     if _severity_of(w.get("mismatch_margin"), cuts) == c["key"])
    unstated = [p for p in (pool or [])
                if pc.prospect_role_fit(p.get("tools"), p.get("position"))["role"]
                not in ("SP", "RP")]
    return {
        "fv_min": PROSPECT_WATCH_FV_MIN,
        "margin_min": margin_min,
        "cap": cap,
        "n_pool": len(pool) if pool is not None else None,
        "n_role_unstated": len(unstated) if pool is not None else None,
        "n_role_unstated_above_fv": (
            sum(1 for p in unstated if (p.get("fv") or 0) >= PROSPECT_WATCH_FV_MIN)
            if pool is not None else None),
        "n_mismatches": len(full),
        "n_qualified": len(qualified),
        "n_shown": len(watch),
        "n_below_margin": len(just_outside),
        "n_over_cap": max(0, len(qualified) - len(watch)),
        "cap_binding": len(qualified) > len(watch),
        "best_margin_below_threshold": best_outside,
        "swing_band": pc.SHAPE_SWING_BAND,
        "severity_cuts": cuts,
        "basis": ("severity = shape points past the SWING band "
                  f"[{pc.SHAPE_RP_MAX:.0f}, {pc.SHAPE_SP_MIN:.0f}]; threshold is half "
                  "the band width, an a-priori structural bound, not a fitted one"),
    }


# --------------------------------------------------------------------------- #
# candidate TIERS: per-direction, ABSOLUTE, stamped into the payload
# --------------------------------------------------------------------------- #
# The tier titles used to live only in assets/pal.js, on ONE set of breakpoints
# (70/55/42) shared by both directions. That was wrong in two ways at once.
#
# 1. THE TWO FIT SCORES ARE NOT ON THE SAME SCALE. sp_rp_fit multiplies relief
#    upside by a conversion-need factor, so a starter who is succeeding scores
#    low no matter how good the stuff is. That compression is the model working
#    as designed, and it means the SP->RP pool tops out well short of 70: live it
#    runs min 4.1 / median 33.2 / max 62.8, so "Bullpen Upside (70+)" had ZERO
#    members in every build while 129 of 176 arms read "Keep Starting". A top
#    tier that can never be reached is decoration, and a bottom tier holding
#    three quarters of the board is not a tier.
# 2. THE COPY COULD DRIFT FROM THE CUT. A legend hard-coded in the renderer can
#    state a threshold the export is not applying, which is the exact failure the
#    prospect_watch_rule block above exists to prevent.
#
# So: cuts per direction, in this module, stamped into the payload with their
# live member counts, and the renderer reads them.
#
# RP->SP KEEPS 70/55/42. The chart annotation highlights 70+ as "a real starter
# profile" and the `successful` split already carries the premium case, so moving
# that direction's cuts would desynchronise two other surfaces for no gain.
# SP->RP gets 55/45/35: ABSOLUTE cuts, informed by the measured spread but NOT
# per-build quantiles. Quantile tiers move a pitcher's tier when the pool
# composition changes rather than when he does, which is the one thing a tier
# must never do.
#
# NAMES. The SP->RP names are ranking language because that direction's backtest
# is the validated one (pre-conversion FIT out-ranked every same-event baseline
# against realized WAR change). The RP->SP names stay SCREEN and PROFILE
# language on purpose: that direction's backtest is sign-wrong (rho -0.17 at
# n=35, a closed no-ship), so its tiers describe a shape, never a rank.
TIER_CUTS = {
    "rp2sp": (70.0, 55.0, 42.0),
    "sp2rp": (55.0, 45.0, 35.0),
}
TIER_LABELS = {
    "rp2sp": ("Starter Upside", "Worth a Look", "Fringe Fit", "Reliever Profile"),
    "sp2rp": ("Bullpen Upside", "Relief Fit", "Marginal Move", "Keep Starting"),
}
# Top-tier variant for an arm already succeeding in his current role. Only
# RP->SP has one: a reliever who is getting outs AND profiles as a starter is
# the value-additive case, because a starter is worth more than a reliever.
TIER_PREMIUM = {"rp2sp": ("Prime Starter Convert", "successful")}


def tier_rule(rows: list, direction: str) -> dict:
    """The tier cuts and their live membership, for one direction.

    Emitted into data/pal.json so the legend, the badge and the shareable board
    all read the same numbers. A renderer that falls back to its own constants is
    reading a stale payload, and says so."""
    cuts = TIER_CUTS[direction]
    labels = TIER_LABELS[direction]
    fits = sorted(f for f in (_num(r.get("fit")) for r in rows) if f is not None)
    tiers = []
    for i, cut in enumerate(cuts):
        hi = cuts[i - 1] if i else None
        n = sum(1 for f in fits if f >= cut and (hi is None or f < hi))
        tiers.append({"rank": i + 1, "min_fit": cut, "label": labels[i], "n": n})
    tiers.append({"rank": len(cuts) + 1, "min_fit": None,
                  "label": labels[-1], "n": sum(1 for f in fits if f < cuts[-1])})
    prem = TIER_PREMIUM.get(direction)
    if prem:
        label, flag = prem
        tiers[0]["premium_label"] = label
        tiers[0]["premium_flag"] = flag
        tiers[0]["n_premium"] = sum(1 for r in rows
                                    if _num(r.get("fit")) is not None
                                    and _num(r.get("fit")) >= cuts[0] and r.get(flag))
    return {
        "direction": direction,
        "tiers": tiers,
        "n_rows": len(fits),
        "fit_min": fits[0] if fits else None,
        "fit_median": round(statistics.median(fits), 1) if fits else None,
        "fit_max": fits[-1] if fits else None,
        "basis": ("absolute cuts on this direction's own FIT scale, not per-build "
                  "quantiles (a quantile tier moves a pitcher when the pool moves, "
                  "not when he does). The two directions are different 0-100 "
                  "scales and are never compared across the tab."),
    }


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def export(season: Optional[int] = None, *, out_path: Optional[Path] = None,
           write: bool = True, log=print, today: Optional[str] = None) -> int:
    season = int(season or date.today().year)
    out_path = out_path or OUT_PATH
    today = today or date.today().isoformat()

    log(f"  pal: loading season pitching {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]}...")
    by_pid: dict = {}
    rows_by_year: dict = {}
    for y in HISTORY_YEARS:
        rows = be.load_season_pitching(y)
        rows_by_year[y] = rows
        for r in rows:
            r = dict(r); r["season"] = y
            by_pid.setdefault(r["mlbam"], {})[y] = r
    if not rows_by_year.get(season):
        log(f"  pal: no {season} pitching (source blocked); skipping")
        return 0

    # conversions from role flips (cheap, season-stats only). The current
    # season is in progress, so held labels only read seasons through season-1
    # (T1-6: an in-progress b+1 GS-share is not a settled role).
    events = pc.detect_conversions(by_pid, last_closed_season=season - 1)
    log(f"  pal: detected {len(events)} role conversions {HISTORY_YEARS[0]}-{HISTORY_YEARS[-1]}")
    # Current-season (in-progress) conversions that season-cumulative role_of misses
    # because a mid-year switch reads as SWING (e.g. Griffin Jax 2026). Always pending;
    # merged de-duped so a pitcher already caught by the historical detector isn't doubled.
    _seen = {(e["mlbam"], e["year"]) for e in events}
    _inprog = [e for e in pc.detect_in_progress_conversions(by_pid, HISTORY_YEARS[-1])
               if (e["mlbam"], e["year"]) not in _seen]
    events.extend(_inprog)
    log(f"  pal: + {len(_inprog)} in-progress {HISTORY_YEARS[-1]} conversions")

    # measured relief K% bump from the converters (RP->SP loses K, SP->RP gains)
    sp2rp_dk = [ (_num(e["post"]["k_pct"]) - _num(e["pre"]["k_pct"]))
                 for e in events if e["direction"] == "SP->RP"
                 and e["post"]["k_pct"] is not None and e["pre"]["k_pct"] is not None ]
    relief_k_bump = round(statistics.median(sp2rp_dk), 4) if len(sp2rp_dk) >= 5 else pc.DEFAULT_RELIEF_K_BUMP

    log("  pal: pulling arsenal + velocity (bulk Statcast)...")
    arsenal_by_year = {y: load_arsenal(y) for y in HISTORY_YEARS}
    velo_by_year = {y: load_velo(y) for y in HISTORY_YEARS}

    # who needs platoon: the current candidate pool + each converter's TRUE
    # pre-year. detect_conversions pairs seasons up to 2 apart (2020 excluded,
    # injury gaps), so the pre row is e["pre"]["season"], NOT year-1 (T1-6:
    # year-1 silently dropped every gap-2 event from the backtest).
    cur_rows = rows_by_year[season]
    cand_pids = [(r["mlbam"], season) for r in cur_rows
                 if be.ip_to_float(r.get("IP")) >= CAND_MIN_IP]
    pre_pids = [(e["mlbam"], (e.get("pre") or {}).get("season", e["year"] - 1))
                for e in events]
    log(f"  pal: pulling platoon splits for {len(set(cand_pids) | set(pre_pids))} pitcher-seasons...")
    platoon = load_platoon(list(set(cand_pids) | set(pre_pids)))

    # REM+ pool (current relievers) for the SP->RP relief projection
    rem_pool = _build_rem_pool(cur_rows, arsenal_by_year[season], velo_by_year[season], platoon)

    # extensions: throwing hand (reverse platoon), MLB + PROSPX starter pedigree
    pitch_hand = load_pitch_hand(season)
    # ... and for the backtest pre-arms: hand is static, so merge the bulk
    # players call across each distinct pre-year (T1-6: backtested scores must
    # carry the same p_throws input the live board scores do).
    hand_all = {}
    for y in sorted({(e.get("pre") or {}).get("season", e["year"] - 1) for e in events}):
        if y != season:
            hand_all.update(load_pitch_hand(y) or {})
    hand_all.update(pitch_hand)
    links = load_player_links()
    # hard MLB-graduation gate for the prospect watch: anyone with meaningful MLB
    # service (career innings across the loaded seasons) has graduated even when
    # the debut tracker missed them (e.g. NPB/KBO arrivals like Senga). Resolve
    # those MLBAM ids back to prospect player_keys via player_links.
    served = _mlb_service_keys(by_pid, links)
    prospects = load_prospect_pitchers(exclude_keys=served)
    prospx_role_map = {p["player_key"]: _prospect_role(p.get("position")) for p in prospects}

    # W3 PAL-XRV flags (default OFF -> both paths byte-identical to incumbent)
    xrv_on = bool(os.environ.get("EEPHUS_PAL_XRV"))
    xrv_reco_on = bool(os.environ.get("EEPHUS_PAL_XRV_RECO"))
    aaa_players, league_xrv = (_load_aaa_stuff() if (xrv_on or xrv_reco_on)
                               else ({}, {}))

    def _prospx_role_for(mlbam):
        lk = links.get(mlbam)
        return prospx_role_map.get(lk.get("prospx")) if lk and lk.get("prospx") else None

    # ---- current candidates -------------------------------------------------
    rp2sp, sp2rp, platoon_rows = [], [], []
    for r in cur_rows:
        if be.ip_to_float(r.get("IP")) < CAND_MIN_IP:
            continue
        arm = build_arm(r, arsenal_by_year[season], velo_by_year[season], platoon, season)
        arm.p_throws = pitch_hand.get(arm.mlbam)
        arm.was_starter = _was_starter(by_pid, arm.mlbam, season)
        arm.prospx_role = _prospx_role_for(arm.mlbam)
        if xrv_on:      # W3 ARM-1: covered arms blend the per-type aStuff+ read
            arm.aaa_by_type = aaa_coverage(aaa_players, arm.mlbam, season)
        rp = pc.reverse_platoon(arm)
        if rp:
            platoon_rows.append({"mlbam": arm.mlbam, "name": arm.name, "team": arm.team,
                                 "role": arm.role, "min_tbf": _r(arm.platoon_tbf, 0), **rp})
        if arm.role == "RP" and arm.arsenal:
            fit = pc.rp_sp_fit(arm)
            row = _cand_row(arm, fit, "rp2sp")
            row["pitch_add"] = pc.recommend_pitch(
                arm, league_xrv if xrv_reco_on else None)   # W3 ARM-2
            row["reverse_platoon"] = rp
            rp2sp.append(row)
        elif arm.role == "SP" and arm.arsenal:
            fit = pc.sp_rp_fit(arm)
            row = _cand_row(arm, fit, "sp2rp")
            row["proj_relief_rem_plus"] = pc.project_relief_rem_plus(arm, rem_pool, relief_k_bump)
            sp2rp.append(row)
    rp2sp.sort(key=lambda x: x["fit"], reverse=True)
    sp2rp.sort(key=lambda x: x["fit"], reverse=True)
    # reverse-platoon radar: most-reverse first (a hidden strength), extremes flagged
    platoon_rows.sort(key=lambda x: x["reverse_index"], reverse=True)

    # ---- conversion history + backtest -------------------------------------
    war_by_year = load_bref_pitcher_war()   # {year: {mlbam: WAR}}, best-effort
    history, mix_changes = [], []
    pre_fits, labels = [], []           # legacy pooled read (REPORTING ONLY)
    per_dir = {d: {"fit_war": [], "war": [], "fit_held": [], "held": []}
               for d in ("RP->SP", "SP->RP")}
    for e in events:
        # TRUE pre-season (T1-6): the season the detector actually paired.
        # year-1 lost every gap-2 pair (2020 exclusion / injury gaps) and
        # silently dropped them from the labeled backtest set.
        py = (e.get("pre") or {}).get("season", e["year"] - 1)
        pre_row = by_pid.get(e["mlbam"], {}).get(py)
        pre_fit = None
        if pre_row and pre_row.get("mlbam") in arsenal_by_year.get(py, {}):
            pre_arm = build_arm(pre_row, arsenal_by_year.get(py, {}), velo_by_year.get(py, {}), platoon, py)
            # backtested scores carry the SAME inputs the live board scores do
            # (T1-6): throwing hand + the +3.0 starter-pedigree nudge.
            pre_arm.p_throws = hand_all.get(pre_arm.mlbam)
            pre_arm.was_starter = _was_starter(by_pid, pre_arm.mlbam, py)
            if xrv_on:  # W3: backtested scores carry the SAME inputs the live
                # board scores do (the T1-6 parity principle)
                pre_arm.aaa_by_type = aaa_coverage(aaa_players, pre_arm.mlbam, py)
            if pre_arm.arsenal:
                fit = (pc.rp_sp_fit(pre_arm) if e["direction"] == "RP->SP"
                       else pc.sp_rp_fit(pre_arm))
                pre_fit = fit["fit"]
        succ = pc.label_success(e)
        h = dict(e); h["pre_fit"] = pre_fit
        h["success"] = succ
        # WAR produced by the conversion: WAR (eWAR basis) in the pre-role season vs the
        # post-role season, plus the delta. Keyed by the seasons the detector
        # recorded. Absent (older season or no bref row) renders as a dash.
        pre_season = (e.get("pre") or {}).get("season", py)
        post_season = (e.get("post") or {}).get("season", e["year"])
        pre_war = (war_by_year.get(pre_season) or {}).get(e["mlbam"])
        post_war = (war_by_year.get(post_season) or {}).get(e["mlbam"])
        # THE DISPLAYED DELTA IS THE DIFFERENCE OF THE DISPLAYED PARTS, and the
        # STATISTIC KEEPS THE EXACT ONE. These used to be the same key computed
        # two different ways: pre_war and post_war were each rounded to a tenth
        # while war_delta was computed on the UNROUNDED pair and rounded after,
        # so on 23 of 115 rows a reader subtracting the two numbers on screen got
        # a different answer from the coloured delta between them. Reynaldo Lopez
        # read 3.8 to 0.5 with a delta of -3.2, and one row showed the same
        # number twice with a red loss between them.
        #
        # Rounding the difference of the rounded parts fixes the arithmetic a
        # reader can do. It must NOT be what the correlation sees: rounding to a
        # tenth manufactures tie groups, and this is the outcome variable behind
        # the site's only PASS verdict on this model, so war_delta_exact carries
        # the unrounded value and is what feeds the statistic below.
        h["pre_war"] = None if pre_war is None else round(pre_war, 1)
        h["post_war"] = None if post_war is None else round(post_war, 1)
        h["war_delta_exact"] = (None if pre_war is None or post_war is None
                                else post_war - pre_war)
        h["war_delta"] = (None if pre_war is None or post_war is None
                          else round(h["post_war"] - h["pre_war"], 1))
        # pitch-mix change (before/after arsenal usage) for the converter,
        # attached INLINE to the record so the history view can show the arsenal
        # shift per conversion (kept as a standalone array too).
        pre_ars = arsenal_by_year.get(py, {}).get(e["mlbam"])
        post_ars = arsenal_by_year.get(e["year"], {}).get(e["mlbam"])
        if pre_ars and post_ars:
            before, after = _mix(pre_ars), _mix(post_ars)
            h["pitch_mix"] = {"before": before, "after": after}
            mix_changes.append({
                "mlbam": e["mlbam"], "name": e["name"], "team": e["team"],
                "direction": e["direction"], "year": e["year"],
                "before": before, "after": after,
            })
        history.append(h)
        if pre_fit is not None and succ is not None:
            pre_fits.append(pre_fit)
            labels.append(1.0 if succ else 0.0)
            if e["direction"] in per_dir:
                per_dir[e["direction"]]["fit_held"].append(pre_fit)
                per_dir[e["direction"]]["held"].append(1.0 if succ else 0.0)
        # PRIMARY continuous outcome (T1-6): war_delta, PER DIRECTION (the two
        # fit scores are different 0-100 scales - pooling them was never
        # meaningful), closed post seasons only (a partial in-progress post
        # season deflates WAR mechanically).
        if (pre_fit is not None and h["war_delta_exact"] is not None
                and post_season < season and e["direction"] in per_dir):
            per_dir[e["direction"]]["fit_war"].append(pre_fit)
            # THE EXACT DELTA, not the display-rounded one. Feeding a tenth-
            # rounded outcome to a rank correlation manufactures ties: on the
            # SP to RP direction 50 of 61 outcomes fell into rounding-created tie
            # groups, which moved the published rho by about +0.008 on the one
            # direction that carries this model's PASS verdict.
            per_dir[e["direction"]]["war"].append(h["war_delta_exact"])
    history.sort(key=lambda h: (h["year"], -(h["pre_fit"] or 0)), reverse=True)

    rho = _spearman(pre_fits, labels)   # legacy pooled - REPORTING ONLY, not the gate
    per_direction = {}
    for d, v in per_dir.items():
        rw = _spearman(v["fit_war"], v["war"])
        rh = _spearman(v["fit_held"], v["held"])
        per_direction[d] = {
            "n_war": len(v["war"]),
            "rho_prefit_vs_war_delta": None if rw is None else round(rw, 3),
            "n_held": len(v["held"]),
            "rho_prefit_vs_held": None if rh is None else round(rh, 3),
        }
    # where do converters fall in the full-pool fit distribution (selection-bias check)
    full_rp_fits = sorted(x["fit"] for x in rp2sp)
    conv_rp_pct = _percentile_of([h["pre_fit"] for h in history
                                  if h["direction"] == "RP->SP" and h["pre_fit"] is not None], full_rp_fits)

    # BASIS STAMP (2026-09-06). The live rhos move with war_source's default
    # provider and the gate verdict does not, so both get stamped by name: the
    # payload said "eWAR basis" in prose while the served verdict copy was
    # hard-coded to the bWAR-era gate. Labelling only, nothing is re-fitted.
    war_basis = _war_basis(war_by_year, today)
    gate = _eval_gate(war_basis.get("provider"))
    backtest = {
        "n_labeled": len(pre_fits),
        "spearman_prefit_vs_held": None if rho is None else round(rho, 3),
        "per_direction": per_direction,
        "war_basis": war_basis,
        "gate": gate,
        "primary_outcome": ("war_delta (post-season minus pre-season on the war_basis series "
                            "stamped below), per direction, closed post seasons only; the pooled "
                            "held rho above is a legacy reporting field (two different 0-100 scales)"),
        "relief_k_bump_measured": relief_k_bump,
        "converter_median_fit_pool_pctile": conv_rp_pct,
        "disclaimer": ("A screen, not a success-probability model. The conversion sample is small and "
                       "selection-biased (only pitchers teams chose to convert), so the weights are frozen "
                       "priors from the literature. The gated evaluation (per-direction rho vs same-event "
                       "baselines, bootstrap CI) lives in tools/pal_backtest_lab.py -> data/pal_eval.json; "
                       "the rhos here are the live stamp of the same repaired harness. Held labels read "
                       "closed >=20 IP follow-up seasons only. " + _basis_sentence(war_basis, gate)),
    }

    # pitch-add lab: RP->SP candidates with a recommended weapon to add
    pitch_add = [{"mlbam": r["mlbam"], "name": r["name"], "team": r["team"], "fit": r["fit"],
                  "n_pitches": r["n_pitches"], "arsenal": r["arsenal"],
                  "platoon_split": r["platoon_split"], "rec": r["pitch_add"]}
                 for r in rp2sp if r.get("pitch_add")]

    # prospect conversion watch (shape-only, no MiLB stuff physics): the role
    # MISMATCHES worth a look (a scouted starter that profiles as a reliever, or
    # vice versa), gated to real prospects (FV >= 40), STAGED at a severity
    # threshold and bounded by a visible cap. Each entry carries player_key so
    # prospx can cross-link the role-fit read onto its pitcher cards -- and the
    # chip joins `prospect_watch_all`, the unbounded set, so the staging bounds
    # the /pal/ LIST without stripping anybody's card (see build_prospect_watch).
    prospect_watch_all = build_prospect_watch_all(prospects)
    prospect_watch = build_prospect_watch(prospects)
    watch_rule = prospect_watch_rule(prospect_watch_all, prospect_watch,
                                     pool=prospects)

    payload = {
        "generated_at": today, "season": season,
        "n_conversions": len(events),
        "rp2sp": rp2sp, "sp2rp": sp2rp, "history": history,
        "pitch_mix_changes": mix_changes,
        "pitch_add": pitch_add,
        "reverse_platoon": platoon_rows,
        "tier_rule": {"rp2sp": tier_rule(rp2sp, "rp2sp"),
                      "sp2rp": tier_rule(sp2rp, "sp2rp")},
        "prospect_watch": prospect_watch,
        "prospect_watch_all": prospect_watch_all,
        "prospect_watch_rule": watch_rule,
        "n_prospects": len(prospects),
        "backtest": backtest,
        "verdict": _verdict(),
    }

    log(f"  pal: {len(rp2sp)} RP->SP, {len(sp2rp)} SP->RP, {len(events)} conversions, "
        f"{watch_rule['n_shown']}/{watch_rule['n_mismatches']} prospect role-mismatches "
        f"shown (margin >= {watch_rule['margin_min']}, cap {watch_rule['cap']}"
        f"{', BINDING' if watch_rule['cap_binding'] else ''}), "
        f"{len(platoon_rows)} platoon rows; "
        f"backtest rho={backtest['spearman_prefit_vs_held']} (n={backtest['n_labeled']})")
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        tmp.replace(out_path)
        try:
            shown = out_path.relative_to(Path(__file__).parent)
        except ValueError:
            shown = out_path.name
        log(f"  pal: wrote {shown}")
    return len(rp2sp) + len(sp2rp)


def _cand_row(arm: PalArm, fit: dict, kind: str) -> dict:
    row = {
        "mlbam": arm.mlbam, "name": arm.name, "team": arm.team,
        "fit": fit["fit"], "n_pitches": fit["n_pitches"],
        "ip": round(arm.ip, 1), "k_pct": _r(arm.k_pct, 4), "bb_pct": _r(arm.bb_pct, 4),
        "fb_velo": arm.fb_velo, "proj_velo": fit.get("proj_velo"),
        "fb_pct": fit.get("fb_pct"),
        "platoon_split": (round(abs(arm.ops_vl - arm.ops_vr), 3)
                          if arm.ops_vl is not None and arm.ops_vr is not None else None),
        "components": fit["components"], "flags": fit["flags"],
        # succeeding in his CURRENT role? (display-only tiering signal, ERA + K-BB)
        "successful": pc.role_success(arm),
        "arsenal": [{"pitch": p.get("pitch"), "usage": _r(p.get("usage"), 3),
                     "whiff": _r(p.get("whiff"), 3), "est_woba": _r(p.get("est_woba"), 3)}
                    for p in arm.arsenal if (p.get("usage") or 0) >= 0.03],
    }
    if kind == "sp2rp":
        row["best_whiff"] = fit.get("best_whiff")
        row["relief_upside"] = fit.get("relief_upside")
        row["starter_era"] = fit.get("starter_era")
    return row


def _mix(arsenal: list) -> list:
    return sorted([{"pitch": p.get("pitch"), "usage": round((p.get("usage") or 0), 3)}
                   for p in arsenal if (p.get("usage") or 0) >= 0.03],
                  key=lambda x: x["usage"], reverse=True)


def _percentile_of(vals: list, dist: list):
    vals = [v for v in vals if v is not None]
    if not vals or not dist:
        return None
    med = statistics.median(vals)
    below = sum(1 for d in dist if d <= med)
    return round(100.0 * below / len(dist))


def _r(v, n):
    v = _num(v)
    return None if v is None else round(v, n)


def _verdict() -> str:
    try:
        j = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
        return (j.get("verdict") or {}).get("status") or "provisional"
    except Exception:
        return "provisional"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export(int(sys.argv[1]) if len(sys.argv) > 1 else None)
