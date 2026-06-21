# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Build data/overseas_timeseries.json for the Overseas frontend section.

Aggregates the parallel `overseas_*` tables into a frontend-friendly JSON:
  {
    "generated_at": <ISO timestamp>,
    "leagues": [
      {
        "league": "NPB",
        "n_prospects": 32,
        "fv_distribution": {"60": 0, "55": 2, "50": 4, ...},
        "league_context": {                     // narrative + reference numbers
          "name": "Nippon Professional Baseball",
          "country": "Japan",
          "season_window": "March-October",
          "split_note": "Central + Pacific Leagues; Pacific runs slightly hotter (~+5 OPS pts)",
          "translation_pct": -5                  // rough wRC+ haircut crossing to MLB
        },
        "prospects": [
          {
            "player_key": "overseas_npb_shunpeita_yamashita",
            "player_name": "Shunpeita Yamashita",
            "position": "SP",
            "league": "NPB",
            "country": "Japan",
            "country_flag": "🇯🇵",
            "current_team": "Orix Buffaloes",
            "proj_team": null,
            "proj_bonus_usd": null,
            "eta_year": 2028,
            "consensus_fv": 55,
            "status": "overseas_active",         // active | posted | signed | mlb_promoted
            "posted_date": null,
            "posting_days_remaining": null,
            "signed_team": null,
            "signed_bonus_usd": null,
            "signed_date": null,
            "milb_key": null,
            "tool_grades": { "fangraphs": {...} },
            "stats": [
              {"season": 2023, "league": "NPB", "team": "ORX",
               "ip": 95.0, "era": 1.61, ...},
              ...
            ],
            "career_arc": {
              "primary_metric": "era",            // "wrc_plus" for hitters
              "values": [{"season": 2023, "value": 1.61}, ...]
            },
            "points": [ /* per-source snapshot timeseries */ ]
          }
        ]
      },
      ...
    ]
  }

Per-league grouping (rather than per-class). Each league carries a
'league_context' block to surface the translation gap to MLB the
user explicitly asked us to add.
"""

from __future__ import annotations

import json
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from player_images import country_flag_svg_url, player_headshot_url
from storage import (
    _grad_wag,
    load_career_stats,
    load_career_war,
    load_overseas_canonical_keys,
    load_overseas_players,
    load_overseas_snapshots,
    load_overseas_statlines,
    overseas_snapshot_count,
)

log = logging.getLogger(__name__)


# Country → emoji flag - kept for back-compat. The frontend now
# prefers SVG flag icons (via country_code) and only falls back to
# emoji when the SVG fails or the country is unmapped.
COUNTRY_FLAG = {
    "Japan": "🇯🇵",
    "South Korea": "🇰🇷",
    "Korea": "🇰🇷",
    "Taiwan": "🇹🇼",
    "Cuba": "🇨🇺",
    "Dominican Republic": "🇩🇴",
    "Venezuela": "🇻🇪",
    "Mexico": "🇲🇽",
    "Puerto Rico": "🇵🇷",
    "Australia": "🇦🇺",
}

# Country name → ISO-3166 alpha-2 code, lowercase. Used by the
# flagcdn.com SVG flag URL (https://flagcdn.com/<cc>.svg). The
# frontend looks up by country_code so the JS doesn't have to
# maintain its own table.
COUNTRY_CODE = {
    "Japan":              "jp",
    "South Korea":        "kr",
    "Korea":              "kr",
    "Taiwan":             "tw",
    "Cuba":               "cu",
    "Dominican Republic": "do",
    "Venezuela":          "ve",
    "Mexico":             "mx",
    "Puerto Rico":        "pr",
    "Australia":          "au",
    "USA":                "us",
    "United States":      "us",
    "Canada":             "ca",
    "Panama":             "pa",
    "Colombia":           "co",
    "Nicaragua":          "ni",
    "Curacao":            "cw",
    "Curaçao":            "cw",
    "Aruba":              "aw",
    "Brazil":             "br",
    "Netherlands":        "nl",
}


# Per-league reference context + MLB-equivalent translation factors.
# Factors are *multipliers* applied to the raw league rate:
#   hitter_wrc_factor:  MLBe wRC+  ≈ league wRC+  × factor
#   pitcher_era_factor: MLBe ERA   ≈ league ERA   × factor
#   hitter_k_pct_delta: MLBe K%    ≈ league K%    + delta
#   fb_velo_delta:      MLBe FB    ≈ league FB    + delta (mph)
#
# Anchors: Eric Longenhagen's NPB/KBO translation primer (FG 2024),
# Davy Andrews' Pitch Type Translation Project (FG 2023), and the
# Hideo Nomo / Hideki Matsui / Yu Darvish / Masahiro Tanaka /
# Shohei Ohtani / Kenta Maeda / Yoshinobu Yamamoto / Lee Jung-hoo
# /Eric Thames / Merrill Kelly transition cohort. The Japan→MLB
# offensive haircut has held at 12-15% wRC+ over the last decade for
# the median-talent batter; the pitcher ERA/FIP haircut is a wider
# 15-30% but anchors at roughly +0.5-0.7 ERA for starters. KBO and
# CPBL haircuts are larger because the cohorts are smaller and
# lower-velocity. Cuba is bracketed by similar studies on the
# defection-era cohort (Cespedes / Abreu / Chapman / Soler).
LEAGUE_CONTEXT = {
    "NPB": {
        "name":          "Nippon Professional Baseball",
        "country":       "Japan",
        "season_window": "March – October",
        "split_note":    "Central + Pacific Leagues; Pacific runs slightly hotter (≈ +5 OPS pts)",
        "hitter_wrc_factor": 0.87, # PRIOR retained - wRC+ refit needs per-season league context (measured raw OPS ratio 0.802, see eval)
        # REFIT (model-audit Phase 4b WS-8, data/overseas_translation_eval.json):
        # measured IP-weighted ERA ratio 1.696 over the n=15 2016-25
        # transition cohort (Maeda...Sasaki), shrunk k=8 toward the old
        # 1.25 prior -> 1.54. The hand-set haircut was badly optimistic.
        "pitcher_era_factor": 1.54,   # NPB ERA  × 1.54 ≈ MLB ERA
        "hitter_k_pct_delta": +0.043, # REFIT: measured +0.0475 (n=6), shrunk
        "fb_velo_delta": -1.0, # PRIOR retained - no historical velo source
        "citation":           "Phase-4b transition refit (overseas_translation_eval) / Longenhagen 2024 priors where unmeasured",
    },
    "NPBF": {
        "name":          "NPB Farm (Eastern / Western Leagues)",
        "country":       "Japan",
        "season_window": "March – October",
        "split_note": "NPB minor leagues - small samples, used mostly for rehab + development",
        "hitter_wrc_factor":  0.72,
        "pitcher_era_factor": 1.45,
        "hitter_k_pct_delta": +0.06,
        "fb_velo_delta":      -1.5,
        "citation":           "Scaled from NPB top-league factors (no direct cohort)",
    },
    "KBO": {
        "name":          "Korea Baseball Organization",
        "country":       "South Korea",
        "season_window": "April – October",
        "split_note":    "10-team single division; hitter-friendly (league OPS ≈ .740-.760)",
        "hitter_wrc_factor": 0.81, # PRIOR retained (measured raw OPS ratio 0.819, n=1 - see eval)
        # REFIT (Phase 4b WS-8): measured ERA ratio 1.215 (n=6, incl.
        # MLB returnees Kelly/Flexen/Fedde - flagged in the eval),
        # shrunk toward 1.32 -> 1.275. KBO prior was slightly harsh.
        "pitcher_era_factor": 1.275,
        "hitter_k_pct_delta": +0.05,  # measured +0.0474 ≈ prior; retained
        "fb_velo_delta": -1.5, # PRIOR retained - no historical velo source
        "citation":           "Phase-4b transition refit (overseas_translation_eval) / Longenhagen 2024 priors where unmeasured",
    },
    "CPBL": {
        "name":          "Chinese Professional Baseball League",
        "country":       "Taiwan",
        "season_window": "April – October",
        "split_note":    "6-team league; extremely hitter-friendly, smaller sample",
        "hitter_wrc_factor":  0.70,
        "pitcher_era_factor": 1.55,
        "hitter_k_pct_delta": +0.06,
        "fb_velo_delta":      -2.0,
        "citation":           "FG aggregate (small cohort: Wei-Yin Chen, Wang Chien-ming era)",
    },
    "CUBA": {
        "name":          "Serie Nacional de Béisbol",
        "country":       "Cuba",
        "season_window": "November – April",
        "split_note":    "Defections + restricted player movement complicate continuity",
        "hitter_wrc_factor":  0.84,
        "pitcher_era_factor": 1.30,
        "hitter_k_pct_delta": +0.04,
        "fb_velo_delta":      -1.0,
        "citation":           "Defection cohort (Cespedes / Abreu / Chapman / Soler)",
    },
}


def _mlb_translate(payload: dict, league_ctx: dict, is_pitcher: bool) -> dict:
    """Return a copy of `payload` augmented with MLB-equivalent
    versions of the rate stats. Adds `_mlbe`-suffixed fields when
    the underlying value + the league factor are both available.
    Untouched when league_ctx has no factors (no double-counting on
    repeat calls)."""
    out = dict(payload)
    if not league_ctx:
        return out
    if is_pitcher:
        era = payload.get("era")
        factor = league_ctx.get("pitcher_era_factor")
        if era is not None and factor:
            try:
                out["era_mlbe"] = round(float(era) * factor, 2)
            except (TypeError, ValueError):
                pass
        # K%/BB% deltas swing in the same direction for both: MLB strikes out
        # more, walks slightly less. We only annotate K%/BB% on hitters
        # below; for pitcher K% the delta is informational not actionable.
    else:
        wrc = payload.get("wrc_plus")
        wf = league_ctx.get("hitter_wrc_factor")
        if wrc is not None and wf:
            try:
                out["wrc_plus_mlbe"] = int(round(float(wrc) * wf))
            except (TypeError, ValueError):
                pass
        k_pct = payload.get("k_pct")
        k_delta = league_ctx.get("hitter_k_pct_delta")
        if k_pct is not None and k_delta is not None:
            try:
                out["k_pct_mlbe"] = round(float(k_pct) + k_delta, 4)
            except (TypeError, ValueError):
                pass
    return out


def _latest_per_source(snaps: list[dict]) -> dict[str, dict]:
    by_source: dict[str, dict] = {}
    for s in sorted(snaps, key=lambda r: r.get("snapshot_date") or ""):
        by_source[s.get("source")] = s
    return by_source


def _consensus(snaps: list[dict], field: str) -> float | None:
    latest = _latest_per_source(snaps)
    vals = [s.get(field) for s in latest.values() if s.get(field) is not None]
    if not vals:
        return None
    try:
        return round(sum(float(v) for v in vals) / len(vals), 2)
    except (TypeError, ValueError):
        return None


def _consensus_fv_plus(snaps: list[dict]) -> bool:
    """v26 - True if any latest-per-source snap has fv_plus=1."""
    latest = _latest_per_source(snaps)
    return any(bool(s.get("fv_plus")) for s in latest.values())


def _fv_bucket(fv: float | None, fv_plus: bool = False) -> str | None:
    """v26 - Bucket from integer FV + '+' flag (no more .5 inflation).
    Integer 45 with fv_plus=True → "45+"; without → "45"."""
    if fv is None:
        return None
    n = int(math.ceil(fv))   # FV rounds UP (55.3 -> 56), consistent with display
    if n >= 60: return "60"
    if n >= 55: return "55" + ("+" if fv_plus else "")
    if n >= 50: return "50" + ("+" if fv_plus else "")
    if n >= 45: return "45" + ("+" if fv_plus else "")
    if n >= 40: return "40" + ("+" if fv_plus else "")
    return "<40"


def _career_arc(stats: list[dict]) -> dict | None:
    """Pick the dominant league's stat sequence + a primary metric for
    a sparkline. Hitters → wrc_plus (fallback ops, slg). Pitchers →
    era (fallback fip)."""
    if not stats:
        return None
    # Restrict to the top league by season count (typically NPB or KBO).
    league_counts: dict[str, int] = defaultdict(int)
    for s in stats:
        league_counts[s.get("league")] += 1
    if not league_counts:
        return None
    primary_league = max(league_counts, key=league_counts.get)
    seq = sorted([s for s in stats if s.get("league") == primary_league],
                 key=lambda r: r.get("season") or 0)
    if not seq:
        return None
    # Hitter vs pitcher heuristic from the payload keys.
    sample = seq[-1].get("payload") or {}
    is_pitcher = "era" in sample or "ip" in sample
    if is_pitcher:
        candidates = ("era", "fip", "k_per_9")
    else:
        candidates = ("wrc_plus", "ops", "slg")
    metric = None
    for c in candidates:
        if any((s.get("payload") or {}).get(c) is not None for s in seq):
            metric = c
            break
    if not metric:
        return None
    values = [{"season": s.get("season"),
               "value": (s.get("payload") or {}).get(metric)}
              for s in seq if (s.get("payload") or {}).get(metric) is not None]
    if not values:
        return None
    return {
        "primary_metric": metric,
        "primary_league": primary_league,
        "values": values,
    }


def _posting_days_remaining(posted_date: str | None) -> int | None:
    """NPB posting window is 30 days from posting. KBO posting periods
    are looser but generally month-long. Return days remaining (or
    negative when expired)."""
    if not posted_date:
        return None
    try:
        d = date.fromisoformat(posted_date)
    except (ValueError, TypeError):
        return None
    days = (d - date.today()).days + 30
    return days


def _load_mlb_career_index() -> dict[str, dict]:
    """player_key -> a graduate-shaped payload sufficient for
    storage._grad_wag: {position, sabermetrics.is_pitcher, fv_close,
    career_war{...}, career_stats[...]}.

    Two layers, last-write-wins:
      1. The career_war / career_stats DB tables - the tracked-prospect
         graduates (same source debuts.json uses), so they're always
         available even on a fresh deploy.
      2. data/mlb_player_detail.json - the BROAD MLB career-WAR layer
         (war_daily keyed by mlbam), keyed by the same canonical
         player_key. This is what covers established NPB/KBO imports who
         were never tracked MiLB prospects (Suzuki, Sugano, Martinez...).

    Best-effort: a missing/unreadable artifact or DB simply yields a
    smaller index, so signings degrade to '-' rather than crashing the
    export. The artifact is a build output (overseas_export runs before
    the MLB-detail export in a full monthly), so it reads the previous
    cycle's file - stale-by-one-run is fine for slow-moving career WAR."""
    idx: dict[str, dict] = {}

    # Layer 1 - DB tables (tracked-prospect graduates).
    try:
        cwar = load_career_war() or {}
        cstats = load_career_stats() or {}
    except Exception:
        cwar, cstats = {}, {}
    for pk, cw in cwar.items():
        if not isinstance(cw, dict) or cw.get("career_war") is None:
            continue
        idx[pk] = {"career_war": cw, "career_stats": cstats.get(pk) or []}

    # Layer 2 - mlb_player_detail.json (broad MLB coverage; wins on overlap).
    # Resolve relative to THIS module, not the cwd: the export runs from the
    # pipeline under varying working directories, and a cwd-relative path was
    # silently missing the file (dropping career WAR for every non-DB player).
    detail_path = Path(__file__).resolve().parent / "data" / "mlb_player_detail.json"
    try:
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        players = (detail or {}).get("players") or {}
    except (OSError, ValueError):
        players = {}
    for pk, rec in players.items():
        if not isinstance(rec, dict):
            continue
        seasons: dict[str, float] = {}
        rows: list[dict] = []
        total = 0.0
        n = 0
        for row in (rec.get("career") or []):
            y = row.get("y")
            if y is None:
                continue
            w = row.get("war")
            if isinstance(w, (int, float)):
                seasons[str(y)] = w
                total += w
                n += 1
            pa, ip = row.get("pa"), row.get("ip")
            rows.append({
                "level": "MLB", "season": y,
                "pa": int(pa) if isinstance(pa, (int, float)) else None,
                "ip": float(ip) if ip not in (None, "") else None,
            })
        if n == 0:
            continue
        origin = rec.get("origin") or {}
        season_years = [c.get("y") for c in (rec.get("career") or []) if c.get("y")]
        idx[pk] = {
            "position": rec.get("pos"),
            "sabermetrics": {"is_pitcher": bool(rec.get("isPit"))},
            "fv_close": origin.get("fvClose"),
            "career_war": {
                "career_war": round(total, 2),
                "war_seasons_count": n,
                "war_per_yr": round(total / n, 2) if n else None,
                "seasons": seasons,
            },
            "career_stats": rows,
            # Extra metadata used to synthesize curated-import signing records
            # (players who never appeared on the overseas prospect board).
            "name": rec.get("name"),
            "team": rec.get("team"),
            "first_season": min(season_years) if season_years else None,
        }
    return idx


def _signing_performance(entry: dict | None, position, consensus_fv) -> dict:
    """Realized career value for a signing: {career_war, war_per_yr, wag}.

    career_war = total bWAR; war_per_yr = career WAR / MLB seasons (the same
    per-season rate the WAG engine compares against - intentionally simpler
    than the playing-time-weighted variant so the two columns stay
    internally coherent). wag runs through the shared storage._grad_wag so it
    matches every other WAG on the site; the grade is the graduate record's
    own FV where present, else the overseas consensus FV. All-None when there
    is no career WAR on file (a player who never reached MLB)."""
    out = {"career_war": None, "war_per_yr": None, "wag": None}
    if not entry:
        return out
    cw = entry.get("career_war") or {}
    total = cw.get("career_war")
    if total is None:
        return out
    try:
        out["career_war"] = round(float(total), 1)
    except (TypeError, ValueError):
        return out
    wpy = cw.get("war_per_yr")
    if wpy is None and cw.get("war_seasons_count"):
        wpy = total / cw["war_seasons_count"]
    out["war_per_yr"] = round(float(wpy), 2) if wpy is not None else None

    fv = entry.get("fv_close")
    if fv is None:
        fv = consensus_fv
    payload = {
        "position": entry.get("position") or position,
        "sabermetrics": entry.get("sabermetrics") or {},
        "fv_close": fv, "fv_close_raw": fv,
        "career_war": cw,
        "career_stats": entry.get("career_stats") or [],
    }
    try:
        out["wag"] = _grad_wag(payload)
    except Exception:
        out["wag"] = None
    return out


def _sort_signings(signings: list[dict]) -> None:
    """Most-recent class first: arrival year desc, then realized career WAR,
    then name. eta_year is the real signing class (signed_date is a backfill
    stamp). Sorts in place."""
    signings.sort(key=lambda s: (
        (s.get("eta_year") or 0),
        (s.get("career_war") if s.get("career_war") is not None else -99),
        s.get("player_name") or "",
    ), reverse=True)


# Marquee overseas -> MLB imports that never appeared on the overseas prospect
# board (signed straight out of NPB/KBO/Cuba before being tracked here, so the
# board carries no snapshot for them). The MLB layer has no origin-league flag,
# so which players are overseas imports is hand-curated; EVERYTHING shown
# (team, career WAR, WAR/yr, WAG, arrival year) is pulled from the MLB career
# layer. `team` is an optional override for the rare case the live roster team
# is null in the source. Extend as new imports arrive.
OVERSEAS_IMPORTS: dict[str, dict] = {
    "roki_sasaki":       {"league": "NPB", "country": "Japan"},
    "munetaka_murakami": {"league": "NPB", "country": "Japan"},
    "shota_imanaga":     {"league": "NPB", "country": "Japan"},
    "kodai_senga":       {"league": "NPB", "country": "Japan"},
    "masataka_yoshida":  {"league": "NPB", "country": "Japan"},
    "kazuma_okamoto":    {"league": "NPB", "country": "Japan"},
    "yariel_rodriguez":  {"league": "NPB", "country": "Cuba", "team": "TOR"},
}


def _build_import_signings(mlb_career_idx: dict[str, dict],
                           existing_keys: set[str]) -> dict[str, list[dict]]:
    """Synthesize signing records for the curated OVERSEAS_IMPORTS that aren't
    already on the board. Returns {league: [signing, ...]}. Stats come from the
    MLB career index; only league/country (and a rare team override) are
    curated. Players with no MLB career on file are skipped."""
    out: dict[str, list[dict]] = defaultdict(list)
    for key, meta in OVERSEAS_IMPORTS.items():
        if key in existing_keys:
            continue
        entry = mlb_career_idx.get(key)
        if not entry or (entry.get("career_war") or {}).get("career_war") is None:
            continue
        country = meta.get("country")
        fv = entry.get("fv_close")
        perf = _signing_performance(entry, entry.get("position"), fv)
        out[meta["league"]].append({
            "player_key":       key,
            "player_name":      entry.get("name") or key,
            "position":         entry.get("position"),
            "league":           meta["league"],
            "country":          country,
            "country_flag":     COUNTRY_FLAG.get(country, ""),
            "country_code":     COUNTRY_CODE.get(country),
            "country_flag_svg": country_flag_svg_url(COUNTRY_CODE.get(country)),
            "consensus_fv":     int(math.ceil(fv)) if fv is not None else None,
            "consensus_fv_plus": False,
            "status":           "mlb_promoted",
            "posted_date":      None,
            "signed_team":      meta.get("team") or entry.get("team"),
            "signed_bonus_usd": None,
            "signed_date":      None,
            "proj_team":        None,
            "proj_bonus_usd":   None,
            "eta_year":         entry.get("first_season"),
            "milb_key":         key,
            "career_war":       perf["career_war"],
            "war_per_yr":       perf["war_per_yr"],
            "wag":              perf["wag"],
            "is_import":        True,
        })
    return out


def _build_league(league: str,
                  all_snaps: list[dict],
                  players_by_key: dict[str, dict],
                  stats_by_player: dict[str, list[dict]],
                  canonical_keys: dict[str, str],
                  mlb_career_idx: dict[str, dict] | None = None) -> dict:
    mlb_career_idx = mlb_career_idx or {}
    snaps = [s for s in all_snaps if s.get("league") == league]
    by_player: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        by_player[s["player_key"]].append(s)

    prospects: list[dict] = []
    signings: list[dict] = []
    fv_dist: dict[str, int] = defaultdict(int)
    n_filtered_promoted = 0
    n_filtered_mlb_active = 0

    # Status priority: mlb_promoted > signed > posted > overseas_active
    status_priority = {"overseas_active": 0, "posted": 1,
                       "signed": 2, "mlb_promoted": 3}

    for pk, plist in by_player.items():
        latest = _latest_per_source(plist)
        any_snap = sorted(plist, key=lambda r: r.get("snapshot_date") or "")[-1]
        player_meta = players_by_key.get(pk) or {}

        fv = _consensus(plist, "fv")
        fv_plus = _consensus_fv_plus(plist)  # v26
        status = max((s.get("status") or "overseas_active" for s in plist),
                     key=lambda x: status_priority.get(x, 0))
        country = any_snap.get("country") or player_meta.get("country")
        posted_date = player_meta.get("posted_date")

        # v7 / v34 - A player who has reached MLB affiliated ball, or who
        # has formally committed to an MLB org, is no longer a CURRENT
        # overseas prospect - but we still want to TRACK the signing.
        # Detection layers (mirrors the historical drop filter):
        # 1) Per-record status flagged mlb_promoted (the promotion
        #    pipeline flips this when the player joins a MiLB roster).
        # 2) Catch-up: any MLB-level stat row on file (covers an
        #    Anthony Kay-style name-normalization miss that left the
        #    status un-flipped).
        # 3) A signed_team on the player meta (committed but not yet
        #    promoted - e.g. a winter signing before reporting).
        # Such players are pulled OUT of the ranked `prospects` pool (so
        # Rankings / Stats never surface graduates - the long-standing
        # invariant) and routed into a parallel `signings` list that
        # powers the Recently Signed + League Context track-record views.
        _statuses = {s.get("status") for s in plist}
        _raw_stats = stats_by_player.get(pk) or []
        _has_mlb_activity = any(
            (row.get("league") in {"MLB", "AL", "NL"})
            or (row.get("payload") or {}).get("level") == "MLB"
            for row in _raw_stats
        )
        _is_promoted = "mlb_promoted" in _statuses
        _is_signed = bool(player_meta.get("signed_team"))
        if _is_promoted or _is_signed:
            # Genuine signing: graduated to MLB from this league, or
            # formally committed to an org. Routed into `signings`.
            if _is_promoted:
                n_filtered_promoted += 1
            milb_key = canonical_keys.get(pk)
            consensus_fv = int(math.ceil(fv)) if fv is not None else None
            # Realized MLB value (career WAR / WAR-per-yr / WAG), joined on
            # the canonical key and embedded so the frontend never has to
            # lazy-load the 100MB+ graduate payload to fill these columns.
            perf = _signing_performance(
                mlb_career_idx.get(milb_key),
                any_snap.get("position") or player_meta.get("position"),
                consensus_fv)
            signings.append({
                "player_key":       pk,
                "player_name":      any_snap.get("player_name"),
                "position":         any_snap.get("position") or player_meta.get("position"),
                "league":           league,
                "country":          country,
                "country_flag":     COUNTRY_FLAG.get(country, ""),
                "country_code":     COUNTRY_CODE.get(country),
                "country_flag_svg": country_flag_svg_url(COUNTRY_CODE.get(country)),
                "consensus_fv":     consensus_fv,
                "consensus_fv_plus": fv_plus,
                "status":           status,
                "posted_date":      posted_date,
                "signed_team":      player_meta.get("signed_team"),
                "signed_bonus_usd": player_meta.get("signed_bonus_usd"),
                "signed_date":      player_meta.get("signed_date"),
                "proj_team":        any_snap.get("proj_team") or player_meta.get("proj_team"),
                "proj_bonus_usd":   any_snap.get("proj_bonus_usd") or player_meta.get("proj_bonus_usd"),
                "eta_year":         any_snap.get("eta_year") or player_meta.get("eta_year"),
                "milb_key":         milb_key,
                "career_war":       perf["career_war"],
                "war_per_yr":       perf["war_per_yr"],
                "wag":              perf["wag"],
            })
            continue

        # MLB stat rows on file but no promotion flag / signing meta - a
        # reverse migration (MLB -> KBO / NPB, e.g. a former big-leaguer
        # finishing his career overseas) or an un-flagged graduate. Either
        # way not a current overseas prospect, and with no signing metadata
        # to show it isn't a trackable signing - drop it from both pools
        # (preserves the long-standing "no MLB-active players in Rankings"
        # invariant).
        if _has_mlb_activity:
            n_filtered_mlb_active += 1
            continue

        bucket = _fv_bucket(fv, fv_plus)
        if bucket:
            fv_dist[bucket] += 1

        tool_grades: dict[str, dict] = {}
        for src, snap in latest.items():
            tools = snap.get("tools") or {}
            if tools:
                tool_grades[src] = tools

        points = []
        for snap in sorted(plist, key=lambda r: r.get("snapshot_date") or ""):
            points.append({
                "snapshot_date":  snap.get("snapshot_date"),
                "source":         snap.get("source"),
                "interval_label": snap.get("interval_label"),
                "fv":             snap.get("fv"),
                "fv_plus":        bool(snap.get("fv_plus")),
                "status":         snap.get("status"),
            })

        # Per-prospect hitter/pitcher classification - look at the most
        # recent season payload. ERA/IP imply pitcher; otherwise hitter.
        raw_stats = stats_by_player.get(pk) or []
        latest_payload = (raw_stats[-1].get("payload") or {}) if raw_stats else {}
        is_pitcher = (latest_payload.get("era") is not None
                      or latest_payload.get("ip") is not None)

        # Augment each stat row's payload with MLB-equivalent fields
        # using the league context that owns the stat's league (so a
        # player's NPB row uses NPB factors, and any MLB stints stay
        # raw because MLB doesn't need translating).
        stats_rows: list[dict] = []
        for row in raw_stats:
            row_league = row.get("league")
            ctx = LEAGUE_CONTEXT.get(row_league) or {}
            stats_rows.append({
                **row,
                "payload": _mlb_translate(row.get("payload") or {}, ctx, is_pitcher),
            })

        prospects.append({
            "player_key":      pk,
            "player_name":     any_snap.get("player_name"),
            "position":        any_snap.get("position") or player_meta.get("position"),
            "league":          league,
            "country":         country,
            "country_flag":    COUNTRY_FLAG.get(country, ""),
            "country_code":    COUNTRY_CODE.get(country),
            "country_flag_svg": country_flag_svg_url(COUNTRY_CODE.get(country)),
            "headshot_url":    player_headshot_url({
                "mlbam_id":     player_meta.get("mlbam_id"),
                "fg_player_id": player_meta.get("fg_player_id"),
            }),
            "current_team":    any_snap.get("current_team") or player_meta.get("current_team"),
            "proj_team":       any_snap.get("proj_team") or player_meta.get("proj_team"),
            "proj_bonus_usd":  any_snap.get("proj_bonus_usd") or player_meta.get("proj_bonus_usd"),
            "eta_year":        any_snap.get("eta_year") or player_meta.get("eta_year"),
            "height":          player_meta.get("height"),
            "weight":          player_meta.get("weight"),
            "bats":            player_meta.get("bats"),
            "throws":          player_meta.get("throws"),
            "fg_player_id":    player_meta.get("fg_player_id"),
            # Round FV to the nearest integer at export time so the
            # frontend never has to render "55.5". _parse_fv keeps the
            # raw float internally for sort precision; only the export
            # surface gets coerced to int.
            "consensus_fv":    int(math.ceil(fv)) if fv is not None else None,   # FV rounds UP
            "consensus_fv_plus": fv_plus, # v26 - '+' upside flag
            "risk":            any_snap.get("risk"),
            "status":          status,
            "posted_date":     posted_date,
            "posting_days_remaining": _posting_days_remaining(posted_date),
            "signed_team":     player_meta.get("signed_team"),
            "signed_bonus_usd": player_meta.get("signed_bonus_usd"),
            "signed_date":     player_meta.get("signed_date"),
            "milb_key":        canonical_keys.get(pk),
            "tool_grades":     tool_grades,
            "stats":           stats_rows,
            "career_arc":      _career_arc(stats_rows),
            "points":          points,
        })

    # v31.12 - Cohort-normalized Tool+ and RPS+ for the overseas
    # league. Tool+ is the league-z-normalized average of per-source
    # tool composites. RPS+ uses the latest-season wRC+ (hitters) or
    # FIP inverted to wRC+-style positive scale (pitchers), then
    # league-z-normalized.
    def _ovs_tool_composite(tg: dict) -> float | None:
        if not tg: return None
        per_source = []
        for src, tools in tg.items():
            if not isinstance(tools, dict): continue
            nums = [float(v) for k, v in tools.items()
                    if k != "_extras" and isinstance(v, (int, float))]
            if nums:
                per_source.append(sum(nums) / len(nums))
        if not per_source: return None
        return sum(per_source) / len(per_source)
    def _ovs_perf_signal(stat_rows: list, is_pitcher: bool):
        if not stat_rows: return None
        # Find the most recent in-league payload (skip MLB rows).
        for row in reversed(stat_rows):
            row_league = row.get("league")
            if row_league in {"MLB", "AL", "NL"}: continue
            pl = row.get("payload") or {}
            if is_pitcher:
                v = pl.get("fip")
                if v is not None:
                    try: return float(v)
                    except (TypeError, ValueError): pass
            else:
                v = pl.get("wrc_plus")
                if v is not None:
                    try: return float(v)
                    except (TypeError, ValueError): pass
        return None
    raw_tool_comps: list[float] = []
    raw_perf_hit: list[float]   = []
    raw_perf_pit: list[float]   = []
    for p in prospects:
        tc = _ovs_tool_composite(p.get("tool_grades"))
        p["_tool_composite_raw"] = tc
        if tc is not None: raw_tool_comps.append(tc)
        # Hitter vs pitcher inferred from same logic used inline above
        # - we have ERA/IP in the payload then pitcher.
        sr = p.get("stats") or []
        is_pit = False
        if sr:
            lpl = (sr[-1].get("payload") or {})
            is_pit = (lpl.get("era") is not None or lpl.get("ip") is not None)
        p["_is_pitcher_hint"] = is_pit
        ps = _ovs_perf_signal(sr, is_pit)
        p["_perf_signal_raw"] = ps
        if ps is None: continue
        (raw_perf_pit if is_pit else raw_perf_hit).append(ps)
    def _cohort_plus(values: list[float], v: float | None, *,
                      lower_better: bool = False) -> int | None:
        if v is None or len(values) < 5: return None
        m = sum(values) / len(values)
        var = sum((x - m) ** 2 for x in values) / len(values)
        sd = var ** 0.5 if var > 0 else 1.0
        z = (v - m) / sd
        if lower_better: z = -z
        return max(60, min(140, int(round(100 + 15 * z))))
    for p in prospects:
        p["tool_plus"] = _cohort_plus(raw_tool_comps, p.pop("_tool_composite_raw", None))
        ps_raw = p.pop("_perf_signal_raw", None)
        is_pit = p.pop("_is_pitcher_hint", False)
        if is_pit:
            p["rps_plus"] = _cohort_plus(raw_perf_pit, ps_raw, lower_better=True)
        else:
            p["rps_plus"] = _cohort_plus(raw_perf_hit, ps_raw, lower_better=False)

    # v26 - Sort by (FV desc, '+' tiebreaker desc) so 42+ ranks above
    # 42 but below 43. None FVs sink to the bottom of the list.
    prospects.sort(key=lambda p: (p.get("consensus_fv") is None,
                                  -(p.get("consensus_fv") or 0),
                                  -(1 if p.get("consensus_fv_plus") else 0)))

    # Most recent class first (eta_year is the real signing class; signed_date
    # is a backfill stamp). Curated imports are merged + re-sorted later.
    _sort_signings(signings)

    if n_filtered_promoted or n_filtered_mlb_active:
        log.info("overseas %s: routed %d MLB-promoted records into the "
                 "signings list; dropped %d MLB-active (reverse-migration) "
                 "records from the ranked pool",
                 league, n_filtered_promoted, n_filtered_mlb_active)

    return {
        "league":          league,
        "n_prospects":     len(prospects),
        "n_signings":      len(signings),
        "fv_distribution": dict(fv_dist),
        "league_context":  LEAGUE_CONTEXT.get(league, {}),
        "prospects":       prospects,
        "signings":        signings,
    }


def build_overseas_export() -> dict:
    """In-memory payload for data/overseas_timeseries.json."""
    all_snaps = load_overseas_snapshots()
    players = load_overseas_players()
    stat_rows = load_overseas_statlines()
    canonical = load_overseas_canonical_keys()

    stats_by_player: dict[str, list[dict]] = defaultdict(list)
    for r in stat_rows:
        stats_by_player[r["player_key"]].append({
            "season":  r["season"],
            "league":  r["league"],
            "team":    r.get("team"),
            "payload": r.get("payload") or {},
        })

    # Sort each player's stats ascending by season for the UI.
    for v in stats_by_player.values():
        v.sort(key=lambda r: r.get("season") or 0)

    # Exclude MLB-family "leagues": these come from overseas players who have
    # already graduated to the majors (overseas_mlb_* keys, league='MLB' - e.g.
    # Senga, Yoshida). They are no longer international prospects and must not
    # surface in the Overseas section (the dynamic league derivation previously
    # spun up a stray "MLB" tab carrying them).
    _MLB_LEAGUES = {"MLB", "AL", "NL"}
    leagues = sorted({s["league"] for s in all_snaps
                      if s.get("league") and s["league"] not in _MLB_LEAGUES})
    # Order leagues by total prospect count desc so NPB / KBO land first.
    counts = defaultdict(int)
    for s in all_snaps:
        if s.get("league"):
            counts[s["league"]] += 1
    leagues.sort(key=lambda l: -counts[l])

    # Realized MLB career value, joined onto signings (loaded once).
    mlb_career_idx = _load_mlb_career_index()

    league_blocks = [_build_league(l, all_snaps, players, stats_by_player,
                                    canonical, mlb_career_idx) for l in leagues]

    # Merge curated overseas -> MLB imports (Sasaki, Murakami, Imanaga, ...)
    # that never appeared on the prospect board. Add to the matching league
    # block (spinning one up if the source league has no board presence).
    existing_keys = {s.get("milb_key") for blk in league_blocks
                     for s in blk["signings"] if s.get("milb_key")}
    blocks_by_league = {blk["league"]: blk for blk in league_blocks}
    for lg, extra in _build_import_signings(mlb_career_idx, existing_keys).items():
        blk = blocks_by_league.get(lg)
        if blk is None:
            blk = {"league": lg, "n_prospects": 0, "n_signings": 0,
                   "fv_distribution": {}, "league_context": LEAGUE_CONTEXT.get(lg, {}),
                   "prospects": [], "signings": []}
            blocks_by_league[lg] = blk
            league_blocks.append(blk)
        blk["signings"].extend(extra)
        _sort_signings(blk["signings"])
        blk["n_signings"] = len(blk["signings"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leagues":      league_blocks,
    }


def export_overseas_json(out_path: Path) -> int:
    payload = build_overseas_export()
    n = sum(b["n_prospects"] for b in payload["leagues"])
    # ── FLOOR GUARD (2026-06 leagues:[] regression fix) ───────────────────────
    # A 0-prospect export must NEVER overwrite a known-good sidecar. If we built 0
    # but overseas_snapshots is non-empty, the build hit a transient failure (the
    # root cause was a swallowed "database is locked" during the concurrent
    # pipeline) - abort the write so the last good file (e.g. 40 prospects) is
    # preserved and the run logs the failure loudly instead of silently shipping
    # an empty Overseas section. A genuinely-empty source (0 rows) writes normally.
    if n == 0:
        have = overseas_snapshot_count()
        if have > 0:
            raise RuntimeError(
                f"overseas export computed 0 prospects but overseas_snapshots has "
                f"{have} rows - refusing to overwrite {out_path.name}. This is the "
                f"empty-export signature (likely a transient DB lock during the "
                f"concurrent pipeline); the existing sidecar is preserved."
            )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    log.info("overseas_export: wrote %d prospects across %d leagues -> %s",
             n, len(payload["leagues"]), out_path)
    return n


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = Path("data/overseas_timeseries.json")
    print(export_overseas_json(out), "prospects exported")
