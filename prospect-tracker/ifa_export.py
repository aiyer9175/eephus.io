# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Build the data/ifa_timeseries.json export for the International Amateurs section.

Mirrors the Draft section's sidecar (`draft_timeseries.json`): one "class" per
signing year (2021–current), each carrying the full Spotrac IFA signing list,
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

# Bonus buckets for the class-level distribution trend (high → low).
_BONUS_BUCKETS = (
    ("≥$3M",        3_000_000, None),
    ("$1–3M",       1_000_000, 3_000_000),
    ("$500k–1M",      500_000, 1_000_000),
    ("$100–500k",     100_000,   500_000),
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


def _enrich(signing: dict, tp: dict | None, xfv_grade: float | None = None) -> dict:
    """Merge one Spotrac signing with the tracked-prospect record (if we
    have one). Signing-team `org` always comes from Spotrac (the signing
    period's team); the tracked record only adds FV / rank / headshot and
    the player's CURRENT org (shown as a 'now' note when traded since).

    The displayed CURRENT grade is xFV (the platform-primary, outcome-grounded
    grade) when we have one for this player, falling back to consensus FV
    otherwise - so the IFA list matches the grade every other PROSPX surface
    shows. `fv_basis` records which was used."""
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
        # xFV primary, consensus fallback. The "+" upside marker is a consensus
        # concept, so only carry it on the consensus path.
        use_xfv = xfv_grade is not None
        fv = xfv_grade if use_xfv else cons_fv
        fv_open = tp.get("fv_open")
        out.update({
            "is_tracked":   True,
            "fv":           fv,                                  # CURRENT grade (xFV or consensus)
            "fv_label":     _fv_label(fv, bool(tp.get("fv_close_plus")) and not use_xfv),
            "fv_basis":     "xfv" if use_xfv else "consensus",
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
        # Look up xFV by the TRACKED (canonical) key, not the signing key.
        xg = (xfv_by_key.get(tp["player_key"]) or {}).get("xfv_grade") if tp else None
        return _enrich(r, tp, xg)

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
                           "bonus_usd", "is_tracked", "fv_label")}
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

    return {
        "year":        year,
        "is_current":  year >= today.year,
        "n_signings":  len(signings),
        "total_usd":   total_usd,
        "n_tracked":   sum(1 for s in signings if s["is_tracked"]),
        "trends":      trends,
        "signings":    signings,
        "org_spending": org_spending,
    }


def build_ifa_export(signings: list[dict], players_by_key: dict | None = None,
                     today: date | None = None, xfv_by_key: dict | None = None) -> dict:
    """Pure builder: group Spotrac IFA signings by year into class blocks
    enriched with tracked-prospect data. Newest year first. `xfv_by_key` (the
    xfv.json by_player map) lets the displayed grade be xFV, matching the rest
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
    return {"classes": classes}


def _xfv_by_key_from_sibling(path: Path) -> dict:
    """Load the sibling xfv.json by_player map so the IFA list can show the
    platform-primary xFV grade. Returns {} when absent (consensus fallback)."""
    xf = path.parent / "xfv.json"
    if not xf.exists():
        return {}
    try:
        with xf.open(encoding="utf-8") as fp:
            return json.load(fp).get("by_player", {}) or {}
    except (OSError, ValueError):
        return {}


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
        return {}
    return {p["player_key"]: p for p in (payload.get("players") or [])
            if p.get("player_key")}


def export_ifa_json(path, players_by_key: dict | None = None,
                    force: bool = False) -> int:
    """Scrape (cache-backed) the Spotrac IFA tracker for 2021–current, build
    the class blocks, and write `ifa_timeseries.json`. Returns the total
    signing count. Enrichment uses `players_by_key` when supplied, else the
    sibling timeseries.json."""
    from spotrac import scrape_spotrac_ifa_range
    path = Path(path)
    years = list(range(2021, date.today().year + 1))
    signings = scrape_spotrac_ifa_range(years, force=force)
    if players_by_key is None:
        players_by_key = _players_by_key_from_sibling(path)
    xfv_by_key = _xfv_by_key_from_sibling(path)
    payload = build_ifa_export(signings, players_by_key, xfv_by_key=xfv_by_key)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, separators=(",", ":"), ensure_ascii=False)
    n = sum(c["n_signings"] for c in payload["classes"])
    log.info("ifa_export: wrote %d signings across %d classes → %s",
             n, len(payload["classes"]), path)
    return n
