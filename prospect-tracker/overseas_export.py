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
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from player_images import country_flag_svg_url, player_headshot_url
from storage import (
    load_overseas_canonical_keys,
    load_overseas_players,
    load_overseas_snapshots,
    load_overseas_statlines,
)

log = logging.getLogger(__name__)


# Country → emoji flag — kept for back-compat. The frontend now
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
        "hitter_wrc_factor":  0.87,   # NPB wRC+ × 0.87 ≈ MLB wRC+
        "pitcher_era_factor": 1.25,   # NPB ERA  × 1.25 ≈ MLB ERA
        "hitter_k_pct_delta": +0.04,  # MLB hitters K out ~4 pts more
        "fb_velo_delta":      -1.0,   # FB plays ~1 mph slower in MLB
        "citation":           "Longenhagen 2024 / Andrews 2023 / 15-yr posting cohort",
    },
    "NPBF": {
        "name":          "NPB Farm (Eastern / Western Leagues)",
        "country":       "Japan",
        "season_window": "March – October",
        "split_note":    "NPB minor leagues — small samples, used mostly for rehab + development",
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
        "hitter_wrc_factor":  0.81,
        "pitcher_era_factor": 1.32,
        "hitter_k_pct_delta": +0.05,
        "fb_velo_delta":      -1.5,
        "citation":           "Longenhagen 2024 / Kim 2022 / Lee Jung-hoo + Bae cohort",
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
    """v26 — True if any latest-per-source snap has fv_plus=1."""
    latest = _latest_per_source(snaps)
    return any(bool(s.get("fv_plus")) for s in latest.values())


def _fv_bucket(fv: float | None, fv_plus: bool = False) -> str | None:
    """v26 — Bucket from integer FV + '+' flag (no more .5 inflation).
    Integer 45 with fv_plus=True → "45+"; without → "45"."""
    if fv is None:
        return None
    n = int(round(fv))
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


def _build_league(league: str,
                  all_snaps: list[dict],
                  players_by_key: dict[str, dict],
                  stats_by_player: dict[str, list[dict]],
                  canonical_keys: dict[str, str]) -> dict:
    snaps = [s for s in all_snaps if s.get("league") == league]
    by_player: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        by_player[s["player_key"]].append(s)

    prospects: list[dict] = []
    fv_dist: dict[str, int] = defaultdict(int)
    n_filtered_promoted = 0
    n_filtered_mlb_active = 0

    for pk, plist in by_player.items():
        latest = _latest_per_source(plist)
        any_snap = sorted(plist, key=lambda r: r.get("snapshot_date") or "")[-1]
        player_meta = players_by_key.get(pk) or {}

        # v7 — drop players who have already signed-and-promoted to MLB
        # affiliated ball. Two filter layers:
        # 1) Per-record status flagged mlb_promoted (the promotion
        #    pipeline flips this when the player joins a MiLB roster).
        # 2) Catch-up: even when the per-record status didn't get
        #    flipped (Anthony Kay-style name-normalization miss),
        #    drop the player if they have MLB activity on file via
        #    the imported career_stats / roster_status sources.
        _statuses = {s.get("status") for s in plist}
        if "mlb_promoted" in _statuses:
            n_filtered_promoted += 1
            continue
        # Catch-up: drop if player has any MLB-level stat row this season
        _raw_stats = stats_by_player.get(pk) or []
        _has_mlb_activity = any(
            (row.get("league") in {"MLB", "AL", "NL"})
            or (row.get("payload") or {}).get("level") == "MLB"
            for row in _raw_stats
        )
        if _has_mlb_activity:
            n_filtered_mlb_active += 1
            continue

        fv = _consensus(plist, "fv")
        fv_plus = _consensus_fv_plus(plist)  # v26
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

        # Status priority: mlb_promoted > signed > posted > overseas_active
        status_priority = {"overseas_active": 0, "posted": 1,
                           "signed": 2, "mlb_promoted": 3}
        status = max((s.get("status") or "overseas_active" for s in plist),
                     key=lambda x: status_priority.get(x, 0))

        country = any_snap.get("country") or player_meta.get("country")
        posted_date = player_meta.get("posted_date")

        # Per-prospect hitter/pitcher classification — look at the most
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
            "consensus_fv":    int(round(fv)) if fv is not None else None,
            "consensus_fv_plus": fv_plus,  # v26 — '+' upside flag
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

    # v31.12 — Cohort-normalized Tool+ and RPS+ for the overseas
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
        # — we have ERA/IP in the payload then pitcher.
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

    # v26 — Sort by (FV desc, '+' tiebreaker desc) so 42+ ranks above
    # 42 but below 43. None FVs sink to the bottom of the list.
    prospects.sort(key=lambda p: (p.get("consensus_fv") is None,
                                  -(p.get("consensus_fv") or 0),
                                  -(1 if p.get("consensus_fv_plus") else 0)))

    if n_filtered_promoted or n_filtered_mlb_active:
        log.info("overseas %s: filtered %d MLB-promoted + %d MLB-active "
                 "records from overseas pool",
                 league, n_filtered_promoted, n_filtered_mlb_active)

    return {
        "league":          league,
        "n_prospects":     len(prospects),
        "fv_distribution": dict(fv_dist),
        "league_context":  LEAGUE_CONTEXT.get(league, {}),
        "prospects":       prospects,
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

    leagues = sorted({s["league"] for s in all_snaps if s.get("league")})
    # Order leagues by total prospect count desc so NPB / KBO land first.
    counts = defaultdict(int)
    for s in all_snaps:
        if s.get("league"):
            counts[s["league"]] += 1
    leagues.sort(key=lambda l: -counts[l])

    league_blocks = [_build_league(l, all_snaps, players, stats_by_player,
                                    canonical) for l in leagues]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "leagues":      league_blocks,
    }


def export_overseas_json(out_path: Path) -> int:
    payload = build_overseas_export()
    n = sum(b["n_prospects"] for b in payload["leagues"])
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
