# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Build the data/ifa_timeseries.json export for the International Amateurs section.

Mirrors the Draft section's sidecar (`draft_timeseries.json`): one "class" per
signing year (2021-current), each carrying the full Spotrac IFA signing list,
an org spending leaderboard, and class-level trends.

The signing data comes from `spotrac.scrape_spotrac_ifa` - the complete per-year
tracker (player, **signing org**, country, bonus, pool%). The `org` field is the
team that signed the player that period, so the section shows the SIGNING team,
not the player's current org. Prospects we also track in the MiLB DB get enriched
(FV / rank / headshot / current-org) by matching on `player_key`.

    {
      "generated_at": ISO,
      "classes": [
        {
          "year": 2026,
          "is_current": true,
          "n_signings": 494,
          "total_usd": 181267500,
          "trends": { ... },
          "signings": [ {player_name, player_key, org, country, position,
                         bonus_usd, pool_pct, is_tracked, fv, fv_label,
                         overall_rank, mlbam_id, headshot_url, current_org}, ... ],
          "org_spending": [ {org, total_usd, signings, top_bonus, top_player,
                             pool_pct_sum}, ... ]
        }, ...
      ]
    }
"""

from __future__ import annotations

import json
import logging
import math
import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

# ── THE BOARD eFV GRADE ─────────────────────────────────────────────────────
# ONE eFV basis for this surface, and it is the SAME one every other surface
# serves. Mirrors proj_export._board_grade / fantasy_export._board_grade /
# build_site._load_xfv_grades, all of which resolve storage.BOARD_GRADE_FIELD
# ("xfv_grade") through efv_board_scale.board_value(). There is deliberately no
# copy of the scale coefficients here.
#
# BASIS REPAIR 2026-08-05. This module resolved `xfv_grade_quantile` FIRST, a
# field RETIRED as a display grade on 2026-07-25 (it survives only as the
# surplus PRICING basis - see efv_export meta.grade_scale). Measured against
# the served pair data/xfv.json + data/ifa_timeseries.json: 2,006 signings
# carried fv_basis="xfv" and averaged +12.31 FV ABOVE the board grade for the
# same player_key (max +21.3, 1,973 of them off by >= 0.5), so a prospect read
# ~57 on /ifa/ and ~45 on PROSPX. That is the exact failure storage's
# BOARD_GRADE_FIELD block exists to prevent, and the third surface to hit it
# after the homepage (2026-07-25) and /fantasy/ (2026-08-03).
#
# The retired-quantile and realized fallbacks are NOT kept. On the live
# artifact they are inert anyway (9,379 of 9,379 by_player rows carry
# xfv_grade, and xfv_grade == xfv_grade_realized on all 9,379), so dropping
# them costs nothing today and removes the only path by which a second basis
# could reach this page tomorrow. When the board grade is genuinely absent we
# return None and _enrich falls back to CONSENSUS, which is a declared basis
# stamped on the row as fv_basis="consensus" - never a silent substitution of
# one eFV scale for another.
try:
    from efv_board_scale import board_value as _efv_board_value
except Exception:                                            # pragma: no cover
    def _efv_board_value(rec):
        return (rec or {}).get("xfv_grade")


def _board_grade(rec: dict | None):
    """THE board eFV grade for an xfv.json record, or None. Unrounded -
    callers that display it round to NEAREST (eFV is not a scouting FV)."""
    g = _efv_board_value(rec or {})
    return float(g) if isinstance(g, (int, float)) else None


# Bonus buckets for the class-level distribution trend (high → low).
_BONUS_BUCKETS = (
    ("≥$3M",        3_000_000, None),
    ("$1-3M",       1_000_000, 3_000_000),
    ("$500k-1M",      500_000, 1_000_000),
    ("$100-500k",     100_000,   500_000),
    ("<$100k",              0,   100_000),
)


def _bonus_bucket(bonus: int | None) -> str | None:
    if bonus is None:
        return None
    for label, lo, hi in _BONUS_BUCKETS:
        if bonus >= lo and (hi is None or bonus < hi):
            return label
    return None


def _fv_label(fv: float | None, is_plus: bool) -> str | None:
    if fv is None:
        return None
    return f"{int(math.ceil(fv))}{'+' if is_plus else ''}"   # FV rounds UP (55.3 -> 56)


_GEN_SUFFIX = re.compile(r"_(jr|sr|ii|iii|iv)$")


def _lookup_tracked(players_by_key: dict, key: str | None) -> dict | None:
    """Resolve a signing's player_key to its tracked-prospect record. Exact
    match first; then a generational-suffix alias, because the Spotrac signing
    tracker keeps "Jr./Sr./III" while StatsAPI-keyed prospects drop it - so the
    IFA signing `angel_nunez_jr` is the graded prospect `angel_nunez`. Only the
    suffix is stripped (never a bare prefix), so it can't collapse two distinct
    players onto one record."""
    if not key:
        return None
    tp = players_by_key.get(key)
    if tp is not None:
        return tp
    base = _GEN_SUFFIX.sub("", key)
    return players_by_key.get(base) if base != key else None


def _enrich(signing: dict, tp: dict | None, xfv_grade: float | None = None,
            xfv_is_floor: bool = False) -> dict:
    """Merge one Spotrac signing with the tracked-prospect record (if we
    have one). Signing-team `org` always comes from Spotrac (the signing
    period's team); the tracked record only adds FV / rank / headshot and
    the player's CURRENT org (shown as a 'now' note when traded since).

    The displayed CURRENT grade is eFV (the platform-primary, outcome-grounded
    grade) when we have one for this player, falling back to consensus FV
    otherwise - so the IFA list matches the grade every other PROSPX surface
    shows. `fv_basis` records which was used.

    `fv_is_floor` is True when the eFV grade is the outcome map's floor
    (xfv.json xfv_grade_is_floor): the map returns its first knot, 20.0, for
    every non-positive projection, so the number is the bottom of the scale
    and not a resolved level. The page shows such a row as a floor, with no
    movement from the signing grade, and keeps it out of FV sums (census
    M03-12). The eFV scale and floor mechanics are unchanged."""
    out = {
        "player_name": signing.get("player_name"),
        "player_key":  signing.get("player_key"),
        "org":         signing.get("org"),          # SIGNING team
        "country":     signing.get("country"),
        "position":    signing.get("position"),
        "bonus_usd":   signing.get("bonus_usd"),
        "pool_pct":    signing.get("pool_pct"),
        "is_tracked":  False,
        "fv":          None,
        "fv_label":    None,
        "fv_basis":    None,
        "fv_is_floor": False,
        "fv_signing":  None,
        "fv_signing_label": None,
        "age_at_signing": None,
        "tool_current": None,
        "tool_signing": None,
        "overall_rank": None,
        "mlbam_id":    None,
        "headshot_url": None,
        "current_org": None,
    }
    if tp:
        cons_fv = tp.get("fv_close_raw")
        if cons_fv is None:
            cons_fv = tp.get("fv_close")
        # eFV primary, consensus fallback. The "+" upside marker is a consensus
        # concept, so only carry it on the consensus path.
        use_xfv = xfv_grade is not None
        fv = xfv_grade if use_xfv else cons_fv
        fv_open = tp.get("fv_open")
        out.update({
            "is_tracked":   True,
            "fv":           fv,                                  # CURRENT grade (eFV or consensus)
            # eFV rounds to NEAREST (owner rule); consensus FV ceils.
            # Half-up like JS Math.round - Python round() is half-even.
            "fv_label":     (str(int(math.floor(fv + 0.5))) if (use_xfv and fv is not None)
                             else _fv_label(fv, bool(tp.get("fv_close_plus")) and not use_xfv)),
            "fv_basis":     "xfv" if use_xfv else "consensus",
            "fv_is_floor":  bool(use_xfv and xfv_is_floor),
            # FV at signing ≈ the earliest grade we have on file (fv_open).
            "fv_signing":       fv_open,
            "fv_signing_label": _fv_label(fv_open, False),
            "overall_rank": tp.get("overall_rank"),
            "mlbam_id":     tp.get("mlbam_id"),
            "current_org":  tp.get("org"),
            # Prefer the tracked position when Spotrac left it blank.
            "position":     out["position"] or tp.get("position"),
        })
        # Age at signing - J2 signing day is Jan 15 of the class year.
        bd = tp.get("birth_date")
        yr = signing.get("year")
        if bd and yr:
            try:
                b = date.fromisoformat(bd)
                out["age_at_signing"] = round((date(yr, 1, 15) - b).days / 365.25, 1)
            except (TypeError, ValueError):
                pass
        # Tool composite: current (tools.composite_overall) vs at-signing
        # (mean of the earliest snapshot's consensus tool grades).
        co = (tp.get("tools") or {}).get("composite_overall")
        if co is not None:
            out["tool_current"] = int(round(co))
        pts = tp.get("points") or []
        if pts:
            tc = pts[0].get("tools_consensus") or {}
            vals = [v for v in tc.values() if isinstance(v, (int, float))]
            if vals:
                out["tool_signing"] = int(round(sum(vals) / len(vals)))
        try:
            from player_images import player_headshot_url
            out["headshot_url"] = player_headshot_url(tp)
        except Exception:
            pass
    return out


def _build_class(year: int, rows: list[dict], players_by_key: dict,
                 today: date, xfv_by_key: dict | None = None) -> dict:
    """Assemble one signing-year class block from its Spotrac rows."""
    xfv_by_key = xfv_by_key or {}

    def _enrich_row(r):
        tp = _lookup_tracked(players_by_key, r.get("player_key"))
        # Look up the board eFV by the TRACKED (canonical) key, not the signing
        # key. ONE basis, resolved through _board_grade - see the BASIS REPAIR
        # block at the top of this module for why there is no chain here.
        xrec = (xfv_by_key.get(tp["player_key"]) or {}) if tp else {}
        return _enrich(r, tp, _board_grade(xrec),
                       xfv_is_floor=xrec.get("xfv_grade_is_floor") is True)

    signings = [_enrich_row(r) for r in rows]
    # Bonus-desc, then tracked-first, then name - deterministic.
    signings.sort(key=lambda s: (
        -(s["bonus_usd"] or 0), not s["is_tracked"], s["player_name"] or ""))

    bonuses = [s["bonus_usd"] for s in signings if s["bonus_usd"] is not None]
    total_usd = sum(bonuses)

    # Org leaderboard (mirrors spotrac.build_org_ifa_spending, + pool%).
    org_agg: dict[str, dict] = {}
    for s in signings:
        org = s["org"]
        if not org:
            continue
        b = org_agg.setdefault(org, {
            "org": org, "total_usd": 0, "signings": 0,
            "top_bonus": 0, "top_player": None, "pool_pct_sum": 0.0,
        })
        b["signings"] += 1
        if s["bonus_usd"]:
            b["total_usd"] += s["bonus_usd"]
            if s["bonus_usd"] > b["top_bonus"]:
                b["top_bonus"] = s["bonus_usd"]
                b["top_player"] = s["player_name"]
        if s["pool_pct"]:
            b["pool_pct_sum"] += s["pool_pct"]
    org_spending = sorted(org_agg.values(),
                          key=lambda o: (-o["total_usd"], -o["signings"]))
    for o in org_spending:
        o["pool_pct_sum"] = round(o["pool_pct_sum"], 1)

    # Trends.
    bucket_counts: dict[str, int] = {label: 0 for label, _, _ in _BONUS_BUCKETS}
    for s in signings:
        bk = _bonus_bucket(s["bonus_usd"])
        if bk:
            bucket_counts[bk] += 1
    country_agg: dict[str, dict] = {}
    for s in signings:
        c = s["country"] or " - "
        cb = country_agg.setdefault(c, {"country": c, "n": 0, "total_usd": 0})
        cb["n"] += 1
        if s["bonus_usd"]:
            cb["total_usd"] += s["bonus_usd"]
    top_countries = sorted(country_agg.values(),
                           key=lambda c: (-c["total_usd"], -c["n"]))[:10]
    pos_split: dict[str, int] = defaultdict(int)
    for s in signings:
        pos_split[s["position"] or " - "] += 1
    biggest = [
        {k: s[k] for k in ("player_name", "player_key", "org", "country",
                           "bonus_usd", "is_tracked", "fv_label", "fv_is_floor")}
        for s in signings[:15] if s["bonus_usd"]
    ]

    trends = {
        "total_usd":     total_usd,
        "n_signings":    len(signings),
        "n_with_bonus":  len(bonuses),
        "avg_bonus":     int(round(statistics.mean(bonuses))) if bonuses else None,
        "median_bonus":  int(round(statistics.median(bonuses))) if bonuses else None,
        "bonus_distribution": bucket_counts,
        "top_countries": top_countries,
        "biggest_signings": biggest,
        "position_split": dict(sorted(pos_split.items(), key=lambda kv: -kv[1])),
    }

    # Publish the eFV resolution count next to the tracked count. A class where
    # n_tracked is healthy but n_efv is 0 means the xfv join produced nothing -
    # the whole class silently drops to consensus grades, and without this
    # number on the artifact there is no way to see it from the outside.
    return {
        "year":        year,
        "is_current":  year >= today.year,
        "n_signings":  len(signings),
        "total_usd":   total_usd,
        "n_tracked":   sum(1 for s in signings if s["is_tracked"]),
        "n_efv":       sum(1 for s in signings if s["fv_basis"] == "xfv"),
        "trends":      trends,
        "signings":    signings,
        "org_spending": org_spending,
    }


def build_ifa_export(signings: list[dict], players_by_key: dict | None = None,
                     today: date | None = None, xfv_by_key: dict | None = None) -> dict:
    """Pure builder: group Spotrac IFA signings by year into class blocks
    enriched with tracked-prospect data. Newest year first. `xfv_by_key` (the
    xfv.json by_player map) lets the displayed grade be eFV, matching the rest
    of the platform."""
    players_by_key = players_by_key or {}
    today = today or date.today()
    by_year: dict[int, list[dict]] = defaultdict(list)
    for s in signings:
        y = s.get("year")
        # IFA tracking starts in 2021; ignore the stray pre-2021 / future
        # row-years Spotrac occasionally tags (re-signings, fixture quirks).
        if y is not None and 2021 <= y <= today.year:
            by_year[y].append(s)
    classes = [_build_class(y, by_year[y], players_by_key, today, xfv_by_key)
               for y in sorted(by_year, reverse=True)]
    # Always log the resolution counts, so "0 resolved" is visible in the run
    # log instead of only being inferable from a page of consensus grades.
    n_sign = sum(c["n_signings"] for c in classes)
    n_trk = sum(c["n_tracked"] for c in classes)
    n_efv = sum(c["n_efv"] for c in classes)
    log.info("ifa_export: %d signings, %d tracked, %d on the board eFV basis "
             "(%d fell back to consensus)", n_sign, n_trk, n_efv, n_trk - n_efv)
    return {"classes": classes}


def _xfv_by_key_from_sibling(path: Path) -> dict | None:
    """Load the sibling xfv.json by_player map so the IFA list can show the
    platform-primary eFV grade.

    NONE-AS-SENTINEL, not {}. An unreadable or empty artifact is an OUTAGE and
    must be distinguishable from "loaded fine, this player simply has no eFV" -
    the empty dict reads as the second downstream and publishes a whole section
    of consensus grades with nothing in the log. Same contract as
    bullpen_export._active_mlbam_ids. Callers treat None as "eFV unavailable
    this run" and report it; the page still renders on consensus."""
    xf = path.parent / "xfv.json"
    if not xf.exists():
        log.error("ifa_export: %s not found - no eFV grades this run, the whole "
                  "signing list falls back to consensus FV", xf)
        return None
    try:
        with xf.open(encoding="utf-8") as fp:
            by = json.load(fp).get("by_player") or {}
    except (OSError, ValueError):
        log.error("ifa_export: %s unreadable - no eFV grades this run, the whole "
                  "signing list falls back to consensus FV", xf, exc_info=True)
        return None
    if not isinstance(by, dict) or not by:
        log.error("ifa_export: %s parsed but by_player is EMPTY - treating as an "
                  "outage rather than as 'nobody has an eFV'", xf)
        return None
    log.info("ifa_export: loaded %d eFV board grades from %s", len(by), xf)
    return by


def _record_efv_health(*, ok: bool, n_rows: int = 0, message: str) -> None:
    """File this run's eFV-join verdict into the ingest-health ledger.

    WHY IT GOES THROUGH bullpen_export RATHER THAN run_monthly DIRECTLY.
    `from run_monthly import _record_ingest` reads as though it reaches the
    pipeline, and under the way the pipeline is actually launched
    (deploy/nightly-build.sh runs `python run_monthly.py`) it did not: the live
    module is sys.modules["__main__"], the name "run_monthly" is unclaimed, and
    the import built a SECOND module with its own empty ledger that nothing
    ever drained. MEASURED before the fix: 0 of 1 filed rows reached the
    drained payload. bullpen_export.record_ingest resolves the LIVE module
    (sys.modules first, __main__ second, fresh import only as a last resort),
    and it is one implementation instead of one per exporter.

    THE SECOND HALF of making the docstring below true: "ifa_efv_join" is named
    in run_monthly.SCHEDULED_EXPORTS. A correctly filed row under an unwatched
    name is written into the payload and then dropped from red[], which is
    exactly how this record was inert on both counts.

    Best-effort by design: this is a reporting path and must never be the
    reason the IFA export fails."""
    try:
        from bullpen_export import record_ingest
        record_ingest("ifa_efv_join", ok=ok, n_rows=n_rows, message=message,
                      # A clean run must not pay the whole pipeline import
                      # graph just to log a heartbeat from a standalone run.
                      import_fallback=not ok)
    except Exception:
        log.debug("could not record the IFA eFV join health row", exc_info=True)


def _record_efv_outage(message: str) -> None:
    """Raise a failed eFV join into the ingest-health RED ledger.

    The ledger is what the deploy shell prints as `!!! INGEST RED`, so an eFV
    join that resolved nothing becomes visible on the run that broke it instead
    of being read off the page weeks later. That claim is true only because of
    the two fixes documented on _record_efv_health, both landed 2026-08-05
    after review found every red filed here was going into a throwaway."""
    _record_efv_health(ok=False, message=message)


def _players_by_key_from_sibling(path: Path) -> dict:
    """Load the freshly-written main timeseries.json (sibling of the IFA
    sidecar) to key tracked players by player_key for enrichment. Returns
    {} when the file isn't present yet (signings still render, sans FV)."""
    ts = path.parent / "timeseries.json"
    if not ts.exists():
        log.info("ifa_export: %s not found - signings export without enrichment", ts)
        return {}
    try:
        with ts.open(encoding="utf-8") as fp:
            payload = json.load(fp)
    except (OSError, ValueError):
        # Same defect class as the eFV join below: an unreadable board file
        # used to return {} in silence, and every signing then published
        # is_tracked=False - a page that reads as "we track none of these
        # players" rather than as an outage. Behavior is unchanged (the
        # signings still render), but the failure is now on the record.
        log.error("ifa_export: %s unreadable - EVERY signing publishes untracked "
                  "(no FV, rank or headshot)", ts, exc_info=True)
        return {}
    by = {p["player_key"]: p for p in (payload.get("players") or [])
          if p.get("player_key")}
    log.info("ifa_export: %d tracked players available for enrichment from %s",
             len(by), ts)
    return by


def export_ifa_json(path, players_by_key: dict | None = None,
                    force: bool = False) -> int:
    """Scrape (cache-backed) the Spotrac IFA tracker for 2021-current, build
    the class blocks, and write `ifa_timeseries.json`. Returns the total
    signing count. Enrichment uses `players_by_key` when supplied, else the
    sibling timeseries.json."""
    from spotrac import scrape_spotrac_ifa_range
    path = Path(path)
    years = list(range(2021, date.today().year + 1))
    signings = scrape_spotrac_ifa_range(years, force=force)
    if players_by_key is None:
        players_by_key = _players_by_key_from_sibling(path)
    xfv_by_key = _xfv_by_key_from_sibling(path)      # None => eFV unavailable
    if xfv_by_key is None:
        _record_efv_outage(
            "xfv.json by_player missing/unreadable/empty; the IFA signing list "
            "published on consensus FV for every player instead of the board eFV.")
    payload = build_ifa_export(signings, players_by_key, xfv_by_key=xfv_by_key)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    n_tracked = sum(c["n_tracked"] for c in payload["classes"])
    n_efv = sum(c["n_efv"] for c in payload["classes"])
    # The join that CANNOT be seen from the artifact: the map loaded fine and
    # tracked prospects exist, but not one of them resolved a board grade. That
    # is a key-space break (the tracked key never appears in xfv.json), and it
    # publishes a full page of consensus grades that looks exactly like a page
    # of eFV grades. Refuse to let it pass silently.
    if xfv_by_key and n_tracked and not n_efv:
        _record_efv_outage(
            f"xfv.json loaded {len(xfv_by_key)} board grades but 0 of {n_tracked} "
            f"tracked IFA signings resolved one; the section published entirely "
            f"on consensus FV.")
        log.error("ifa_export: 0 of %d tracked signings resolved a board eFV "
                  "grade against %d xfv.json rows - key-space break, not a data gap",
                  n_tracked, len(xfv_by_key))
    elif xfv_by_key:
        # HEARTBEAT. Without an ok=True row, a ledger reader cannot separate
        # "the eFV join ran and resolved grades" from "the IFA step never ran
        # at all" - both look like silence, and that ambiguity is what let the
        # 8-day TJStats gap pass for a week of healthy-looking runs. n_rows
        # carries the resolved count, so a collapse from hundreds to a handful
        # is legible in the ledger even though it never trips a red.
        _record_efv_health(
            ok=True, n_rows=n_efv,
            message=(f"{n_efv} of {n_tracked} tracked IFA signings resolved a "
                     f"board eFV grade from {len(xfv_by_key)} xfv.json rows"))
    payload["efv_resolved"] = n_efv
    payload["efv_available"] = xfv_by_key is not None
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, separators=(",", ":"), ensure_ascii=False)
    n = sum(c["n_signings"] for c in payload["classes"])
    log.info("ifa_export: wrote %d signings across %d classes (%d of %d tracked "
             "on the board eFV basis) → %s",
             n, len(payload["classes"]), n_efv, n_tracked, path)
    return n
