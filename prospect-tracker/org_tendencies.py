# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Organization Tendencies — per-org behavioral profiles for the PROSPX
farm detail pages (data/org_tendencies.json).

Eight panels, every number LEAGUE-RELATIVE (each org's value next to the
league mean/sd so the UI can draw z-bars and the labels can't drift from
the data that earned them):

  promotion    aggressive vs conservative: how young-for-level the org
               runs its prospects (age_vs_level) + promotions per active
               prospect over the trailing year (level_changes). Its label
               reads promotionTiming.labelAggr, so the two never disagree.
  promotionTiming  debut timing against the rookie-status cutoff and the
               service-year line, median debut age and age for level, each
               with n and CI95; labels only on a tested difference (BH q <
               0.10 across the 30 orgs). Display only: the ETA does not use it.
  draftPos     what the org drafts: pitcher share, prep share,
               up-the-middle share of signed picks (2021-present).
  draftTraits  WHO the org drafts: mean FG tool profile of its signed
               draftees vs the league draftee mean (power-over-hit,
               speed/athleticism, command-over-stuff...).
  arsenal      pitch-shape identity of the CURRENT pitching inventory:
               per-pitch-type usage vs league, fastball velocity. v1 is a
               PROFILE, not a conversion ledger — per-pitch usage history
               isn't stored, so "turns four-seamers into sinkers" claims
               wait for arsenal snapshots (documented fork).
  toolDev      what the org actually DEVELOPS: per-tool future-grade
               drift per prospect-year in org, from same-source snapshot
               pairs (2017-present grade history), minus the league mean.
               Includes pitch tools (fb/sl/cb/ch/cmd) — the honest version
               of "best at developing sliders". Plus the SC+ (Statcast
               composite) drift over the platform's metric history
               (early window, disclosed).
  ifa          quality vs quantity: bonus-pool concentration (top-signing
               share, HHI), seven-figure signings, volume per class.
  trades       trade-happy vs reluctant (volume z), prospect-capital
               direction (acquirer vs shipper), quality-vs-depth of
               acquired prospects (graded near trade date), cash-
               consideration involvement (parsed from MLB tx descriptions).
  health/slot  two extras: IL burden per active prospect, and draft-pool
               allocation style (over-slot rate; round-1 underslot
               cut-deals that spread pool money later).

Read-only consumer of the DB + committed sidecars (same contract as the
FA module): never writes prospect data. Wired into run_monthly after the
exports; safe to run standalone: python org_tendencies.py
"""

from __future__ import annotations

import csv
import json
import logging
import math
import re
import statistics
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import storage
from trades import canonical_org

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "org_tendencies.json"

DRAFT_FIRST_YEAR = 2021
TRADE_FIRST_DATE = "2022-01-01"
# Owner answer M8-3 (2026-09-25): the trade profile counts the MLB transaction feed
# plus board-inferred org changes, after an A -> B -> A round-trip filter. A move and
# its reverse for the same player within this many days is read as two sources
# disagreeing on his org, not two trades (see trade_moves).
ROUND_TRIP_DAYS = 90
HIT_TOOLS = ("hit", "game_pwr", "raw_pwr", "speed", "field", "pitch_sel", "bat_ctrl")
PIT_TOOLS = ("fb", "sl", "cb", "ch", "cmd")
UP_MIDDLE = {"C", "SS", "CF", "2B"}
DRAFT_BUCKETS = ("P", "C", "MI", "CI", "OF")   # position-split order for the draft panel
MIN_PAIR_DAYS = 60          # same-source snapshot pairs must span at least this
MIN_TOOL_PAIRS = 6          # org-tool cells below this report null, never noise

AAA_CACHE = Path(__file__).parent / ".cache" / "aaa_pitches"
# Pitch-type codes we trust from the Savant minors feed; everything else
# (blank, PO pitchout, UN unknown, position-player junk) is dropped.
AAA_KEEP_PT = {"FF", "SI", "FC", "FT", "SL", "ST", "SW", "CU", "KC", "CS",
               "SV", "CH", "FS", "FO", "SC", "EP", "KN"}
# Canonical display order for pitch types, shared with the frontend table.
PITCH_ORDER = ("FF", "SI", "FC", "FT", "SL", "ST", "SW", "CU", "KC", "CS",
               "SV", "CH", "FS", "FO", "SC", "EP", "KN")
# Hard (fastball-family) codes whose mean velo defines the org "fb velo" line.
HARD_PT = {"FF", "SI", "FC", "FT"}


def _z(v, mean, sd):
    if v is None or mean is None or not sd:
        return None
    return round((v - mean) / sd, 2)


def _league_stats(values: dict[str, float | None]) -> dict:
    vals = [v for v in values.values() if v is not None]
    if len(vals) < 8:
        return {"mean": None, "sd": None}
    return {"mean": round(statistics.mean(vals), 4),
            "sd": round(statistics.pstdev(vals), 4) or None}


def _label(z, hi: str, lo: str, mid: str = "typical", cut: float = 0.5) -> str | None:
    if z is None:
        return None
    if z >= cut:
        return hi
    if z <= -cut:
        return lo
    return mid


# ============================================================================
# Inputs
# ============================================================================

def _timeseries_players() -> list[dict]:
    try:
        return json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8"))["players"]
    except (OSError, ValueError, KeyError):
        log.warning("org_tendencies: timeseries.json unavailable")
        return []


def _actives_by_org(players) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for p in players:
        if p.get("status") == "active" and p.get("org"):
            out[p["org"]].append(p)
    return dict(out)


def _load_debuts() -> list[dict]:
    """Graduated players (data/debuts.json) — the org-attributed record of who
    each club developed. Loaded once and threaded into the panels that need it."""
    try:
        d = json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8"))
        return d if isinstance(d, list) else (d.get("players") or [])
    except (OSError, ValueError):
        log.warning("org_tendencies: debuts.json unavailable")
        return []


def _pos_bucket(pos: str | None) -> str | None:
    """Coarse fielding bucket for draft/debut splits: P / C / MI / CI / OF.
    (Distinct from UP_MIDDLE, which lumps C+CF for the up-the-middle share.)"""
    head = (pos or "").upper().split("/")[0].strip()
    if head in ("P", "SP", "RP", "RHP", "LHP", "SP2"):
        return "P"
    if head == "C":
        return "C"
    if head in ("SS", "2B"):
        return "MI"
    if head in ("1B", "3B"):
        return "CI"
    if head in ("OF", "CF", "LF", "RF"):
        return "OF"
    return None


def _mlbam_org_map(players: list[dict], debuts: list[dict]) -> dict[int, str]:
    """{mlbam_id: developing org} — actives win, debuts (graduates) fill the
    rest. Used to attribute AAA pitch CSVs to an org."""
    out: dict[int, str] = {}
    for p in players:
        mid, org = p.get("mlbam_id"), p.get("org")
        if mid and org:
            out.setdefault(int(mid), org)
    for d in debuts:
        mid, org = d.get("mlbam_id"), d.get("org")
        if mid and org:
            out.setdefault(int(mid), org)
    return out


def _aaa_iter(mlbam_org: dict[int, str]):
    """Yield (org, mlbam, rows) for each ATTRIBUTABLE AAA pitcher, latest
    season only. Restricting to mlbams we can map to an org keeps the read to
    ~1s instead of scanning all ~2,200 cached CSVs. Resilient to a missing
    cache dir and to empty/malformed files."""
    if not AAA_CACHE.is_dir():
        return
    latest: dict[int, tuple[int, Path]] = {}
    for path in AAA_CACHE.glob("*.csv"):
        mid_s, _, season_s = path.stem.rpartition("_")
        try:
            mid, season = int(mid_s), int(season_s)
        except ValueError:
            continue
        if mid not in mlbam_org:
            continue
        if mid not in latest or season > latest[mid][0]:
            latest[mid] = (season, path)
    for mid, (_season, path) in latest.items():
        try:
            with path.open(encoding="utf-8", newline="") as fh:
                rows = [r for r in csv.DictReader(fh)
                        if (r.get("pitch_type") or "").strip() in AAA_KEEP_PT]
        except (OSError, csv.Error):
            continue
        if rows:
            yield mlbam_org[mid], mid, rows


def _aaa_usage_by_arm(mlbam_org: dict[int, str],
                      exclude: set[int] | None = None) -> dict[str, list[dict[str, float]]]:
    """Per-org list of one usage-fraction dict per AAA arm: {pitch_type: share}.
    Averaging across arms (not pooling raw pitches) keeps a 2,000-pitch starter
    from drowning out a 200-pitch reliever — the same 'average arm's mix'
    footing the MLB usage_pct already uses. `exclude` skips mlbams already
    counted on the MLB-graduate side so a grad isn't double-weighted."""
    skip = exclude or set()
    out: dict[str, list[dict[str, float]]] = defaultdict(list)
    for org, mid, rows in _aaa_iter(mlbam_org):
        if mid in skip:
            continue
        counts: dict[str, int] = defaultdict(int)
        for r in rows:
            counts[(r.get("pitch_type") or "").strip()] += 1
        tot = sum(counts.values())
        if tot < 30:           # too few tracked pitches to trust a mix
            continue
        out[org].append({pt: c / tot for pt, c in counts.items()})
    return dict(out)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ============================================================================
# Panel 1 — promotion aggressiveness
# ============================================================================

def _debut_age(rec: dict) -> float | None:
    """Age (years) at MLB debut from debut_date − birth_date."""
    try:
        d0 = date.fromisoformat(str(rec["birth_date"])[:10])
        d1 = date.fromisoformat(str(rec["debut_date"])[:10])
    except (KeyError, TypeError, ValueError):
        return None
    yrs = (d1 - d0).days / 365.25
    return yrs if 16 <= yrs <= 40 else None       # guard junk dates


def promotion_panel(by_org: dict[str, list[dict]], debuts: list[dict], today: date) -> dict:
    cutoff = (today - timedelta(days=365)).isoformat()
    # Mean debut age per org, split pitchers vs hitters (graduates).
    debut_pit: dict[str, list] = defaultdict(list)
    debut_hit: dict[str, list] = defaultdict(list)
    for d in debuts:
        org = d.get("org")
        age = _debut_age(d)
        if not org or age is None:
            continue
        (debut_pit if _is_pitcher_pos(d.get("position")) else debut_hit)[org].append(age)
    raw = {}
    for org, roster in by_org.items():
        diffs = [(p.get("age_vs_level") or {}).get("diff") for p in roster]
        diffs = [d for d in diffs if d is not None]
        promos = sum(1 for p in roster for lc in (p.get("level_changes") or [])
                     if lc.get("kind") == "promotion" and (lc.get("date") or "") >= cutoff)
        raw[org] = {
            "avlDiff": round(statistics.mean(diffs), 2) if diffs else None,
            "promoRate": round(promos / len(roster), 2) if roster else None,
            "n": len(roster),
            "debutAgePit": round(statistics.mean(debut_pit[org]), 1) if len(debut_pit[org]) >= 3 else None,
            "debutAgeHit": round(statistics.mean(debut_hit[org]), 1) if len(debut_hit[org]) >= 3 else None,
            "nDebutPit": len(debut_pit[org]),
            "nDebutHit": len(debut_hit[org]),
        }
    lg_avl = _league_stats({o: r["avlDiff"] for o, r in raw.items()})
    lg_pr = _league_stats({o: r["promoRate"] for o, r in raw.items()})
    lg_dap = _league_stats({o: r["debutAgePit"] for o, r in raw.items()})
    lg_dah = _league_stats({o: r["debutAgeHit"] for o, r in raw.items()})
    for r in raw.values():
        z_young = _z(r["avlDiff"], lg_avl["mean"], lg_avl["sd"])
        z_promo = _z(r["promoRate"], lg_pr["mean"], lg_pr["sd"])
        # Aggressive = young-for-level (negative avl z) AND promotes often.
        score = None
        if z_young is not None or z_promo is not None:
            parts = [v for v in (-(z_young or 0), z_promo or 0)
                     if z_young is not None or z_promo is not None]
            score = round(sum(parts) / 2, 2)
        r["zYoung"] = z_young
        r["zPromo"] = z_promo
        # Younger debut age is the "aggressive" direction, so negate the z.
        r["zDebutAgePit"] = _z(r["debutAgePit"], lg_dap["mean"], lg_dap["sd"])
        r["zDebutAgeHit"] = _z(r["debutAgeHit"], lg_dah["mean"], lg_dah["sd"])
        r["score"] = score
        r["label"] = _label(score, "aggressive", "conservative")
    return {"orgs": raw, "league": {"avlDiff": lg_avl, "promoRate": lg_pr,
                                    "debutAgePit": lg_dap, "debutAgeHit": lg_dah}}


# ============================================================================
# Panel 1b - promotion timing (rookie cutoff, service-year window, age for level)
# ============================================================================
#
# Display only. The 2026-09-25 roster-aware ETA lane (etaroster RESULT.md) found
# that none of these figures moves the served ETA once level, age and 40-man
# status are known, so no surface may say the ETA uses them. One rule era: MLB
# debuts since 2022 under the current rookie rule (September days count since
# 2020; 2020 and 2021 sit out). A label fires only when the org is n-sufficient,
# its Benjamini-Hochberg q across the 30 orgs is under PT_Q_MAX and its CI95
# excludes the league value; today that is age for level alone.

PT_FIRST_SEASON = 2022
PT_AGGR_FIRST_SEASON = 2023
PT_MIN_DEBUTS = 20            # fewer debuts than this is thin: no timing label
PT_MIN_AGGR_PLAYERS = 40      # fewer players than this: no age-for-level label
PT_Q_MAX = 0.10
PT_ROOKIE_DAYS = 45           # MLB glossary, Rookie Eligibility
PT_SERVICE_YEAR_DAYS = 172    # MLB glossary, Service Time
PT_SVC_WINDOW = (15, 45)      # days after Opening Day: just past the full-year line
PT_PRE2020_CUTOFF = "07-18"   # 45 counted days before September 1 under the old rule
PT_FULL_SLATE = 7             # games on a date that opens or closes a season
PT_TX_WINDOW_DAYS = 5         # a debut's org is the club he joined in the 5 days before
PT_CACHE = Path(__file__).parent / ".cache" / "promotion_timing"
PT_TX_DIR = Path(__file__).parent / ".cache" / "mlb_transactions"
PT_GAME_DATES = Path(__file__).parent / ".cache" / "mgmt_game_dates.json"
PT_STATSAPI = "https://statsapi.mlb.com/api/v1"
PT_RULE_TEXT = ("Rookie status ends past 130 AB, 50 IP or 45 active-roster days (IL excluded). "
                "Since 2020 September counts, so a first call-up on or after the cutoff keeps "
                "rookie status for next season. The cutoff is 45 days before the final scheduled "
                "game (July 18 before 2020). One service year is 172 days, so a call-up more than "
                "15 days after Opening Day cannot bank a full year that season.")
PT_SOURCES = [
    {"label": "MLB glossary: Rookie Eligibility", "url": "https://www.mlb.com/glossary/rules/rookie-eligibility"},
    {"label": "MLB glossary: Service Time", "url": "https://www.mlb.com/glossary/transactions/service-time"},
    {"label": "Baseball America, 2024-08-28",
     "url": "https://www.baseballamerica.com/stories/explaining-mlb-rookie-eligibility-ppi-callup-target-date-and-september-roster-rules/"},
]


def _pt_fetch_json(url: str, path: Path, max_age_days: float | None):
    """Read a cached StatsAPI document, refetching when it is older than
    max_age_days (None = never refetch). A failed fetch keeps the stale copy;
    no copy and no network returns None."""
    import time
    import urllib.request
    fresh = path.exists() and (max_age_days is None
                               or time.time() - path.stat().st_mtime < max_age_days * 86400)
    if not fresh:
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                doc = json.load(resp)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
            return doc
        except (OSError, ValueError) as exc:
            log.warning("promotion timing: fetch failed for %s (%s)", url, exc)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pt_season_dates(seasons, today: date) -> dict[int, dict]:
    """{season: {"open": date, "final": date}}. A finished season reads the
    StatsAPI play corpus: the first and last dates with a full slate, so a lone
    overseas opener or a makeup game after the scheduled finale moves neither
    (2024: the final scheduled game is Sep 29, the makeup on Sep 30 is not).
    A season the corpus has not finished reads the StatsAPI season calendar."""
    by: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    try:
        for iso in json.loads(PT_GAME_DATES.read_text(encoding="utf-8")).values():
            s = str(iso or "")[:10]
            if len(s) == 10 and s[:4].isdigit():
                by[int(s[:4])][s] += 1
    except (OSError, ValueError):
        log.warning("promotion timing: %s unavailable", PT_GAME_DATES.name)
    cal_doc = _pt_fetch_json(f"{PT_STATSAPI}/seasons/all?sportId=1", PT_CACHE / "seasons.json", 7)
    cal = {}
    for s in (cal_doc or {}).get("seasons") or []:
        try:
            cal[int(s["seasonId"])] = (date.fromisoformat(s["regularSeasonStartDate"]),
                                       date.fromisoformat(s["regularSeasonEndDate"]))
        except (KeyError, TypeError, ValueError):
            continue
    out = {}
    for y in seasons:
        full = sorted(d for d, n in by.get(y, {}).items() if n >= PT_FULL_SLATE)
        c_open = date.fromisoformat(full[0]) if full else None
        c_final = date.fromisoformat(full[-1]) if full else None
        if y in cal:
            done = c_final is not None and c_final >= cal[y][1] - timedelta(days=3)
            out[y] = {"open": c_open or cal[y][0], "final": c_final if done else cal[y][1]}
        elif c_final is not None and (y < today.year or c_final >= date(y, 9, 24)):
            out[y] = {"open": c_open, "final": c_final}
    return out


def pt_rookie_cutoff(season: int, final: date | None) -> date | None:
    """The first call-up date that keeps rookie status for next season: 45 days
    before the final scheduled game, counting both days, since 2020; July 18
    (45 counted days before September 1) before 2020."""
    if season < 2020:
        return date(season, 7, 18)
    return final - timedelta(days=PT_ROOKIE_DAYS - 1) if final else None


def _pt_people(seasons, today: date) -> dict[int, tuple[str, str | None]]:
    """{mlbam: (debut_iso, birth_iso)} for players whose MLB debut falls in
    `seasons`, from the StatsAPI season player lists (cached per season; a
    finished season is fetched once, the current one again after 7 days)."""
    out: dict[int, tuple[str, str | None]] = {}
    for y in seasons:
        doc = _pt_fetch_json(
            f"{PT_STATSAPI}/sports/1/players?season={y}&fields=people,id,mlbDebutDate,birthDate",
            PT_CACHE / f"players_{y}.json", 7 if y >= today.year else None)
        for p in (doc or {}).get("people") or []:
            d = str(p.get("mlbDebutDate") or "")
            if d[:4].isdigit() and int(d[:4]) in seasons and p.get("id"):
                out[int(p["id"])] = (d[:10], p.get("birthDate"))
    return out


def _pt_debut_org_lookup(seasons) -> tuple[dict, dict]:
    """(transactions by mlbam -> [(date, org)], war_seasons team by (mlbam, year)).
    The debut org is the MLB club he joined in the PT_TX_WINDOW_DAYS before his
    debut (the transaction log), else his war_seasons club that year."""
    import gzip
    from trades import canonical_org_from_id
    tx: dict[int, list] = defaultdict(list)
    for y in sorted(seasons):
        for m in range(1, 13):
            path = PT_TX_DIR / f"tx_{y}_{m:02d}.json.gz"
            if not path.exists():
                continue
            try:
                with gzip.open(path, "rt", encoding="utf-8") as fh:
                    rows = json.load(fh).get("transactions") or []
            except (OSError, ValueError):
                continue
            for t in rows:
                pid = (t.get("person") or {}).get("id")
                tid = (t.get("toTeam") or {}).get("id")
                org = canonical_org_from_id(tid) if tid else None
                if pid and org:
                    tx[int(pid)].append(((t.get("date") or "")[:10], org))
    wtm: dict[tuple[int, int], str] = {}
    try:
        W = json.loads((DATA_DIR / "war_seasons.json").read_text(encoding="utf-8"))
        tms = W.get("tm") or []
        for pid, rec in (W.get("players") or {}).items():
            for s in rec[1]:
                if s[0] in seasons and s[9] is not None and (int(pid), s[0]) not in wtm:
                    wtm[(int(pid), s[0])] = canonical_org(tms[s[9]].split("/")[0])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        log.warning("promotion timing: war_seasons.json unavailable for the org fallback")
    return tx, wtm


def promotion_timing_debuts(today: date) -> tuple[list[dict], dict[str, str]]:
    """Every MLB debut since PT_FIRST_SEASON with its debut org, age and the two
    timing flags, plus the rookie cutoff per season. Debuts whose org cannot be
    resolved are dropped (counted in the log)."""
    seasons = set(range(PT_FIRST_SEASON, today.year + 1))
    dates = _pt_season_dates(seasons, today)
    people = _pt_people(seasons, today)
    tx, wtm = _pt_debut_org_lookup(seasons)
    debuts, dropped = [], 0
    for pid, (d_iso, b_iso) in people.items():
        dd = date.fromisoformat(d_iso)
        sd = dates.get(dd.year)
        if dd > today or not sd or not sd.get("open") or not sd.get("final"):
            continue
        lo = (dd - timedelta(days=PT_TX_WINDOW_DAYS)).isoformat()
        hits = sorted(x for x in tx.get(pid, ()) if lo <= x[0] <= d_iso)
        org = hits[-1][1] if hits else wtm.get((pid, dd.year))
        if not org:
            dropped += 1
            continue
        try:
            age = (dd - date.fromisoformat(str(b_iso)[:10])).days / 365.25 if b_iso else None
        except ValueError:
            age = None
        gap = (dd - sd["open"]).days
        debuts.append({"year": dd.year, "org": org, "age": age,
                       "late": dd >= pt_rookie_cutoff(dd.year, sd["final"]),
                       "svc": PT_SVC_WINDOW[0] <= gap <= PT_SVC_WINDOW[1]})
    if dropped:
        log.info("promotion timing: %d debuts with no resolvable org dropped", dropped)
    cutoffs = {str(y): pt_rookie_cutoff(y, v["final"]).isoformat()
               for y, v in sorted(dates.items()) if v.get("final")}
    return debuts, cutoffs


def promotion_timing_aggr_rows(con, orgs: set) -> list[tuple]:
    """(player_key, org, season, level, is_pitcher, age_jul1, games) for every
    A to AAA season line of a player with a known birth date (career_stats)."""
    births = {k: b for k, b in con.execute("SELECT player_key, birth_date FROM players") if b}
    rows = []
    for key, payload in con.execute("SELECT player_key, payload_json FROM career_stats"):
        b = births.get(key)
        try:
            bd = date.fromisoformat(str(b)[:10]) if b else None
            lines = json.loads(payload) or []
        except ValueError:
            continue
        if bd is None:
            continue
        for s in lines:
            org = canonical_org(s.get("org")) if s.get("org") else None
            if (s.get("level") in ("A", "A+", "AA", "AAA") and org in orgs and s.get("season")
                    and float(s.get("games") or 0) > 0):
                y = int(s["season"])
                rows.append((key, org, y, s["level"], bool(s.get("is_pitcher")),
                             (date(y, 7, 1) - bd).days / 365.25, float(s["games"])))
    return rows


def _pt_wilson(s: int, n: int, z: float = 1.96) -> list:
    if n == 0:
        return [None, None]
    p = s / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - h, 3), round(c + h, 3)]


def _pt_prop_p(s1: int, n1: int, s2: int, n2: int) -> float:
    """Two-sided two-proportion z test, the org against every other org."""
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2)) or 1e-9
    return math.erfc(abs((s1 / n1 - s2 / n2) / se) / math.sqrt(2))


def _pt_bh(ps: list[float]) -> list[float]:
    idx = sorted(range(len(ps)), key=lambda i: ps[i])
    q = [1.0] * len(ps)
    prev = 1.0
    for rank, i in reversed(list(enumerate(idx, 1))):
        prev = min(prev, ps[i] * len(ps) / rank)
        q[i] = prev
    return q


def _pt_median_ci(vals: list[float], z: float = 1.96) -> list:
    """Distribution-free CI95 for a median from order statistics."""
    v = sorted(vals)
    n = len(v)
    if n < 3:
        return [None, None]
    lo = max(0, int(math.floor(n / 2 - z * math.sqrt(n) / 2)) - 1)
    hi = min(n - 1, int(math.ceil(n / 2 + 1 + z * math.sqrt(n) / 2)) - 1)
    return [round(v[lo], 2), round(v[hi], 2)]


def promotion_timing_panel(debuts: list[dict], aggr_rows: list[tuple], cutoffs: dict,
                           mlb30: set, aggr_seasons=None) -> dict:
    """Per-org debut timing and age for level against the league, each figure
    with its n, CI95 and a BH q across the orgs; labels only where the org is
    distinguishable from the league (see the section header)."""
    from scipy.stats import ttest_ind
    deb = [d for d in debuts if d["org"] in mlb30]
    orgs = sorted({d["org"] for d in deb})
    if not orgs:
        return {"orgs": {}, "league": {}}
    aggr_seasons = set(aggr_seasons or range(PT_AGGR_FIRST_SEASON, max(d["year"] for d in deb) + 1))
    # age for level: each player's mean (age minus the games-weighted league age
    # at his level, season and side), centred on the league player mean; an org's
    # figure is minus its players' mean, so positive reads younger than the level
    lm: dict[tuple, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for _k, _o, y, lvl, ip, a, gm in aggr_rows:
        lm[(y, lvl, ip)][0] += a * gm
        lm[(y, lvl, ip)][1] += gm
    pp: dict[tuple, list[float]] = defaultdict(list)
    for k, o, y, lvl, ip, a, _gm in aggr_rows:
        if y in aggr_seasons and o in orgs:
            m = lm[(y, lvl, ip)]
            pp[(o, k)].append(a - m[0] / m[1])
    ares: dict[str, list[float]] = defaultdict(list)
    for (o, _k), v in pp.items():
        ares[o].append(statistics.fmean(v))
    allv = [x for v in ares.values() for x in v]
    lpm = statistics.fmean(allv) if allv else 0.0
    ares = {o: [x - lpm for x in v] for o, v in ares.items()}

    n_all = len(deb)
    late_all = sum(d["late"] for d in deb)
    svc_all = sum(d["svc"] for d in deb)
    lg_late, lg_svc = late_all / n_all, svc_all / n_all
    ages_all = [d["age"] for d in deb if d["age"]]
    lg_age = statistics.median(ages_all) if ages_all else None
    rows, p_late, p_svc, p_aggr = {}, [], [], []
    for o in orgs:
        mine = [d for d in deb if d["org"] == o]
        n = len(mine)
        sl, sv = sum(d["late"] for d in mine), sum(d["svc"] for d in mine)
        ages = [d["age"] for d in mine if d["age"]]
        ar = ares.get(o, [])
        rest = [x for oo, v in ares.items() if oo != o for x in v]
        if len(ar) > 1 and rest:
            mu = -statistics.fmean(ar)
            half = 1.96 * statistics.pstdev(ar) / math.sqrt(len(ar))
            a_ci = [round(mu - half, 2), round(mu + half, 2)]
            pa = float(ttest_ind(ar, rest, equal_var=False).pvalue)
        else:
            mu, a_ci, pa = (-ar[0] if ar else None), [None, None], 1.0
        p_late.append(_pt_prop_p(sl, n, late_all - sl, n_all - n) if n < n_all else 1.0)
        p_svc.append(_pt_prop_p(sv, n, svc_all - sv, n_all - n) if n < n_all else 1.0)
        p_aggr.append(pa if pa == pa else 1.0)
        rows[o] = {"nDebuts": n,
                   "medianDebutAge": round(statistics.median(ages), 2) if ages else None,
                   "medianAgeCi": _pt_median_ci(ages),
                   "lateShare": round(sl / n, 3), "lateCi": _pt_wilson(sl, n),
                   "svcShare": round(sv / n, 3), "svcCi": _pt_wilson(sv, n),
                   "aggrYears": round(mu, 2) if mu is not None else None, "aggrCi": a_ci,
                   "nAggrPlayers": len(ar)}
    for key, ps in (("qLate", p_late), ("qSvc", p_svc), ("qAggr", p_aggr)):
        for o, q in zip(orgs, _pt_bh(ps)):
            rows[o][key] = round(q, 4)
    for r in rows.values():
        r["thin"] = r["nDebuts"] < PT_MIN_DEBUTS
        lo, hi = r["lateCi"]
        r["labelTiming"] = None
        if not r["thin"] and r["qLate"] < PT_Q_MAX and lo is not None and (lo > lg_late or hi < lg_late):
            r["labelTiming"] = ("waits past the rookie cutoff" if r["lateShare"] > lg_late
                                else "calls up before the rookie cutoff")
        lo, hi = r["aggrCi"]
        r["labelAggr"] = None
        if (r["nAggrPlayers"] >= PT_MIN_AGGR_PLAYERS and r["qAggr"] < PT_Q_MAX
                and lo is not None and (lo > 0 or hi < 0)):
            r["labelAggr"] = "young for level" if r["aggrYears"] > 0 else "old for level"

    def spread(k, centre):
        vals = [r[k] for r in rows.values() if r[k] is not None]
        sd = round(statistics.pstdev(vals), 4) if len(vals) >= 8 else None
        return {"mean": round(centre, 4) if centre is not None else None, "sd": sd or None}

    league = {
        "nDebuts": n_all, "years": sorted({d["year"] for d in deb}),
        "aggrSeasons": sorted(aggr_seasons), "nAggrPlayers": len(allv),
        "lateShare": spread("lateShare", lg_late), "svcShare": spread("svcShare", lg_svc),
        "medianDebutAge": spread("medianDebutAge", lg_age), "aggrYears": spread("aggrYears", 0.0),
        "rookieCutoff": cutoffs, "cutoffRulePre2020": PT_PRE2020_CUTOFF,
        "serviceYearDays": PT_SERVICE_YEAR_DAYS, "svcWindowDays": list(PT_SVC_WINDOW),
        "labelRule": {"minDebuts": PT_MIN_DEBUTS, "minAggrPlayers": PT_MIN_AGGR_PLAYERS,
                      "qMax": PT_Q_MAX, "ciExcludesLeague": True},
        "rule": {"text": PT_RULE_TEXT, "sources": PT_SOURCES},
    }
    return {"orgs": rows, "league": league}


def align_promotion_label(promotion: dict, timing: dict) -> None:
    """The promotion badge reads the tested age-for-level label, so the badge
    and the Promotion timing card cannot disagree on one page. The blended
    score stays in `score`, which only orders the badges."""
    torgs = (timing or {}).get("orgs") or {}
    if not torgs:
        return
    for org, r in (promotion.get("orgs") or {}).items():
        if org in torgs:
            r["label"] = {"young for level": "aggressive",
                          "old for level": "conservative"}.get(torgs[org].get("labelAggr"), "typical")
            r["labelBasis"] = "promotionTiming.labelAggr"


# ============================================================================
# Panels 2+3 — draft position & trait preferences (+ slot allocation)
# ============================================================================

def _is_pitcher_pos(pos: str | None) -> bool:
    head = (pos or "").upper().split("/")[0].strip()
    return head in ("P", "SP", "RP", "RHP", "LHP", "SP2")


def draft_panels(con) -> tuple[dict, dict, dict]:
    picks = con.execute("""
        SELECT r.team, r.draft_year, r.pick_overall, r.round_label, r.slot_usd,
               r.bonus_usd, p.position, p.player_type, r.player_key
        FROM draft_results r LEFT JOIN draft_players p USING (player_key)
        WHERE r.signed = 1 AND r.draft_year >= ?""", (DRAFT_FIRST_YEAR,)).fetchall()
    tools_by_key: dict[str, dict] = {}
    for key, tj in con.execute("""
        SELECT player_key, tools_json FROM draft_snapshots
        WHERE source = 'fangraphs' AND tools_json IS NOT NULL
          AND draft_year >= ? ORDER BY snapshot_date""", (DRAFT_FIRST_YEAR,)):
        try:
            tools_by_key[key] = json.loads(tj)        # latest per key wins
        except ValueError:
            continue
    pos_raw: dict[str, dict] = {}
    trait_acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    league_acc: dict[str, list] = defaultdict(list)
    slot_raw: dict[str, dict] = {}
    by_org: dict[str, list] = defaultdict(list)
    for row in picks:
        by_org[row[0]].append(row)
    for org, rows in by_org.items():
        n = len(rows)
        n_pos_known = sum(1 for r in rows if r[6])
        pitch = sum(1 for r in rows if _is_pitcher_pos(r[6]))
        prep = sum(1 for r in rows if (r[7] or "").upper().startswith("HS"))
        coll = sum(1 for r in rows if (r[7] or "").upper().startswith("COL"))
        upmid = sum(1 for r in rows
                    if (r[6] or "").upper().split("/")[0] in UP_MIDDLE)
        bkt_counts: dict[str, int] = defaultdict(int)
        n_bkt = 0
        for r in rows:
            b = _pos_bucket(r[6])
            if b:
                bkt_counts[b] += 1
                n_bkt += 1
        pos_raw[org] = {
            "n": n,
            "pitchShare": round(pitch / n_pos_known, 3) if n_pos_known else None,
            "prepShare": round(prep / n_pos_known, 3) if n_pos_known else None,
            "collShare": round(coll / n_pos_known, 3) if n_pos_known else None,
            "upMidShare": round(upmid / n_pos_known, 3) if n_pos_known else None,
            "posBuckets": {b: round(bkt_counts.get(b, 0) / n_bkt, 3)
                           for b in DRAFT_BUCKETS} if n_bkt else {},
        }
        # slot allocation: rounds with published slots only
        slotted = [(r[5], r[4], r[3]) for r in rows if r[4] and r[5]]
        over = sum(1 for b, s, _ in slotted if b > s * 1.05)
        r1 = [(b, s) for b, s, rl in slotted if rl == "1"]
        r1_under = sum(1 for b, s in r1 if b < s * 0.95)
        # spend distribution across all signed picks with a known bonus:
        # bonusHHI = concentration of pool $ (top-heavy vs spread); prep $
        # share = how much of the pool went to high-schoolers.
        bonuses = [r[5] for r in rows if r[5]]
        tot_bonus = sum(bonuses)
        hhi = (sum((b / tot_bonus) ** 2 for b in bonuses)
               if tot_bonus and len(bonuses) >= 5 else None)
        prep_bonus = sum(r[5] for r in rows
                         if r[5] and (r[7] or "").upper().startswith("HS"))
        slot_raw[org] = {
            "nSlotted": len(slotted),
            "overSlotShare": round(over / len(slotted), 3) if slotted else None,
            "r1UnderShare": round(r1_under / len(r1), 3) if r1 else None,
            "bonusHHI": round(hhi, 3) if hhi is not None else None,
            "prepDollarShare": round(prep_bonus / tot_bonus, 3) if tot_bonus else None,
        }
        for r in rows:
            t = tools_by_key.get(r[8])
            if not t:
                continue
            for k in HIT_TOOLS + PIT_TOOLS:
                v = t.get(k)
                if isinstance(v, (int, float)) and 20 <= v <= 80:
                    trait_acc[org][k].append(float(v))
                    league_acc[k].append(float(v))
    lg_tool = {k: {"mean": round(statistics.mean(v), 2),
                   "sd": round(statistics.pstdev(v), 2) or None}
               for k, v in league_acc.items() if len(v) >= 60}
    traits = {}
    for org, acc in trait_acc.items():
        tilts = {}
        for k, vals in acc.items():
            if k in lg_tool and len(vals) >= 5:
                tilts[k] = _z(statistics.mean(vals), lg_tool[k]["mean"], lg_tool[k]["sd"])
        ranked = sorted((kv for kv in tilts.items() if kv[1] is not None),
                        key=lambda kv: -abs(kv[1]))
        traits[org] = {"tilts": tilts,
                       "top": [{"tool": k, "z": z} for k, z in ranked[:3] if abs(z) >= 0.4]}
    lg_pos = {k: _league_stats({o: r[k] for o, r in pos_raw.items()})
              for k in ("pitchShare", "prepShare", "collShare", "upMidShare")}
    lg_bkt = {b: _league_stats({o: (r.get("posBuckets") or {}).get(b)
                                for o, r in pos_raw.items()})
              for b in DRAFT_BUCKETS}
    lg_pos["posBuckets"] = lg_bkt
    for org, r in pos_raw.items():
        r["zPitch"] = _z(r["pitchShare"], lg_pos["pitchShare"]["mean"], lg_pos["pitchShare"]["sd"])
        r["zPrep"] = _z(r["prepShare"], lg_pos["prepShare"]["mean"], lg_pos["prepShare"]["sd"])
        r["zColl"] = _z(r["collShare"], lg_pos["collShare"]["mean"], lg_pos["collShare"]["sd"])
        r["zUpMid"] = _z(r["upMidShare"], lg_pos["upMidShare"]["mean"], lg_pos["upMidShare"]["sd"])
        r["posBucketsZ"] = {b: _z((r.get("posBuckets") or {}).get(b),
                                  lg_bkt[b]["mean"], lg_bkt[b]["sd"])
                            for b in DRAFT_BUCKETS}
    lg_slot = {k: _league_stats({o: r[k] for o, r in slot_raw.items()})
               for k in ("overSlotShare", "r1UnderShare", "bonusHHI", "prepDollarShare")}
    for org, r in slot_raw.items():
        r["zOver"] = _z(r["overSlotShare"], lg_slot["overSlotShare"]["mean"], lg_slot["overSlotShare"]["sd"])
        r["zBonusHHI"] = _z(r["bonusHHI"], lg_slot["bonusHHI"]["mean"], lg_slot["bonusHHI"]["sd"])
        r["zPrepDollar"] = _z(r["prepDollarShare"], lg_slot["prepDollarShare"]["mean"], lg_slot["prepDollarShare"]["sd"])
        r["label"] = _label(r.get("zOver"), "over-slot shoppers", "slot-disciplined")
        r["spendLabel"] = _label(r.get("zBonusHHI"), "top-heavy pool", "spread the pool")
    return ({"orgs": pos_raw, "league": lg_pos},
            {"orgs": traits, "league": lg_tool},
            {"orgs": slot_raw, "league": lg_slot})


# ============================================================================
# Panel 4 — current arsenal profile
# ============================================================================

def _mlb_arsenal_usage(con, players, debuts):
    """MLB-tracked (graduate) arsenals → per-org list of per-arm usage-fraction
    dicts, per-org fb_velo list, and the set of mlbams seen (so AAA can skip
    them). org attribution: active board first, then the debuts sidecar."""
    org_key = {p["player_key"]: p["org"] for p in players if p.get("org")}
    for d in debuts:
        if d.get("player_key") and d.get("org"):
            org_key.setdefault(d["player_key"], d["org"])
    usage: dict[str, list[dict[str, float]]] = defaultdict(list)
    velo: dict[str, list] = defaultdict(list)
    seen: set[int] = set()
    for key, payload in con.execute("SELECT player_key, payload_json FROM pitch_arsenals"):
        org = org_key.get(key)
        if not org:
            continue
        try:
            a = json.loads(payload)
        except ValueError:
            continue
        if a.get("mlbam_id"):
            seen.add(int(a["mlbam_id"]))
        mix: dict[str, float] = defaultdict(float)
        for p in a.get("pitches") or []:
            pt = (p.get("pitch_type") or "").strip()
            u = p.get("usage_pct") or 0
            if pt and u:
                mix[pt] += float(u)
        tot = sum(mix.values())
        if tot > 0:
            usage[org].append({pt: v / tot for pt, v in mix.items()})   # normalize to fractions
        if a.get("fb_velo"):
            velo[org].append(float(a["fb_velo"]))
    return usage, velo, seen


def arsenal_panel(con, players: list[dict], debuts: list[dict],
                  mlbam_org: dict[int, str] | None = None) -> dict:
    """Pitch-shape identity of the org's pitching inventory — BLENDED across
    the MLB arsenals of the arms it developed (Statcast, graduates) and the
    Savant-minors arsenals of its current AAA arms. Each arm contributes one
    usage-fraction mix; org/league shares are the AVERAGE ARM'S mix, so the
    table reads 'their typical arm throws sinkers 1.6× the league rate'.
    Graduates that also threw in AAA are counted once (on the MLB side)."""
    if mlbam_org is None:
        mlbam_org = _mlbam_org_map(players, debuts)
    mlb_usage, velo, mlb_seen = _mlb_arsenal_usage(con, players, debuts)
    aaa_usage = _aaa_usage_by_arm(mlbam_org, exclude=mlb_seen)

    arms: dict[str, list[dict[str, float]]] = defaultdict(list)
    n_mlb: dict[str, int] = defaultdict(int)
    n_aaa: dict[str, int] = defaultdict(int)
    for org, lst in mlb_usage.items():
        arms[org].extend(lst)
        n_mlb[org] += len(lst)
    for org, lst in aaa_usage.items():
        arms[org].extend(lst)
        n_aaa[org] += len(lst)

    # League per-pitch share = mean of every arm's share of that pitch.
    all_arms = [mix for lst in arms.values() for mix in lst]
    n_all = len(all_arms) or 1
    pt_union = {pt for mix in all_arms for pt in mix}
    lg_share = {pt: sum(mix.get(pt, 0.0) for mix in all_arms) / n_all for pt in pt_union}

    def _ordered(pts):
        known = [pt for pt in PITCH_ORDER if pt in pts]
        return known + sorted(pt for pt in pts if pt not in PITCH_ORDER)

    raw = {}
    for org, lst in arms.items():
        n = len(lst) or 1
        usage_matrix = {}
        ratios = {}
        for pt in _ordered({p for mix in lst for p in mix} | {p for p in lg_share}):
            base = lg_share.get(pt, 0.0)
            if base < 0.01:                       # league barely throws it — skip noise
                continue
            share = sum(mix.get(pt, 0.0) for mix in lst) / n
            usage_matrix[pt] = {"share": round(share, 3),
                                "leagueShare": round(base, 3),
                                "ratio": round(share / base, 2) if base else None}
            if share >= 0.01:
                ratios[pt] = round(share / base, 2)
        ranked = sorted(ratios.items(), key=lambda kv: -abs(kv[1] - 1.0))
        raw[org] = {
            "nArms": n_mlb[org] + n_aaa[org],
            "nArmsMlb": n_mlb[org],
            "nArmsAaa": n_aaa[org],
            "fbVelo": round(statistics.mean(velo[org]), 1) if velo.get(org) else None,
            "usage": usage_matrix,
            "usageRatio": dict(ranked),                       # back-compat
            "lean": [{"pt": pt, "x": x} for pt, x in ranked[:3] if abs(x - 1.0) >= 0.25],
            "blendNote": f"{n_mlb[org]} MLB + {n_aaa[org]} AAA arms",
        }
    lg_velo = _league_stats({o: r["fbVelo"] for o, r in raw.items()})
    for r in raw.values():
        r["zVelo"] = _z(r["fbVelo"], lg_velo["mean"], lg_velo["sd"])
    return {"orgs": raw, "league": {"fbVelo": lg_velo, "share": {
        pt: round(s, 4) for pt, s in sorted(lg_share.items(), key=lambda kv: -kv[1])}}}


# ============================================================================
# Panel 4b — per-pitch STUFF (velo + movement) profile
# ============================================================================

def _enum(vals: list[float]) -> dict:
    return {i: v for i, v in enumerate(vals)}


def pitch_stuff_panel(con, players: list[dict], debuts: list[dict],
                      mlbam_org: dict[int, str] | None = None) -> dict:
    """For each pitch type, the org's velo + movement vs league. Movement
    (arm-side horizontal break = pfx_x·sign(throws), vertical break = pfx_z,
    both in inches) comes from the AAA Savant-minors CSVs; velo blends AAA
    release_speed with MLB avg_speed for the org's developed arms. Each arm
    contributes one mean per pitch type; org/league cells are means across
    arms, z vs the per-pitch-type league."""
    if mlbam_org is None:
        mlbam_org = _mlbam_org_map(players, debuts)
    acc: dict[str, dict[str, dict[str, list]]] = defaultdict(
        lambda: defaultdict(lambda: {"velo": [], "h": [], "v": []}))
    # --- AAA: velo + movement, per arm ---
    for org, _mid, rows in _aaa_iter(mlbam_org):
        sign = 1.0 if (rows[0].get("p_throws") or "R") == "R" else -1.0
        by_pt: dict[str, dict[str, list]] = defaultdict(lambda: {"velo": [], "h": [], "v": []})
        for r in rows:
            pt = (r.get("pitch_type") or "").strip()
            if pt not in AAA_KEEP_PT:
                continue
            sp, hx, vz = _f(r.get("release_speed")), _f(r.get("pfx_x")), _f(r.get("pfx_z"))
            if sp is not None:
                by_pt[pt]["velo"].append(sp)
            if hx is not None:
                by_pt[pt]["h"].append(hx * sign * 12.0)     # arm-side inches
            if vz is not None:
                by_pt[pt]["v"].append(vz * 12.0)
        for pt, d in by_pt.items():
            slot = acc[org][pt]
            if d["velo"]:
                slot["velo"].append(statistics.mean(d["velo"]))
            if d["h"]:
                slot["h"].append(statistics.mean(d["h"]))
            if d["v"]:
                slot["v"].append(statistics.mean(d["v"]))
    # --- MLB arsenals: avg_speed per pitch type (velo only) ---
    org_key = {p["player_key"]: p["org"] for p in players if p.get("org")}
    for d in debuts:
        if d.get("player_key") and d.get("org"):
            org_key.setdefault(d["player_key"], d["org"])
    for key, payload in con.execute("SELECT player_key, payload_json FROM pitch_arsenals"):
        org = org_key.get(key)
        if not org:
            continue
        try:
            a = json.loads(payload)
        except ValueError:
            continue
        for p in a.get("pitches") or []:
            pt = (p.get("pitch_type") or "").strip()
            sp = _f(p.get("avg_speed"))
            if pt in AAA_KEEP_PT and sp is not None:
                acc[org][pt]["velo"].append(sp)
    # --- per-org cells + league per-pitch-type stats ---
    org_pt: dict[str, dict[str, dict]] = {}
    lg_acc: dict[str, dict[str, list]] = defaultdict(lambda: {"velo": [], "h": [], "v": []})
    for org, by_pt in acc.items():
        row = {}
        for pt, d in by_pt.items():
            n = max(len(d["velo"]), len(d["h"]), len(d["v"]))
            if n < 4:                                   # too few arms throwing it
                continue
            velo = round(statistics.mean(d["velo"]), 1) if d["velo"] else None
            h = round(statistics.mean(d["h"]), 1) if d["h"] else None
            v = round(statistics.mean(d["v"]), 1) if d["v"] else None
            row[pt] = {"velo": velo, "hBreak": h, "vBreak": v, "n": n}
            if velo is not None:
                lg_acc[pt]["velo"].append(velo)
            if h is not None:
                lg_acc[pt]["h"].append(h)
            if v is not None:
                lg_acc[pt]["v"].append(v)
        if row:
            org_pt[org] = row
    lg = {pt: {"velo": _league_stats(_enum(d["velo"])),
               "hBreak": _league_stats(_enum(d["h"])),
               "vBreak": _league_stats(_enum(d["v"]))}
          for pt, d in lg_acc.items()}
    for row in org_pt.values():
        for pt, cell in row.items():
            L = lg.get(pt, {})
            cell["zVelo"] = _z(cell["velo"], L.get("velo", {}).get("mean"), L.get("velo", {}).get("sd"))
            cell["zHBreak"] = _z(cell["hBreak"], L.get("hBreak", {}).get("mean"), L.get("hBreak", {}).get("sd"))
            cell["zVBreak"] = _z(cell["vBreak"], L.get("vBreak", {}).get("mean"), L.get("vBreak", {}).get("sd"))
    return {"orgs": {o: {"pitches": row} for o, row in org_pt.items()}, "league": lg}


# ============================================================================
# Panel 5 — tool development (grade drift per prospect-year in org)
# ============================================================================

def dev_calendars(con, players: list[dict], debuts: list[dict]) -> dict[str, list]:
    """VAL_4: player_key -> org tenures from dev_attribution, the calendar the farm
    grade credits development on. Graduates read the tenures baked on their debuts
    row (storage stamps dev_credit); everyone else with a grade history is
    attributed here from the dated transactions. {} when the module cannot run, in
    which case toolDev keeps the org on each snapshot row."""
    try:
        import dev_attribution as _da
    except ImportError:
        return {}
    cal: dict[str, list] = {}
    for d in debuts or []:
        ts = (d.get("dev_credit") or {}).get("tenures")
        if d.get("player_key") and ts:
            cal[d["player_key"]] = [_da.Tenure(o, s, e) for o, s, e in ts]
    infos = []
    seen = set(cal)
    for p in players or []:
        k = p.get("player_key")
        if k and k not in seen:
            seen.add(k)
            infos.append(_da.PlayerInfo(k, p.get("org"),
                                        "active" if p.get("status") == "active" else "inactive"))
    try:
        for (k,) in con.execute("SELECT DISTINCT player_key FROM snapshots "
                                "WHERE tools_json IS NOT NULL AND status = 'active'"):
            if k and k not in seen:
                seen.add(k)
                infos.append(_da.PlayerInfo(k, None, "inactive"))
        att = _da.build(infos, con=con)
    except Exception as exc:                                # noqa: BLE001 - degrade, never abort
        log.warning("org_tendencies: dev attribution unavailable (%s); toolDev reads snapshot orgs", exc)
        return cal
    for k, pa in att.players.items():
        if pa.tenures:
            cal[k] = pa.tenures
    return cal


def tool_dev_panel(con, calendars: dict | None = None) -> dict:
    """Per-tool grade drift per prospect-year in org, from same-source pairs at
    least MIN_PAIR_DAYS apart. VAL_4: with a calendar the club comes from the
    player's org tenures, and a pair that spans a club change is split by days
    (delta, years and pair count alike) instead of being dropped; an
    unaffiliated stretch credits nobody. Without one, the org on the snapshot
    row, and only pairs inside one org, as before."""
    from dev_attribution import split_pair as _split
    calendars = calendars or {}
    rows = con.execute("""
        SELECT player_key, source, snapshot_date, org, tools_json
        FROM snapshots
        WHERE tools_json IS NOT NULL AND org IS NOT NULL AND status = 'active'
        ORDER BY player_key, source, snapshot_date""").fetchall()
    acc: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(lambda: {"d": 0.0, "yr": 0.0, "n": 0}))
    prev = None
    for key, src, d, org, tj in rows:
        try:
            tools = {k: v for k, v in json.loads(tj).items()
                     if k in HIT_TOOLS + PIT_TOOLS and isinstance(v, (int, float))
                     and 20 <= v <= 80}
        except ValueError:
            prev = None
            continue
        cur = (key, src, d, org, tools)
        cal = calendars.get(key)
        if prev and prev[0] == key and prev[1] == src and (cal or prev[3] == org):
            try:
                dt = (date.fromisoformat(d[:10]) - date.fromisoformat(prev[2][:10])).days
            except ValueError:
                dt = 0
            if dt >= MIN_PAIR_DAYS:
                yrs = dt / 365.25
                parts = ([(cal[i].org, f) for i, f in _split(prev[2][:10], d[:10], cal)]
                         if cal else [(org, 1.0)])
                for k, v1 in tools.items():
                    v0 = prev[4].get(k)
                    if v0 is None:
                        continue
                    for o, f in parts:
                        if not o:
                            continue
                        slot = acc[o][k]
                        slot["d"] += (v1 - v0) * f
                        slot["yr"] += yrs * f
                        slot["n"] += f
        prev = cur
    per_org: dict[str, dict[str, float]] = {}
    league_rates: dict[str, list] = defaultdict(list)
    for org, by_tool in acc.items():
        rates = {}
        for k, s in by_tool.items():
            if s["n"] >= MIN_TOOL_PAIRS and s["yr"] > 0:
                rates[k] = round(s["d"] / s["yr"], 2)
                league_rates[k].append(rates[k])
        per_org[org] = rates
    lg = {k: {"mean": round(statistics.mean(v), 2),
              "sd": round(statistics.pstdev(v), 2) or None}
          for k, v in league_rates.items() if len(v) >= 10}
    out = {}
    for org, rates in per_org.items():
        rel = {}
        for k, r in rates.items():
            if k in lg:
                rel[k] = {"rate": r, "vsLeague": round(r - lg[k]["mean"], 2),
                          "z": _z(r, lg[k]["mean"], lg[k]["sd"])}
        best = sorted((kv for kv in rel.items() if kv[1]["z"] is not None),
                      key=lambda kv: -kv[1]["z"])
        out[org] = {"tools": rel,
                    "best": [{"tool": k, "z": v["z"], "vsLeague": v["vsLeague"]}
                             for k, v in best[:3] if v["z"] >= 0.4],
                    "worst": [{"tool": k, "z": v["z"], "vsLeague": v["vsLeague"]}
                              for k, v in reversed(best[-2:]) if v["z"] <= -0.4]}
    # SC+ drift over the platform's metric history (short window — disclosed)
    sc_rows = con.execute("""
        SELECT player_key, org, snapshot_date, payload_json FROM metric_snapshots
        WHERE org IS NOT NULL ORDER BY player_key, snapshot_date""").fetchall()
    first_last: dict[tuple, list] = {}
    for key, org, d, payload in sc_rows:
        try:
            sc = json.loads(payload).get("statcast_plus")
        except ValueError:
            continue
        if sc is None:
            continue
        slot = first_last.setdefault((key, org), [None, None])
        if slot[0] is None:
            slot[0] = (d, sc)
        slot[1] = (d, sc)
    sc_acc: dict[str, list] = defaultdict(list)
    for (key, org), (a, b) in first_last.items():
        if a and b and a[0] != b[0]:
            sc_acc[org].append(b[1] - a[1])
    sc_org = {org: round(statistics.mean(v), 1) for org, v in sc_acc.items() if len(v) >= 5}
    lg_sc = _league_stats(sc_org)
    for org, v in sc_org.items():
        if org in out:
            out[org]["scPlusDrift"] = v
            out[org]["scPlusZ"] = _z(v, lg_sc["mean"], lg_sc["sd"])
    return {"orgs": out, "league": {"tools": lg, "scPlus": lg_sc}}


# ============================================================================
# Panel 6 — IFA strategy (quality vs quantity)
# ============================================================================

def ifa_panel() -> dict:
    try:
        classes = json.loads((DATA_DIR / "ifa_timeseries.json")
                             .read_text(encoding="utf-8"))["classes"]
    except (OSError, ValueError, KeyError):
        log.warning("org_tendencies: ifa_timeseries.json unavailable")
        return {"orgs": {}, "league": {}}
    per: dict[str, dict[int, list]] = defaultdict(dict)
    for cls in classes:
        for s in cls.get("signings") or []:
            org, b = s.get("org"), s.get("bonus_usd")
            if org:
                per[org].setdefault(cls["year"], []).append(b or 0)
    raw = {}
    for org, by_year in per.items():
        t1, hhi, mil, n = [], [], 0, 0
        for _yr, bonuses in by_year.items():
            known = [b for b in bonuses if b > 0]
            n += len(bonuses)
            mil += sum(1 for b in known if b >= 1_000_000)
            tot = sum(known)
            if tot and len(known) >= 3:
                shares = [b / tot for b in known]
                t1.append(max(shares))
                hhi.append(sum(s * s for s in shares))
        raw[org] = {
            "classes": len(by_year),
            "signingsPerClass": round(n / len(by_year), 1) if by_year else None,
            "top1Share": round(statistics.mean(t1), 3) if t1 else None,
            "hhi": round(statistics.mean(hhi), 3) if hhi else None,
            "sevenFigure": mil,
        }
    lg = {k: _league_stats({o: r[k] for o, r in raw.items()})
          for k in ("top1Share", "hhi", "signingsPerClass")}
    for r in raw.values():
        r["zConc"] = _z(r["hhi"], lg["hhi"]["mean"], lg["hhi"]["sd"])
        r["zVolume"] = _z(r["signingsPerClass"], lg["signingsPerClass"]["mean"],
                          lg["signingsPerClass"]["sd"])
        r["label"] = _label(r["zConc"], "quality (one big fish)", "quantity (spread the pool)",
                            "balanced")
    return {"orgs": raw, "league": lg}


# ============================================================================
# Panel 7 — trade tendencies
# ============================================================================

_CASH_RE = re.compile(r"^(?P<from>.+?) traded .+? to (?P<to>.+?) for (?P<ret>.+)\.?$")


def cash_direction(description: str) -> str | None:
    """Which side RECEIVED cash in an MLB tx description. 'A traded X to B
    for ... cash' → A received cash. Returns the receiving club name."""
    m = _CASH_RE.match(description or "")
    if not m:
        return None
    if "cash" in m.group("ret").lower():
        return m.group("from").strip()
    return None


def _drop_round_trips(moves: list[tuple[str, str, str, str, bool]],
                      days: int) -> list[tuple[str, str, str, str, bool]]:
    """Drop A -> B -> A round trips from (player_key, date, from, to, is_feed) moves.

    Per player, in date order: when a move reverses the last kept move (B -> A after
    A -> B) within `days`, the pair is read as two sources disagreeing on the
    player's org. The feed is the authority: two feed legs are two real
    transactions and both stay; a feed leg with an inferred leg keeps the feed leg
    and drops the inferred one; two inferred legs both drop. Cancelling against the
    last KEPT move handles flip-flops (A -> B -> A -> B keeps at most one move)."""
    by_key: dict[str, list] = defaultdict(list)
    for m in moves:
        by_key[m[0]].append(m)
    kept: list = []
    for key in sorted(by_key):
        stack: list = []
        for m in sorted(by_key[key], key=lambda x: (x[1], not x[4])):
            top = stack[-1] if stack else None
            if (top is not None and top[2] == m[3] and top[3] == m[2]
                    and not (top[4] and m[4])
                    and (date.fromisoformat(m[1][:10])
                         - date.fromisoformat(top[1][:10])).days <= days):
                if top[4]:
                    continue                  # feed leg stays, inferred reverse drops
                stack.pop()                   # the inferred leg drops
                if m[4]:
                    stack.append(m)           # a feed reverse of an inferred leg stays
                continue
            stack.append(m)
        kept += stack
    return kept


def trade_moves(rows, mlb30: set,
                include_inferred: bool = False,
                round_trip_days: int | None = None) -> list[tuple[str, str, str, str]]:
    """Distinct cross-org moves (player_key, trade_date, from, to) from trades rows
    (player_key, trade_date, from_org, to_org, source, date_range_start).

    By default only mlb_api rows (the MLB transaction feed) count. Inferred rows
    (an org change between two board snapshots) stay out: after de-duplication
    2,104 of 3,706 cross-club moves were inferred-only, and 1,512 of all moves
    were A -> B -> A round trips, mostly two sources disagreeing on a player's org
    (adam_kloffenstein TOR -> NYY -> TOR within a month); on mlb_api rows alone
    26 of 1,602 are round trips. include_inferred=True keeps the de-duplicated
    inferred moves the feed does not confirm; round_trip_days then drops the
    A -> B -> A round trips inside that window (_drop_round_trips). The served
    trade profile uses both (owner answer M8-3, trades_panel).

    Census M02-05 (2026-09-25). The table carries four artifacts that inflated
    every org's trade panel:
      * inferred rows re-fire daily when a player's newest snapshot is the rolling
        performance_ingest row, so one move sits on up to 45 rows; a move is
        (player, from, to, date_range_start) and counts once, dated by its
        earliest row;
      * affiliate codes (SAL, ALB, OMA...) pass through canonical_org, so a
        SAL -> LAA transition (a Salt Lake roster row, then an Angels row) read as
        a trade; a move counts only when BOTH ends are one of the 30 clubs and they
        differ;
      * mlb_api rows carry full club names, which the old len(org) > 3 skip dropped
        entirely; they are canonicalised here and counted;
      * an inferred move that an mlb_api row confirms for the same player and clubs
        is the same move and is dropped.
    """
    api: dict[tuple, str] = {}
    inferred: dict[tuple, str] = {}
    for key, d, frm, to, src, start in rows:
        a, b = canonical_org(frm), canonical_org(to)
        if not key or a not in mlb30 or b not in mlb30 or a == b:
            continue
        if src == "mlb_api":
            api.setdefault((key, a, b, d), d)
        elif include_inferred:
            k = (key, a, b, start or d)
            if k not in inferred or d < inferred[k]:
                inferred[k] = d
    confirmed = {(k[0], k[1], k[2]) for k in api}
    moves = [(k[0], d, k[1], k[2], True) for k, d in api.items()]
    moves += [(k[0], d, k[1], k[2], False) for k, d in inferred.items()
              if (k[0], k[1], k[2]) not in confirmed]
    if include_inferred and round_trip_days is not None:
        moves = _drop_round_trips(moves, round_trip_days)
    return [m[:4] for m in moves]


def trades_panel(con, mlb30: set | None = None) -> dict:
    rows = con.execute("""
        SELECT player_key, trade_date, from_org, to_org, source, description,
               date_range_start
        FROM trades WHERE trade_date >= ?""", (TRADE_FIRST_DATE,)).fetchall()
    if mlb30 is None:
        mlb30 = set(storage.MLB_30_ORGS)
    fv_near = _fv_near_date_index(con)
    inb: dict[str, list] = defaultdict(list)
    out_n: dict[str, int] = defaultdict(int)
    deals: dict[str, set] = defaultdict(set)
    cash_recv: dict[str, int] = defaultdict(int)
    cash_any: dict[str, int] = defaultdict(int)
    for key, d, frm, to in trade_moves(
            [(k, d, f, t, s, st) for k, d, f, t, s, _desc, st in rows], mlb30,
            include_inferred=True, round_trip_days=ROUND_TRIP_DAYS):
        inb[to].append((key, d))
        deals[to].add((d, frm, to))
        out_n[frm] += 1
        deals[frm].add((d, frm, to))
    # A multi-player deal writes one mlb_api row per player, all with the same
    # description: count each described deal once.
    seen_desc: set = set()
    for key, d, frm, to, _src, desc, _st in rows:
        if not desc or (d, desc) in seen_desc:
            continue
        seen_desc.add((d, desc))
        if "cash" in desc.lower():
            # mlb_api description rows often carry NULL org columns — both
            # clubs come from the description parse, never the columns.
            m = _CASH_RE.match(desc)
            if m:
                a = canonical_org(m.group("from").strip())
                b = canonical_org(m.group("to").strip())
                for org in (a, b):
                    if org:
                        cash_any[org] += 1
                recv = cash_direction(desc)
                recv_org = canonical_org(recv) if recv else None
                if recv_org:
                    cash_recv[recv_org] += 1
    raw = {}
    # League stats run over the 30 clubs only (they ran over 69 codes, 39 of them
    # affiliate or foreign, which put 24 of 30 clubs at z >= +0.5).
    for org in sorted(mlb30):
        acquired = inb.get(org, [])
        fvs = [fv for fv in (fv_near(key, d) for key, d in acquired) if fv is not None]
        n_in, n_out = len(acquired), out_n.get(org, 0)
        n_deals = len(deals.get(org, ())) or 1
        raw[org] = {
            "in": n_in, "out": n_out, "volume": n_in + n_out,
            "netProspects": n_in - n_out,
            "prospectsPerDeal": round((n_in + n_out) / n_deals, 2),
            "acqFvMean": round(statistics.mean(fvs), 1) if fvs else None,
            "acqTopShare": round(sum(1 for v in fvs if v >= 50) / len(fvs), 2) if fvs else None,
            "nGraded": len(fvs),
            "cashReceived": cash_recv.get(org, 0),
            "cashInvolved": cash_any.get(org, 0),
        }
    lg = {k: _league_stats({o: r[k] for o, r in raw.items()})
          for k in ("volume", "netProspects", "acqTopShare", "prospectsPerDeal",
                    "cashReceived")}
    for r in raw.values():
        r["zVolume"] = _z(r["volume"], lg["volume"]["mean"], lg["volume"]["sd"])
        r["zNet"] = _z(r["netProspects"], lg["netProspects"]["mean"], lg["netProspects"]["sd"])
        r["zQuality"] = _z(r["acqTopShare"], lg["acqTopShare"]["mean"], lg["acqTopShare"]["sd"])
        r["zCash"] = _z(r["cashReceived"], lg["cashReceived"]["mean"], lg["cashReceived"]["sd"])
        r["volLabel"] = _label(r["zVolume"], "trade-happy", "trade-reluctant")
        r["dirLabel"] = _label(r["zNet"], "prospect acquirer", "prospect shipper (MLB buyer)",
                               "two-way")
        r["qdLabel"] = _label(r["zQuality"], "quality (top prospects)", "depth (volume)",
                              "balanced")
    return {"orgs": raw, "league": lg,
            "window": f"{TRADE_FIRST_DATE[:4]}-present",
            "roundTripDays": ROUND_TRIP_DAYS,
            "note": ("prospect-capital lens: 'in'/'out' count distinct tracked-prospect "
                     "moves between two of the 30 clubs, from the MLB transaction feed "
                     "plus org changes seen on board snapshots; a move reversed for the "
                     f"same player within {ROUND_TRIP_DAYS} days (A to B to A) is read as "
                     "two sources disagreeing and drops, except that two feed moves both "
                     "count and a feed move outranks a snapshot-inferred one; FV "
                     "graded from board snapshots within ±120d of the trade, ungraded "
                     "moves are counted, never guessed")}


def _fv_near_date_index(con):
    """fv(player_key, trade_date) — median board FV within ±120 days."""
    rows = con.execute("""
        SELECT player_key, snapshot_date, fv FROM snapshots
        WHERE fv IS NOT NULL ORDER BY player_key, snapshot_date""").fetchall()
    by_key: dict[str, list] = defaultdict(list)
    for key, d, fv in rows:
        by_key[key].append((d, fv))

    def lookup(key: str, trade_date: str) -> float | None:
        pts = by_key.get(key)
        if not pts:
            return None
        try:
            td = date.fromisoformat(trade_date[:10])
        except ValueError:
            return None
        near = [fv for d, fv in pts
                if abs((date.fromisoformat(d[:10]) - td).days) <= 120]
        return statistics.median(near) if near else None
    return lookup


# ============================================================================
# Panel 8 — IL burden
# ============================================================================

def health_panel(con, by_org: dict[str, list[dict]]) -> dict:
    keys_org = {p["player_key"]: org for org, roster in by_org.items() for p in roster}
    stints: dict[str, int] = defaultdict(int)
    for (key,) in con.execute("SELECT player_key FROM il_history"):
        org = keys_org.get(key)
        if org:
            stints[org] += 1
    raw = {}
    for org, roster in by_org.items():
        raw[org] = {"stintsPer100": round(100 * stints.get(org, 0) / len(roster), 1)
                    if roster else None}
    lg = _league_stats({o: r["stintsPer100"] for o, r in raw.items()})
    for r in raw.values():
        r["z"] = _z(r["stintsPer100"], lg["mean"], lg["sd"])
        r["label"] = _label(r["z"], "high IL burden", "healthy pipeline")
    return {"orgs": raw, "league": lg}


# ============================================================================
# Panel 9 — graduation track record
# ============================================================================

def _whole(v: float):
    """A graduate-equivalent count: an int when whole, else 2 decimals."""
    v = round(float(v), 2)
    return int(v) if v.is_integer() else v


def graduation_panel(con, debuts: list[dict]) -> dict:
    """How well the pipeline produces MLB players: graduates/year, mean
    graduate career WAR, and draft-to-MLB hit rate (signed picks 2021+ whose
    promoted_key reached the bigs / signed picks 2021+). Recent draft classes
    have little runway, so absolute hit rates are low — the z is the signal."""
    # VAL_4: a graduate counts at each club that developed him by its development
    # share (debuts row dev_credit.shares); the current club only when the row
    # carries no attribution. Counts are graduate-equivalents, means share-weighted.
    grads_year: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    war_by_org: dict[str, list] = defaultdict(list)
    debut_keys: set[str] = set()
    for d in debuts:
        if d.get("player_key"):
            debut_keys.add(d["player_key"])
        shares = (d.get("dev_credit") or {}).get("shares") or (
            [[d.get("org"), 1.0]] if d.get("org") else [])
        yr = (d.get("debut_date") or "")[:4]
        cw = d.get("career_war")
        for org, w in shares:
            if not org or not w:
                continue
            if yr.isdigit():
                grads_year[org][yr] += w
            if isinstance(cw, dict) and cw.get("career_war") is not None:
                war_by_org[org].append((float(cw["career_war"]), w))
    signed: dict[str, int] = defaultdict(int)
    hit: dict[str, int] = defaultdict(int)
    try:
        for team, _pk, promoted in con.execute("""
            SELECT r.team, r.player_key, p.promoted_key
            FROM draft_results r LEFT JOIN draft_players p USING (player_key)
            WHERE r.signed = 1 AND r.draft_year >= ?""", (DRAFT_FIRST_YEAR,)):
            if not team:
                continue
            signed[team] += 1
            if promoted and promoted in debut_keys:
                hit[team] += 1
    except Exception as e:                                  # noqa: BLE001 — degrade, never abort
        log.warning("org_tendencies: draft hit-rate unavailable: %s", e)
    raw = {}
    for org in set(grads_year) | set(war_by_org) | set(signed):
        years = grads_year.get(org, {})
        wars = war_by_org.get(org, [])
        n_war = sum(w for _, w in wars)
        ns = signed.get(org, 0)
        raw[org] = {
            "gradsPerYear": round(sum(years.values()) / len(years), 1) if years else None,
            "totalGrads": _whole(sum(years.values())),
            "meanGradWar": round(sum(v * w for v, w in wars) / n_war, 2) if n_war > 0 else None,
            "nWar": _whole(n_war),
            "nSignedDraft": ns,
            "nGradsFromDraft": hit.get(org, 0),
            "draftHitRate": round(hit.get(org, 0) / ns, 3) if ns else None,
        }
    lg = {k: _league_stats({o: r[k] for o, r in raw.items()})
          for k in ("gradsPerYear", "meanGradWar", "draftHitRate")}
    for r in raw.values():
        r["zGrads"] = _z(r["gradsPerYear"], lg["gradsPerYear"]["mean"], lg["gradsPerYear"]["sd"])
        r["zWar"] = _z(r["meanGradWar"], lg["meanGradWar"]["mean"], lg["meanGradWar"]["sd"])
        r["zHitRate"] = _z(r["draftHitRate"], lg["draftHitRate"]["mean"], lg["draftHitRate"]["sd"])
        r["label"] = _label(r["zWar"], "produces MLB value", "thin track record")
    return {"orgs": raw, "league": lg,
            "note": ("draft hit rate = signed picks 2021+ reaching MLB / signed picks 2021+ — "
                     "recent classes have little runway, so the z (relative) is the read")}


# ============================================================================
# Panel 10 — hitter approach (current lean, level-adjusted)
# ============================================================================

# (zone-metric field, friendly key, aggressive-direction sign for the label)
APPROACH_MAP = (("o_swing_pct", "chase"), ("z_contact_pct", "zoneContact"), ("whiff_pct", "whiff"))


def hitter_approach_panel(players: list[dict]) -> dict:
    """Org hitters' plate-discipline LEAN vs league: chase (o-swing), in-zone
    contact, and whiff. Level-adjusted (each hitter expressed as a deviation
    from his level's league mean) so an AAA-heavy system isn't penalized.
    NOTE: zone-metric history isn't archived, so this is a current lean, not a
    development drift."""
    by_level: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    rows: list[tuple[str, str, dict]] = []
    for p in players:
        if p.get("status") != "active" or not p.get("org"):
            continue
        zm = p.get("zone_metrics")
        if not isinstance(zm, dict) or zm.get("is_pitcher"):
            continue
        level = zm.get("level") or p.get("statline_level") or "?"
        vals = {}
        for field, name in APPROACH_MAP:
            v = zm.get(field)
            if isinstance(v, (int, float)):
                vals[name] = float(v)
                by_level[name][level].append(float(v))
        if vals:
            rows.append((p["org"], level, vals))
    level_mean = {name: {lv: statistics.mean(vs) for lv, vs in lvs.items() if len(vs) >= 5}
                  for name, lvs in by_level.items()}
    acc: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for org, level, vals in rows:
        for name, v in vals.items():
            base = level_mean.get(name, {}).get(level)
            if base is not None:
                acc[org][name].append(v - base)
    raw = {}
    for org, by_name in acc.items():
        cell, n = {}, 0
        for _field, name in APPROACH_MAP:
            xs = by_name.get(name, [])
            if len(xs) >= 5:
                cell[name] = {"adj": round(statistics.mean(xs), 3)}
                n = max(n, len(xs))
        if cell:
            raw[org] = {"metrics": cell, "nHitters": n}
    lg = {name: _league_stats({o: (r["metrics"].get(name) or {}).get("adj")
                               for o, r in raw.items()})
          for _f, name in APPROACH_MAP}
    for r in raw.values():
        for _field, name in APPROACH_MAP:
            if name in r["metrics"]:
                r["metrics"][name]["z"] = _z(r["metrics"][name]["adj"],
                                             lg[name]["mean"], lg[name]["sd"])
        zc = (r["metrics"].get("chase") or {}).get("z")
        r["label"] = _label(-zc if zc is not None else None,
                            "disciplined approach", "aggressive swingers")
    return {"orgs": raw, "league": lg, "levelAdjusted": True,
            "note": ("current approach lean vs league (level-adjusted); zone-metric history "
                     "isn't archived yet, so no development drift")}


# ============================================================================
# Panel 11 — similar farms (tendency-vector cosine)
# ============================================================================

# (panel key, z-field) pairs composing the similarity vector. Null → 0
# (league-typical). All already z-normalized so no rescaling needed.
SIM_FEATURES = (
    ("promotion", "zYoung"), ("promotion", "zPromo"),
    ("promotion", "zDebutAgePit"), ("promotion", "zDebutAgeHit"),
    ("draftPos", "zPitch"), ("draftPos", "zPrep"), ("draftPos", "zColl"), ("draftPos", "zUpMid"),
    ("slot", "zOver"), ("slot", "zBonusHHI"), ("slot", "zPrepDollar"),
    ("arsenal", "zVelo"),
    ("ifa", "zConc"), ("ifa", "zVolume"),
    ("trades", "zVolume"), ("trades", "zNet"), ("trades", "zQuality"),
    ("health", "z"),
    ("graduation", "zWar"), ("graduation", "zHitRate"),
)
# Human labels for the shared-dimension chips on the UI.
SIM_FEATURE_LABELS = {
    "promotion.zYoung": "young-for-level", "promotion.zPromo": "promotes often",
    "promotion.zDebutAgePit": "arm debut age", "promotion.zDebutAgeHit": "bat debut age",
    "draftPos.zPitch": "drafts pitching", "draftPos.zPrep": "drafts prep",
    "draftPos.zColl": "drafts college", "draftPos.zUpMid": "up-the-middle",
    "slot.zOver": "over-slot", "slot.zBonusHHI": "top-heavy pool", "slot.zPrepDollar": "prep $",
    "arsenal.zVelo": "fastball velo",
    "ifa.zConc": "IFA concentration", "ifa.zVolume": "IFA volume",
    "trades.zVolume": "trade volume", "trades.zNet": "prospect acquirer", "trades.zQuality": "trades for quality",
    "health.z": "IL burden",
    "graduation.zWar": "graduate WAR", "graduation.zHitRate": "draft hit rate",
}


def similar_farms_panel(payload: dict) -> dict:
    """Most-similar farms by tendency overlap: cosine similarity over the
    SIM_FEATURES z-vector. Per org, the top 4 nearest plus the 2-3 shared
    same-sign dimensions driving the match."""
    fnames = [f"{p}.{f}" for p, f in SIM_FEATURES]
    orgs = list(payload["promotion"]["orgs"].keys())
    vecs: dict[str, list[float]] = {}
    for org in orgs:
        v = []
        for panel, field in SIM_FEATURES:
            cell = (payload.get(panel, {}).get("orgs", {}) or {}).get(org, {})
            x = cell.get(field)
            v.append(float(x) if isinstance(x, (int, float)) else 0.0)
        vecs[org] = v

    def cos(a, b):
        num = sum(x * y for x, y in zip(a, b))
        da = math.sqrt(sum(x * x for x in a))
        db = math.sqrt(sum(y * y for y in b))
        return num / (da * db) if da and db else 0.0

    out = {}
    for org in orgs:
        sims = sorted(((o, cos(vecs[org], vecs[o])) for o in orgs if o != org),
                      key=lambda kv: -kv[1])
        top = []
        for other, s in sims[:4]:
            shared = []
            for i, fn in enumerate(fnames):
                a, b = vecs[org][i], vecs[other][i]
                if a and b and (a > 0) == (b > 0) and abs(a) >= 0.5 and abs(b) >= 0.5:
                    shared.append((fn, a * b, a, b))
            shared.sort(key=lambda t: -t[1])
            top.append({"org": other, "score": round(s, 3),
                        "shared": [{"feature": fn, "label": SIM_FEATURE_LABELS.get(fn, fn),
                                    "a": round(av, 2), "b": round(bv, 2)}
                                   for fn, _p, av, bv in shared[:3]]})
        out[org] = {"similar": top}
    return {"orgs": out, "features": fnames}


# ============================================================================
# Payload
# ============================================================================

def _filter_mlb30(panel: dict, mlb30: set) -> dict:
    """Foreign-league and stale org codes (postings, renames) never get a
    tendencies page — every panel is filtered to the 30 live MLB orgs."""
    panel["orgs"] = {o: r for o, r in panel["orgs"].items() if o in mlb30}
    return panel


def build_payload() -> dict:
    players = _timeseries_players()
    debuts = _load_debuts()
    mlbam_org = _mlbam_org_map(players, debuts)
    by_org = _actives_by_org(players)
    mlb30 = set(by_org)
    with storage.connect() as con:
        draft_pos, draft_traits, slot = draft_panels(con)
        promotion = promotion_panel(by_org, debuts, date.today())
        try:
            pt_debuts, pt_cutoffs = promotion_timing_debuts(date.today())
            timing = promotion_timing_panel(pt_debuts, promotion_timing_aggr_rows(con, mlb30),
                                            pt_cutoffs, mlb30)
        except Exception as exc:                            # noqa: BLE001
            log.warning("promotion timing panel skipped: %s", exc)
            timing = {"orgs": {}, "league": {}}
        align_promotion_label(promotion, timing)
        payload = {
            "generated_at": date.today().isoformat(),
            "windows": {"draft": f"{DRAFT_FIRST_YEAR}-present",
                        "trades": f"{TRADE_FIRST_DATE[:4]}-present",
                        "gradeHistory": "2017-present (same-source snapshot pairs)",
                        "promotion": "active roster, trailing 365d",
                        "promotionTiming": f"MLB debuts {PT_FIRST_SEASON}-present (current rookie rule); age for level {PT_AGGR_FIRST_SEASON}-present",
                        "graduation": f"debuts; draft hit rate {DRAFT_FIRST_YEAR}-present",
                        "approach": "current active hitters (zone metrics; no history)"},
            "promotion": promotion,
            "promotionTiming": timing,
            "draftPos": _filter_mlb30(draft_pos, mlb30),
            "draftTraits": _filter_mlb30(draft_traits, mlb30),
            "slot": _filter_mlb30(slot, mlb30),
            "arsenal": _filter_mlb30(arsenal_panel(con, players, debuts, mlbam_org), mlb30),
            "pitchStuff": _filter_mlb30(pitch_stuff_panel(con, players, debuts, mlbam_org), mlb30),
            "toolDev": _filter_mlb30(tool_dev_panel(con, dev_calendars(con, players, debuts)), mlb30),
            "ifa": _filter_mlb30(ifa_panel(), mlb30),
            "trades": _filter_mlb30(trades_panel(con, mlb30), mlb30),
            "health": health_panel(con, by_org),
            "graduation": _filter_mlb30(graduation_panel(con, debuts), mlb30),
            "hitterApproach": _filter_mlb30(hitter_approach_panel(players), mlb30),
            "notes": [
                "every value is league-relative: z = (org minus league mean) / league sd across the 30 orgs; labels fire at |z| >= 0.5, except the promotion badge, which needs a tested difference (BH q < 0.10, CI95 clear of the league)",
                "arsenal BLENDS the MLB arsenals of an org's graduates with the Savant-minors arsenals of its current AAA arms (each arm counted once); the table is the average arm's pitch mix vs league. about half of AAA arms can't be org-attributed, so the AAA arm count is partial, disclosed per org",
                "pitchStuff: per-pitch velo + arm-side movement (AAA Gameday pfx) vs league; velo blends AAA + MLB",
                "toolDev measures grade drift per prospect-year inside the org from SAME-SOURCE snapshot pairs (>=60d apart); cross-source noise never counts as development; the club on each date comes from the player's org tenures (dated transactions), and a pair that spans a club change is split by days between the clubs",
                "graduation counts each graduate at the clubs that developed him, by development share (graduate-equivalents), not at the club he plays for now",
                "SC+ drift covers the platform's metric-snapshot window only (2026-05 onward), an early read, labeled as such",
                "trade quality/depth grades acquired prospects from board snapshots within 120 days of the trade; ungraded moves count toward volume only",
                "graduation draft-hit-rate denominator is signed picks 2021+ (little MLB runway for recent classes; read the z, not the absolute)",
                "hitterApproach is a current level-adjusted LEAN vs league, not a development drift (zone-metric history isn't archived)",
            ],
        }
        payload["similarFarms"] = _filter_mlb30(similar_farms_panel(payload), mlb30)
    return payload


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    OUT_PATH.write_text(raw, encoding="utf-8")
    log.info("org tendencies export: %dKB, %d orgs",
             len(raw) // 1024, len(payload["promotion"]["orgs"]))
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
