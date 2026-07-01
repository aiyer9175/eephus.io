# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

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
import math
import re
import statistics
import unicodedata
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
    load_draft_statlines,
)

log = logging.getLogger(__name__)


# v31.7 - College / amateur stats integration. Each draft prospect
# with FG-side amateur stats (college conference, HS, summer-league
# rows from draft_statlines) gets a `college_stats` summary block on
# their export record: latest season's headline stats + a 2-3 season
# career trail. The summary also drives a SMALL Draft Stock+ boost
# (z-scored against the class cohort) so an outlier college season
# nudges the prospect's DS+ above/below the rank-derived baseline.

# Headline hitter stats surfaced on player cards + detail pages.
# Pick wRC+ first when present (best park-adjusted aggregate); fall
# back to OPS / AVG / OBP for sparse rows.
_COLLEGE_HIT_HEADLINE_KEYS = (
    ("wRC+",  "wrc_plus", "{:.0f}"),
    ("OPS",   "ops",      "{:.3f}"),
    ("AVG",   "avg",      "{:.3f}"),
    ("OBP",   "obp",      "{:.3f}"),
    ("SLG",   "slg",      "{:.3f}"),
    ("HR",    "hr",       "{:.0f}"),
    ("SB",    "sb",       "{:.0f}"),
)
_COLLEGE_PIT_HEADLINE_KEYS = (
    ("ERA",   "era",      "{:.2f}"),
    ("FIP",   "fip",      "{:.2f}"),
    ("K/9",   "k_per_9",  "{:.1f}"),
    ("BB/9",  "bb_per_9", "{:.1f}"),
    ("K%",    "k_pct",    "{:.0%}"),
    ("WHIP",  "whip",     "{:.2f}"),
    ("IP",    "ip",       "{:.1f}"),
)


def _is_pitcher_stat_row(payload: dict) -> bool:
    """A statline carries pitcher fields only when ERA / IP / K/9 are
    set; hitter rows have PA / AVG / wRC+ instead."""
    return any(payload.get(k) is not None for k in ("ip", "era", "k_per_9", "fip"))


def _summarize_college_stats(statlines: list[dict]) -> dict | None:
    """Return a compact summary for one player's college / HS / amateur
    statline list. Picks the most recent season as the headline, then
    keeps up to 3 prior seasons (newest first) for the detail page."""
    if not statlines:
        return None
    # Sort newest first by season.
    rows = sorted(statlines, key=lambda r: -(r.get("season") or 0))
    latest = rows[0]
    payload = latest.get("payload") or {}
    is_pit = _is_pitcher_stat_row(payload)
    headline_keys = _COLLEGE_PIT_HEADLINE_KEYS if is_pit else _COLLEGE_HIT_HEADLINE_KEYS
    # Build headline chip list (label + formatted value), skipping
    # missing values. Cap at 4 chips for the player-card row.
    headline = []
    for label, k, fmt in headline_keys:
        v = payload.get(k)
        if v is None:
            continue
        try:
            formatted = fmt.format(float(v))
        except (TypeError, ValueError):
            formatted = str(v)
        headline.append({"label": label, "value": formatted, "raw": v})
        if len(headline) >= 4:
            break
    # Build the per-season trail (compact). Keep the same shape as
    # what the detail page already renders for overseas players.
    trail = []
    for r in rows[:3]:
        trail.append({
            "season":  r.get("season"),
            "league":  r.get("league"),
            "team":    r.get("team"),
            "payload": r.get("payload") or {},
        })
    return {
        "is_pitcher":     is_pit,
        "latest_season":  latest.get("season"),
        "latest_league":  latest.get("league"),
        "latest_team":    latest.get("team"),
        "headline":       headline,
        "trail":          trail,
        "season_count":   len(rows),
    }


def _college_perf_z(summary: dict | None) -> float | None:
    """Translate a player's college summary into a small z-style boost
    score for Draft Stock+. Uses wRC+ for hitters (anchored at 100,
    each +30 = ~1σ in college samples), ERA- for pitchers (lower =
    better, each -10 = ~1σ; we negate so positive = better). Returns
    None when the headline metric isn't available."""
    if not summary:
        return None
    latest = (summary.get("trail") or [{}])[0]
    payload = latest.get("payload") or {}
    if summary.get("is_pitcher"):
        # Prefer FIP when present (more predictive than ERA at college
        # level due to small samples + variable defense); fall back to
        # ERA. Anchor at 4.00 ERA / FIP ≈ league avg in college.
        v = payload.get("fip") if payload.get("fip") is not None else payload.get("era")
        if v is None:
            return None
        try:
            return round((4.0 - float(v)) / 1.5, 2)   # negative ERA → +z
        except (TypeError, ValueError):
            return None
    else:
        # Hitter - prefer wRC+ then fall back to OPS-anchored.
        wrc = payload.get("wrc_plus")
        if wrc is not None:
            try:
                return round((float(wrc) - 100.0) / 30.0, 2)
            except (TypeError, ValueError):
                return None
        ops = payload.get("ops")
        if ops is not None:
            try:
                return round((float(ops) - 0.850) / 0.150, 2)
            except (TypeError, ValueError):
                return None
        return None


# Draft Stock+ - class-normalized index. 100 = class median rank,
# 130 ≈ +2 sigma toward #1 (so a top-5 pick reads ≥130 in most classes),
# 70 ≈ -2 sigma (toward the back of the class). Lower rank = higher stock.
def _stock_plus(rank: float | None, class_ranks: list[float]) -> int | None:
    if rank is None or not class_ranks:
        return None
    n = len(class_ranks)
    if n < 2:
        return 100
    # Convert rank → percentile (lower rank = higher percentile). Position is
    # the count of strictly-better (lower) consensus ranks, computed on the raw
    # floats so 4.4 and 4.6 stay distinct; an exact tie shares a position.
    sorted_ranks = sorted(class_ranks)
    pos = sum(1 for r in sorted_ranks if r < rank)
    pct = 1.0 - (pos / max(1, n - 1))
    # Map pct → 70-130 index, with 0.5 → 100 (median)
    return int(round(70 + pct * 60))


def _projected_round(pick: float | None) -> int | None:
    """Map a pick number → round number. Pick 1-30 = R1, 31-60 = R2, etc.
    Accepts either the continuous consensus_rank or the integer
    consensus_pick - same math either way."""
    if pick is None or pick < 1:
        return None
    return min(int((pick - 1) // 30) + 1, 20)


def _latest_per_source(snaps: list[dict]) -> dict[str, dict]:
    """For one player's snapshots, return {source: latest_snapshot}."""
    by_source: dict[str, dict] = {}
    for s in sorted(snaps, key=lambda r: r.get("snapshot_date") or ""):
        by_source[s.get("source")] = s
    return by_source


def _load_draft_source_weights() -> dict[str, float]:
    """Accuracy-derived relative draft-FV vote weights, shipped behind the
    backtest gate in data/draft_source_weights.json (draft_source_backtest.py).
    Sources absent from the file vote at 1.0 - ESPN and any new source are never
    punished for lacking resolved draft history. Missing file (the backtest did
    not ship weights, e.g. the sources tested equally accurate) = equal
    weighting everywhere. Mirrors consensus.load_source_weights."""
    p = Path(__file__).parent / "data" / "draft_source_weights.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in (d.get("weights") or {}).items()}
    except (OSError, ValueError):
        return {}


# Loaded once per process; vintage-frozen (changes only when the backtest
# re-ships). Empty = equal weighting (the current, ship=False state).
_DRAFT_SOURCE_WEIGHTS = _load_draft_source_weights()


def _consensus(snaps: list[dict], field: str,
               weights: dict[str, float] | None = None) -> float | None:
    """Mean of latest non-null `field` per source across this player's snaps.
    When `weights` is given, sources vote by their relative weight (default 1.0
    for any source not listed) - an accuracy-weighted mean instead of equal."""
    latest = _latest_per_source(snaps)
    pairs = [(src, s.get(field)) for src, s in latest.items() if s.get(field) is not None]
    if not pairs:
        return None
    try:
        if weights:
            num = sum(weights.get(src, 1.0) * float(v) for src, v in pairs)
            den = sum(weights.get(src, 1.0) for src, _ in pairs)
            return round(num / den, 2) if den else None
        return round(sum(float(v) for _, v in pairs) / len(pairs), 2)
    except (TypeError, ValueError):
        return None


def _consensus_fv_plus(snaps: list[dict]) -> bool:
    """v26 - True if any latest-per-source snap for this player has
    fv_plus=1. Mirrors the consensus.py aggregation rule (the upside
    marker propagates to the consensus when any contributing source
    carried it)."""
    latest = _latest_per_source(snaps)
    return any(bool(s.get("fv_plus")) for s in latest.values())


def _fv_bucket(fv: float | None, fv_plus: bool = False) -> str | None:
    """Map (integer FV, '+' flag) to a display bucket.

    v26 - '+' is a separate flag, not a .5 numeric. Integer 45 with
    fv_plus=True buckets to "45+"; integer 45 without buckets to "45".
    The old `.5`-based bucketing went away with the 40+ → 42.5
    interpolation removal.
    """
    if fv is None:
        return None
    n = int(math.ceil(fv))   # FV rounds UP (55.3 -> 56), consistent with display
    if n >= 70: return "70"
    if n >= 65: return "65"
    if n >= 60: return "60"
    if n >= 55: return "55" + ("+" if fv_plus else "")
    if n >= 50: return "50" + ("+" if fv_plus else "")
    if n >= 45: return "45" + ("+" if fv_plus else "")
    if n >= 40: return "40" + ("+" if fv_plus else "")
    if n >= 35: return "35" + ("+" if fv_plus else "")
    return "<40"


def _name_part(s: str | None) -> str:
    """Lowercased, accent- and punctuation-stripped alpha-only token."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z]", "", s)


_GEN_SUFFIX_RE = re.compile(r"^(jr|sr|ii|iii|iv|v)$")


def _name_first_last(name: str | None) -> tuple[str, str]:
    """Return (first, last) name parts with commas normalized and generational
    suffixes (Jr/Sr/II..V) stripped, so suffix-variant twins bucket together.

    The pipeline's old `parts[-1]` last-name pick put "Robert Hassell III" under
    bucket "iii" and "Robert Hassell" under "hassell" - different buckets, never
    compared - so the same player shipped as two records. Stripping the suffix
    (and unmangling comma forms like "Lonnie, Jr. White") makes both bucket on
    "hassell" / "white" and merge."""
    toks = [t.strip(",.").strip() for t in (name or "").replace(",", " ").split()]
    toks = [t for t in toks if t]
    core = [t for t in toks if not _GEN_SUFFIX_RE.match(_name_part(t))]
    if not core:
        core = toks
    first = _name_part(core[0]) if core else ""
    last = _name_part(core[-1]) if len(core) > 1 else ""
    return first, last


def _edit_distance_le1(a: str, b: str) -> bool:
    """True when a and b differ by at most one insert/delete/substitution.
    Catches spelling variants like Kaeden/Kaden, Issac/Isaac."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:                                   # one substitution
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    short, lng = (a, b) if la < lb else (b, a)     # one insert/delete
    i = j = diff = 0
    while i < len(short) and j < len(lng):
        if short[i] == lng[j]:
            i += 1; j += 1
        else:
            diff += 1; j += 1
            if diff > 1:
                return False
    return True


def _pos_class(pos: str | None) -> str | None:
    head = (pos or "").upper().split("/")[0].strip()
    if head in {"P", "RHP", "LHP", "SP", "RP", "SIRP", "MIRP"}:
        return "P"
    return "H" if head else None


def _canon_player_type(pt: str | None, school: str | None = None,
                       position: str | None = None) -> str | None:
    """Canonicalize player_type to one of COLh / COLp / HSh / HSp.

    Folds the inconsistent casing the sources emit (ColH/Colh/HsP -> COLh/HSp),
    maps JuCo ('JC*') into the COL pool, and backfills the pool/side for rows
    that arrive untyped ('2Way', null) - HS vs college from the school string
    (our school strings tag high schools with an 'HS' token), bat vs arm from
    the position. Keeps Pool / Side filters from silently dropping these rows.
    Returns the original value when neither pool nor side can be resolved."""
    s = (pt or "").strip().lower()
    pool = ("HS" if s.startswith("hs")
            else "COL" if (s.startswith("col") or s.startswith("jc"))
            else None)
    side = ("p" if s.endswith("p") else "h" if s.endswith("h") else None)
    if pool is None and school:
        pool = "HS" if (re.search(r"\bHS\b", school)
                        or re.search(r"high school", school, re.I)) else "COL"
    if side is None and position:
        pc = _pos_class(position)
        side = "p" if pc == "P" else "h" if pc == "H" else None
    return (pool + side) if (pool and side) else (pt or None)


def _same_person(a: dict, b: dict) -> bool:
    """Conservative same-person test for two snapshot reprs {first,last,school,pos}.
    Requires same last name, same (or one-missing) school, COMPATIBLE first name
    (one a prefix of the other -> Chris/Christopher, Cam/Camden; or edit distance
    <=1 -> Kaeden/Kaden), and a COMPATIBLE position class (both hitters / both
    pitchers, or one unknown). The position guard is what keeps two genuinely
    distinct same-school players apart (e.g. Camden Johnson 3B vs Cameron Johnson
    LHP at Oklahoma stay separate)."""
    if not a["last"] or a["last"] != b["last"]:
        return False
    if a["school"] and b["school"] and a["school"] != b["school"]:
        return False
    f1, f2 = a["first"], b["first"]
    if f1 and f2:
        prefix = f1.startswith(f2) or f2.startswith(f1)
        if not (prefix or _edit_distance_le1(f1, f2)):
            return False
    ca, cb = _pos_class(a["pos"]), _pos_class(b["pos"])
    if ca and cb and ca != cb:
        return False
    return True


def _dedupe_merge_map(by_player: dict[str, list[dict]]) -> tuple[dict[str, str], dict[str, str]]:
    """Detect split name-variant duplicates (one real prospect listed under two
    name forms by different sources -> two player_keys) and return:
      merge_map: raw player_key -> canonical player_key (canonical = the variant
                 with the LONGEST display name, i.e. the fuller form)
      name_map:  canonical player_key -> canonical display name.
    Only keys that actually merge appear; everything else is untouched."""
    # One representative per key (latest snapshot's bio fields).
    reps: dict[str, dict] = {}
    for pk, plist in by_player.items():
        last_snap = sorted(plist, key=lambda r: r.get("snapshot_date") or "")[-1]
        name = (last_snap.get("player_name") or "").strip()
        first, last = _name_first_last(name)
        reps[pk] = {
            "name": name,
            "first": first,
            "last": last,
            "school": _name_part(last_snap.get("school")),
            "pos": last_snap.get("position"),
        }
    # Bucket by last name to keep the pairwise scan cheap, union same-person keys.
    parent: dict[str, str] = {pk: pk for pk in by_player}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    by_last: dict[str, list[str]] = defaultdict(list)
    for pk, r in reps.items():
        if r["last"]:
            by_last[r["last"]].append(pk)
    for keys in by_last.values():
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if _same_person(reps[keys[i]], reps[keys[j]]):
                    parent[find(keys[i])] = find(keys[j])
    # Resolve each union -> canonical key (longest display name; tiebreak: the
    # key itself so the result is deterministic).
    groups: dict[str, list[str]] = defaultdict(list)
    for pk in by_player:
        groups[find(pk)].append(pk)
    merge_map: dict[str, str] = {}
    name_map: dict[str, str] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        canon = max(members, key=lambda k: (len(reps[k]["name"]), k))
        name_map[canon] = reps[canon]["name"]
        for k in members:
            merge_map[k] = canon
    return merge_map, name_map


def _build_class(year: int,
                 all_snaps: list[dict],
                 players_by_key: dict[str, dict],
                 results_by_year: dict[int, list[dict]],
                 order_by_year: dict[int, list[dict]],
                 canonical_keys: dict[str, str],
                 lottery_by_year: dict[int, list[dict]] | None = None,
                 college_by_player: dict[str, list[dict]] | None = None) -> dict:
    """Build one draft-class payload."""
    snaps = [s for s in all_snaps if s.get("draft_year") == year]
    # Collapse split name-variant duplicates (e.g. a source calling a prospect
    # "Chris Hacopian" and another "Christopher Hacopian") onto one canonical key
    # so the class lists each real player once with all sources merged.
    _raw_by_player: dict[str, list[dict]] = defaultdict(list)
    for s in snaps:
        _raw_by_player[s["player_key"]].append(s)
    merge_map, dedupe_name = _dedupe_merge_map(_raw_by_player)
    if merge_map:
        log.info("draft %s: merged %d name-variant duplicate key(s)", year,
                 sum(1 for k, v in merge_map.items() if k != v))
    by_player: dict[str, list[dict]] = defaultdict(list)
    for pk, plist in _raw_by_player.items():
        by_player[merge_map.get(pk, pk)].extend(plist)

    # Consensus ranks for the whole class (used by stock+ normalization).
    consensus_ranks: dict[str, float] = {}
    for pk, plist in by_player.items():
        r = _consensus(plist, "rank")
        if r is not None:
            consensus_ranks[pk] = r
    # Keep the consensus ranks as floats. int() truncation collapsed distinct
    # fractional ranks (4.4 and 4.6 both became 4), giving tied prospects an
    # identical DS+; the float list keeps a dense top-of-board separable.
    class_rank_list = sorted(consensus_ranks.values())

    # Per-pick results for this class (by player_key for fast lookup). Remap
    # through merge_map so a pick recorded under a merged twin's key lands on the
    # canonical key the prospect now lives under; when both halves carry a row,
    # the one with an actual pick wins (the orphan twin's row is pick-less).
    results = results_by_year.get(year) or []
    result_by_player: dict[str, dict] = {}
    for r in results:
        pk = r.get("player_key")
        if not pk:
            continue
        ck = merge_map.get(pk, pk)
        cur = result_by_player.get(ck)
        if cur is None or (r.get("pick_overall") and not cur.get("pick_overall")):
            result_by_player[ck] = r

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
        # Accuracy-weighted across sources when the backtest shipped weights;
        # equal mean otherwise (the current, ship=False state). Rank stays
        # unweighted - vote weights are a FV-accuracy result, not a rank one.
        fv_raw = _consensus(plist, "fv", weights=_DRAFT_SOURCE_WEIGHTS)
        fv = int(math.ceil(fv_raw)) if fv_raw is not None else None   # FV rounds UP (62.1 -> 63)
        # v26 - '+' upside flag: True if any source published "55+" etc.
        fv_plus = _consensus_fv_plus(plist)
        rank = consensus_ranks.get(pk)
        sp = _stock_plus(rank, class_rank_list)
        if sp is not None:
            stock_plus_values.append(sp)
        # Bucket from integer FV + the '+' flag (v26 - no more .5 inflation).
        bucket = _fv_bucket(fv, fv_plus)
        if bucket:
            fv_dist[bucket] += 1

        # Per-source tool grades - keep latest only
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
                "fv_plus":       bool(snap.get("fv_plus")),
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

        # v31.7 - College stats summary + Draft Stock+ boost.
        # The college signal nudges DS+ by ±6 (clamped) so it stays
        # secondary to the rank-derived baseline but visible enough
        # to push an outlier hitter / arm up or down a few slots.
        cstats_rows = (college_by_player or {}).get(pk) or []
        cstats_summary = _summarize_college_stats(cstats_rows)
        cperf_z = _college_perf_z(cstats_summary)
        sp_boosted = sp
        if sp is not None and cperf_z is not None:
            # Cap the boost at ±6 pts so DS+ retains its rank-driven
            # character (rank is the primary signal - college is a
            # secondary confidence layer).
            boost = max(-6, min(6, round(cperf_z * 3.0)))
            sp_boosted = max(60, min(140, sp + boost))
        _pos_val = any_snap.get("position") or player_meta.get("position")
        # Prefer a school string carrying the HS state tag "(XX)". MLB
        # Pipeline supplies it for high-schoolers across all draft years,
        # while older FanGraphs boards omit it and the latest-dated snapshot
        # (any_snap) is often the FG one. Preferring the state-tagged school
        # backfills home-state coverage for the HS Details geography section
        # on older classes (and sharpens HS-vs-college typing below). College
        # schools carry no "(XX)" tag, so they are unaffected.
        _state_school = None
        for _src in ("mlb_pipeline_draft", "espn_draft"):
            _state_school = next((sn.get("school") for sn in plist
                                  if sn.get("source") == _src and sn.get("school")
                                  and re.search(r"\([A-Z]{2}\)\s*$", sn["school"])), None)
            if _state_school:
                break
        if not _state_school:
            _state_school = next((sn.get("school") for sn in plist
                                  if sn.get("school")
                                  and re.search(r"\([A-Z]{2}\)\s*$", sn["school"])), None)
        # Deep-tail fallback: the MLB Stats API draft tracker (draft_results.
        # school) carries every drafted player's HS + state, beyond MLB
        # Pipeline's ~200-row boards, so the long tail of older-class HS
        # draftees still gets a home state. Only used when no snapshot did.
        if not _state_school:
            _rs = result.get("school")
            if _rs and re.search(r"\([A-Z]{2}\)\s*$", _rs):
                _state_school = _rs
        _school_val = _state_school or any_snap.get("school") or player_meta.get("school")
        prospects.append({
            "player_key":     pk,
            "player_name":    dedupe_name.get(pk) or any_snap.get("player_name"),
            "position":       _pos_val,
            "school":         _school_val,
            "college_commit": any_snap.get("college_commit") or player_meta.get("college_commit"),
            "player_type":    _canon_player_type(
                                  any_snap.get("player_type") or player_meta.get("player_type"),
                                  _school_val, _pos_val),
            "height":         player_meta.get("height"),
            "weight":         player_meta.get("weight"),
            "bats":           player_meta.get("bats"),
            "throws":         player_meta.get("throws"),
            "fg_player_id":   player_meta.get("fg_player_id"),
            "draft_year":     year,
            "consensus_fv":   fv,                # snapped integer (e.g. 48)
            "consensus_fv_raw": fv_raw, # raw avg (e.g. 47.5) - for tooltips / analytics
            "consensus_fv_plus": fv_plus, # v26 - '+' upside flag
            "consensus_rank": rank,              # raw avg of per-source ranks
            "consensus_pick": None,              # populated post-sort (sequential 1, 2, 3, ...)
            "projected_round": None,             # populated post-sort from consensus_pick
            "draft_stock_plus": sp_boosted,
            "draft_stock_plus_pre_college": sp,
            "draft_stock_plus_college_boost": (sp_boosted - sp) if (sp is not None and sp_boosted is not None) else None,
            "college_stats":  cstats_summary,
            "headshot_url":   player_headshot_url({
                "mlbam_id":     player_meta.get("mlbam_id"),
                "fg_player_id": player_meta.get("fg_player_id"),
            }),
            "school_logo_url": college_logo_url(_school_val),
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

    # v31.12 - Cohort-normalized Tool+ and RPS+ for the draft class.
    # Both surface in the front-end tiebreaker so two prospects with
    # the same FV (e.g. two 50-FV college hitters) can be separated on
    # underlying tool quality + performance.
    #
    # Tool+ = class-normalized average of per-source tool composites.
    # Each prospect's "composite" is the mean of their numeric tool
    # grades (skipping the `_extras` metadata sub-dict). Players with
    # no tool data on file get `tool_plus = None`.
    #
    # RPS+ = 100 + 15*cperf_z (already a z-score from college perf).
    # Clipped to [60, 140] so an outlier season doesn't dominate.
    def _draft_tool_composite(tg: dict) -> float | None:
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
    raw_tool_comps: list[float] = []
    for p in prospects:
        tc = _draft_tool_composite(p.get("tool_grades"))
        p["_tool_composite_raw"] = tc
        if tc is not None:
            raw_tool_comps.append(tc)
    if len(raw_tool_comps) >= 5:
        _tmean = sum(raw_tool_comps) / len(raw_tool_comps)
        _tvar = sum((x - _tmean) ** 2 for x in raw_tool_comps) / len(raw_tool_comps)
        _tstd = _tvar ** 0.5 if _tvar > 0 else 1.0
        for p in prospects:
            tc = p.get("_tool_composite_raw")
            if tc is None:
                p["tool_plus"] = None
            else:
                z = (tc - _tmean) / _tstd
                p["tool_plus"] = max(60, min(140, int(round(100 + 15 * z))))
    else:
        for p in prospects:
            p["tool_plus"] = None
    for p in prospects:
        p.pop("_tool_composite_raw", None)
        cstats = p.get("college_stats")
        cperf_z_p = _college_perf_z(cstats) if cstats else None
        if cperf_z_p is None:
            p["rps_plus"] = None
        else:
            p["rps_plus"] = max(60, min(140, int(round(100 + 15 * cperf_z_p))))

    # Sort by continuous consensus_rank ascending, with FV (desc) +
    # player name as deterministic tiebreakers. Then assign sequential
    # consensus_pick = 1, 2, 3, ... so the UI never shows duplicate
    # ranks or gaps. consensus_rank stays as the raw average (visible
    # in tooltips); consensus_pick is what the rendered "rank" reads.
    prospects.sort(key=lambda p: (
        p.get("consensus_rank") is None,
        p.get("consensus_rank") if p.get("consensus_rank") is not None else 9999,
        -(p.get("consensus_fv_raw") or 0),
        # v26 - '+' tiebreaker: 42+ ranks above 42 when raw FVs tie.
        -(1 if p.get("consensus_fv_plus") else 0),
        p.get("player_name") or "",
    ))
    for i, p in enumerate(prospects, start=1):
        if p.get("consensus_rank") is not None:
            p["consensus_pick"] = i
            p["projected_round"] = _projected_round(i)
        # Else leaves consensus_pick / projected_round as None (unranked).

    # Draft order - pre-draft, this is the pick-by-pick sequence from
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

    # Lottery + projected order - only populated for classes that
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


# Pick buckets for the empirical "expected value by draft slot" curve. Picks
# are noisy, so we bucket and take the MEDIAN realized FV within each band; a
# player's overperformance is their realized FV minus their bucket's median.
_OVERPERF_PICK_BUCKETS = [(1, 5), (6, 10), (11, 20), (21, 40),
                          (41, 75), (76, 150), (151, 10 ** 9)]


def _attach_overperformance(classes: list[dict]) -> None:
    """Bake draft-overperformance fields onto each COMPLETED class's drafted
    prospects, in place. For every drafted pick we resolve the player's CURRENT
    value (latest prospect FV via promoted/milb key, plus career WAR where they
    reached MLB) from the main timeseries + debuts payloads, then compare it to
    the empirical median FV for that pick band:

        current_fv, career_war, expected_fv_for_pick, overperf_fv

    The frontend Overperformers leaderboard sorts on overperf_fv ("realized
    outcome"); the "draft-day value" lens needs no baked field (it uses the
    already-present consensus_pick vs drafted_pick). Players we can't resolve to
    a board record fall back to their own consensus_fv (draft-time grade)."""
    val: dict[str, dict] = {}   # player_key -> {"fv":..., "war":...}

    def _ingest(path: str) -> None:
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        rows = d.get("players") if isinstance(d, dict) else d
        for p in (rows or []):
            k = p.get("player_key")
            if not k:
                continue
            war = (p.get("career_war") or {}).get("career_war")
            val[k] = {"fv": p.get("fv_close"), "war": war}

    _ingest("data/timeseries.json")
    _ingest("data/debuts.json")

    pooled: list[tuple[int, float]] = []   # (drafted_pick, current_fv)
    for cls in classes:
        if cls.get("is_current"):
            continue
        for p in cls.get("prospects", []):
            pick = p.get("drafted_pick")
            if not pick:
                continue
            cand = None
            for kk in (p.get("promoted_key"), p.get("milb_key"), p.get("player_key")):
                if kk and kk in val:
                    cand = val[kk]
                    break
            cur_fv = (cand or {}).get("fv")
            if cur_fv is None:
                cur_fv = p.get("consensus_fv")   # fall back to draft-time grade
            p["current_fv"] = cur_fv
            p["career_war"] = (cand or {}).get("war")
            if cur_fv is not None:
                pooled.append((int(pick), float(cur_fv)))

    bucket_med: dict[tuple[int, int], float] = {}
    for lo, hi in _OVERPERF_PICK_BUCKETS:
        vals = [fv for pk, fv in pooled if lo <= pk <= hi]
        if vals:
            bucket_med[(lo, hi)] = statistics.median(vals)

    def _expected(pick: int) -> float | None:
        for (lo, hi), m in bucket_med.items():
            if lo <= pick <= hi:
                return m
        return None

    for cls in classes:
        if cls.get("is_current"):
            continue
        for p in cls.get("prospects", []):
            pick, cur = p.get("drafted_pick"), p.get("current_fv")
            if not pick or cur is None:
                continue
            exp = _expected(int(pick))
            if exp is None:
                continue
            p["expected_fv_for_pick"] = round(exp, 1)
            p["overperf_fv"] = round(float(cur) - exp, 1)


def build_draft_export() -> dict:
    """Build the in-memory draft export payload."""
    all_snaps = load_draft_snapshots()
    players = load_draft_players()
    results_all = load_draft_results()
    order_all = load_draft_order()
    canonical = load_draft_canonical_keys()
    lottery_all = load_draft_lottery_odds(latest_only=True)
    # v31.7 - College / amateur statlines, grouped by player_key.
    # Populated only for prospects with an fg_player_id who had at
    # least one parsed amateur row (see draft_stats.refresh_draft_stats).
    college_all = load_draft_statlines()
    college_by_player: dict[str, list[dict]] = defaultdict(list)
    for r in college_all:
        pk = r.get("player_key")
        if pk:
            college_by_player[pk].append(r)

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
                            order_by_year, canonical, lottery_by_year,
                            college_by_player=college_by_player)
               for y in years]

    # Draft-overperformance fields (realized FV vs expected-for-pick) for the
    # Overperformers leaderboard.
    _attach_overperformance(classes)

    # Tendency-driven mock draft for the current pre-draft class. Build the
    # three draft tendency panels FRESH from the DB here (rather than reading the
    # org_tendencies.json sidecar, which the pipeline regenerates AFTER this
    # export, so the file would always be one generation stale and absent on a
    # first-ever run). attach_mock_draft falls back to the sidecar, then to pure
    # best-player-available, if this fresh build is unavailable.
    try:
        import storage
        from org_tendencies import draft_panels
        with storage.connect() as con:
            _dpos, _dtraits, _dslot = draft_panels(con)
        _tendencies = {"draftPos": _dpos, "draftTraits": _dtraits, "slot": _dslot}
    except Exception:
        log.exception("mock_draft: fresh tendency build failed - "
                      "falling back to the org_tendencies.json sidecar")
        _tendencies = None
    try:
        from mock_draft import attach_mock_draft
        attach_mock_draft(classes, _tendencies)
    except Exception:
        log.exception("mock_draft attach crashed - continuing without it")

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
    log.info("draft_export: wrote %d prospects across %d classes -> %s",
             n, len(payload["classes"]), out_path)
    return n


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = Path("data/draft_timeseries.json")
    print(export_draft_json(out), "prospects exported")
