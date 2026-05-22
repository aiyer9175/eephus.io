"""Build the data/draft_timeseries.json export for the Draft section.

Aggregates the parallel draft_* tables into a frontend-friendly JSON:
  {
    "generated_at": ISO timestamp,
    "classes": [
      {
        "year": 2026,
        "is_current": true,
        "stock_plus_mean": <class-median draft stock+>,
        "fv_distribution": {"60": 2, "55": 8, "50": 14, ...},
        "prospects": [
          {
            "player_key": "draft_2026_roch_cholowsky",
            "player_name": "Roch Cholowsky",
            "position": "SS",
            "school": "UCLA",
            "college_commit": null,
            "player_type": "COLh",
            "consensus_fv": 57.5,         // avg of latest snapshot per source
            "consensus_rank": 1.5,        // avg rank, lower is better
            "projected_round": 1,         // derived from consensus_rank
            "draft_stock_plus": 145,      // class-normalized index, 100 = median
            "status": "draft_active",     // 'draft_active' | 'drafted' | 'unsigned'
            "drafted_pick": null,         // populated post-draft
            "drafted_team": null,
            "signing_bonus": null,
            "slot_value": null,
            "milb_key": null,             // populated post-promotion
            "promoted_key": null,
            "points": [
              {
                "snapshot_date": "2026-05-22",
                "source": "espn_draft",
                "rank": 1,
                "fv": 60,
                "draft_stock_plus": 150,
                "tools": {...}
              },
              ...
            ],
            "tool_grades": { /* latest per source, source → tools dict */ }
          },
          ...
        ],
        "draft_order": [    // pre-draft picks + slots, post-draft results
          {"pick_overall": 1, "team": "LAA", "round_label": "1",
           "pick_in_round": 1, "slot_usd": 10570600,
           "bonus_usd": null, "player_key": null, "player_name": null,
           "signed": 0},
          ...
        ],
        "team_pool_usd": {"LAA": 10570600, ...}    // cap totals by org
      },
      ...
    ]
  }

Frontend consumes this through a `data/draft_timeseries.json` sidecar,
separate from `data/timeseries.json` so the MiLB payload stays unchanged.
"""

from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

from player_images import college_logo_url, player_headshot_url
from storage import (
    load_draft_canonical_keys,
    load_draft_lottery_odds,
    load_draft_order,
    load_draft_players,
    load_draft_results,
    load_draft_snapshots,
)

log = logging.getLogger(__name__)


# Draft Stock+ — class-normalized index. 100 = class median rank,
# 130 ≈ +2 sigma toward #1 (so a top-5 pick reads ≥130 in most classes),
# 70 ≈ -2 sigma (toward the back of the class). Lower rank = higher stock.
def _stock_plus(rank: float | None, class_ranks: list[int]) -> int | None:
    if rank is None or not class_ranks:
        return None
    n = len(class_ranks)
    if n < 2:
        return 100
    # Convert rank → percentile (lower rank = higher percentile)
    sorted_ranks = sorted(class_ranks)
    # The player's rank's position from the top.
    # Use a simple inverted-z mapping: percentile from 1.0 (best) to 0.0.
    try:
        # Position of this rank in the sorted list (0 = best)
        pos = sorted_ranks.index(int(rank))
    except ValueError:
        # Interpolate
        pos = sum(1 for r in sorted_ranks if r < rank)
    pct = 1.0 - (pos / max(1, n - 1))
    # Map pct → 70-130 index, with 0.5 → 100 (median)
    return int(round(70 + pct * 60))


def _projected_round(pick: float | None) -> int | None:
    """Map a pick number → round number. Pick 1-30 = R1, 31-60 = R2, etc.
    Accepts either the continuous consensus_rank or the integer
    consensus_pick — same math either way."""
    if pick is None or pick < 1:
        return None
    return min(int((pick - 1) // 30) + 1, 20)


def _latest_per_source(snaps: list[dict]) -> dict[str, dict]:
    """For one player's snapshots, return {source: latest_snapshot}."""
    by_source: dict[str, dict] = {}
    for s in sorted(snaps, key=lambda r: r.get("snapshot_date") or ""):
        by_source[s.get("source")] = s
    return by_source


def _consensus(snaps: list[dict], field: str) -> float | None:
    """Avg of latest non-null `field` per source across this player's snaps."""
    latest = _latest_per_source(snaps)
    vals = [s.get(field) for s in latest.values() if s.get(field) is not None]
    if not vals:
        return None
    try:
        return round(sum(float(v) for v in vals) / len(vals), 2)
    except (TypeError, ValueError):
        return None


def _fv_bucket(fv: float | None) -> str | None:
    if fv is None:
        return None
    if fv >= 70: return "70"
    if fv >= 65: return "65"
    if fv >= 60: return "60"
    if fv >= 55: return "55"
    if fv >= 52.5: return "50+"
    if fv >= 50: return "50"
    if fv >= 47.5: return "45+"
    if fv >= 45: return "45"
    if fv >= 42.5: return "40+"
    if fv >= 40: return "40"
    return "<40"


def _build_class(year: int,
                 all_snaps: list[dict],
                 players_by_key: dict[str, dict],
                 results_by_year: dict[int, list[dict]],
                 order_by_year: dict[int, list[dict]],
                 canonical_keys: dict[str, str],
                 lottery_by_year: dict[int, list[dict]] | None = None) -> dict:
    """Build one draft-class payload."""
    snaps = [s for s in all_snaps if s.get("draft_year") == year]
    by_player: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        by_player[s["player_key"]].append(s)

    # Consensus ranks for the whole class (used by stock+ normalization).
    consensus_ranks: dict[str, float] = {}
    for pk, plist in by_player.items():
        r = _consensus(plist, "rank")
        if r is not None:
            consensus_ranks[pk] = r
    class_rank_list = sorted(int(r) for r in consensus_ranks.values())

    # Per-pick results for this class (by player_key for fast lookup).
    results = results_by_year.get(year) or []
    result_by_player: dict[str, dict] = {r["player_key"]: r
                                          for r in results if r.get("player_key")}

    prospects: list[dict] = []
    fv_dist: dict[str, int] = defaultdict(int)
    stock_plus_values: list[int] = []

    for pk, plist in by_player.items():
        # Take latest per source for tool merge + player info
        latest = _latest_per_source(plist)
        # Pick the most recent FG snapshot for player metadata (height/bats/etc).
        any_snap = sorted(plist, key=lambda r: r.get("snapshot_date") or "")[-1]
        player_meta = players_by_key.get(pk) or {}

        # Snap consensus FV to the nearest integer for display. Keep
        # the raw average around so Draft Stock+ and FV-bucket math can
        # still see fractional resolution.
        fv_raw = _consensus(plist, "fv")
        fv = int(round(fv_raw)) if fv_raw is not None else None
        rank = consensus_ranks.get(pk)
        sp = _stock_plus(rank, class_rank_list)
        if sp is not None:
            stock_plus_values.append(sp)
        # Bucket from the raw value so the 47.5 → "45+" bucket survives
        # even after we round display FV to 48.
        bucket = _fv_bucket(fv_raw)
        if bucket:
            fv_dist[bucket] += 1

        # Per-source tool grades — keep latest only
        tool_grades: dict[str, dict] = {}
        for src, snap in latest.items():
            tools = snap.get("tools") or {}
            if tools:
                tool_grades[src] = tools

        # Build the points timeseries (one entry per source-snapshot).
        points = []
        for snap in sorted(plist, key=lambda r: r.get("snapshot_date") or ""):
            points.append({
                "snapshot_date": snap.get("snapshot_date"),
                "source":        snap.get("source"),
                "interval_label": snap.get("interval_label"),
                "rank":          snap.get("rank"),
                "fv":            snap.get("fv"),
                "tools":         snap.get("tools"),
            })

        # Pick / bonus / slot (post-draft only)
        result = result_by_player.get(pk) or {}
        drafted_pick = result.get("pick_overall")
        drafted_team = result.get("team")
        bonus_usd = result.get("bonus_usd")
        slot_usd = result.get("slot_usd")
        signed = bool(result.get("signed"))

        status = any_snap.get("status") or "draft_active"
        if drafted_pick and status != "drafted":
            status = "drafted"

        prospects.append({
            "player_key":     pk,
            "player_name":    any_snap.get("player_name"),
            "position":       any_snap.get("position") or player_meta.get("position"),
            "school":         any_snap.get("school") or player_meta.get("school"),
            "college_commit": any_snap.get("college_commit") or player_meta.get("college_commit"),
            "player_type":    any_snap.get("player_type") or player_meta.get("player_type"),
            "height":         player_meta.get("height"),
            "weight":         player_meta.get("weight"),
            "bats":           player_meta.get("bats"),
            "throws":         player_meta.get("throws"),
            "fg_player_id":   player_meta.get("fg_player_id"),
            "draft_year":     year,
            "consensus_fv":   fv,                # snapped integer (e.g. 48)
            "consensus_fv_raw": fv_raw,          # raw avg (e.g. 47.5) — for tooltips / analytics
            "consensus_rank": rank,              # raw avg of per-source ranks
            "consensus_pick": None,              # populated post-sort (sequential 1, 2, 3, ...)
            "projected_round": None,             # populated post-sort from consensus_pick
            "draft_stock_plus": sp,
            "headshot_url":   player_headshot_url({
                "mlbam_id":     player_meta.get("mlbam_id"),
                "fg_player_id": player_meta.get("fg_player_id"),
            }),
            "school_logo_url": college_logo_url(any_snap.get("school") or player_meta.get("school")),
            "status":         status,
            "drafted_pick":   drafted_pick,
            "drafted_team":   drafted_team,
            "drafted_round":  result.get("round_label"),
            "drafted_pick_in_round": result.get("pick_in_round"),
            "signing_bonus":  bonus_usd,
            "slot_value":     slot_usd,
            "over_slot_usd":  (bonus_usd - slot_usd) if (bonus_usd and slot_usd) else None,
            "over_slot_pct":  round((bonus_usd / slot_usd - 1.0) * 100, 1) if (bonus_usd and slot_usd) else None,
            "signed":         signed,
            "milb_key":       canonical_keys.get(pk),
            "promoted_key":   player_meta.get("promoted_key"),
            "tool_grades":    tool_grades,
            "points":         points,
        })

    # Sort by continuous consensus_rank ascending, with FV (desc) +
    # player name as deterministic tiebreakers. Then assign sequential
    # consensus_pick = 1, 2, 3, ... so the UI never shows duplicate
    # ranks or gaps. consensus_rank stays as the raw average (visible
    # in tooltips); consensus_pick is what the rendered "rank" reads.
    prospects.sort(key=lambda p: (
        p.get("consensus_rank") is None,
        p.get("consensus_rank") if p.get("consensus_rank") is not None else 9999,
        -(p.get("consensus_fv_raw") or 0),
        p.get("player_name") or "",
    ))
    for i, p in enumerate(prospects, start=1):
        if p.get("consensus_rank") is not None:
            p["consensus_pick"] = i
            p["projected_round"] = _projected_round(i)
        # Else leaves consensus_pick / projected_round as None (unranked).

    # Draft order — pre-draft, this is the pick-by-pick sequence from
    # `draft_order` (slot values only). Post-draft, augment with actual
    # results (drafted player + signing bonus per pick).
    order_rows = order_by_year.get(year) or []
    by_pick_order: dict[int, dict] = {r["pick_overall"]: dict(r) for r in order_rows}
    for r in results:
        pk = r["pick_overall"]
        cur = by_pick_order.setdefault(pk, {})
        cur.update({
            "pick_overall": pk,
            "team":         r.get("team") or cur.get("team"),
            "round_label":  r.get("round_label") or cur.get("round_label"),
            "pick_in_round": r.get("pick_in_round") or cur.get("pick_in_round"),
            "slot_usd":     r.get("slot_usd") or cur.get("slot_usd"),
            "bonus_usd":    r.get("bonus_usd"),
            "player_key":   r.get("player_key"),
            "player_name":  r.get("player_name"),
            "signed":       1 if r.get("signed") else 0,
        })
    order_list = sorted(by_pick_order.values(), key=lambda r: r.get("pick_overall") or 9999)

    # Team pool totals (sum of slot values per team for this class)
    team_pool: dict[str, int] = defaultdict(int)
    team_spend: dict[str, int] = defaultdict(int)
    for row in order_list:
        team = row.get("team")
        if team:
            if row.get("slot_usd"):
                team_pool[team] += int(row["slot_usd"])
            if row.get("bonus_usd"):
                team_spend[team] += int(row["bonus_usd"])

    today = date.today()
    is_current = (year >= today.year)

    # Lottery + projected order — only populated for classes that
    # haven't drafted yet AND for which Tankathon has shipped a
    # projection. Now stores the FULL first-round projection (picks
    # 1-30 + 12 competitive-balance picks at 31-42 with round_label
    # "1A" / "1B"). Picks 7+ have odds_pct=None (deterministic slots).
    # Sort by pick_pos so the consumer renders the natural draft order.
    lottery_rows = (lottery_by_year or {}).get(year) or []
    lottery_odds = sorted(
        ({"team": r["team"], "odds_pct": r.get("odds_pct"),
          "pick_pos": r["pick_pos"],
          "round_label": r.get("round_label") or "1",
          "snapshot_date": r["snapshot_date"]}
         for r in lottery_rows),
        key=lambda r: r["pick_pos"],
    )

    return {
        "year":            year,
        "is_current":      is_current,
        "n_prospects":     len(prospects),
        "stock_plus_mean": round(sum(stock_plus_values) / len(stock_plus_values), 1) if stock_plus_values else None,
        "fv_distribution": dict(fv_dist),
        "prospects":       prospects,
        "draft_order":     order_list,
        "team_pool_usd":   dict(team_pool),
        "team_spend_usd":  dict(team_spend),
        "lottery_odds":    lottery_odds,
    }


def build_draft_export() -> dict:
    """Build the in-memory draft export payload."""
    all_snaps = load_draft_snapshots()
    players = load_draft_players()
    results_all = load_draft_results()
    order_all = load_draft_order()
    canonical = load_draft_canonical_keys()
    lottery_all = load_draft_lottery_odds(latest_only=True)

    results_by_year: dict[int, list[dict]] = defaultdict(list)
    for r in results_all:
        results_by_year[r["draft_year"]].append(r)
    order_by_year: dict[int, list[dict]] = defaultdict(list)
    for r in order_all:
        order_by_year[r["draft_year"]].append(r)
    lottery_by_year: dict[int, list[dict]] = defaultdict(list)
    for r in lottery_all:
        lottery_by_year[r["draft_year"]].append(r)

    # Years come from snapshots ∪ results ∪ order ∪ lottery so a
    # forward-looking lottery year (e.g. 2027 when we only have 2026
    # snapshots) still surfaces as its own class block.
    years = sorted({s["draft_year"] for s in all_snaps} |
                   {r["draft_year"] for r in results_all} |
                   {r["draft_year"] for r in order_all} |
                   {r["draft_year"] for r in lottery_all},
                   reverse=True)

    classes = [_build_class(y, all_snaps, players, results_by_year,
                            order_by_year, canonical, lottery_by_year)
               for y in years]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classes":      classes,
    }


def export_draft_json(out_path: Path) -> int:
    """Build + write the draft JSON. Returns the number of prospects exported."""
    payload = build_draft_export()
    n = sum(c["n_prospects"] for c in payload["classes"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    log.info("draft_export: wrote %d prospects across %d classes → %s",
             n, len(payload["classes"]), out_path)
    return n


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = Path("data/draft_timeseries.json")
    print(export_draft_json(out), "prospects exported")
