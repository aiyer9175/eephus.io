# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Sidecar exports for the MLB Free Agency module (Stage 5).

Three sidecars consumed by the standalone /fa/ surface (assets/fa.js +
build_site.py::build_fa - the FA module is SEPARATE from PROSPX, which
carries zero FA bytes; these are fetched from /data/ directly):

  fa_class.json    the 2026-27 Class Board: every constructed member with
                   status/option flags, and - where identity + history
                   resolve - the gated projection, market prediction with
                   bands (mYears/mGuarantee/mAAV), rational value, Contract
                   Surplus ($), Deal+, real comps, and top team fits.
  fa_archive.json  twelve archived winters: condensed signings with the
                   retrospective ledger, per-winter totals and implied $/WAR.
  fa_meta.json     CBA snapshot (carry-forward flags ride every consumer),
                   the estimated $/WAR series, BOTH gate verdicts verbatim
                   (the Accountability surface renders this - misses and
                   all), park factors, team affordability + behavior priors.

Money is exported in raw USD; the frontend's formatMetric(`moneyM`)
owns display rounding. Nulls are omitted; floats rounded - lean wire
format per the owner's load-time ask.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import fa_cba
import fa_fit
import fa_ident
import fa_market as fm
import fa_projection as fp
import storage

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CLASS_YEAR = 2027


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


TWO_WAY_NOTE = ("Two-way profile. The market model prices one side only, so the "
                "predicted contract is a floor.")


def _compact_fit(f: dict, with_org: bool = True) -> dict:
    """Wire-compact fit row. blockedBy entries carry WHO and WHAT KIND - 
    {n, t} where t is 'prospect' (PROSPX near-ETA) or 'mlb' (a contracted
    incumbent already producing at the slot)."""
    blocked = [{"n": b["player_name"], "t": b.get("kind", "prospect")}
               for b in f["components"]["need"]["blocked_by"]]
    out = {
        "fit": f["fit"],
        "need": f["components"]["need"]["score"],
        "window": f["components"]["window"]["score"],
        "afford": f["components"]["afford"]["score"],
        "park": f["components"]["park"]["score"],
        "behavior": f["components"]["behavior"]["score"],
        "blockedBy": blocked or None,
    }
    if with_org:
        out = {"org": f["org"], **out}
    return _clean(out)


def _load_overrides() -> dict[str, dict]:
    """Owner-curated per-player overrides (data/fa_overrides.json):
    two_way / note / exclude. Disclosure and curation only - never
    touches the model. '_'-prefixed keys are documentation."""
    try:
        d = json.loads((DATA_DIR / "fa_overrides.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (d.get("players") or {}).items()
            if not k.startswith("_") and isinstance(v, dict)}


# Prospect-to-Payday reads BOTH boot exports, in this order.
#
# JOIN REPAIR 2026-08-05. This read timeseries.json ONLY, and timeseries.json is
# the ACTIVE prospect board: a player is removed from it the moment he graduates.
# Every member of an MLB free-agent class graduated years ago, so the join was
# structurally impossible, not merely thin. Measured on the served artifacts:
# 0 of 228 fa_class.json members carry fvArc, and 0 of 228 member keys exist in
# timeseries.json - while 153 of them DO exist in debuts.json, the graduated
# cohort's export, which carries the identical `points` shape (consensus_fv_raw +
# snapshot_date). The whole "Prospect-to-Payday" feature on /fa/ has therefore
# been dark since it shipped, and it looked healthy because a missing arc is
# indistinguishable from "this veteran was never a tracked prospect".
#
# ORDER: the live board first, the graduated cohort second, first source wins.
# A key in both is the same human and the active-board copy is the fresher one;
# in practice the sets are disjoint by construction (graduation moves a player
# from one file to the other).
_ARC_SOURCES = ("timeseries.json", "debuts.json")


def _load_arc_players(name: str) -> list | None:
    """Player rows from one boot export, or NONE when the file is absent or
    unreadable. None-as-sentinel on purpose (same contract as
    bullpen_export._active_mlbam_ids): a load failure must not read downstream
    as "this export legitimately contains nobody", which is the shape that let
    a structurally-broken join publish as a quietly missing feature.

    Handles both layouts: timeseries.json is {"players": [...]}, debuts.json is
    a bare list."""
    path = DATA_DIR / name
    if not path.exists():
        log.warning("fa arc: %s not found - no Prospect-to-Payday arcs from it", path)
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.error("fa arc: %s unreadable - no Prospect-to-Payday arcs from it",
                  path, exc_info=True)
        return None
    players = doc.get("players") if isinstance(doc, dict) else doc
    return players if isinstance(players, list) else None


def _prospect_fv_history(keys: set) -> dict[str, dict]:
    """Read-only Prospect-to-Payday source: condensed consensus-FV arcs from
    the PROSPX boot exports, for class members who were tracked prospects.
    mlbam rides along so the caller can id-gate name-key collisions (the FA
    Jacob Webb is NOT the FV-40 prospect Jacob Webb).

    Only players actually found are returned. A member we cannot resolve gets
    no arc rather than a fabricated or borrowed one."""
    out: dict[str, dict] = {}
    n_loaded = 0
    per_source: list[str] = []
    for name in _ARC_SOURCES:
        players = _load_arc_players(name)
        if players is None:
            continue
        n_loaded += 1
        found = 0
        for p in players:
            key = p.get("player_key")
            if key not in keys or key in out or not p.get("mlbam_id"):
                continue
            pts: list = []
            last = None
            for pt in (p.get("points") or []):
                fv = pt.get("consensus_fv_raw")
                d = (pt.get("snapshot_date") or "")[:10]
                if fv is None or not d:
                    continue
                if last is None or fv != last:
                    pts.append([d, round(fv, 1)])
                    last = fv
            if len(pts) >= 2:
                out[key] = {"mlbam": int(p["mlbam_id"]), "pts": pts[-40:]}
                found += 1
        per_source.append(f"{name}={found}")
    # ALWAYS log the resolved count. A 0 here is the exact state that hid the
    # broken join for its whole life, and it is only visible if it is printed.
    log.info("fa arc: resolved %d of %d class members from %d/%d sources (%s)",
             len(out), len(keys), n_loaded, len(_ARC_SOURCES),
             ", ".join(per_source) or "none")
    if keys and n_loaded and not out:
        log.error("fa arc: 0 of %d class members resolved an FV arc from %d loaded "
                  "source(s) - Prospect-to-Payday will publish dark",
                  len(keys), n_loaded)
        _record_arc_outage(len(keys), n_loaded)
    elif out:
        # HEARTBEAT. Without an ok=True row the ledger cannot separate "the arc
        # join ran and resolved arcs" from "the FA export never ran" - both are
        # silence, and that ambiguity is what let the TJStats gap read as seven
        # healthy runs. n_rows carries the resolved count, so a collapse from
        # hundreds to a handful is legible without tripping a red.
        _record_arc_health(
            ok=True, n_rows=len(out),
            message=(f"{len(out)} of {len(keys)} FA class members resolved an FV "
                     f"arc from {n_loaded}/{len(_ARC_SOURCES)} boot export(s)"))
    return out


def _record_arc_health(*, ok: bool, n_rows: int = 0, message: str) -> None:
    """File this run's Prospect-to-Payday join verdict into the ingest-health
    ledger.

    WHY IT GOES THROUGH bullpen_export RATHER THAN run_monthly DIRECTLY.
    `from run_monthly import _record_ingest` reads as though it reaches the
    pipeline, and under the way the pipeline is actually launched
    (deploy/nightly-build.sh runs `python run_monthly.py`) it did not: the live
    module is sys.modules["__main__"], the name "run_monthly" is unclaimed, and
    the import built a SECOND module object with its own empty ledger that
    nothing ever drained. MEASURED before the fix: 0 of 1 filed rows reached
    the drained payload. bullpen_export.record_ingest resolves the LIVE module
    (sys.modules first, __main__ second, fresh import only as a last resort),
    and it is one implementation instead of one per exporter.

    THE SECOND HALF of making the red claim true: "fa_prospect_arc" is named in
    run_monthly.SCHEDULED_EXPORTS. A correctly filed row under an unwatched
    name is written into the payload and then dropped from red[], which is
    exactly how this record was inert on both counts.

    Best-effort by design: this is a reporting path and must never be the
    reason the FA export fails."""
    try:
        from bullpen_export import record_ingest
        record_ingest("fa_prospect_arc", ok=ok, n_rows=n_rows, message=message,
                      # A clean run must not pay the whole pipeline import
                      # graph just to log a heartbeat from a standalone run.
                      import_fallback=not ok)
    except Exception:
        log.debug("could not record the FA arc health row", exc_info=True)


def _record_arc_outage(n_keys: int, n_loaded: int) -> None:
    """Raise a fully-empty Prospect-to-Payday join into the ingest-health RED
    ledger. The ledger is what the deploy shell prints as `!!! INGEST RED`, so
    a dark feature is caught on the run that darkened it rather than by someone
    eventually noticing a missing chart. That claim is true only because of the
    two fixes documented on _record_arc_health, both landed 2026-08-05 after
    review found every red filed here was going into a throwaway."""
    _record_arc_health(
        ok=False,
        message=(f"0 of {n_keys} FA class members resolved an FV arc from "
                 f"{n_loaded} loaded boot export(s) ({', '.join(_ARC_SOURCES)}); "
                 f"the Prospect-to-Payday chart on /fa/ has no data."))


# ===========================================================================
# WHY A CLASS MEMBER CARRIES NO PRICE (lane D-1, 2026-08-05)
# ===========================================================================
# THE DEFECT. The 2026-08-04 23:53 re-export (dc3e2af) published 149 of 228
# members with a projection and 79 blank rows, 77 of the 79 pitchers, among
# them Skubal, Imanaga, Gallen, Gausman, Bassitt, Flaherty and Scherzer. The
# immediately preceding export (d50c1af, same day) had projected 223. No code
# in this module changed between the two commits: dc3e2af is a pure re-run.
# The payload said nothing about the collapse beyond n_projected going
# 223 -> 149, so the board rendered 79 em-dashes and still read as a board.
# fa_class_2028.json fell 181 -> 111 and fa_class_2029.json 133 -> 83 in the
# same process, and the 2026-08-05 re-export reproduced all three.
#
# ROOT CAUSE, MEASURED. fa_ident.war_daily_index() builds ONE index out of TWO
# Baseball-Reference frames (war_daily_bat + war_daily_pitch) and wraps each
# fetch in `except Exception: log.warning(...); continue` (fa_ident.py:32-36).
# When the PITCHING fetch fails the function still returns, with a
# batting-only index, and every caller receives a normal-looking dict. Both
# index variants were rebuilt against the live class tables on 2026-08-05:
#
#   index         2027 hit         2027 pit        2028 pit        2029 pit
#   bat+pit   89/90  (98.9%)  135/138 (97.8%)  110/114 (96.5%)  74/79 (93.7%)
#   bat only  89/90  (98.9%)   60/138 (43.5%)   37/114 (32.5%)  19/79 (24.1%)
#
# The bat-only column reproduces the served artifact EXACTLY. The 79 members
# it cannot resolve are the same 79 members served with no price: 79 of 79,
# zero false positives, zero false negatives. Its class totals are
# 149 / 111 / 90 against the served 149 / 111 / 85.
# The 60 pitchers that survived a batting-only index are simply the ones who
# own a PLATE APPEARANCE inside the four-season resolution window, which is
# why the survivors are almost all relievers and why the six surviving
# starters look arbitrary: Trevor Rogers is on the board because he batted in
# 2025, not because anything about him projects better than Skubal.
#
# WHY THE DEFENCE LANDS HERE AND NOT IN fa_ident. The swallow is fa_ident's,
# but the publishing decision is this module's: it is the writer that turned a
# degraded substrate into a served artifact and overwrote a good one. One bad
# index build poisons every consumer in the process anyway (war_daily_index is
# lru_cached at maxsize=1, so fa_fit.py:200's contracted-roster resolution went
# with it), so the check belongs at the seam that publishes.
#
#: Reason codes stamped on every member that reaches the board without a
#: price. Values are the on-page sentence: keep them free of em-dashes
#: (copy_lint) and free of internal jargon, because a reader of /fa/ sees them.
#
# SPLIT 2026-08-07. There used to be ONE code, identity_unresolved, carrying a
# sentence that offered the reader two possibilities and made him pick. The
# three cases behind it are not equally interesting and the code knows which
# one it hit: Woo Jin An has no affiliated record to resolve (KBO), Rowan Wick
# and Tyler Austin have B-Ref careers that ended before the window, and Jake
# Junis was a spelling miss that is now aliased. Only the last of those was a
# defect, and it was invisible while all three shared a label.
NO_PROJ_REASONS = {
    fa_ident.NO_MLB_RECORD:
        "no Baseball-Reference major-league record, so no history to project "
        "from. Expected for a KBO/NPB entrant with no affiliated ball.",
    fa_ident.NO_RECORD_IN_WINDOW:
        "has a Baseball-Reference career, but no major-league season in "
        "{y0}-{y1}, so nothing recent to project from.",
    fa_ident.IDENTITY_AMBIGUOUS:
        "more than one Baseball-Reference player of this name was active in "
        "{y0}-{y1}, so no career is attached.",
    "no_recent_seasons":
        "identified, but no major-league season in the {y0}-{y1} projection "
        "window.",
    "projection_unavailable":
        "the projection engine returned no WAR path for the seasons on file.",
}

#: Codes whose sentence spans the 4-year IDENTITY window rather than the
#: 3-year projection window.
_IDENT_WINDOW_REASONS = frozenset(
    {fa_ident.NO_MLB_RECORD, fa_ident.NO_RECORD_IN_WINDOW,
     fa_ident.IDENTITY_AMBIGUOUS})

# The pitcher-side resolution rate, as a fraction of the hitter-side rate,
# below which the war_daily PITCHING frame is treated as missing.
#
# NOT TUNED, MEASURED. The two states are separated by a factor of two on the
# WORST case of each. Healthy ratios across the three live classes are
# 0.989 (2027), 0.991 (2028) and 0.977 (2029); the degraded ratios from the
# same measurement are 0.440, 0.329 and 0.251. 0.70 sits 1.40x below the worst
# healthy ratio and 1.59x above the worst degraded one. This is a monitoring
# predicate, not a model input: it changes no price, no coefficient and no
# member's projection.
IDENT_COLLAPSE_RATIO = 0.70

# Below this many members on a side the ratio above is noise, so the check
# abstains rather than guesses. The three live classes carry 74-90 hitters and
# 79-138 pitchers, so this never abstains in production; it exists so a small
# custom class in a test or a lab cannot fire a false red.
IDENT_MIN_SIDE_N = 20


def _identity_health(ident: dict[str, dict[str, int]], class_year: int) -> dict:
    """Per-side identity-resolution census plus the degraded verdict.

    Published on every fa_class payload so the answer to "why is half this
    board blank" is IN THE ARTIFACT, not in a run log nobody kept."""
    def _rate(d: dict) -> float | None:
        return (d["ok"] / d["n"]) if d["n"] else None
    hit, pit = ident["hit"], ident["pit"]
    r_hit, r_pit = _rate(hit), _rate(pit)
    degraded = False
    if (hit["n"] >= IDENT_MIN_SIDE_N and pit["n"] >= IDENT_MIN_SIDE_N
            and r_hit and r_pit is not None):
        degraded = (r_pit / r_hit) < IDENT_COLLAPSE_RATIO
    # A frame served from the last-good cache is degraded even when the
    # resolution RATES look healthy, because the rates are computed against
    # whatever loaded. war_source now keeps a per-side copy and records when it
    # falls back to one; a stale pitching frame is the upstream half of exactly
    # the outage the ratio test below was written to catch after the fact.
    stale: dict = {}
    try:
        import war_source
        stale = war_source.served_stale()
    except Exception:                                        # noqa: BLE001
        log.debug("could not read war_source.served_stale()", exc_info=True)
    if stale:
        degraded = True

    out = {
        "class_year": class_year,
        "hit_n": hit["n"], "hit_resolved": hit["ok"],
        "pit_n": pit["n"], "pit_resolved": pit["ok"],
        "degraded": degraded,
    }
    if stale:
        out["stale_frames"] = {
            side: {"age_days": (None if v.get("age_days") is None
                                else round(v["age_days"], 2)),
                   "rows": v.get("rows"), "error": v.get("error")}
            for side, v in stale.items()
        }
    if r_hit is not None:
        out["hit_rate"] = round(r_hit, 4)
    if r_pit is not None:
        out["pit_rate"] = round(r_pit, 4)
    if stale:
        # Name the upstream cause when we know it. This is strictly better
        # evidence than the ratio test, which can only infer the frame failed
        # from the shape of the damage downstream.
        def _one(side: str, v: dict) -> str:
            age = v.get("age_days")
            age_s = "unknown" if age is None else f"{age:.1f}"
            return (f"{side} ({age_s} days old, {v.get('rows')} rows, "
                    f"{v.get('error')})")

        parts = ", ".join(_one(side, v) for side, v in stale.items())
        out["degraded_why"] = (
            f"the war_daily download failed and a cached frame was served: "
            f"{parts}. The identity index was built on a stale substrate, so "
            f"the resolution rates below describe the cached frame rather than "
            f"today's league. Do not publish a board off this run.")
    elif degraded:
        # The verdict carries its own evidence so a reader of the JSON, the
        # page or the ledger does not have to come back here for the numbers.
        out["degraded_why"] = (
            f"war_daily identity resolved {pit['ok']} of {pit['n']} pitchers "
            f"({100 * (r_pit or 0):.1f}%) against {hit['ok']} of {hit['n']} "
            f"hitters ({100 * (r_hit or 0):.1f}%). Both sides are drawn from "
            f"the same league over the same window, so a gap this size means "
            f"the war_daily PITCHING frame did not load: "
            f"fa_ident.war_daily_index swallows a per-frame fetch failure and "
            f"returns the half it did get.")
    return out


def _record_identity_outage(health: dict) -> None:
    """File a degraded identity substrate into the ingest-health ledger.

    KNOWN GAP, stated rather than papered over: "fa_class_identity" is NOT in
    run_monthly.SCHEDULED_EXPORTS, so this row lands in the ingest-health
    payload but is filtered out of red[] and the deploy shell will not print
    it as `!!! INGEST RED`. Adding the name there is a one-line change in a
    file this lane does not own; until it happens the log.error below is the
    loud channel. Same trap as the one documented on _record_arc_health.

    Best-effort by design: reporting must never be why the FA export fails."""
    log.error("fa identity substrate DEGRADED for class %s: %s",
              health.get("class_year"), health.get("degraded_why"))
    try:
        from bullpen_export import record_ingest
        record_ingest("fa_class_identity", ok=False,
                      n_rows=health.get("pit_resolved", 0),
                      message=str(health.get("degraded_why") or "degraded"))
    except Exception:                                    # noqa: BLE001
        log.debug("could not record the FA identity health row", exc_info=True)


def _class_supply_rows(cls: list[dict], class_year: int,
                       by_player: dict[str, dict[int, dict]]) -> list[dict]:
    """ARM supply_pop: the class-supply population under the ALIGNED
    definition -- members whose identity resolves against war_daily AND who
    carry >=1 corpus season inside the 3-season history window; exactly the
    members the market model can price, and the serve-time analog of the
    enriched TRAINING filter (mlb_deal + mlbam_id + corpus history -- see
    fm.enriched_signings). Fringe class members bound for minors deals fail
    the same bar here that their signings fail at train time, so train and
    serve count the same population definition. fa_ident.resolve rides an
    lru-cached index, so the member loop's later resolve is a dict hit."""
    out = []
    for row in cls:
        mlbam = fa_ident.resolve(row["player_name"], range(class_year - 4, class_year))
        if not mlbam:
            continue
        side = "pit" if fm._pos_group(row.get("position")) in ("SP", "RP") else "hit"
        seasons = by_player[side].get(mlbam) or {}
        if any(t in seasons for t in (class_year - 1, class_year - 2, class_year - 3)):
            out.append({"class_year": class_year, "position": row.get("position")})
    return out


# --- MLB projections bridge (future FA classes) -----------------------------
# For class years beyond CLASS_YEAR the platform season hasn't happened yet, so
# the Marcel engine rides stale history (every member flags thinPlatform). The
# /projections/ module already runs the same FA engine forward (5-year war[]
# from first_season), so for FUTURE classes we overlay its per-player WAR path
# (joined by mlbam, then player_key) and let the market model re-price AAV /
# guarantee / surplus off it. Falls back to the Marcel path when unprojected.
_MLB_PROJ_CACHE: dict | None = None

#: How a FUTURE class's path runs past the projection's last season (owner answer
#: Q-A (b), 2026-09-30).
#:   "chained"  fa_market.chain_aging_tail along the projection's champion aging
#:              curve (warChamp + warChampTail, the curve /projections/ chains its
#:              contract tail on), from this page's own 2031 value, so the two
#:              pages extend a path with one function and one curve. The P10/P90
#:              chain at the FA module's anchors (0.6 / 1.4 x the champion), the
#:              P10 without the zero floor (the same rule as the /projections/
#:              tail range; moot here, the overlaid head is floored at 0).
#:   "ratio"    the projection's last two seasons' ratio, clamped to 0.5-0.95
#:              (0.82 when it cannot be read): the rule before 2026-09-30, and
#:              what a row without the published champion tail still takes.
FUTURE_CLASS_TAIL = "chained"


def _load_mlb_projections() -> dict:
    global _MLB_PROJ_CACHE
    if _MLB_PROJ_CACHE is None:
        try:
            d = json.loads((DATA_DIR / "mlb_projections.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        vets = d.get("vets") or []
        _MLB_PROJ_CACHE = {
            "first_season": d.get("first_season"),
            # The rate /projections/ prices veteran seasons at (the committed
            # fa_dpw_series carried forward). Read only for the $/WAR basis
            # disclosure on /fa/ (M04-08); nothing here prices on it.
            "dpw_usd": d.get("dpw_usd"),
            "by_mlbam": {v["mlbam"]: v for v in vets if v.get("mlbam")},
            "by_key": {v["key"]: v for v in vets if v.get("key")},
        }
    return _MLB_PROJ_CACHE


def _apply_proj_override(path: dict, pv: dict, class_year: int,
                         first_season: int | None) -> bool:
    """Overlay the projection module's war[] onto `path` (mutates in place),
    aligned so projection season == class_year maps to path year 1. Contract
    years the 5y projection doesn't reach are chained from its last season
    along the projection's champion aging curve (FUTURE_CLASS_TAIL).
    Returns True when applied."""
    if first_season is None:
        return False
    start = class_year - first_season
    # BASIS (2026-07-24 FA lane) -- this used to read pv["war"], proj_ml's q50
    # QUANTILE head, and splice it into a stack whose pricer
    # (rational_value_usd through the convex tier curve) and whose every
    # market feature (war_y1, log_rational, prime_war) are calibrated on
    # champion MEAN paths. Measured on the served payloads: mlb_projections
    # year-1 league sum is 602.8 WAR on `war` vs 984.4 on `warChamp`; across
    # the 212 players the 2027 class shares with it, in the SAME season,
    # fa_class's own champion warY1 sums to 191.4 and warChamp[0] to 191.4
    # (ratio 1.000) while war[0] sums to 90.7 (ratio 0.474). The q50 head is
    # also unfloored, which is why 72 of the served 2028 members carried a
    # negative season in warPath and 176 in warPathP10 while
    # tiered_war_value_usd() truncates negatives at 0 -- warTotal and
    # rational then described different paths on the same row.
    war = pv.get("warChamp") or pv.get("war") or []
    if start < 0 or start >= len(war):
        return False
    new = war[start:]

    def _decay_ratio(seq: list) -> float:
        # Continue the projection's own recent year-over-year decline; clamp to
        # a sane aging band, default ~0.82 when it can't be inferred.
        if len(seq) >= 2 and seq[-2] > 0:
            return max(0.5, min(0.95, seq[-1] / seq[-2]))
        return 0.82

    champ = _future_tail_champion(pv, path, start)

    def _overlay(key: str, src: list | None, mult: float = 1.0, floor: bool = True) -> None:
        # Overlay the projected years, then EXTEND past the projection horizon
        # (not the stale Marcel tail, which collapses to ~0 for young stars on
        # long future-class deals): along the projection's champion aging curve
        # chained from the last projected value (FUTURE_CLASS_TAIL "chained"),
        # else by decaying it at the clamped ratio.
        cur = path.get(key)
        seq = (src or [])[start:]
        if not seq or not isinstance(cur, list):
            return
        seq = [max(0.0, float(v)) for v in seq]   # fm._decay_path floors at 0
        cur[:len(seq)] = seq
        if champ is not None and len(champ) >= len(cur) > len(seq):
            # branch_champ: the band decides the chain's branch on the
            # unmultiplied champion, as the point does (mult 1.0: unchanged).
            full = fm.chain_aging_tail(seq, [mult * c for c in champ], len(seq),
                                       len(cur), floor=floor, branch_champ=champ)
            cur[len(seq):] = full[len(seq):len(cur)]
            return
        ratio = _decay_ratio(seq)
        last = seq[-1]
        for i in range(len(seq), len(cur)):
            last = round(max(0.0, last * ratio), 2)
            cur[i] = last

    _overlay("war_by_year", war)        # champion MEAN path
    path["war_y1"] = new[0]
    # Bands: proj_ml's quantile heads are cut around its OWN q50, so their
    # absolute spread is transferred onto the champion mean rather than
    # spliced raw (a raw splice puts p90 below the mean wherever champ >
    # q90). Floored at 0 like fm._decay_path, then clamped so the invariant
    # p10 <= mean <= p90 holds on every served season.
    q50 = pv.get("war") or []
    for key, src, mult, floor in (("war_by_year_p10", pv.get("warP10"), 0.6, False),
                                  ("war_by_year_p90", pv.get("warP90"), 1.4, True)):
        if src and q50 and len(src) == len(q50) == len(war):
            _overlay(key, [w + (q - m) for w, q, m in zip(war, src, q50)], mult, floor)
        else:
            _overlay(key, src, mult, floor)
    lo, hi = path.get("war_by_year_p10"), path.get("war_by_year_p90")
    for t, w in enumerate(path["war_by_year"]):
        if isinstance(lo, list) and t < len(lo):
            lo[t] = round(min(lo[t], w), 2)
        if isinstance(hi, list) and t < len(hi):
            hi[t] = round(max(hi[t], w), 2)
    path["war_total"] = round(sum(path["war_by_year"]), 2)
    return True


def _future_tail_champion(pv: dict, path: dict, start: int) -> list[float] | None:
    """The champion aging curve a future class's path chains along past the
    projection's last season, aligned so index 0 is the class year, or None
    (FUTURE_CLASS_TAIL "ratio", or a projection row without the published
    champion tail).

    It is the projection's own champion MEAN path (warChamp, then warChampTail
    past the five printed seasons): the curve proj_export's contract tail
    chains on. Seasons past its end (a path runs fa_market.MAX_PATH_YEARS from
    the class year, the projection's from its first season) continue on this
    path's Marcel champion's year-over-year ratio, capped at 1.0 (0.7 where the
    prior champion season is 0.05 WAR or less), chain_aging_tail's own ratio
    rule."""
    if FUTURE_CLASS_TAIL != "chained":
        return None
    head, tail = pv.get("warChamp"), pv.get("warChampTail")
    if not head or not tail or start < 0 or start >= len(head):
        return None
    cs = [float(c or 0.0) for c in (list(head) + list(tail))[start:]]
    fc = path.get("war_by_year_champ") or path.get("war_by_year") or []
    n = len(path.get("war_by_year") or [])
    while len(cs) < n:
        t = len(cs)
        r = (fc[t] / fc[t - 1]) if (t < len(fc) and fc[t - 1] > 0.05) else 0.7
        cs.append(max(0.0, cs[-1] * min(1.0, r)))
    return cs


_CONTRACT_ORGS: dict[str, str] | None = None


def _contract_orgs() -> dict[str, str]:
    """player_key -> club, taken from the projection artifact's `team`.

    The FA availability page is a per-class scrape and its club column is not
    trustworthy, so 'from' reads the club proj_export resolves instead, which
    runs before this module in both the monthly and daily chains. That club is
    the one holding the player TODAY (proj_export.resolve_current_club: the
    transaction feed, then this season's club, then the Spotrac contract club).
    It used to be the contract club first, which is stale for every deadline
    trade: 48 of 236 'from' cells named the club a player had left (Tarik Skubal
    DET after his move to LAD). A.J. Minter, once cited here as a scrape error
    for reading MIN, was in fact traded to Minnesota; his season line says so.

    Best effort by design: a missing or unreadable artifact leaves the scraped
    value in place rather than blanking the column.
    """
    global _CONTRACT_ORGS
    if _CONTRACT_ORGS is None:
        # Reuses the module's existing projection cache rather than reading the
        # same artifact a second time.
        by_key = (_load_mlb_projections() or {}).get("by_key") or {}
        _CONTRACT_ORGS = {k: v["team"] for k, v in by_key.items() if v.get("team")}
    return _CONTRACT_ORGS


def build_fa_class_payload(class_year: int = CLASS_YEAR) -> dict:
    """The /fa/ class payload. In unified $/WAR path mode (VAL_5, rows 11 and 24)
    it carries the written path by season and its band, the level of the class
    season P(c) and the pricing basis; the escalator stamp goes (rational value
    no longer reads it). OFF it is the legacy payload byte for byte."""
    payload = _build_fa_class_payload_body(class_year)
    import value_framework as _vfm
    if _vfm.dpw_path_active():
        summ = _vfm.dpw_path_summary()
        seasons = range(int(class_year), int(class_year) + fm.MAX_PATH_YEARS)
        payload["dpw_usd"] = int(round(_vfm.price_level(int(class_year))))
        payload.pop("dpw_infl", None)
        payload["dpw_path_by_season"] = {str(s): int(round(_vfm.price_level(s))) for s in seasons}
        band = summ.get("band") or {}
        payload["dpw_path_band"] = {k: {s: v for s, v in (band.get(k) or {}).items()
                                        if int(s) in seasons} for k in ("p10", "p90")}
        payload["pricing_basis"] = {k: summ[k] for k in ("basis_id", "method", "base_season",
                                                         "nominal_rate", "g_ref", "level_basis")}
    return payload


def _build_fa_class_payload_body(class_year: int = CLASS_YEAR) -> dict:
    corpus = fp.build_corpus()
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, class_year - 1)
    frac = fp.season_fraction(league, class_year - 1)
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r

    enriched = fm.enriched_signings(2015, class_year - 1)
    # VAL_1 (owner decision FP2-1, 2026-09-25): the board prices on THE one
    # written series (data/fa_dpw_series.json, fa_market.write_dpw_series), the
    # same file /projections/ and prospect surplus read, instead of a series
    # re-derived here and written nowhere. The in-run derivation is kept only as
    # a check: the two agree unless the corpus moved after the writer ran, and
    # the gap is published so a disagreement is visible, not silent.
    in_run = fm.dollars_per_war_by_winter(enriched)
    dpw_series = fm.written_dpw_series(through=class_year - 1)
    if dpw_series:
        series_src = "data/fa_dpw_series.json"
        yrs = set(dpw_series) | set(in_run)
        series_gap = max((abs(dpw_series.get(y, 0.0) - in_run.get(y, 0.0)) for y in yrs),
                         default=0.0)
        if series_gap > 1.0:
            log.warning("fa_dpw_series.json differs from this run's corpus by up to $%.0f "
                        "per WAR (class %d); pricing on the written series", series_gap,
                        class_year)
    else:
        log.error("fa_dpw_series.json absent or empty: class %d prices on the in-run series",
                  class_year)
        dpw_series, series_src, series_gap = in_run, "in_run_fallback", 0.0
    model = fm.MarketModel(enriched, dpw_series)
    cls = list(storage.load_fa_class_players(class_year).values())
    # Winter-tracker state: in-class signings (terms from the class page) +
    # the first-seen event ledger. Both empty preseason.
    signings = {k: v for (k, yr), v in storage.load_fa_signings(class_year).items()
                if yr == class_year}
    # SERVED ledger, not the raw table: served_fa_events filters quarantined
    # rows (the 16 suspect pre-offseason qo_offered stamps of 2026-08-12).
    # Reading storage.load_fa_events here was the one remaining carrier of
    # quarantined rows into fa_class.json (found by the 2026-08-19 penter
    # hardening; fa_pipeline.py:356 states the serving contract).
    from fa_pipeline import served_fa_events
    events = served_fa_events(class_year)
    ev_date = {(e["player_key"], e["event_type"]): e["event_date"] for e in events}
    fv_hist = _prospect_fv_history({p.get("player_key") for p in cls})
    if fm.X_FEATURES.get("supply_pop"):
        # ARM supply_pop (default OFF; pre-registered in
        # tools/fa_market_feature_lab.py): serve-time supply counts the
        # ALIGNED population (identity+history members, the analog of the
        # enriched training filter) instead of the whole scraped class,
        # whose counts z-scored +2.6..+2.8 against the training moments.
        model.supply_by_year[class_year] = fm._supply(
            _class_supply_rows(cls, class_year, by_player), class_year)
    else:
        model.supply_by_year[class_year] = fm._supply(
            [{"class_year": class_year, "position": p.get("position")} for p in cls], class_year)
    dpw = (fm.written_pricing_level_usd(class_year) if series_src != "in_run_fallback"
           else None) or fm.winter_dpw(dpw_series, class_year)
    # The rate this winter carries dollars forward at. Estimated from the
    # module's OWN realized $/WAR series over the training winters (see
    # fm._destale_rate) instead of borrowing value_framework's
    # dollars_per_war_inflation, which is 0.0 in production for a
    # prospect-side reason and silently made three separate FA mechanisms
    # no-ops (comps de-staling, rational-value escalation, the $/WAR carry).
    destale = fm._destale_rate(dpw_series, class_year)

    overrides = _load_overrides()
    proj = _load_mlb_projections()   # future-class WAR override source
    members = []
    full_fits: list[tuple[dict, list[dict]]] = []   # (member, all-org fits)
    n_proj = 0
    n_arc = 0
    # Lane D-1 instrumentation. Every member leaves this loop with a DEFINITE
    # outcome: priced, or unpriced with a named reason. The three gates below
    # used to be bare `if`s whose else-branch was silence, which is how 79 of
    # 228 members went blank for two days without anything saying so.
    drops: Counter = Counter()
    ident = {"hit": {"n": 0, "ok": 0}, "pit": {"n": 0, "ok": 0}}
    for row in cls:
        ovr = overrides.get(row.get("player_key")) or {}
        if ovr.get("exclude"):
            continue
        m = _clean({
            "key": row.get("player_key"), "name": row["player_name"],
            "pos": row.get("position"), "age": row.get("age"),
            "from": _contract_orgs().get(row.get("player_key")) or row.get("from_team"), "bt": row.get("bat_throw"),
            "status": row.get("status"), "type": row.get("fa_type"),
            "optPrice": row.get("option_price_usd"),
            "enterProb": row.get("enter_prob"),
            "prevAav": row.get("prev_aav_usd"), "prevWar": row.get("prev_war"),
            "qoValue": row.get("qo_value_usd"),
        })
        if ovr.get("two_way"):
            m["twoWay"] = True
        if ovr.get("note") or ovr.get("two_way"):
            m["note"] = ovr.get("note") or TWO_WAY_NOTE
        # The side is decided BEFORE resolution so the per-side census below
        # counts DENOMINATORS, not just successes. A census that only counts
        # what worked cannot see a half-loaded index.
        pos_grp = fm._pos_group(row.get("position"))
        side = "pit" if pos_grp in ("SP", "RP") else "hit"
        ident[side]["n"] += 1
        mlbam, why = fa_ident.resolve_with_reason(
            row["player_name"], range(class_year - 4, class_year))
        drop = None if mlbam else why
        if mlbam:
            # QMLP10: the board draws each row's headshot from this id at
            # paint time, so /fa/ no longer fetches the 1.9 MB player_links
            # map at boot just to look the id up again.
            m["mlbam"] = int(mlbam)
            ident[side]["ok"] += 1
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                    if t in seasons]
            # Thin-platform disclosure: a projection riding a missing or
            # injury-shortened platform year is the model's weakest case
            # (Burnes-type) - badge it, don't hide it. The exposure floor
            # scales by season_fraction, so a normal in-progress June season
            # never flags; 30% of a regular's pace does.
            platform = seasons.get(class_year - 1)
            if platform is None:
                m["thinPlatform"] = (f"no {class_year - 1} season in the corpus - "
                                     "projection rides older years")
            else:
                # Full-season volume is ROLE-aware: a reliever at 20 IP in
                # June is on pace, not hurt (65 IP RP season vs 180 SP).
                vol_key, full = (("pa", 600) if side == "hit"
                                 else ("ip", 65 if pos_grp == "RP" else 180))
                vol = platform.get(vol_key) or 0
                if vol < 0.3 * full * max(frac, 0.1):
                    m["thinPlatform"] = (f"only {vol:.0f} {vol_key.upper()} in "
                                         f"{class_year - 1} - injury-thin platform")
            if hist:
                if fm.X_FEATURES.get("age_anchor"):
                    # ARM age_anchor (default OFF; pre-registered in
                    # tools/fa_market_feature_lab.py): anchor the offset to
                    # the SEASON of the row that supplied the age -- the
                    # proj_export / fm.enriched_signings (ba3917d)
                    # convention. The stale hist[0] anchor understated age
                    # by the season gap whenever the platform row lacked an
                    # age; training ages are already anchored, so the stale
                    # form is a train/serve skew.
                    age_row = next((h for h in hist if h.get("age")), None)
                    age = ((age_row["age"] + (class_year - age_row["season"]))
                           if age_row else int(row.get("age") or 30))
                else:
                    age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                    age = ((age_prev + (class_year - hist[0]["season"])) if age_prev
                           else int(row.get("age") or 30))
                # CHAMPION paths throughout the FA pricing stack: the market
                # model's Gate-2 verdict holds under champion inputs only
                # (the ML-path version FAILED its gate - see
                # fa_market.enriched_signings). Display, rational value,
                # verdict terciles and market features stay one consistent
                # engine; /projections/ serves the gate-winning ML paths.
                path = fm.contract_war_path(hist, side, class_year, 10, age,
                                            curves, war_map, league,
                                            in_progress=(class_year - 1, frac),
                                            use_ml=False)
                if path and class_year > CLASS_YEAR:
                    # Future class: overlay the projection module's WAR path
                    # (the platform season hasn't happened; Marcel is stale).
                    pv = (proj["by_mlbam"].get(mlbam)
                          or proj["by_key"].get(row.get("player_key")))
                    if pv and _apply_proj_override(path, pv, class_year,
                                                   proj["first_season"]):
                        m["warSource"] = "mlb_projections"
                        m.pop("thinPlatform", None)
                if path:
                    s = {**row, "_war_path": path, "_age": age, "class_year": class_year}
                    pred = model.predict(s)
                    # WS-2d - option-pending members get P(enter) re-priced
                    # from the market model's own band distribution (the v1
                    # $-gap logistic stays for mutual/conditional types and
                    # as the fallback where bands are missing).
                    v2 = fm.enter_probability_v2(pred, row.get("fa_type"),
                                                 row.get("option_price_usd"))
                    if v2 is not None:
                        m["enterProb"] = v2["enter_prob"]
                        m["enterProbSrc"] = v2["method"]
                    # T1.5 - the option, priced as a contingent claim on the
                    # band rather than served as a bare flag. The SIGN is the
                    # point: a player option is a liability the team is SHORT.
                    optv = fm.option_value_usd(pred, row.get("fa_type"),
                                               row.get("option_price_usd"))
                    if optv:
                        m["optValue"] = optv["option_value_usd"]
                        m["optTeamValue"] = optv["team_value_usd"]
                        m["optKind"] = optv["kind"]
                        m["optHeldBy"] = optv["held_by"]
                        m["optBasis"] = optv["basis"]
                    yrs = pred["proj_years"]
                    guar = pred["proj_guarantee_usd"]
                    # T1.4 - the EXPECTATION of the convex tier price over the
                    # shipped band, not the tier price of the mean path.
                    rational = fm.expected_rational_value_usd(
                        path, yrs, class_year, dpw, infl=destale)
                    deal_plus = round(100 * rational / max(guar, 1))
                    import value_framework as _vfm
                    if _vfm.dpw_path_active() and _vfm.dpw_stage("U2") \
                            and _vfm.dpw_option("level_basis") == "round_trip":
                        # VAL_5 row 13: under the round-trip level the price is
                        # the predicted guarantee's cash in PV at R (level over
                        # the predicted years); the verdict edges are re-cut in
                        # the flip commit under M14-2's procedure.
                        _R = _vfm.nominal_rate()
                        _ny = max(1, int(round(float(yrs))))
                        _pv = sum((guar / _ny) / ((1.0 + _R) ** t) for t in range(_ny))
                        deal_plus = round(100 * rational / max(_pv, 1))
                    # Probability buckets: floor/ceiling WAR paths (Gate-1
                    # empirical quantiles decayed along the aging curves),
                    # priced as paths. This is the surplus range for a
                    # one-season term; longer terms read the copula draws
                    # below (M04-01) and keep this as the Comon pair.
                    p10_path = path.get("war_by_year_p10")
                    p90_path = path.get("war_by_year_p90")
                    rational_p10 = (fm.rational_value_usd(p10_path[:yrs], class_year,
                                                          dpw, infl=destale)
                                    if p10_path else None)
                    rational_p90 = (fm.rational_value_usd(p90_path[:yrs], class_year,
                                                          dpw, infl=destale)
                                    if p90_path else None)
                    comps = fm.comps_for(s, enriched, k=3)
                    # Full 30-org fit vector: top-3 rides the member row (the
                    # board's Fits column), the rest feeds the per-team view
                    # via the compact teamFits block below.
                    all_fits = fa_fit.fit_scores(s, pred, class_year, top_n=30)
                    fits = all_fits[:3]
                    full_fits.append((m, all_fits))
                    # T1.3 - the TOTAL comes from a correlated-path Monte
                    # Carlo, not from adding the per-year quantiles. Adding
                    # quantiles is only valid under comonotonicity (a player
                    # who lands at his P10 in year 1 landing at his P10 every
                    # remaining year); the measured horizon residual Spearman
                    # is 0.4455 / 0.3594 / 0.3090 / 0.2571 at lags 1-4.
                    mc = None
                    sims = None
                    if p10_path and p90_path and yrs >= 1:
                        try:
                            import fa_mc
                            sims = fa_mc.simulate(
                                path["war_by_year"], p10_path, p90_path, yrs,
                                draws=fa_mc.N_DRAWS)
                            mc = fa_mc.path_quantiles(sims)
                        except Exception:                    # noqa: BLE001
                            log.warning("fa mc failed for %s - falling back "
                                        "to the quantile sum", row.get("player_key"))
                            mc = None
                            sims = None
                    # M04-01 (2026-09-25). The surplus RANGE reads the P10 and
                    # P90 of contract VALUE across the same copula draws that
                    # give warTotalP10/P90 and the downside WAR, not the value
                    # of the per-season P10 and P90 paths. Pricing those paths
                    # assumed a player at his P10 in every season at once:
                    # Skubal's 7-year P10 read -$268.8M (zero WAR for seven
                    # years) beside a downside WAR of 5.0. On a one-season term
                    # the two readings agree (a monotone price of one season),
                    # so the path value stays there and no draw noise enters.
                    # The path-priced band is still served as the Comon pair,
                    # as the WAR totals are (T1.3 precedent).
                    comon_p10, comon_p90 = rational_p10, rational_p90
                    if sims is not None and yrs >= 2:
                        import numpy as np
                        vals = fm.rational_value_draws_usd(sims, class_year,
                                                           dpw, infl=destale)
                        rational_p10 = int(np.quantile(vals, 0.10))
                        rational_p90 = int(np.quantile(vals, 0.90))
                    m.update(_clean({
                        "warY1": path["war_y1"],
                        "warPath": path["war_by_year"][:max(yrs, 5)],
                        "warPathP10": p10_path[:max(yrs, 5)] if p10_path else None,
                        "warPathP90": p90_path[:max(yrs, 5)] if p90_path else None,
                        "warTotal": round(sum(path["war_by_year"][:yrs]), 1),
                        "warTotalP10": (round(mc["p10"], 1) if mc else
                                        (round(sum(p10_path[:yrs]), 1) if p10_path else None)),
                        "warTotalP90": (round(mc["p90"], 1) if mc else
                                        (round(sum(p90_path[:yrs]), 1) if p90_path else None)),
                        # The superseded COMONOTONE total, served alongside so
                        # the Accountability surface can show both. It is not
                        # decoration: measured on 3,913 held 5-year paths the
                        # quantile sum COVERS BETTER (0.647 vs 0.386 against a
                        # nominal 0.80) despite being the invalid aggregation,
                        # because it was compensating for per-year marginals
                        # that are themselves far too narrow conditional on the
                        # player appearing (survived coverage 0.367). Both
                        # numbers are published rather than one being quietly
                        # chosen. See fa_mc for the full ledger.
                        "warTotalP10Comon": (round(sum(p10_path[:yrs]), 1)
                                             if p10_path else None),
                        "warTotalP90Comon": (round(sum(p90_path[:yrs]), 1)
                                             if p90_path else None),
                        # Functionals a quantile sum cannot express at all.
                        "warCvar10": round(mc["cvar10"], 1) if mc else None,
                        "pAnyStar": round(mc["p_any_star"], 3) if mc else None,
                        "totalSrc": "mc_copula" if mc else "quantile_sum",
                        "projYears": yrs,
                        "projYearsP10": pred.get("proj_years_p10"),
                        "projYearsP90": pred.get("proj_years_p90"),
                        "projGuar": guar,
                        "projGuarP10": pred.get("proj_guarantee_p10_usd"),
                        "projGuarP90": pred.get("proj_guarantee_p90_usd"),
                        "projAav": pred["proj_aav_usd"],
                        "projAavP10": pred.get("proj_aav_p10_usd"),
                        "projAavP90": pred.get("proj_aav_p90_usd"),
                        "rational": rational,
                        "surplus": rational - guar,
                        "surplusP10": (rational_p10 - guar) if rational_p10 is not None else None,
                        "surplusP90": (rational_p90 - guar) if rational_p90 is not None else None,
                        # The superseded path-priced band (each season at its
                        # own P10 / P90, priced and added), kept for the
                        # Accountability comparison like warTotalP10Comon.
                        "surplusP10Comon": (comon_p10 - guar) if comon_p10 is not None else None,
                        "surplusP90Comon": (comon_p90 - guar) if comon_p90 is not None else None,
                        "surplusBandSrc": ("mc_copula" if (sims is not None and yrs >= 2)
                                           else "season_path" if rational_p10 is not None
                                           else None),
                        "dealPlus": deal_plus,
                        # POSITION IS REQUIRED, not optional (2026-07-30). Under
                        # fa_market.VERDICT_BAND_MODE == "group" the edges are keyed by
                        # _pos_group, and _pos_group(None) returns "POS" - so omitting
                        # the position here silently banded EVERY pitcher on the board
                        # against HITTER edges (103/237 instead of SP 86/182, RP 65/146).
                        # That is worse than pooled banding, not better. The mode is a
                        # one-constant flip in fa_market but it is only correct with
                        # this argument present.
                        "verdict": fm.deal_verdict(deal_plus, row.get("position")),
                        "comps": [_clean({"name": c["player_name"], "yr": c["class_year"],
                                          "to": c.get("to_team"), "years": c.get("years"),
                                          "guar": c.get("guarantee_usd")}) for c in comps],
                        "fits": [_compact_fit(f) for f in fits],
                    }))
                    n_proj += 1
                else:
                    drop = "projection_unavailable"
            else:
                drop = "no_recent_seasons"
        if drop:
            # THE DISCLOSURE. A blank price row now carries WHY it is blank,
            # per row and in aggregate. Absence and silence are different
            # failures: three of these reasons are legitimate (a KBO signing,
            # a man who has not pitched since 2022, a season lost to surgery)
            # and one of them was an outage that blanked 79 rows. A reader
            # could not tell those apart from an em-dash.
            drops[drop] += 1
            # The CODE rides the row, the sentence rides the payload once
            # (unprojected_reason_text below). 79 copies of a 230-character
            # sentence is 18KB on the wire for one repeated string, and this
            # module's contract is the owner's lean wire format.
            m["noProj"] = drop
        # Winter overrides: the reconciled pipeline status beats the stale
        # as-scraped payload status, and signed members carry their ACTUAL
        # terms next to the prediction (the tracker's whole point).
        key = row.get("player_key")
        sgn = signings.get(key)
        if sgn:
            m["status"] = "signed"
            npv_signed, had_sched = fm.npv_guarantee_usd(
                key, class_year, sgn.get("guarantee_usd") or 0)
            m.update(_clean({
                "signedTo": sgn.get("to_team"),
                "signedYears": sgn.get("years"),
                "signedGuar": sgn.get("guarantee_usd"),
                # Deferral-adjusted actual - predictions are NPV-basis, so
                # the tracker's actual-vs-predicted delta must compare like
                # with like (only present when a schedule is on file).
                "signedGuarNpv": npv_signed if had_sched else None,
                "signedAav": sgn.get("aav_usd"),
                "signedDate": ev_date.get((key, "signing")),
                "signedMilb": True if sgn.get("mlb_deal") is False else None,
                "qoAccepted": True if sgn.get("qo_accepted") else None,
            }))
        elif (key, "option_exercised") in ev_date:
            m["status"] = "option_exercised"
        # Prospect-to-Payday arc - id-gated so a name-key collision can
        # never paste a prospect's FV history onto a same-named veteran.
        arc = fv_hist.get(key)
        if arc and mlbam and arc["mlbam"] == mlbam:
            m["fvArc"] = arc["pts"]
            n_arc += 1
        # TWO SOURCES, ONE PLAYER, AND THE DISAGREEMENT MADE VISIBLE
        # (2026-09-17). Class membership is SCRAPED from Spotrac's
        # free-agents-available list and never consults the arbitration board,
        # so a member can be published here as a 2027 free agent while
        # mlb_projections prices him club-controlled into 2028 or 2029. This
        # does NOT move membership - that is a data-sourcing question with its
        # own gate - it stamps the contradiction so the site stops publishing
        # two confident and incompatible answers with no acknowledgement.
        #
        # The gate is `ctrlThru > class_year AND ctrlEst`, not `ctrlThru >
        # class_year` alone: 11 further members run past the class year on an
        # OPTION season whose dollars Spotrac already lists as guaranteed, and
        # the status column names that option on the row. Those are explained.
        # A season priced on a PROJECTED arbitration award past the guarantee
        # is not, and there are 3 of them.
        pv = (proj.get("by_key") or {}).get(key) or {}
        _ct, _thru, _st = pv.get("ctrlThru"), pv.get("thru"), pv.get("salThru")
        if _ct is None and (_thru is not None or _st is not None):
            _ct = max(_thru or 0, _st or 0) or None
        _est = bool(pv.get("ctrlEst")) or (
            _st is not None and (not _thru or _st > _thru))
        if _ct is not None and _ct > class_year and _est:
            m["ctrlFlag"] = True
            m["ctrlThru"] = _ct
        members.append(m)
    # Log what actually SHIPPED, not just what resolved. The id gate above can
    # drop a resolved arc (name-key collision, or the class row never resolved
    # an mlbam at all), so "resolved N" from _prospect_fv_history and "published
    # N" are different numbers and a gap between them is worth seeing.
    log.info("fa arc: %d of %d members published an fvArc (%d resolved upstream)",
             n_arc, len(members), len(fv_hist))
    # Lane D-1: the counts go in the RUN LOG as well as the payload, because
    # the artifact is only read after someone already suspects a problem and
    # the log is read on the run that caused it.
    health = _identity_health(ident, class_year)
    log.info("fa class %d: %d of %d members priced; unpriced by reason %s; "
             "identity resolved hit %d/%d, pit %d/%d",
             class_year, n_proj, len(members), dict(sorted(drops.items())),
             ident["hit"]["ok"], ident["hit"]["n"],
             ident["pit"]["ok"], ident["pit"]["n"])
    if health["degraded"]:
        _record_identity_outage(health)
    members.sort(key=lambda m: -(m.get("projGuar") or 0))
    # Per-team fit lists covering ALL 30 orgs (the member rows only carry
    # top-3, which left half the league without a Fits view). Members are
    # referenced by post-sort index ("i") so nothing is duplicated; top-12
    # per org keeps the block ~40KB.
    idx_of = {id(m): i for i, m in enumerate(members)}
    team_fits: dict[str, list[dict]] = defaultdict(list)
    for m, fits in full_fits:
        for f in fits:
            team_fits[f["org"]].append(_clean({"i": idx_of[id(m)],
                                               **_compact_fit(f, with_org=False)}))
    team_fits = {org: sorted(rows, key=lambda r: -r["fit"])[:12]
                 for org, rows in sorted(team_fits.items())}
    thr = fa_cba.cbt_threshold(class_year)
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "dpw_usd": int(dpw),
        # M04-08 (2026-09-25). The series dpw_usd was carried forward FROM.
        # Since VAL_1 (same day) it is the one written data/fa_dpw_series.json
        # every surface reads (dpw_series_source), so it equals the committed
        # series on every winter up to the class; the in-run derivation is a
        # check whose largest per-winter gap ships as dpw_series_check_gap_usd.
        "dpw_series_pricing": {str(y): int(v) for y, v in sorted(dpw_series.items())},
        "dpw_series_source": series_src,
        "dpw_series_check_gap_usd": int(round(series_gap)),
        # The rate the module ACTUALLY carries dollars forward at. This used
        # to publish value_framework's dollars_per_war_inflation, which is 0.0
        # in production, while assets/fa.js printed "escalating 5%/yr" from its
        # own default -- the served page and the served number disagreed.
        "dpw_infl": round(destale, 4),
        "cba_carry_forward": bool(thr.get("carry_forward")),
        "n_members": len(members), "n_projected": n_proj,
        # Lane D-1. n_projected alone let a board go from 223 priced to 149
        # priced and still read as normal. The complement and its BREAKDOWN
        # ship next to it, so "79 blank rows" is a sentence the artifact says
        # out loud instead of something a reader has to infer by subtracting.
        "n_unprojected": len(members) - n_proj,
        "unprojected_by_reason": dict(sorted(drops.items())),
        # code -> the sentence a reader of /fa/ should see next to a blank
        # price. Only the codes this class actually produced are shipped, so
        # the join from a member's noProj is always satisfiable.
        "unprojected_reason_text": {
            k: v.format(y0=class_year - (4 if k in _IDENT_WINDOW_REASONS else 3),
                        y1=class_year - 1)
            for k, v in NO_PROJ_REASONS.items() if k in drops},
        # The per-side identity census, and the verdict on whether the
        # war_daily substrate this whole gate depends on actually loaded.
        "identity_health": health,
        # Published on the artifact so a dark Prospect-to-Payday is readable
        # from the served file, not only from a run log nobody kept.
        "n_fv_arc": n_arc,
        "n_signed": sum(1 for m in members if m.get("status") == "signed"),
        "members": members,
        "teamFits": team_fits,
        # First-seen winter events (newest first, capped) - the WIRE and the
        # Signing Tracker timeline. Dates are observation stamps, not
        # Spotrac dates (the source publishes none).
        "events": [_clean({
            "date": e["event_date"], "type": e["event_type"],
            "key": e["player_key"], "name": e.get("player_name"),
            "pos": e.get("position"), "from": e.get("from_team"),
            "to": e.get("to_team"), "years": e.get("years"),
            "guar": e.get("guarantee_usd"), "aav": e.get("aav_usd"),
            "qo": True if e.get("qo") else None,
            "milb": True if e.get("mlb_deal") is False else None,
            "optPrice": e.get("option_price_usd"),
        }) for e in events[:80]],
    }


def serve_alignment_diagnostics(class_year: int = CLASS_YEAR) -> dict:
    """Read-only evidence block for the wave-2 serve-side arms (pre-registered
    in tools/fa_market_feature_lab.py; recorded into its eval artifact by the
    lab). Writes NOTHING, never constructs a MarketModel, never calls
    predict -- safe to run alongside challenger/no-persist gate runs.

      supply -- per-pos-group class counts under the live whole-class
        convention (raw) vs the ALIGNED identity+history population
        (_class_supply_rows), each z-scored against the CHAMPION training
        supply moments (enriched signings 2015..class_year-1, the same
        counts MarketModel.__init__ fits its z-moments on).
      age -- the serve age every member would get under the stale hist[0]
        anchor vs the anchored convention. Deltas (anchored - stale) are
        structurally in [+1, +2] when nonzero: the anchored form adds the
        gap between hist[0]'s season and the age-supplying row's season,
        bounded by the 3-season history window."""
    corpus = fp.build_corpus()
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    cls = list(storage.load_fa_class_players(class_year).values())
    enriched = fm.enriched_signings(2015, class_year - 1)
    sup_by = {y: fm._supply(enriched, y) for y in {s["class_year"] for s in enriched}}
    sup_all = [c for by in sup_by.values() for c in by.values()]
    mean = statistics.mean(sup_all) if sup_all else 0.0
    sd = statistics.pstdev(sup_all) if len(sup_all) > 1 else 1.0

    raw = fm._supply([{"class_year": class_year, "position": p.get("position")}
                      for p in cls], class_year)
    aligned = fm._supply(_class_supply_rows(cls, class_year, by_player), class_year)

    def _z(counts: dict) -> dict:
        return {g: round((counts.get(g, 0.0) - mean) / (sd or 1.0), 3)
                for g in fm.POS_GROUPS}

    z_raw, z_aligned = _z(raw), _z(aligned)
    age = {"n_members_with_hist": 0, "n_changed": 0,
           "min_delta": None, "max_delta": None, "changed": []}
    for row in cls:
        mlbam = fa_ident.resolve(row["player_name"], range(class_year - 4, class_year))
        if not mlbam:
            continue
        side = "pit" if fm._pos_group(row.get("position")) in ("SP", "RP") else "hit"
        seasons = by_player[side].get(mlbam) or {}
        hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                if t in seasons]
        if not hist:
            continue
        age["n_members_with_hist"] += 1
        age_row = next((h for h in hist if h.get("age")), None)
        if age_row is None:
            continue                    # both conventions fall back identically
        stale = age_row["age"] + (class_year - hist[0]["season"])
        anchored = age_row["age"] + (class_year - age_row["season"])
        if anchored != stale:
            d = anchored - stale
            age["n_changed"] += 1
            age["min_delta"] = d if age["min_delta"] is None else min(age["min_delta"], d)
            age["max_delta"] = d if age["max_delta"] is None else max(age["max_delta"], d)
            if len(age["changed"]) < 40:
                age["changed"].append({"key": row.get("player_key"),
                                       "stale": stale, "anchored": anchored})
    return {
        "class_year": class_year,
        "supply": {
            "raw": {g: raw.get(g, 0.0) for g in fm.POS_GROUPS},
            "aligned": {g: aligned.get(g, 0.0) for g in fm.POS_GROUPS},
            "z_raw": z_raw, "z_aligned": z_aligned,
            "train_mean": round(mean, 2), "train_sd": round(sd, 2),
            "mean_abs_z_raw": round(statistics.mean(abs(v) for v in z_raw.values()), 4),
            "mean_abs_z_aligned": round(statistics.mean(abs(v) for v in z_aligned.values()), 4),
        },
        "age": age,
    }


# M04-04. A realized-ledger row with no war_basis was built before
# 2026-09-25, and every such row was built from the war_daily frames in June
# 2026, before the 2026-09-03 eWAR label epoch: it is bWAR. (Measured
# 2026-09-25 against data/ewar.json: warTd equals the elapsed-season bWAR sum
# on 1,429 of 1,429 rows to 0.1, and differs from eWAR by a mean 0.64 WAR on
# 809 SP/RP deals.)
LEGACY_LEDGER_WAR_BASIS = "bwar"


def _ledger_war_basis(led: dict) -> str:
    return led.get("war_basis") or LEGACY_LEDGER_WAR_BASIS


def build_fa_archive_payload(first: int = 2015, last: int = CLASS_YEAR - 1) -> dict:
    try:
        series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
        dpw_by = {int(k): v for k, v in series["usd_per_war_by_winter"].items()}
    except (OSError, ValueError, KeyError):
        dpw_by = {}
    winters = []
    bases: Counter = Counter()
    methods: Counter = Counter()
    built: set = set()
    for year in range(first, last + 1):
        rows = []
        spend = 0
        for s in storage.load_fa_signings(year).values():
            led = s.get("ledger") or {}
            if led:
                bases[_ledger_war_basis(led)] += 1
                methods[led.get("method") or "unknown"] += 1
                if led.get("built"):
                    built.add(led["built"])
            rows.append(_clean({
                "key": s.get("player_key"), "name": s["player_name"],
                "pos": s.get("position"), "from": s.get("from_team"),
                "to": s.get("to_team"), "years": s.get("years"),
                "guar": s.get("guarantee_usd"), "aav": s.get("aav_usd"),
                "qo": s.get("qo") or None, "milb": (not s.get("mlb_deal")) or None,
                "warTd": led.get("war_to_date"),
                "surplusTd": led.get("surplus_to_date_usd"),
                # Any REALIZED $/WAR the client computes needs the money that
                # has actually been paid and how far through the deal we are.
                # Without these, warTd (a partial) divided into guar (the whole
                # contract) reads $40M+/WAR on any recent winter - not a market
                # signal, an arithmetic error. `done` alone cannot fix it: a
                # 6-year deal in year 2 is neither complete nor comparable.
                "paidTd": led.get("paid_to_date_usd"),
                "elapsed": (round(float(led["elapsed_years"])
                                  / max(float(led.get("total_years") or s.get("years") or 1), 1.0), 3)
                            if led.get("elapsed_years") is not None else None),
                "done": led.get("complete"),
            }))
            spend += s.get("guarantee_usd") or 0
        rows.sort(key=lambda r: -(r.get("guar") or 0))
        winters.append({
            "year": year, "n": len(rows), "spend_usd": spend,
            "dpw_usd": int(dpw_by[year]) if year in dpw_by else None,
            "qo_offered": fa_cba.qo_offered_count(year),
            "signings": rows,
        })
    return {"generated_at": date.today().isoformat(),
            # M04-04: the WAR the realized columns read. "mixed" only while a
            # partial rebuild is in progress; the counts say how mixed.
            "warBasis": (next(iter(bases)) if len(bases) == 1 else
                         ("mixed" if bases else None)),
            "warBasisCounts": dict(bases) or None,
            # M14-3: the ledger method the rows were built with, so a consumer
            # names it from the archive instead of typing it ("mixed" while a
            # rebuild is partial).
            "ledgerMethod": (next(iter(methods)) if len(methods) == 1 else
                             ("mixed" if methods else None)),
            "ledgerBuilt": max(built) if built else None,
            "winters": winters}


def _source_freshness(class_year: int | None = None) -> dict:
    """Last-successful-check date per FA source - the UI's staleness stamps.

    Two granularity rules, both learned from live defects:

    - The class board is read SCOPED TO `class_year`. A global MAX read fresh
      off the 2028/2029 rows while the served 2027 board sat frozen behind a
      broken parse.
    - Signings take the later of (row MAX, recorded check). Before the winter
      opens a class has zero signing rows, so a row-only read froze on the
      previous class and tripped the UI 14-day flag every day from 2026-07-10.

    Read-only; missing tables (fresh DB) just drop out."""
    out = {}
    checks = storage.load_source_checks()
    try:
        with storage.connect() as con:
            for label, table, scoped in (("class", "fa_class_players", True),
                                         ("signings", "fa_signings", True),
                                         ("payroll", "fa_team_payroll", False),
                                         ("parks", "fa_park_factors", False)):
                if scoped and class_year is not None:
                    r = con.execute(
                        f"SELECT MAX(fetched_at) FROM {table} WHERE class_year = ?",
                        (class_year,)).fetchone()
                else:
                    r = con.execute(f"SELECT MAX(fetched_at) FROM {table}").fetchone()
                stamps = [str(r[0])[:10]] if r and r[0] else []
                chk = checks.get((f"fa_{label}", str(class_year) if class_year else ""))
                if chk and chk.get("checked_at"):
                    stamps.append(str(chk["checked_at"])[:10])
                if stamps:
                    out[label] = max(stamps)
    except Exception: # noqa: BLE001 - stamps are best-effort
        pass
    return out


def _qo_tax_block(class_year: int) -> dict:
    """{payor_tier: qo_tax_usd(...)} for the class winter. Best-effort: a
    missing or unmapped tier drops out rather than failing the export."""
    out = {}
    as_of = f"{class_year - 1}-12-15"
    try:
        tiers = sorted(fa_cba.qo_compensation(as_of)["signing_team_forfeits"])
    except Exception:                                       # noqa: BLE001
        log.warning("qo tax block: compensation matrix unavailable")
        return {}
    for tier in tiers:
        try:
            out[tier] = fm.qo_tax_usd(tier, as_of)
        except Exception:                                   # noqa: BLE001
            log.warning("qo tax block: tier %s failed - skipping", tier)
    return out


# J4: the before/after, as a public receipt rather than prose. Numbers from the
# four-arm attribution run, same rows both sides. The disclosure sentences in
# _war_input_divergence read their figures from these rows.
_DEF_PIN_ROWS = (
    {"metric": "AAV", "before": 3.135, "after": 2.909,
     "unit": "$M mean absolute error", "better": "lower"},
    {"metric": "Guarantee", "before": 10.207, "after": 9.690,
     "unit": "$M mean absolute error", "better": "lower"},
    {"metric": "Mega deals", "before": 86.065, "after": 79.814,
     "unit": "$M mean absolute error", "better": "lower"},
    {"metric": "Length", "before": 0.429, "after": 0.433,
     "unit": "years mean absolute error", "better": "lower"},
)


def _war_input_divergence() -> dict:
    """DISCLOSURE, required by the owner decision that created the pin
    (2026-08-06). FA pricing deliberately reads a DIFFERENT WAR than
    /projections/ does for the same player. A reader who finds two figures
    and no explanation has found a bug even when both numbers are right, so
    the divergence ships with the numbers rather than living in a commit
    message."""
    rows = [dict(r) for r in _DEF_PIN_ROWS]
    by = {r["metric"]: r for r in rows}
    aav, length = by["AAV"], by["Length"]
    return {
        "diverges": bool(not fm.FA_PRICING_USE_DEF),
        "pinned_off": "F-DEF, the fitted defensive and positional column",
        "why": ("F-DEF wins the WAR projection gate and loses the money gate. "
                f"Dropped from pricing only: AAV error {aav['before']:.3f} to "
                f"{aav['after']:.3f} (about 2.5x the smallest resolvable "
                "difference), edge over baseline 0.224 to 0.340, guarantee "
                "and mega-deal error also lower."),
        "consequence": ("FA prices here use a WAR projection without defense. "
                        "MLB Projections includes it, so the two can show "
                        "different WAR for one player."),
        "measured": "docs/fa-gate2-attribution-2026-08-06.md",
        "before_after": {
            "shipped": "2026-08-06",
            "change": "F-DEF removed from free agent pricing only",
            "rows": rows,
            "note": (f"Length got worse ({length['before']:.3f} to "
                     f"{length['after']:.3f} years) and is listed anyway."),
        },
    }


def build_fa_meta_payload(class_year: int = CLASS_YEAR,
                          pricing: dict | None = None) -> dict:
    def _gate(path: str):
        try:
            return json.loads((DATA_DIR / path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    thr = fa_cba.cbt_threshold(class_year)
    afford = fa_fit.affordability(class_year)
    priors = fa_fit.behavior_priors()
    bases = fa_fit.team_baselines(class_year)
    # Per-team blocked positions (the needs matrix's blocker lists, both
    # kinds): blocked teams fall OUT of the top-fits lists by construction
    # (their need craters), so the Fits view names the blockers here - 
    # "why isn't this team shopping at SS" is half the product.
    needs = fa_fit.needs_matrix(class_year)
    teams = {}
    for org in sorted(set(afford) | set(priors) | set(bases)):
        a, b, w = afford.get(org) or {}, priors.get(org) or {}, bases.get(org) or {}
        blocked = []
        for pos, cell in (needs.get(org) or {}).items():
            for bl in cell.get("mlb_blockers") or []:
                blocked.append({"pos": pos, "n": bl["player_name"], "t": "mlb",
                                "w": bl.get("war_proj")})
            for bl in (cell.get("blockers") or [])[:1]:
                blocked.append({"pos": pos, "n": bl["player_name"], "t": "prospect"})
        teams[org] = _clean({
            "committed": a.get("committed_usd"),
            "taxPayroll": a.get("tax_payroll_usd"),
            "space": a.get("space_usd"),
            "payor": a.get("payor_status"),
            "maxGuar": b.get("max_guarantee_usd"), "n100m": b.get("n_100m"),
            "recentSpend": b.get("recent_spend_usd"),
            "baseWins": w.get("baseline_wins"),
            # WHERE the baseline came from: "mlb_projections" (the same
            # team_outlook the /projections/ surface serves) or
            # "contracted_core" (the documented fallback). The surface must
            # not describe an outlook win total as a contracted-core number.
            "baseSrc": w.get("baseline_source"),
            "blocked": blocked or None,
        })
    try:
        dpw_series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dpw_series = None
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "sources": _source_freshness(class_year),
        "cba": {"threshold_usd": thr["threshold_usd"],
                "carry_forward": thr["carry_forward"],
                "regime": thr.get("regime"),
                "unverified_records": len(fa_cba.unverified_records())},
        # T1.5 - qo_tax_usd was DEAD CODE: fully implemented, tested, and
        # never called anywhere in the serve path. WIRED rather than deleted,
        # because the pick forfeiture is a real cost that changes who can
        # rationally sign a QO'd free agent and the module already prices it
        # off the platform's own realized draft-slot curve. It is served PER
        # PAYOR TIER instead of per member for a reason a reader can check:
        # the tax is a property of the SIGNING TEAM, and before a signing
        # there is no signing team. The board can apply the right tier once
        # a destination is known.
        "qo_tax_by_payor_tier": _qo_tax_block(class_year),
        "dpw_series": dpw_series,
        # M04-08: the series the class board actually prices on, beside the
        # committed one above, so the $/WAR view can name both levels.
        "dpw_pricing": pricing,
        # M04-03: the WAR basis the board prices on today, so the Model view
        # can say when a gate artifact was measured on another one.
        "war_provider": fp._war_provider(),
        "gate1": _gate("fa_gate1_eval.json"),
        "gate2": _gate("fa_gate2_eval.json"),
        "war_input_divergence": _war_input_divergence(),
        "park_factors": fa_fit.park_factors(class_year - 1),
        # Two SIBLING blocks (2026-09-11, docs/diamond-betting.md section 5i).
        # `park_factors` above is untouched. The short-window block carries every
        # club whose venue holds less than a full 3-season sample (the
        # Athletics at Sutter Health Park, the Rays' two-season Tropicana row),
        # and since the 2026-09-11 venue audit it prices, through the one shrink
        # in betting_model: the betting board (SERVE_ATH_PARK), dfs_export's park
        # leg and the team fit's park component (fa_fit.venue_park_row). The
        # by-hand block stays dark.
        "park_factors_short_window": _park_sibling(
            fa_fit.park_factors_short_window, class_year - 1),
        "park_factors_by_hand": _park_sibling(
            fa_fit.park_factors_by_hand, class_year - 1),
        "teams": teams,
    }


def _park_sibling(builder, season: int) -> dict | None:
    """One best-effort park sibling block. A Savant outage costs the block a
    null, never the fa_meta write: a failed optional fetch must not keep the
    free-agent board from publishing. A null short-window block prices the
    short-sample clubs the way they priced before 2026-09-11 (the Athletics
    neutral, the Rays at their raw 3-season row), stated, never invented."""
    try:
        blk = builder(season)
    except Exception:                                       # noqa: BLE001
        log.warning("fa_meta: %s(%s) failed; block written as null",
                    getattr(builder, "__name__", "park sibling"), season)
        return None
    return blk or None


def refresh_park_siblings(path: Path | None = None, *, log_fn=None) -> dict:
    """Rewrite ONLY the two park sibling blocks of an existing fa_meta.json,
    from the same builders `build_fa_meta_payload` calls, and leave every other
    key byte-for-byte where it was.

    WHY IT EXISTS. The short-window block PRICES (betting_model.SERVE_ATH_PARK,
    dfs_export's park leg, the team fit), but the full fa_meta write runs late
    in the nightly (run_monthly d10b), after DFS (9d-bis), the betting refit
    (9e-pre1) and the board (9e) have already read the file, and the nightly
    checkout reverts the file to its committed copy first. So a Savant refresh
    reaches those consumers only through a committed fa_meta.json, or through
    this call placed before 9d-bis. It fetches only the Savant pages (cached by
    fa_sources) and StatsAPI's team list (cached by fantasy_schedule).

    A block whose builder fails is KEPT as it was on disk, never overwritten
    with a null, so an outage costs a refresh and never a served park. Returns
    {"path", "season", "written", "blocks": {key: "refreshed" | "kept" |
    "unchanged"}}."""
    path = Path(path) if path else DATA_DIR / "fa_meta.json"
    say = log_fn or log.info
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        say(f"fa_meta park blocks: {path.name} unreadable; nothing refreshed")
        return {"path": str(path), "season": None, "written": False, "blocks": {}}
    season = int(meta.get("class_year") or CLASS_YEAR) - 1
    status = {}
    changed = False
    for key, builder in (("park_factors_short_window", fa_fit.park_factors_short_window),
                         ("park_factors_by_hand", fa_fit.park_factors_by_hand)):
        blk = _park_sibling(builder, season)
        if blk is None:
            status[key] = "kept"
            continue
        if meta.get(key) == blk:
            status[key] = "unchanged"
            continue
        meta[key] = blk
        status[key] = "refreshed"
        changed = True
    if changed:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    short = (meta.get("park_factors_short_window") or {}).get("orgs") or {}
    say(f"fa_meta park blocks ({season}): {status}; short-window clubs "
        f"{sorted(short)}")
    return {"path": str(path), "season": season, "written": changed, "blocks": status}


# Future winters exported alongside the current class (the board's year
# selector; current stays the default). Spotrac publishes forward class
# pages, so the SAME constructed-class pipeline runs per year - future
# members are contract-expiry projections with option/QO statuses, no
# signings/events yet (the tracker goes live when their winter does).
FUTURE_CLASS_YEARS = (CLASS_YEAR + 1, CLASS_YEAR + 2)


def _keep_previous(name: str, payload: dict) -> bool:
    """True when this payload must NOT overwrite the file already on disk.

    THE FIX FOR THE 2026-08-04 OVERWRITE (lane D-1). A good 223-of-228 board
    was replaced by a 149-of-228 one because a Baseball-Reference frame did
    not load, and nothing in the write path had an opinion about that. The
    posture the repo settled on this day is fantasy_export's: when the input
    is degraded, KEEP THE PREVIOUS ARTIFACT rather than publish the damage.
    A day-old board that prices Skubal is strictly better than a fresh one
    that leaves him blank, and staleness is already visible on the page via
    generated_at while a half-populated board is not visible at all.

    Deliberately conditional on the file EXISTING: a first-ever export has no
    previous version to keep, and shipping nothing is worse than shipping a
    board that carries its own degraded_why. Only fa_class payloads are
    gated; fa_archive and fa_meta never touch war_daily identity."""
    if not (payload.get("identity_health") or {}).get("degraded"):
        return False
    if not (DATA_DIR / name).exists():
        log.error("fa %s: identity substrate degraded and no previous file to "
                  "keep, publishing the degraded board with its disclosure", name)
        return False
    log.error("fa %s: NOT overwritten. The identity substrate is degraded "
              "(%d of %d pitchers resolved) and the file on disk is a better "
              "board than this run can build. Re-run once war_daily is back.",
              name, (payload.get("identity_health") or {}).get("pit_resolved", 0),
              (payload.get("identity_health") or {}).get("pit_n", 0))
    return True


def snapshot_served_penter(path: Path | None = None) -> int:
    """M04-05. Record tonight's served P(enter) for every pending_option
    member of the current class, READ BACK from the fa_class.json on disk
    (never recomputed), into storage.fa_penter_served_history. Called by
    run_monthly after the night's last FA export; the date is today and
    cannot be set, so nothing is ever back-filled. Returns rows written."""
    import socket
    import subprocess
    p = Path(path) if path else DATA_DIR / "fa_class.json"
    try:
        cls = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("penter snapshot: %s unreadable; nothing recorded", p.name)
        return 0
    rows = [m for m in cls.get("members") or [] if m.get("status") == "pending_option"]
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                             capture_output=True, text=True, timeout=10).stdout.strip() or None
    except Exception:                                       # noqa: BLE001
        sha = None
    try:
        host = socket.gethostname()
    except Exception:                                       # noqa: BLE001
        host = None
    return storage.snapshot_fa_penter(cls.get("class_year") or CLASS_YEAR, rows,
                                      generated_at=cls.get("generated_at"),
                                      host=host, git_sha=sha)


def _dpw_pricing_block(cls_payload: dict) -> dict | None:
    """The class board's own $/WAR basis for fa_meta (M04-08): the in-run
    series, the ex-ante level it carries to, the escalator, and the rate
    /projections/ prices the same winter at. None when the class did not
    price (no dpw_usd), so the page says nothing rather than a zero."""
    if not cls_payload or cls_payload.get("dpw_usd") is None:
        return None
    return {
        "class_year": cls_payload.get("class_year"),
        "usd_per_war_by_winter": cls_payload.get("dpw_series_pricing") or {},
        "winter_dpw_usd": cls_payload.get("dpw_usd"),
        "escalator": cls_payload.get("dpw_infl"),
        "method": fm._dpw_forecast_method(),
        "projections_dpw_usd": (_load_mlb_projections() or {}).get("dpw_usd"),
        "projections_first_season": (_load_mlb_projections() or {}).get("first_season"),
    }


def export_all() -> dict[str, int]:
    sizes = {}
    cls_payload = build_fa_class_payload()
    arc_payload = build_fa_archive_payload()
    meta_payload = build_fa_meta_payload(pricing=_dpw_pricing_block(cls_payload))
    # M04-04: the $/WAR view's realized series is built from the same ledger.
    meta_payload["archive_war_basis"] = arc_payload.get("warBasis")
    exports = [("fa_class.json", cls_payload),
               ("fa_archive.json", arc_payload),
               ("fa_meta.json", meta_payload)]
    for y in FUTURE_CLASS_YEARS:
        try:
            exports.append((f"fa_class_{y}.json", build_fa_class_payload(y)))
        except Exception:                                     # noqa: BLE001
            log.exception("future class %d export failed - continuing", y)
    kept = []
    for name, payload in exports:
        if _keep_previous(name, payload):
            kept.append(name)
            continue
        raw = json.dumps(payload, separators=(",", ":"))
        (DATA_DIR / name).write_text(raw, encoding="utf-8")
        sizes[name] = len(raw)
    log.info("fa exports: %s", {k: f"{v/1024:.0f}KB" for k, v in sizes.items()})
    if kept:
        log.error("fa exports HELD (previous version kept): %s", kept)
    return sizes


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--park-blocks" in sys.argv[1:]:
        print(refresh_park_siblings())
    else:
        print(export_all())
