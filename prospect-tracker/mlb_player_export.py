# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""MLB player detail export - the per-player payload behind the
/projections/ player pages (and the FA board's player links).

Prospects have full PROSPX detail pages; until now MLB players only had
board rows. This sidecar gives every projections veteran and every
FA-class member a real page: identity + contract chips, the projection
path with bands, season-by-season career lines with bWAR, Savant
percentile sliders, pitch arsenal (pitchers), and Swing+ (hitters,
Will Cahoon's model via data/swing_plus.json).

  UNIVERSE   union of mlb_projections.json vets and fa_class.json
             members, keyed by the platform's normalized name key.
             mlbam: vets carry it (proj_export emits it); FA members
             resolve through fa_ident's war_daily identity index.
  CAREER     MLB season lines 2014+ from the cached StatsAPI ladder
             (milb_history sport 1) + per-season bWAR from war_daily
             (pybaseball cache), joined on mlbam.
  STATCAST   Savant MLB leaderboards per season (statcast + expected_
             statistics + pitch-arsenal-stats), cached under
             .cache/savant_mlb/. Percentiles computed within the
             latest qualified season pool - the same Savant-style
             slider data prospect cards carry.
  SWING+     joined from data/swing_plus.json where scored (MLB bat
             tracking 2024+ only - the documented boundary).

Artifact: data/mlb_player_detail.json (single sidecar, lazy-fetched by
assets/projections.js on first player view). Wired into run_monthly
after proj_export.

Run: python mlb_player_export.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import statistics
import urllib.request
from datetime import date
from pathlib import Path

import milb_history as mh

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "mlb_player_detail.json"
CACHE_DIR = ROOT / ".cache" / "savant_mlb"

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


def _savant(kind: str, year: int, side: str = "batter") -> list[dict]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{kind}_{side}_{year}.csv"
    if not path.exists():
        url = LB[kind].format(side=side, year=year)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                path.write_bytes(r.read())
        except Exception as e:                                # noqa: BLE001
            log.warning("savant %s/%s/%s failed: %s", kind, side, year, e)
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
                 war_by: dict[int, dict[int, float]]) -> list[dict]:
    group = "pitching" if is_pitcher else "hitting"
    out = []
    for season in range(CAREER_FROM, date.today().year + 1):
        rows = [r for r in (mh.player_index(season, group).get(mlbam) or [])
                if r.get("level") == "MLB"]
        if not rows:
            continue
        r = max(rows, key=lambda x: _f(x.get("bf" if is_pitcher else "pa")) or 0)
        war = (war_by.get(mlbam) or {}).get(season)
        if is_pitcher:
            bf = _f(r.get("bf")) or 0
            so, bb = _f(r.get("so")), _f(r.get("bb"))
            out.append({"y": season, "ip": r.get("ip"), "era": _f(r.get("era")),
                        "kPct": round(so / bf * 100, 1) if so is not None and bf else None,
                        "bbPct": round(bb / bf * 100, 1) if bb is not None and bf else None,
                        "war": round(war, 1) if war is not None else None})
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
                        "war": round(war, 1) if war is not None else None})
    return out


def _war_daily() -> dict[int, dict[int, float]]:
    import pybaseball as pyb
    out: dict[int, dict[int, float]] = {}
    for fn in (pyb.bwar_bat, pyb.bwar_pitch):
        try:
            df = fn(return_all=True)
        except Exception:                                      # noqa: BLE001
            continue
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                mid, yr, war = int(row.mlb_ID), int(row.year_ID), float(row.WAR)
            except (TypeError, ValueError):
                continue
            seasons = out.setdefault(mid, {})
            seasons[yr] = seasons.get(yr, 0.0) + war
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


def _debut_origins() -> dict[int, dict]:
    """{mlbam: prospect origin} from debuts.json - the PROSPX identity +
    the FV arc endpoints for ex-prospects."""
    out: dict[int, dict] = {}
    try:
        for d in json.loads((DATA_DIR / "debuts.json").read_text(encoding="utf-8")):
            if d.get("mlbam_id"):
                out[int(d["mlbam_id"])] = {
                    "prospx": d.get("player_key"),
                    "fvOpen": d.get("fv_open"),
                    "fvClose": d.get("fv_close"),
                    "debut": d.get("debut_date"),
                }
    except (OSError, ValueError):
        log.warning("mlb player export: debuts.json unavailable - no origins")
    return out


def build_payload() -> dict:
    proj = json.loads((DATA_DIR / "mlb_projections.json").read_text(encoding="utf-8"))
    fa = json.loads((DATA_DIR / "fa_class.json").read_text(encoding="utf-8"))
    members = {m["key"]: m for m in fa.get("members") or []}
    swing = {}
    try:
        sp = json.loads((DATA_DIR / "swing_plus.json").read_text(encoding="utf-8"))
        swing = sp.get("players") or {}
    except (OSError, ValueError):
        pass
    origins = _debut_origins()

    all_keys = [v["key"] for v in proj.get("vets") or []] + list(members)
    fa_ids = _ident_mlbams(all_keys)
    war_by = _war_daily()
    year = date.today().year
    players: dict[str, dict] = {}

    # vets from the projections universe
    for v in proj.get("vets") or []:
        key = v["key"]
        mlbam = v.get("mlbam") or fa_ids.get(key)
        is_pit = _is_pitcher_pos(v.get("pos"))
        p = {"key": key, "name": v.get("name"), "mlbam": mlbam,
             "pos": v.get("pos"), "team": v.get("team"), "age": v.get("age"),
             "proj": {k: v.get(k) for k in ("war", "warP10", "warP90",
                                            "warTotal", "warTotalP10",
                                            "warTotalP90", "sur", "surNpv",
                                            "thru", "aav")},
             "isPit": is_pit}
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
            "verdict", "prevAav", "enterProb")}

    n_sc = n_ar = n_car = 0
    for key, p in players.items():
        mlbam = p.get("mlbam")
        if not mlbam:
            continue
        org = origins.get(int(mlbam))
        if org and org.get("prospx"):
            p["origin"] = org          # ex-PROSPX prospect: arc + hub link
        p["career"] = _career_rows(int(mlbam), p["isPit"], war_by)
        n_car += 1 if p["career"] else 0
        sc = _statcast_block(int(mlbam), p["isPit"], year)
        if sc:
            p["sc"] = sc
            n_sc += 1
        if p["isPit"]:
            ar = _arsenal_block(int(mlbam), year)
            if ar:
                p["arsenal"] = ar
                n_ar += 1
        sw = swing.get(str(mlbam))
        if sw and not p["isPit"]:
            p["swingPlus"] = sw["swing_plus"]
            p["swingN"] = sw["n_swings"]
    return {
        "generated_at": date.today().isoformat(),
        "n_players": len(players),
        "coverage": {"career": n_car, "statcast": n_sc, "arsenal": n_ar,
                     "swing_plus": sum(1 for p in players.values()
                                       if p.get("swingPlus") is not None)},
        "notes": [
            "career: MLB season lines (StatsAPI) + per-season bWAR (war_daily)",
            "statcast: Savant leaderboard percentiles within the season's qualified pool; pitcher contact metrics invert (suppression = good)",
            "swing_plus: Will Cahoon's model, MLB bat tracking 2024+ only",
            "fa fields attach for current class members; verdict/dealPlus from the gate-validated market model",
        ],
        "players": players,
    }


def _export_links(payload: dict) -> None:
    """data/player_links.json - the cross-module identity map every card
    surface reads for its hub strip: one player, every page that renders
    them. byMlbam serves PROSPX (it knows mlbam_id); byKey serves the FA
    and projections apps (they share the normalized-name key)."""
    by_key: dict[str, dict] = {}
    by_mlbam: dict[str, dict] = {}
    for key, p in payload["players"].items():
        row = {"key": key, "mlbam": p.get("mlbam"),
               "fa": bool(p.get("fa")),
               "prospx": (p.get("origin") or {}).get("prospx")}
        by_key[key] = row
        if p.get("mlbam"):
            by_mlbam[str(p["mlbam"])] = row
    out = {"generated_at": payload["generated_at"],
           "byKey": by_key, "byMlbam": by_mlbam}
    (DATA_DIR / "player_links.json").write_text(
        json.dumps(out, separators=(",", ":")), encoding="utf-8")
    log.info("player links: %d keys, %d mlbam-joined", len(by_key), len(by_mlbam))


def export() -> int:
    payload = build_payload()
    raw = json.dumps(payload, separators=(",", ":"))
    OUT_PATH.write_text(raw, encoding="utf-8")
    _export_links(payload)
    log.info("mlb player detail: %dKB, %d players, coverage %s",
             len(raw) // 1024, payload["n_players"], payload["coverage"])
    return len(raw)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export())
