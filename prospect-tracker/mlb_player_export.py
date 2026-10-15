# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB player detail export - the per-player payload behind the
/projections/ player pages (and the FA board's player links).

Prospects have full PROSPX detail pages; until now MLB players only had
board rows. This sidecar gives every projections veteran and every
FA-class member a real page: identity + contract chips, the projection
path with bands, season-by-season career lines with eWAR, Savant
percentile sliders, pitch arsenal (pitchers), and Swing+ (hitters,
Will Cahoon's model via data/swing_plus.json).

  UNIVERSE   union of mlb_projections.json vets and fa_class.json
             members, keyed by the platform's normalized name key.
             mlbam: vets carry it (proj_export emits it); FA members
             resolve through fa_ident's war_daily identity index.
  CAREER     MLB season lines 2014+ from the cached StatsAPI ladder
             (milb_history sport 1) + per-season WAR from war_daily
             (pybaseball cache) through the war_source facade on provider
             ewar_v2 by name, the displayed WAR (bWAR is the input frame and
             rides beside the served number as war_bwar where the two
             differ; FanGraphs' published WAR rides as war_fwar on every row
             the frozen fWAR vintage covers, a reference only), joined on
             mlbam.
  STATCAST   Savant MLB leaderboards per season (statcast + expected_
             statistics + pitch-arsenal-stats), cached under
             .cache/savant_mlb/. Percentiles computed within the
             latest qualified season pool - the same Savant-style
             slider data prospect cards carry.
  SWING+     joined from data/swing_plus.json where scored (MLB bat
             tracking 2024+ only - the documented boundary).
  AAA STUFF+ joined from data/stuff_plus_aaa.json for ex-PROSPX
             pitchers (the in-house pitch-quality model; origin gate
             keeps vets' rehab-stint AAA pitches off their pages).
  SKILLS     the /mlbstats/ boards joined by mlbam (_skill_index): HEM+,
             REM+/RIV+/SEM+, leverage (skills.lev) and the Defense board's
             DEM+ with published defensive runs (skills.def).
  HOF        the /hof/ shelf's row (career bWAR, WAR7, JAWS, WAA+, WAR ink)
             for its Cooperstown Watch and Not Yet Eligible bands, B-Ref id
             to MLBAM through the war_daily ids (_hof_index).

Artifacts: data/mlb_player_detail.json (the whole set, read by the Trade
Machine and the Python consumers) and data/mlb_player_detail/<key>.json, one
card per player with the board's first_season and horizon, which a
/projections/#player= page fetches at boot instead of the whole set (QMLP01).
Wired into run_monthly after proj_export.

Run: python mlb_player_export.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import statistics
import time
import urllib.request
from datetime import date
from pathlib import Path

import milb_history as mh
from scrapers import normalize_key

try:                                    # site-wide copy rule: no em/en-dashes
    from tools.strip_emdashes import strip_emdashes
except Exception:                       # noqa: BLE001 - normalizer is optional
    def strip_emdashes(text: str) -> str:
        return text.replace("—", "-").replace("–", "-")

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "mlb_player_detail.json"
SHARD_DIRNAME = "mlb_player_detail"   # data/mlb_player_detail/<key>.json
CACHE_DIR = ROOT / ".cache" / "savant_mlb"
# The component lines proj_export writes once PROJ_COMPONENTS_LIVE is True
# (task PJ_6; proj_export.COMPONENTS_LIVE_PATH). Read only when the board
# payload says components_live, and copied verbatim into proj.comp of the
# PER-CARD SHARD only (owner answer PJ6-SIZE (a), 2026-10-14): the whole-set
# payload the Trade Machine and the Python readers load never carries it.
COMPONENTS_PATH = DATA_DIR / "mlb_proj_components.json"
#: {card key: component block} of the last build_payload, for _export_shards.
_SHARD_COMP: dict[str, dict] = {}


def _component_rows(proj: dict) -> dict | None:
    """{board key: component block} when the board payload carries
    components_live, else None (the dark default: no card gains a key)."""
    if not proj.get("components_live"):
        return None
    try:
        doc = json.loads(COMPONENTS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("mlb player export: components_live but %s unreadable", COMPONENTS_PATH.name)
        return {}
    return doc.get("rows") or {}

CAREER_FROM = 2014
LB = {
    "statcast": ("https://baseballsavant.mlb.com/leaderboard/statcast"
                 "?type={side}&year={year}&csv=true&min=25"),
    "expected": ("https://baseballsavant.mlb.com/leaderboard/expected_statistics"
                 "?type={side}&year={year}&csv=true&min=25"),
    "arsenal": ("https://baseballsavant.mlb.com/leaderboard/pitch-arsenal-stats"
                "?type=pitcher&year={year}&csv=true&min=10"),
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


_SAVANT_LIVE_TTL_S = 24 * 3600   # current-season CSVs refresh daily; past seasons are final


def _savant(kind: str, year: int, side: str = "batter") -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{kind}_{side}_{year}.csv"
    # Past seasons are immutable -> cache forever. The CURRENT season's leaderboard
    # moves daily; a forever-cache froze xwOBA/xERA (and every xHEM+/xREM+/xSEM+
    # deserved-stat join downstream) at whatever day the file first landed, so the
    # in-season file gets a TTL. A failed refresh falls back to the stale file
    # (better than dropping the join).
    stale = False
    if path.exists() and year >= date.today().year:
        try:
            stale = (time.time() - path.stat().st_mtime) > _SAVANT_LIVE_TTL_S
        except OSError:
            stale = False
    if not path.exists() or stale:
        url = LB[kind].format(side=side, year=year)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        except Exception as e:                                # noqa: BLE001
            log.warning("savant %s/%s/%s failed: %s", kind, side, year, e)
            if not path.exists():
                return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _pct_rank(pool: list[float], v: float, invert: bool = False) -> int:
    if not pool:
        return 50
    below = sum(1 for x in pool if x < v) + 0.5 * sum(1 for x in pool if x == v)
    p = below / len(pool)
    if invert:
        p = 1 - p
    return int(round(p * 100))


def _statcast_block(mlbam: int, is_pitcher: bool, year: int) -> dict | None:
    """Savant-style percentile sliders for the latest qualified season.
    Pitcher contact metrics invert (suppression is good)."""
    side = "pitcher" if is_pitcher else "batter"
    for y in range(year, year - 3, -1):
        sc = _savant("statcast", y, side)
        ex = _savant("expected", y, side)
        sc_by = {r.get("player_id"): r for r in sc if r.get("player_id")}
        ex_by = {r.get("player_id"): r for r in ex if r.get("player_id")}
        me_sc = sc_by.get(str(mlbam))
        me_ex = ex_by.get(str(mlbam))
        if not me_sc and not me_ex:
            continue
        out = {"season": y, "metrics": []}

        def add(label, rows_by, row, col, fmt, invert=False):
            if not row:
                return
            v = _f(row.get(col))
            if v is None:
                return
            pool = [x for x in (_f(r.get(col)) for r in rows_by.values())
                    if x is not None]
            out["metrics"].append({
                "label": label, "value": fmt.format(v),
                "pct": _pct_rank(pool, v, invert=invert if is_pitcher else False)})

        add("Exit Velo" if not is_pitcher else "EV Against", sc_by, me_sc,
            "avg_hit_speed", "{:.1f}", invert=True)
        add("Hard-Hit%" if not is_pitcher else "Hard-Hit% Against", sc_by, me_sc,
            "ev95percent", "{:.1f}%", invert=True)
        add("Barrel%" if not is_pitcher else "Barrel% Against", sc_by, me_sc,
            "brl_percent", "{:.1f}%", invert=True)
        add("xwOBA" if not is_pitcher else "xwOBA Against", ex_by, me_ex,
            "est_woba", "{:.3f}", invert=True)
        add("xBA" if not is_pitcher else "xBA Against", ex_by, me_ex,
            "est_ba", "{:.3f}", invert=True)
        # Deserved power + luck (HITTER-SIDE display only; xwOBA-allowed vs FIP was
        # tested and rejected for the pitcher models, so no pitcher claim here).
        # xSLG is a Savant column; xISO = xSLG - xBA (deserved isolated power);
        # Luck = deserved minus actual wOBA (positive = the contact deserved
        # more), the sign the xHEM+ glossary entry and /mlbstats/ luck_gap use.
        # Its pct ranks that same gap, so a high pct is a large positive gap.
        if not is_pitcher:
            add("xSLG", ex_by, me_ex, "est_slg", "{:.3f}")
            if me_ex is not None:
                xslg, xba = _f(me_ex.get("est_slg")), _f(me_ex.get("est_ba"))
                if xslg is not None and xba is not None:
                    xiso_pool = [s - b for s, b in
                                 ((_f(r.get("est_slg")), _f(r.get("est_ba"))) for r in ex_by.values())
                                 if s is not None and b is not None]
                    out["metrics"].append({
                        "label": "xISO", "value": "{:.3f}".format(xslg - xba),
                        "pct": _pct_rank(xiso_pool, xslg - xba)})
                woba, xwoba = _f(me_ex.get("woba")), _f(me_ex.get("est_woba"))
                if woba is not None and xwoba is not None:
                    luck_pool = [x - w for w, x in
                                 ((_f(r.get("woba")), _f(r.get("est_woba"))) for r in ex_by.values())
                                 if w is not None and x is not None]
                    out["metrics"].append({
                        "label": "Luck (xwOBA-wOBA)", "value": "{:+.3f}".format(xwoba - woba),
                        "pct": _pct_rank(luck_pool, xwoba - woba)})
        return out if out["metrics"] else None
    return None


def _arsenal_block(mlbam: int, year: int) -> list[dict] | None:
    for y in range(year, year - 3, -1):
        rows = [r for r in _savant("arsenal", y, "pitcher")
                if r.get("player_id") == str(mlbam)]
        if rows:
            out = []
            for r in sorted(rows, key=lambda x: -(_f(x.get("pitch_usage")) or 0)):
                out.append({
                    "pitch": r.get("pitch_name"),
                    "usage": _f(r.get("pitch_usage")),
                    "rv100": _f(r.get("run_value_per_100")),
                    "whiff": _f(r.get("whiff_percent")),
                    "ba": _f(r.get("ba")),
                })
            return out[:6]
    return None


def _career_rows(mlbam: int, is_pitcher: bool,
                 war_by: dict[int, dict[int, dict[str, float]]],
                 war_bwar_by: dict[int, dict[int, dict[str, float]]] | None = None,
                 war_fwar_by: dict[int, dict[int, dict[str, float]]] | None = None
                 ) -> list[dict]:
    group = "pitching" if is_pitcher else "hitting"
    out = []
    for season in range(CAREER_FROM, date.today().year + 1):
        rows = [r for r in (mh.player_index(season, group).get(mlbam) or [])
                if r.get("level") == "MLB"]
        if not rows:
            continue
        r = max(rows, key=lambda x: _f(x.get("bf" if is_pitcher else "pa")) or 0)
        # Side-specific bWAR (batting vs pitching kept separate) so a two-way arm or a
        # position player's mop-up inning doesn't fold pitching WAR into the hitting row.
        _sw = (war_by.get(mlbam) or {}).get(season) or {}
        war = _sw.get("pit" if is_pitcher else "bat")
        # war_bwar: the bWAR input beside the served WAR, carried only where
        # the two differ at display precision (1dp). That is pitcher rows
        # under the FIP re-pricing; a position player's row never carries it
        # until the SDR defense drop (eWAR == bWAR there). Absent means equal.
        _ref = ((war_bwar_by or {}).get(mlbam) or {}).get(season) or {}
        war_bwar = _ref.get("pit" if is_pitcher else "bat")
        extra = {}
        if (war is not None and war_bwar is not None
                and round(war, 1) != round(war_bwar, 1)):
            extra["war_bwar"] = round(war_bwar, 1)
        # war_fwar: FanGraphs' published WAR for this season and side, a
        # reference beside the displayed eWAR v2 (owner answer EPOCH-Q4). Unlike
        # war_bwar it rides on EVERY row the published vintage covers, so an
        # absent war_fwar always means "no published value", never "equal".
        # Display only: never a sort key, a model input or a derived stat.
        _fw = (((war_fwar_by or {}).get(mlbam) or {}).get(season) or {}).get(
            "pit" if is_pitcher else "bat")
        if _fw is not None:
            extra["war_fwar"] = round(_fw, 1)
        if is_pitcher:
            bf = _f(r.get("bf")) or 0
            so, bb = _f(r.get("so")), _f(r.get("bb"))
            out.append({"y": season, "ip": r.get("ip"), "era": _f(r.get("era")),
                        "kPct": round(so / bf * 100, 1) if so is not None and bf else None,
                        "bbPct": round(bb / bf * 100, 1) if bb is not None and bf else None,
                        "war": round(war, 1) if war is not None else None,
                        **extra})
        else:
            pa = _f(r.get("pa")) or 0
            so, bb = _f(r.get("so")), _f(r.get("bb"))
            slg, avg = _f(r.get("slg")), _f(r.get("avg"))
            out.append({"y": season, "pa": int(pa), "avg": r.get("avg"),
                        "obp": r.get("obp"), "slg": r.get("slg"),
                        "ops": r.get("ops"), "hr": r.get("hr"), "sb": r.get("sb"),
                        "kPct": round(so / pa * 100, 1) if so is not None and pa else None,
                        "bbPct": round(bb / pa * 100, 1) if bb is not None and pa else None,
                        "iso": round(slg - avg, 3) if slg is not None and avg is not None else None,
                        "war": round(war, 1) if war is not None else None,
                        **extra})
    return out


def _war_daily() -> dict[int, dict[int, dict[str, float]]]:
    """{mlbam: {season: {"bat": WAR, "pit": WAR}}} -- batting and pitching WAR kept
    on SEPARATE keys (they used to be summed onto one number and attached to both the
    hitting and pitching career rows, distorting two-way players and position-player
    pitching cameos).

    THE FACADE'S DELEGATE, NOT A SURFACE READ. war_source.side_war_by_season
    calls this under _frames_pinned('bwar') for BOTH providers, so here the
    stint frames are raw bWAR and this is the bWAR map the facade overlays
    eWAR on. Called bare it sums whatever stint_frame serves on the process
    default (eWAR v2 since 2026-09-03: per (mlb_ID, year_ID) the stint WARs
    sum to the artifact's side total). build_payload reads the facade
    (_war_maps), never this directly."""
    import pybaseball  # noqa: F401 - availability probe; frames come via war_source
    import war_source
    out: dict[int, dict[int, dict[str, float]]] = {}
    for side in ("bat", "pit"):
        try:
            df = war_source.stint_frame(side)
        except Exception:                                      # noqa: BLE001
            continue
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid, yr, war = int(row.mlb_ID), int(row.year_ID), float(row.WAR)
            except (TypeError, ValueError):
                continue
            cell = out.setdefault(mid, {}).setdefault(yr, {})
            cell[side] = cell.get(side, 0.0) + war
    return out


def _war_maps() -> tuple[dict, dict]:
    """(served, reference): two side maps from the war_source facade.

    served     side_war_by_season() on the DEFAULT provider: eWAR v2 since the
               2026-09-03 basis decision (pitching re-priced on FIP within
               role; the batting side equals bWAR until the SDR defense drop).
    reference  side_war_by_season(provider='bwar'), the input frame, so a card
               can show bWAR beside the served WAR (tooltip). The same object
               as `served` when the default IS bwar, so the reference costs a
               second war_daily read only under a non-bwar default.

    Both are {mlbam: {season: {"bat": w, "pit": w}}}; the facade keeps the
    served key set a superset of the reference's (coverage never shrinks).

    DISPLAY DOOR (fWAR label epoch step D + U, 2026-10-03): the served map is
    eWAR v2 by name (owner answer EPOCH-Q4 "Keep eWAR v2 shown"), never
    war_source.DEFAULT_PROVIDER, which is now the training label (fWAR). An fWAR
    reference column beside it is its own later task (EPOCH_FWAR_REFERENCE_COLUMN)."""
    import war_source
    served = war_source.side_war_by_season(provider="ewar_v2")
    return served, war_source.side_war_by_season(provider="bwar")


def _fwar_reference_map() -> dict[int, dict[int, dict[str, float]]]:
    """{mlbam: {season: {"bat": w, "pit": w}}}: FanGraphs' published WAR, the
    reference column beside the displayed eWAR v2 (owner answer EPOCH-Q4, task
    EPOCH_FWAR_REFERENCE_COLUMN). A REFERENCE ONLY: the served `war` stays
    eWAR v2 (_war_maps), and nothing here feeds a rank, sort, model or stat.

    Values come from war_source.side_war_by_season(provider="fwar"), kept ONLY
    on the (mlbam, season, side) cells the frozen vintage publishes
    (fwar_vintage.side_targets). The provider fills every other cell with the
    incumbent eWAR v2 value, and that fallback must never be printed under a
    FanGraphs label, so a cell outside the vintage, or one the provider's
    blank-row rule skipped, is absent: absent means no published value.

    Empty (logged) when the vintage cannot serve, so a missing vintage drops
    the reference column and never the card."""
    import fwar_vintage
    import war_source
    try:
        provider = war_source.side_war_by_season(provider="fwar")
        blob = fwar_vintage.load()
    except war_source.DataUnavailable as e:
        log.warning("mlb player detail: no fWAR reference column (%s)", e)
        return {}
    out: dict[int, dict[int, dict[str, float]]] = {}
    for side in ("bat", "pit"):
        for mid, season in fwar_vintage.side_targets(blob, side):
            val = ((provider.get(mid) or {}).get(season) or {}).get(side)
            if val is None:
                continue
            out.setdefault(mid, {}).setdefault(season, {})[side] = float(val)
    return out


#: The two /hof/ bands a player page can carry: active players with ten or more
#: seasons, and players inside the five-year wait. The Eligible band is retired
#: players, who have no /projections/ page.
HOF_BANDS = ("watch", "not_yet_eligible")
#: The shelf fields the line prints, copied verbatim (no rounding, no
#: re-derivation), so the page and /hof/ cannot disagree about one player.
HOF_FIELDS = ("war", "war7", "jaws", "waa_pos", "ink", "first", "last", "seasons")
HOF_BASIS_LABEL = "B-Ref bWAR"


def _hof_index() -> dict[int, dict]:
    """{mlbam: hof line}: the /hof/ shelf's own row for every player on its
    Cooperstown Watch and Not Yet Eligible bands (wiring W05, task Q9_25).

    THE SHELF'S NUMBERS, NOT OURS. Every value is the hof_board.json row for the
    same B-Ref id, copied verbatim, so the line and /hof/ always agree. The
    basis is Baseball-Reference bWAR, the shelf's pinned frame, and the block
    says so in `basis`; a shelf on any other basis prints no line at all,
    because a label we cannot name is a label we would get wrong.

    THE JOIN. The shelf keys rows by B-Ref id; the cards key by MLBAM id. The
    bridge is hof_data.crosswalk_bbref_mlbam(), read off the same war_daily
    parquets the shelf is built from, one to one (no name matching). A row the
    bridge cannot reach prints nothing.

    NO POSITION STANDARD. The shelf's six position groups have no 3B group and
    put Albert Pujols and Miguel Cabrera in OF, so the line carries the
    player's own numbers only. The band is a shelf band, not a forecast: the
    /hof/ predictor stays dark.

    Empty (logged) when the shelf or the bridge is unreadable: the card renders
    without the line."""
    try:
        hb = json.loads((DATA_DIR / "hof_board.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("mlb player detail: hof_board.json unavailable - no Hall of Fame line")
        return {}
    basis = str((hb.get("basis") or {}).get("war") or "")
    if "Baseball-Reference bWAR" not in basis:
        log.warning("mlb player detail: hof shelf basis %r is not bWAR - no Hall of "
                    "Fame line until the label follows it", basis[:60])
        return {}
    try:
        import hof_data
        xw = hof_data.crosswalk_bbref_mlbam()          # {str(mlbam): bbref id}
    except Exception as e:                             # noqa: BLE001
        log.warning("mlb player detail: no bbref-mlbam bridge (%s) - no Hall of Fame line", e)
        return {}
    by_bbref: dict[str, int] = {}
    for mid, bid in xw.items():
        try:
            by_bbref[str(bid)] = int(mid)
        except (TypeError, ValueError):
            continue
    out: dict[int, dict] = {}
    for band in HOF_BANDS:
        for r in hb.get(band) or []:
            mid = by_bbref.get(str(r.get("id")))
            if mid is None:
                continue
            out[mid] = {"id": r.get("id"), "band": band, "basis": HOF_BASIS_LABEL,
                        **{k: r.get(k) for k in HOF_FIELDS}}
    return out


def _ident_mlbams(keys: list[str]) -> dict[str, int]:
    """key -> mlbam via the war_daily identity index (single-candidate
    matches only - ambiguous names stay unresolved and the page renders
    without statcast/career joins). Covers vets exported before
    proj_export carried mlbam, and every FA member."""
    import fa_ident
    idx = fa_ident.war_daily_index()
    out = {}
    for key in keys:
        cands = idx.get(key) or {}
        if len(cands) == 1:
            out[key] = next(iter(cands))
    return out


def _is_pitcher_pos(pos: str | None) -> bool:
    return str(pos or "").upper().split("/")[0].strip() in (
        "P", "SP", "RP", "LHP", "RHP", "SP2", "CL", "SIRP", "MIRP")


def _fv_spark(points: list, cap: int = 40) -> list | None:
    """Compact consensus-FV arc [[date, fv], ...] from a debut row's points[]
    (the same series the PROSPX FV-history chart draws). Downsampled to `cap`
    points if longer, always keeping the first and last snapshot."""
    spark = []
    for pt in points or []:
        dt = pt.get("snapshot_date")
        fv = pt.get("consensus_fv_raw")
        if dt and fv is not None:
            try:
                spark.append([dt, round(float(fv), 1)])
            except (TypeError, ValueError):
                continue
    if len(spark) <= 1:
        return spark or None
    if len(spark) > cap:
        step = (len(spark) - 1) / (cap - 1)
        idx = sorted({int(round(i * step)) for i in range(cap)} | {len(spark) - 1})
        spark = [spark[i] for i in idx]
    return spark


def _debut_origins() -> dict[int, dict]:
    """{mlbam: prospect origin} from debuts.json - the PROSPX identity, the FV
    arc endpoints + full consensus-FV spark, and the consensus tool grades for
    ex-prospects (the scouting slice + hero sparkline sources), plus the
    graduate bridge: the eFV at debut (xfv.json) and the club he debuted with."""
    out: dict[int, dict] = {}
    try:
        for d in json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8")):
            if d.get("mlbam_id"):
                tools = ((d.get("tools") or {}).get("grades")) or None
                out[int(d["mlbam_id"])] = {
                    "prospx": d.get("player_key"),
                    "fvOpen": d.get("fv_open"),
                    "fvClose": d.get("fv_close"),
                    "debut": d.get("debut_date"),
                    "fvSpark": _fv_spark(d.get("points")),
                    "tools": {k: v for k, v in tools.items() if v is not None} if tools else None,
                    "devOrg": _graduate_org(d),
                }
    except (OSError, ValueError):
        log.warning("mlb player export: debuts.json unavailable - no origins")
    efv = _efv_at_debut()
    for org in out.values():
        org["efvDebut"] = efv.get(org.get("prospx"))
    return out


# ---- the PROSPX graduate bridge (wiring W06) --------------------------------
# A graduate's MLB card says what PROSPX said before he arrived: the eFV he
# carried into the majors, the club he debuted with and his final tracked-park
# Statcast hitter line. Each is one player's own number, already served on
# PROSPX; nothing here groups players by a grade (docs/PROSPECT_ANCHOR_GATE.md).
_CLUB_RE = re.compile(r"^[A-Z]{2,3}$")


def _graduate_org(d: dict) -> str | None:
    """The club he debuted with, by the homepage On This Day rule
    (build_site._debut_org: the debut-season MLB stat row, never the current
    org). None when that resolves to no club code (the old placeholder rows
    carry "Office of the Commissioner")."""
    try:
        from build_site import _debut_org
        org = _debut_org(d)
    except Exception:                    # noqa: BLE001 - the org is optional
        return None
    return org if isinstance(org, str) and _CLUB_RE.match(org) else None


def _efv_at_debut() -> dict[str, float]:
    """{player_key: xfv_grade_at_debut} from data/xfv.json: the eFV grade the
    player carried into the majors (efv_score.run_backgrade writes it; the WAG
    baseline pins to the same field). Never the served grade, which the rookie
    window may have moved past the debut."""
    try:
        doc = json.loads((DATA_DIR / "xfv.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("mlb player export: xfv.json unavailable - no eFV at debut")
        return {}
    out: dict[str, float] = {}
    for key, row in ((doc or {}).get("by_player") or {}).items():
        v = (row or {}).get("xfv_grade_at_debut")
        if isinstance(v, (int, float)):
            out[key] = float(v)
    return out


def _aaa_hitter_lines() -> dict[int, dict]:
    """{mlbam: final tracked-park Statcast hitter line} from
    data/statcast_aaa_hitters.json, the PROSPX hitter card's sidecar: the
    player's latest season with 100+ PA in a tracked park (every AAA park and
    the Single-A Florida State League), its level(s), and the date its games
    run through (source_through) or the date a same-season CSV was fetched
    (source_fetched), so a partial season never reads as the full one. The
    luck gap is left out: a card number takes no forecast word."""
    try:
        doc = json.loads((DATA_DIR / "statcast_aaa_hitters.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("mlb player export: statcast_aaa_hitters.json unavailable - no AAA lines")
        return {}
    through = (doc or {}).get("source_through") or {}
    fetched = (doc or {}).get("source_fetched") or {}
    out: dict[int, dict] = {}
    for mid, r in ((doc or {}).get("by_mlbam") or {}).items():
        season = (r or {}).get("season")
        if not str(mid).isdigit() or season is None:
            continue
        line = {"season": season, "levels": r.get("levels") or None, "pa": r.get("pa"),
                "xwoba": r.get("xwoba"), "ev": r.get("ev"),
                "hardHit": r.get("hardhit_percent"), "whiff": r.get("whiff")}
        thru, got = through.get(str(season)), fetched.get(str(season))
        if thru and str(thru)[:4] == str(season):
            line["thru"] = thru
        elif got and str(got)[:4] == str(season):
            line["asOf"] = got
        out[int(mid)] = {k: v for k, v in line.items() if v is not None}
    return out


_SCOUT_SRC_LABELS = {"fangraphs": "FanGraphs", "mlb_pipeline": "MLB Pipeline",
                     "espn": "ESPN", "just_baseball": "Just Baseball"}


def _scout_report_slice(prospx: str, reports: dict) -> dict | None:
    """The single most-recent published scouting report for an ex-PROSPX player,
    as the excerpt plus source link the scout_reports sidecar carries (owner
    answer 2026-09-25, census X07-02 option b; report_excerpt.py). NEVER bakes
    the whole report set; one latest excerpt per player only."""
    from report_excerpt import report_excerpt
    rec = reports.get(prospx)
    if not rec:
        return None
    best = None   # (date, source_key, entry)
    for src in _SCOUT_SRC_LABELS:
        for it in rec.get(src) or []:
            txt = (it.get("text") or "").strip()
            if not txt:
                continue
            dt = it.get("date") or ""
            if best is None or dt > best[0]:
                best = (dt, src, it)
    if not best:
        return None
    dt, src, it = best
    # The sidecar text is already an excerpt; cutting again is a no-op there and
    # keeps an older full-text sidecar from reaching the card.
    txt, cut = report_excerpt(it.get("text"))
    txt = strip_emdashes(txt)           # verbatim quote, dash-normalized to site policy
    out = {"source": _SCOUT_SRC_LABELS.get(src, src), "date": dt or None,
           "label": it.get("label"), "url": it.get("url"),
           "text": txt, "truncated": bool(cut or it.get("truncated"))}
    # No page of the player's own: the publisher's list page the sidecar
    # carries (owner answer 2026-10-01, REPEX-1 option b).
    if not out["url"] and it.get("list_url"):
        out["list_url"] = it.get("list_url")
        out["list_page"] = bool(it.get("list_page"))
    return out


def _record_skill_index_outage(missing: list[str], n_joined: int) -> None:
    """Raise an unreadable leaderboard into the ingest-health RED ledger.

    The join is silent by construction: every consumer of this index reads it
    with `.get()`, so a leaderboard that failed to load costs the HEM+/REM+/
    SEM+/leverage tiles on EVERY MLB player card and produces a card payload
    that is structurally perfect. Nothing else in the pipeline reads these
    files back at bake time, so without this row there is no other place the
    outage shows up.

    Filed through bullpen_export.record_ingest rather than importing
    run_monthly directly: under the deploy launch shape (`python
    run_monthly.py`) the live pipeline is sys.modules["__main__"] and a plain
    import builds a second module with a ledger nothing drains. The other half
    of the claim is that "mlb_card_skill_index" is named in
    run_monthly.SCHEDULED_EXPORTS, or the row is filed and then dropped from
    red[] at drain time. Best-effort: reporting never fails an export."""
    try:
        from bullpen_export import record_ingest
        record_ingest(
            "mlb_card_skill_index", ok=False, n_rows=n_joined,
            message=(f"unreadable /mlbstats/ leaderboard(s): {', '.join(missing)}. "
                     f"Only {n_joined} players joined a skill block, so the tiles "
                     f"those files feed are blank on every MLB player card."))
    except Exception:                      # noqa: BLE001
        log.debug("could not record the skill-index outage row", exc_info=True)


def _skill_index() -> dict[int, dict]:
    """{mlbam: {"hem" | "pitch" | "lev" | "def": {...}}} from the /mlbstats/
    leaderboards (hitter HEM+, reliever REM+/RIV+, starter SEM+, leverage, and
    the Defense board), joined by MLBAM. Baked onto the card so it no longer
    client-fetches the whole leaderboard just to show a few tiles. Relievers
    take priority over starters for the rare swingman.

    "lev" is stored PER SIDE ({"bat": {...}, "sp": {...}}): one merged dict let
    a player on both boards have the starter row's None pLI and Clutch overwrite
    the batter row's values. _card_skills hands each card the side it renders."""
    out: dict[int, dict] = {}
    unreadable: list[str] = []

    def _load(fname):
        """None means the file could not be READ. That is a different fact from
        a leaderboard that legitimately holds no rows, and collapsing the two
        into {} is what let an unreadable artifact blank the skill tiles on
        every card with nothing anywhere saying so. The callers below still
        tolerate the absence (a card without tiles beats no card), but the run
        now reports it."""
        try:
            return json.loads((DATA_DIR / fname).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.error("mlb player export: %s is unreadable (%s); every tile it "
                      "feeds will be blank on every MLB player card this run",
                      fname, e)
            unreadable.append(fname)
            return None

    hd = _load("hitter_leaderboards.json") or {}
    h_season = hd.get("season")
    for r in hd.get("hitters") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        out.setdefault(mid, {})["hem"] = {
            "season": h_season,
            "hemPlus": r.get("hem_plus"), "hemPlus3yr": r.get("hem_plus_3yr"),
            "xhemPlus": r.get("xhem_plus"), "tier": r.get("tier"),
            # luckGap (the board's luck_gap) is no longer baked: it is xwOBA
            # minus wOBA in wOBA points since 2026-09-24, the card's Statcast
            # block already carries Savant's xwOBA-wOBA row, and the xHEM+
            # tile's "vs HEM+" note is computed client-side from the two dots.
            "qualified": bool(r.get("qualified")),
            # Baked 2026-07-30 (Lane B): every one of these was computed and served
            # on /mlbstats/ but absent from the player card, so a reader had to open
            # a different module to see the same player's own numbers.
            # WAR/PA+ is 100+10z, NOT the wRC+-width ratio scale HEM+ uses -- the
            # renderer must band it with remCell, never hemCell.
            "warPaPlus": r.get("war_pa_plus"), "warPaPlusAdj": r.get("war_pa_plus_adj"),
            "warPaPlusPct": r.get("war_pa_plus_pct"),
            "warPaPlus3yr": r.get("war_pa_plus_3yr"),
            "war": r.get("war"), "pa": r.get("pa"),
            "pwoba": r.get("pwoba"), "fwdhemPlus": r.get("fwdhem_plus"),
            "wrcPlus": r.get("wrc_plus")}

    bd = _load("bullpen_leaderboards.json") or {}
    b_season = bd.get("season")
    for r in bd.get("relievers") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        out.setdefault(mid, {})["pitch"] = {
            "kind": "rel", "season": b_season, "role": r.get("role"),
            "ip": r.get("ip"), "qualified": bool(r.get("qualified")),
            "remPlus": r.get("rem_plus"), "rivPlus": r.get("riv_plus"),
            "remPlus3yr": r.get("rem_plus_3yr"), "xremPlus": r.get("xrem_plus"),
            # Lane B bake. warIpPlus here is RELIEVER-anchored and is NOT comparable
            # with the starter block's field of the same name (separate pools, the
            # SEM+/REM+ precedent). gmLI and the save/hold counts are the deployment
            # story REM+ deliberately leaves out.
            "warIpPlus": r.get("war_ip_plus"), "warIpPlusAdj": r.get("war_ip_plus_adj"),
            "warIpPlusPct": r.get("war_ip_plus_pct"),
            "warIpPlus3yr": r.get("war_ip_plus_3yr"), "war": r.get("war"),
            "gmli": r.get("gmli"), "gmli3yr": r.get("gmli_3yr"),
            "saves": r.get("saves"), "holds": r.get("holds"),
            "wpa": r.get("wpa"), "sd": r.get("sd"), "md": r.get("md")}

    sd = _load("starter_leaderboards.json") or {}
    s_season = sd.get("season")
    for r in sd.get("starters") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        e = out.setdefault(mid, {})
        if "pitch" in e:            # reliever board already claimed this arm
            continue
        e["pitch"] = {
            "kind": "sp", "season": s_season, "role": r.get("role"),
            "ip": r.get("ip"), "qualified": bool(r.get("qualified")),
            "semPlus": r.get("sem_plus"), "semPlus3yr": r.get("sem_plus_3yr"),
            "xsemPlus": r.get("xsem_plus"),
            # Lane B bake. STARTER-anchored WAR/IP+; see the reliever note above for
            # why the two must never share a scale in the renderer.
            "warIpPlus": r.get("war_ip_plus"), "warIpPlusAdj": r.get("war_ip_plus_adj"),
            "warIpPlusPct": r.get("war_ip_plus_pct"),
            "warIpPlus3yr": r.get("war_ip_plus_3yr"), "war": r.get("war"),
            "ipPerGs": r.get("ip_per_gs"), "gs": r.get("gs")}
    # Two-way players: the board keeps them out of its pool, and the export scores
    # them against that pool for the card alone. cardOnly tells the renderer this
    # number has no board row behind it.
    for r in ((sd.get("two_way_card_only") or {}).get("starters") or []):
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        e = out.setdefault(mid, {})
        if "pitch" in e:
            continue
        e["pitch"] = {
            "kind": "sp", "season": s_season, "cardOnly": True,
            "ip": r.get("ip"), "qualified": bool(r.get("qualified")),
            "semPlus": r.get("sem_plus"), "ipPerGs": r.get("ip_per_gs"), "gs": r.get("gs")}

    # Leverage block (batters + starters), from the fourth /mlbstats/ board. Kept
    # OUT of the hem/pitch blocks on purpose: it is descriptive game-context, not a
    # skill index, and bundling it into "hem" would invite a renderer to band it on
    # a plus scale it does not share.
    ld = _load("leverage_leaderboards.json") or {}
    l_season = ld.get("season")
    for grp, key in (("batters", "bat"), ("starters", "sp")):
        for r in ld.get(grp) or []:
            try:
                mid = int(r.get("mlbam"))
            except (TypeError, ValueError):
                continue
            blk = {"kind": key, "season": l_season,
                   "wpa": r.get("wpa"), "wpaLi": r.get("wpa_li"),
                   "pli": r.get("pli"), "clutch": r.get("clutch"),
                   "wpaPerStart": r.get("wpa_per_start")}
            out.setdefault(mid, {}).setdefault("lev", {})[key] = {
                k: v for k, v in blk.items() if v is not None}

    # Defense block (fielders), from the Defense board. Its own key, never folded
    # into "hem" or "pitch": DEM+ is 100 + 10z (the WAR/PA+ ruler, bands
    # 93/107/120 on both the card and /mlbstats/), not the ratio ruler those
    # blocks band on. Fielding and framing runs are FanGraphs' published values
    # carried verbatim; posRuns (the term inside defRuns) is the board's own
    # positional ladder, and posRunsFg is FanGraphs' published positional, for
    # the card's comparison row. Only the columns the card renders ride along;
    # the board's lab columns (shrunk rate, reliability, HEM+ join, 3-year lab
    # output) stay on /mlbstats/.
    dd = _load("defense_leaderboards.json") or {}
    d_season = dd.get("season")
    for r in dd.get("fielders") or []:
        try:
            mid = int(r.get("mlbam"))
        except (TypeError, ValueError):
            continue
        blk = {"season": d_season, "pos": r.get("pos"), "inn": r.get("inn"),
               "posInn": r.get("pos_inn") or None,
               "qualified": bool(r.get("qualified")),
               "demPlus": r.get("dem_plus"), "demPlusPct": r.get("dem_plus_pct"),
               "demPlusPosPct": r.get("dem_plus_pos_pct"),
               "fldTotal": r.get("fld_total"), "frmRuns": r.get("frm_runs"),
               "posRuns": r.get("pos_runs"), "posRunsFg": r.get("pos_runs_fg"),
               "defRuns": r.get("def_runs")}
        out.setdefault(mid, {})["def"] = {k: v for k, v in blk.items() if v is not None}

    # Baserunning block (runners), from the Baserunning board (task
    # EBR_2_BUILD_DARK; integration.md 3.1), its own key beside def. eBR and its
    # three parts are the board's own runs (OURS, descriptive, zero-sum per
    # season); bsrFg and brvSavant are the published comparison rows, carried
    # verbatim. Only the columns the card renders ride along. Read only while
    # baserunning_export.CARD_BASERUNNING_LIVE is on: before the flip the board
    # file is not under data/ and the card is the card it was.
    import baserunning_export as _bre
    if _bre.CARD_BASERUNNING_LIVE:
        rd = _load(_bre.OUT_NAME) or {}
        r_season = rd.get("season")
        for r in rd.get("runners") or []:
            try:
                mid = int(r.get("mlbam"))
            except (TypeError, ValueError):
                continue
            if r.get("ebr") is None:
                continue
            blk = {"season": r_season, "qualified": bool(r.get("qualified")),
                   "ebr": r.get("ebr"), "ebrSb": r.get("ebr_sb"), "ebrXb": r.get("ebr_xb"),
                   "ebrDp": r.get("ebr_dp"), "sb": r.get("sb"), "cs": r.get("cs"), "pk": r.get("pk"),
                   "sbPct": r.get("sb_pct"), "attRate": r.get("att_rate"), "xbtPct": r.get("xbt_pct"),
                   "gidpPct": r.get("gidp_pct"), "sprint": r.get("sprint"), "sprintPct": r.get("sprint_pct"),
                   "bsrFg": r.get("bsr"), "brvSavant": r.get("brv")}
            out.setdefault(mid, {})["br"] = {k: v for k, v in blk.items() if v is not None}
    if unreadable:
        _record_skill_index_outage(unreadable, len(out))
    return out


def _card_skills(sk: dict | None, is_pit: bool, two_way: bool) -> dict:
    """The skill blocks one card carries, chosen by the side the card renders.

    hem and def are hitter-side, pitch is pitcher-side, and a two-way card takes
    both. lev arrives per side from _skill_index: a hitter card gets the batter
    row, a pitcher card the starter row, and a two-way card the batter row as
    lev plus the starter row as levPit, so neither side's WPA stands in for the
    other's."""
    if not sk:
        return {}
    hit_side = (not is_pit) or two_way
    pit_side = is_pit or two_way
    block: dict = {}
    if sk.get("hem") and hit_side:
        block["hem"] = sk["hem"]
    if sk.get("pitch") and pit_side:
        block["pitch"] = sk["pitch"]
    if sk.get("def") and hit_side:
        block["def"] = sk["def"]
    if sk.get("br") and hit_side:
        block["br"] = sk["br"]
    lev = sk.get("lev") or {}
    if hit_side and lev.get("bat"):
        block["lev"] = lev["bat"]
        if two_way and lev.get("sp"):
            block["levPit"] = lev["sp"]
    elif pit_side and lev.get("sp"):
        block["lev"] = lev["sp"]
    return block


def build_payload() -> dict:
    proj = json.loads((DATA_DIR / "mlb_projections.json").read_text(encoding="utf-8"))
    frame = {"first_season": proj.get("first_season"), "horizon": proj.get("horizon")}
    comp_rows = _component_rows(proj)
    _SHARD_COMP.clear()
    fa = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
    members = {m["key"]: m for m in fa.get("members") or []}
    swing = {}
    try:
        sp = json.loads((DATA_DIR / "swing_plus.json").read_text(encoding="utf-8"))
        swing = sp.get("players") or {}
    except (OSError, ValueError):
        pass
    aaa_stuff = {}
    try:
        st = json.loads((DATA_DIR / "stuff_plus_aaa.json").read_text(encoding="utf-8"))
        aaa_stuff = st.get("players") or {}
    except (OSError, ValueError):
        pass
    origins = _debut_origins()
    aaa_hit = _aaa_hitter_lines()
    scout_reports = {}
    try:
        scout_reports = json.loads((DATA_DIR / "scout_reports.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("mlb player export: scout_reports.json unavailable - no scouting slices")
    skills_by_mlbam = _skill_index()

    all_keys = [v["key"] for v in proj.get("vets") or []] + list(members)
    fa_ids = _ident_mlbams(all_keys)
    war_by, war_bwar_by = _war_maps()
    war_fwar_by = _fwar_reference_map()
    hof_by = _hof_index()
    year = date.today().year
    players: dict[str, dict] = {}

    # vets from the projections universe. proj_export now emits collision-safe keys
    # (base__mlbam for same-named vets), but guard here too: a duplicate key must
    # NEVER silently overwrite an existing card (the Will Smith reliever once
    # replaced the LAD catcher's page) - suffix with mlbam instead.
    for v in proj.get("vets") or []:
        key = v["key"]
        mlbam = v.get("mlbam") or fa_ids.get(key)
        if key in players:
            key = f"{key}__{mlbam or 'dup'}"
        is_pit = _is_pitcher_pos(v.get("pos"))
        p = {"key": key, "name": v.get("name"), "mlbam": mlbam,
             "pos": v.get("pos"), "team": v.get("team"), "age": v.get("age"),
             # surTotal / surRos / rosWar / rosFrac (2026-08-03): the balance of
             # the season in progress. Without them on the card the Trade
             # Machine cannot price a rental and the "Trade Machine" link never
             # renders for one, which is what hid A.J. Minter.
             # salPath / salThru / salSrc / surSalLo / surSalHi / salCut /
             # salTrunc / salVintage (ask C, 2026-09-16): the control-window
             # salary path. The card's Surplus tile prices the SAME number the
             # /projections/ board does, so it has to carry the same basis, and
             # the card renders the year-by-year strip from salPath. This list
             # is a VERBATIM copy of the projection row - it must stay verbatim,
             # because the moment it starts deriving a field the two surfaces
             # can disagree about one player's price.
             # ctrlThru / ctrlOpen / ctrlEst / ctrlWhy (2026-09-17): the CONTROL
             # window, derived once in salary_path.control_end. Copied for the
             # same reason as the rest: the card's hero line states the control
             # end, and a card that re-derived it could disagree with the board
             # about which season a club holds a player through.
             # warTail (owner answers 2026-09-25 and VAL2-Q1): the WAR each
             # guaranteed season past the horizon is priced on, the champion
             # aging curve chained from the 2031 WAR.
             "proj": {k: v.get(k) for k in ("war", "warP10", "warP90",
                                            "warTotal", "warTotalP10Comon",
                                            "warTotalP90Comon", "sur", "surNpv",
                                            "surTotal", "surRos", "rosWar",
                                            "rosFrac",
                                            "salPath", "salThru", "salSrc",
                                            "surSalLo", "surSalHi", "salCut",
                                            "salTrunc", "salOpt", "salOptDecl", "salVintage",
                                            "ctrlThru", "ctrlOpen", "ctrlEst",
                                            "ctrlWhy",
                                            "thru", "aav", "warHit", "warPit",
                                            "warTail", "warP10Tail", "warP90Tail")},
             "twoWay": bool(v.get("twoWay")) or None,
             "isPit": is_pit and not v.get("twoWay")}
        # The component lines (PJ_6), a verbatim copy of proj_export's block
        # for this board row, held for the card's shard (never this payload);
        # absent while the lines are dark.
        if comp_rows and comp_rows.get(v["key"]) is not None:
            _SHARD_COMP[key] = comp_rows[v["key"]]
        players[key] = p
    # FA members (some overlap vets; FA fields attach either way)
    for key, m in members.items():
        p = players.setdefault(key, {
            "key": key, "name": m.get("name"), "mlbam": fa_ids.get(key),
            "pos": m.get("pos"), "team": m.get("from"), "age": m.get("age"),
            "isPit": _is_pitcher_pos(m.get("pos"))})
        p.setdefault("mlbam", fa_ids.get(key))
        p["fa"] = {k: m.get(k) for k in (
            "status", "type", "projYears", "projGuar", "projAav",
            "projAavP10", "projAavP90", "rational", "surplus", "dealPlus",
            "verdict", "prevAav", "enterProb",
            # The path the FA numbers above are priced on (the Marcel
            # champion, fa_export use_ml=False) and its Deal WAR, so the card
            # can name it beside the proj_lgbm_v1 path it prints (M05-06).
            "warPath", "warTotal")}

    # Thin cards for MLB Stats leaderboard players outside the projections / FA
    # universe, so their leaderboard names link to a card. Collision-safe keys
    # (base__mlbam when the normalized name is already taken) mean a name-key
    # collision no longer silently drops a player's link. Enriched by the same
    # career / statcast / arsenal loop below (keyed by mlbam), so a thin card that
    # has cached data shows a real page; otherwise it degrades to identity only.
    _existing_mlbams = {int(p["mlbam"]) for p in players.values() if p.get("mlbam")}
    _n_thin = 0
    for row in _leaderboard_thin_rows():
        mid = row["mlbam"]
        if mid in _existing_mlbams:
            continue
        base = normalize_key(row["name"] or "") or f"mlbam-{mid}"
        key = base if base not in players else f"{base}__{mid}"
        players[key] = {"key": key, "name": row["name"], "mlbam": mid,
                        "pos": row.get("pos"), "team": row.get("team"), "age": None,
                        "isPit": row["isPit"], "leaderboardOnly": True}
        _existing_mlbams.add(mid)
        _n_thin += 1
    log.info("player detail: +%d thin leaderboard cards", _n_thin)

    n_sc = n_ar = n_car = 0
    for key, p in players.items():
        mlbam = p.get("mlbam")
        if not mlbam:
            continue
        org = origins.get(int(mlbam))
        if org and org.get("prospx"):
            # ex-PROSPX prospect: arc + hub link (hero). Only the render-facing
            # arc fields ride in origin; tool grades go into the scout slice.
            p["origin"] = {k: org[k] for k in ("prospx", "fvOpen", "fvClose",
                                               "debut", "fvSpark", "efvDebut",
                                               "devOrg")
                           if org.get(k) is not None}
            # The graduate bridge's hitter line, the batter twin of the
            # aStuff+ tile pitchers get: hitters and two-way players only.
            hl = aaa_hit.get(int(mlbam))
            if hl and (not p["isPit"] or p.get("twoWay")):
                p["origin"]["aaaHit"] = hl
            # Scouting slice (ex-PROSPX only): latest report blurb + tool grades.
            rep = _scout_report_slice(org["prospx"], scout_reports)
            tools = org.get("tools")
            if rep or tools:
                sc_block = {}
                if rep:
                    sc_block["report"] = rep
                if tools:
                    sc_block["tools"] = tools
                p["scout"] = sc_block
        # Skill ratings from the MLB Stats leaderboards (HEM+ for hitters,
        # REM+/RIV+/SEM+ for pitchers, leverage, DEM+ and published defensive
        # runs for fielders), baked so the card stops client-fetching whole
        # leaderboards for a few tiles.
        block = _card_skills(skills_by_mlbam.get(int(mlbam)),
                             bool(p["isPit"]), bool(p.get("twoWay")))
        if block:
            p["skills"] = block
        hof = hof_by.get(int(mlbam))
        if hof:
            p["hof"] = hof
        p["career"] =_career_rows(int(mlbam), p["isPit"], war_by, war_bwar_by,
                                   war_fwar_by)
        n_car += 1 if p["career"] else 0
        sc = _statcast_block(int(mlbam), p["isPit"], year)
        if sc:
            p["sc"] = sc
            n_sc += 1
        # Two-way players carry BOTH sides: the primary career/sc above is
        # the hitting line (isPit forced False for two-way); the pitching
        # line + arsenal ride alongside.
        if p.get("twoWay"):
            p["careerPit"] = _career_rows(int(mlbam), True, war_by, war_bwar_by,
                                          war_fwar_by)
            scp = _statcast_block(int(mlbam), True, year)
            if scp:
                p["scPit"] = scp
        if p["isPit"] or p.get("twoWay"):
            ar = _arsenal_block(int(mlbam), year)
            if ar:
                p["arsenal"] = ar
                n_ar += 1
        sw = swing.get(str(mlbam))
        if sw and (not p["isPit"] or p.get("twoWay")):
            p["swingPlus"] = sw["swing_plus"]
            p["swingN"] = sw["n_swings"]
            # W6 display-only: per-season Swing+ slices for the card trend
            # line (same filter + shrink, grouped by season; low_n = under
            # the model's 180-swing floor). Never a model input.
            if sw.get("seasons"):
                p["swingPlusSeasons"] = sw["seasons"]
        # In-house AAA Stuff+ - recent graduates only (the ex-PROSPX origin
        # gate keeps a vet's rehab-stint AAA pitches off his page).
        st = aaa_stuff.get(str(mlbam))
        if st and (p["isPit"] or p.get("twoWay")) and p.get("origin"):
            p["aaaStuffPlus"] = st["stuff_plus"]
            p["aaaStuffN"] = st["n_pitches"]
            p["aaaStuffSeason"] = st["season"]
    return {
        "generated_at": date.today().isoformat(),
        # The board scalars a card reads (the projection's first season and
        # horizon), so a per-player shard renders without the board payload.
        **frame,
        "n_players": len(players),
        "coverage": {"career": n_car, "statcast": n_sc, "arsenal": n_ar,
                     "swing_plus": sum(1 for p in players.values()
                                       if p.get("swingPlus") is not None),
                     "aaa_stuff_plus": sum(1 for p in players.values()
                                           if p.get("aaaStuffPlus") is not None),
                     "skills": sum(1 for p in players.values() if p.get("skills")),
                     # Per-block counts, so a served-artifact test can tell a
                     # payload baked before these blocks existed (key absent)
                     # from one whose join came back empty (key present, 0).
                     "lev": sum(1 for p in players.values()
                                if (p.get("skills") or {}).get("lev")),
                     "def": sum(1 for p in players.values()
                                if (p.get("skills") or {}).get("def")),
                     "br": sum(1 for p in players.values()
                               if (p.get("skills") or {}).get("br")),
                     "scout": sum(1 for p in players.values() if p.get("scout")),
                     "hof": sum(1 for p in players.values() if p.get("hof")),
                     "origin_efv": sum(1 for p in players.values()
                                       if (p.get("origin") or {}).get("efvDebut") is not None),
                     "origin_aaa_hit": sum(1 for p in players.values()
                                           if (p.get("origin") or {}).get("aaaHit"))},
        "notes": [
            "career: MLB season lines (StatsAPI) + per-season WAR on war_source provider ewar_v2, the displayed WAR (eWAR v2: FIP-repriced pitching within role; batting side equal to bWAR until the SDR defense drop); war_bwar = the bWAR input where it differs at 1dp, absent means equal; war_fwar = FanGraphs' published WAR (MLB StatsAPI sabermetrics feed), a reference beside the displayed eWAR v2; absent means no published value",
            "statcast: Savant leaderboard percentiles within the season's pool (contact board 25+ batted balls; expected-stats board unfloored); pitcher contact metrics invert (suppression = good); hitter Luck = xwOBA minus wOBA",
            "swing_plus: Will Cahoon's model, MLB bat tracking 2024+ only; swingPlusSeasons = per-season slices (low_n under 180 swings)",
            "aaa_stuff_plus: in-house AAA pitch-quality model (stuff_plus_aaa.py), ex-PROSPX pitchers' latest tracked AAA season",
            "skills: HEM+ (hitters), REM+/RIV+/SEM+ (pitchers) from the MLB Stats leaderboards, joined by MLBAM",
            "skills.lev: WPA, WPA/LI, pLI, Clutch (batters) or WPA, WPA/LI, WPA/start (starters) from leverage_leaderboards.json, the side the card renders; two-way cards carry the pitching side as levPit",
            "skills.def: DEM+ (100 + 10z), FanGraphs' published fielding and framing runs, the Defense board's own positional ladder (posRuns, the term in defRuns) and FanGraphs' published positional beside it (posRunsFg), from defense_leaderboards.json, fielders only",
            "skills.br: eBR and its SB, XB and DP runs (the Baserunning board's own, descriptive, this season on its run expectancy), the official SB and CS, the record's pickoffs and rates, Savant sprint speed, and the published BsR (FanGraphs) and BRV (Savant) as comparison rows, from baserunning_leaderboards.json, hitter-side and two-way cards only; present only while baserunning_export.CARD_BASERUNNING_LIVE is on",
            "scout: latest published report blurb (capped) + consensus tool grades, ex-PROSPX players only",
            "origin.fvSpark: consensus-FV arc [[date, fv], ...] for ex-PROSPX players",
            "origin.efvDebut: xfv.json xfv_grade_at_debut, the eFV the player carried into the majors (the card prints it to the nearest point); origin.devOrg: the club he debuted with (build_site._debut_org); origin.aaaHit: his final tracked-park Statcast hitter line from statcast_aaa_hitters.json (hitters and two-way only; thru or asOf dates a partial season); one player's own numbers, never grouped by grade",
            "hof: the /hof/ shelf's own row (career WAR, WAR7, JAWS, WAA+ as waa_pos, WAR ink, first and last season, seasons) for players on its Cooperstown Watch and Not Yet Eligible bands, copied verbatim and joined B-Ref id to MLBAM through the war_daily ids; basis B-Ref bWAR, the shelf's; the player's own numbers only, no position standard; the band is a shelf band, not a forecast",
            "fa fields attach for current class members; verdict/dealPlus from the gate-validated market model",
        ],
        "players": players,
    }


def _leaderboard_thin_rows() -> list[dict]:
    """Identity rows for MLB Stats leaderboard players (bullpen / starter / hitter
    boards) so their leaderboard names link to a real player card even when they
    aren't in the projections / FA universe. This closes the dominant clickability
    gap (rookies / up-and-down arms like Erik Sabrowski, Didier Fuentes) and, via
    the collision-safe keying in build_payload, gives name-key-collided veterans
    (e.g. Max Muncy 571970 vs the A's Max Muncy 691777) their own linkable card.
    Deduped by mlbam; empty on any error."""
    out: list[dict] = []
    seen: set[int] = set()
    specs = [("bullpen_leaderboards.json", "relievers", True, "RP"),
             ("starter_leaderboards.json", "starters", True, "SP"),
             ("hitter_leaderboards.json", "hitters", False, None)]
    for fname, akey, is_pit, pos in specs:
        try:
            d = json.loads((DATA_DIR / fname).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in d.get(akey) or []:
            try:
                mid = int(r.get("mlbam"))
            except (TypeError, ValueError):
                continue
            if mid in seen or not r.get("name"):
                continue
            seen.add(mid)
            out.append({"mlbam": mid, "name": r.get("name"),
                        "team": r.get("team"), "pos": pos, "isPit": is_pit})
    return out


def _active_prospect_rows() -> list[dict]:
    """Slim identity rows for ACTIVE PROSPX prospects (timeseries.json boot
    file) so the site-wide search covers players who haven't debuted yet.
    Empty on any error - the links map degrades to the MLB population."""
    try:
        boot = json.loads((DATA_DIR / "timeseries.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("player links: timeseries.json unavailable - search index "
                    "covers the MLB population only")
        return []
    rows = []
    for p in boot.get("players") or []:
        pkey = p.get("player_key")
        if not pkey:
            continue
        rows.append({"key": pkey, "mlbam": p.get("mlbam_id"),
                     "fa": False, "prospx": pkey,
                     "name": p.get("player_name"),
                     "team": p.get("org"), "pos": p.get("position")})
    return rows


def _export_links(payload: dict) -> None:
    """data/player_links.json - the cross-module identity map every card
    surface reads for its hub strip: one player, every page that renders
    them. byMlbam serves PROSPX (it knows mlbam_id); byKey serves the FA
    and projections apps (they share the normalized-name key). name/team/pos
    ride along so the site-wide ⌘K palette can search players from any page;
    active PROSPX prospects merge in for the same reason (the /player/
    router resolves their keys to the prospect card)."""
    by_key: dict[str, dict] = {}
    by_mlbam: dict[str, dict] = {}
    for key, p in payload["players"].items():
        row = {"key": key, "mlbam": p.get("mlbam"),
               "fa": bool(p.get("fa")),
               # AUDIT 2026-07-18 (A6): mark projection-universe players so the hub
               # strip only offers the "MLB Projections -> player page" chip to
               # players who actually HAVE that page. Every key in payload["players"]
               # is a projections vet or FA member with a real /projections/#player=
               # page; the active-prospect rows merged below are NOT and get proj=False.
               "proj": True,
               "prospx": (p.get("origin") or {}).get("prospx"),
               "name": p.get("name"), "team": p.get("team"), "pos": p.get("pos")}
        # The graduate bridge (wiring W06): a PROSPX graduate carries the flag
        # and his debut season, which the /mlbstats/ chip and debut-season
        # filter read. Absent on every other row, so the map grows only by
        # the graduates.
        org = p.get("origin") or {}
        if org.get("prospx"):
            row["grad"] = True
            yr = str(org.get("debut") or "")[:4]
            if yr.isdigit():
                row["debutYr"] = int(yr)
        by_key[key] = row
        if p.get("mlbam"):
            by_mlbam[str(p["mlbam"])] = row
    n_prospects = 0
    for row in _active_prospect_rows():
        if row["key"] in by_key:
            continue   # ex-prospect already carried by the MLB payload
        row.setdefault("proj", False)   # never-debuted prospect: no projections page
        by_key[row["key"]] = row
        if row.get("mlbam"):
            by_mlbam.setdefault(str(row["mlbam"]), row)
        n_prospects += 1
    out = {"generated_at": payload["generated_at"],
           "byKey": by_key, "byMlbam": by_mlbam}
    (DATA_DIR / "player_links.json").write_text(
        json.dumps(out, separators=(",", ":")), encoding="utf-8")
    write_player_search(out)
    log.info("player links: %d keys (%d active prospects merged), %d mlbam-joined",
             len(by_key), n_prospects, len(by_mlbam))


PLAYER_SEARCH_FIELDS = ("key", "name", "team", "pos", "prospx")


def write_player_search(links: dict | None = None) -> dict:
    """data/player_search.json - the quick-search palette's own index (QHOP06).

    The palette (assets/eephus-gl.js) reads five fields of each byKey row, but
    used to download all of player_links.json for them, byMlbam included (a
    second copy of nearly every row). This writes those five fields as one
    array per row beside player_links.json, in the same step and from the same
    rows. Called with no argument it reads the player_links.json already on
    disk, so the index can be rebuilt without re-running the export."""
    if links is None:
        links = json.loads((DATA_DIR / "player_links.json").read_text(encoding="utf-8"))
    rows = [[row.get(k) or "" for k in PLAYER_SEARCH_FIELDS]
            for row in (links.get("byKey") or {}).values() if row and row.get("name")]
    doc = {"generated_at": links.get("generated_at"), "fields": list(PLAYER_SEARCH_FIELDS),
           "rows": rows}
    (DATA_DIR / "player_search.json").write_text(
        json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return doc


def build_position_games() -> dict:
    """The games-by-position strip on /projections/ and PROSPX player pages:
    the latest season of fielding_innings (the nightly StatsAPI fielding feed,
    refreshed at d9b1 just before this export), keyed by MLBAM id.

    Both pages used to read a June snapshot keyed by name slug that nothing
    refreshed (owner decision 24 repointed /dfs/ and /redraft/ off it on
    2026-09-11). The slug key also crossed players who share a name: the
    Dodgers' Max Muncy showed the A's Max Muncy's line and the infielder Jose
    Fermin showed the pitcher's. MLBAM keys cannot collide that way.

    Rows are [games, games started, innings] per position; innings are decimal
    (fielding_innings converts baseball thirds at ingest). as_of is the feed's
    own date, so a stale feed reads as stale on the page. Empty players when
    the feed is unreadable; the strip then renders nothing."""
    try:
        fi = json.loads((DATA_DIR / "fielding_innings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fi = {}
    seasons = fi.get("seasons") or {}
    season = max((int(s) for s in seasons if str(s).isdigit()), default=None)
    players: dict[str, dict] = {}
    latest = seasons.get(str(season)) if season is not None else None
    for mid, positions in (latest or {}).items():
        rows = {}
        for pos, r in (positions or {}).items():
            g = (r or {}).get("g")
            if not isinstance(g, (int, float)) or g <= 0:
                continue
            rows[pos] = [int(g), (r or {}).get("gs"), (r or {}).get("inn")]
        if rows:
            players[str(mid)] = rows
    return {"generated_at": date.today().isoformat(),
            "as_of": fi.get("generated_at"),
            "season": season,
            "source": "fielding_innings.json (StatsAPI season fielding, sportId=1)",
            "row": ["g", "gs", "inn"],
            "players": players}


def _export_position_games() -> None:
    out = build_position_games()
    (DATA_DIR / "mlb_position_games.json").write_text(
        json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log.info("position games: %d players, season %s, feed as of %s",
             len(out["players"]), out["season"], out["as_of"])


_PAYLOAD_SOFT_BUDGET = 6 * 1024 * 1024   # 6MB - lazy-fetched on first player view


def _shard_dir() -> Path:
    # A function, not a module constant, so a test that redirects DATA_DIR
    # redirects the shards with it.
    return DATA_DIR / SHARD_DIRNAME


def _export_shards(payload: dict, comp: dict | None = None) -> int:
    """data/mlb_player_detail/<key>.json: one card per player, carrying the
    payload's generated_at, first_season and horizon beside it. Shards of
    players no longer in the payload are removed, so the directory is always
    exactly the payload's players. `comp` ({card key: component block}, the
    live component lines) lands in that card's proj.comp in the shard alone.
    Returns the number written."""
    out_dir = _shard_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    head = {k: payload.get(k) for k in ("generated_at", "first_season", "horizon")}
    names = set()
    for key, p in payload["players"].items():
        name = f"{key}.json"
        names.add(name)
        if comp and comp.get(key) is not None:
            p = {**p, "proj": {**(p.get("proj") or {}), "comp": comp[key]}}
        (out_dir / name).write_text(
            json.dumps({**head, "key": key, "player": p}, separators=(",", ":")),
            encoding="utf-8")
    for f in out_dir.glob("*.json"):
        if f.name not in names:
            f.unlink()
    return len(names)


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    OUT_PATH.write_text(raw, encoding="utf-8")
    n_shards = _export_shards(payload, _SHARD_COMP)
    log.info("mlb player detail: %d per-player shards under data/%s/", n_shards, SHARD_DIRNAME)
    _export_links(payload)
    _export_position_games()
    if len(raw) > _PAYLOAD_SOFT_BUDGET:
        log.warning("mlb player detail: payload %.1fMB exceeds the %dMB soft "
                    "budget (lazy-fetched on first player view) - consider "
                    "trimming baked blocks", len(raw) / 1048576,
                    _PAYLOAD_SOFT_BUDGET // 1048576)
    log.info("mlb player detail: %dKB, %d players, coverage %s",
             len(raw) // 1024, payload["n_players"], payload["coverage"])
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
