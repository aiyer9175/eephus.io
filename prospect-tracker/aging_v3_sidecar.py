# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The aging v3 sidecar: per (mlbam, season) inputs the service needs beyond
the corpus (docs/AGING_V3_GATE.md sections 2 and 5; LANE_B.md 2.8).

``.cache/aging_v3_sidecar_{first}_{last}_{sig}.pkl``, keyed by (mlbam, season):

- from the raw StatsAPI season cache the corpus is built from
  (``fa_sources.fetch_statsapi_season_range``, ``.cache/fa_statsapi_*``): the
  position abbreviation, stolenBases, caughtStealing, groundOuts, airOuts,
  plateAppearances (hitting); gamesStarted, gamesPlayed, inningsPitched,
  battersFaced (pitching); ``two_way`` when the player has a non-pitcher
  hitting line AND a pitching line that season;
- the run parts batting, baseRunning and fielding from the FROZEN fWAR vintage
  reader (``fwar_vintage.load``, unifier amendment U6), never the live
  sabermetrics cache; a season the vintage does not carry is absent (None), not
  filled; fielding innings (``inn``) from ``proj_components.read_fielding`` for
  the per-1,000-innings fld curve;
- IL days, IL stints and 60-day placements per season from the league
  transactions cache ``.cache/mlb_transactions/`` through tools/pt_risk_lab.py's
  reconstruction and stint-truncation functions (a-priori choices 3 and 4,
  IMPORTED, not copied), over 2008 onward; a season outside the cache's
  coverage carries None;
- ``tj``: {mlbam: [surgery years]} from data/tj_surgery.json (the as_of rule is
  applied by the consumer: pitchers, year <= t).

It never rewrites ``.cache/fa_corpus.pkl``. Missing transaction months are
fetched only on request (``--fetch``), with the lab's own fetch code, into
``.cache`` only, never on a look day.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import fa_projection as fp
import fa_sources
import fwar_vintage

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
CACHE_DIR = fp.CACHE_DIR
TJ_PATH = ROOT / "data" / "tj_surgery.json"
SIDECAR_VERSION = 1
IL_FIRST = (2008, 1)
WINDOW_MONTHS = range(4, 10)        # the season window's months (Apr 1 to Oct 1)


def _lab():
    tools = str(ROOT / "tools")
    if tools not in sys.path:
        sys.path.insert(0, tools)
    import pt_risk_lab
    return pt_risk_lab


def sidecar_path(corpus: dict) -> Path:
    return CACHE_DIR / f"aging_v3_sidecar_{corpus['first']}_{corpus['last']}_{fp._corpus_sig(corpus)}.pkl"


def _f(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def cached_months(lab) -> list[tuple[int, int]]:
    out = []
    for p in sorted(lab.TX_DIR.glob("tx_*.json.gz")):
        try:
            _, y, m = p.stem.replace(".json", "").split("_")
            out.append((int(y), int(m)))
        except ValueError:
            continue
    return out


def il_coverage(months: list[tuple[int, int]]) -> list[int]:
    """Seasons whose window months (April to September) are all cached."""
    have = set(months)
    years = sorted({y for y, _ in have})
    return [y for y in years if all((y, m) in have for m in WINDOW_MONTHS)]


def fetch_missing(last: tuple[int, int] | None = None) -> list[tuple[int, int]]:
    """Fetch the transaction months from IL_FIRST through ``last`` (default:
    the current month) that are not cached, with the lab's own fetch code,
    into .cache only. Returns the months fetched. Never called by ``load``."""
    lab = _lab()
    today = _dt.date.today()
    last = last or (today.year, today.month)
    before = set(cached_months(lab))
    saved = (lab.FETCH_FIRST, lab.FETCH_LAST)
    try:
        lab.FETCH_FIRST, lab.FETCH_LAST = IL_FIRST, last
        lab.cmd_fetch()
    finally:
        lab.FETCH_FIRST, lab.FETCH_LAST = saved
    return sorted(set(cached_months(lab)) - before)


def il_tables() -> tuple[dict, dict, list[int]]:
    """({pid: {year: [il_days, il_stints]}}, {(pid, year): il60}, covered years)
    through the lab's reconstruction over every cached month from 2008."""
    lab = _lab()
    months = cached_months(lab)
    if not months:
        return {}, {}, []
    saved = (lab.FETCH_FIRST, lab.FETCH_LAST)
    try:
        lab.FETCH_FIRST, lab.FETCH_LAST = IL_FIRST, max(months)
        il, _per_year, _counts = lab.build_stints()
        events, _ = lab._load_events(keep_desc=True)
    finally:
        lab.FETCH_FIRST, lab.FETCH_LAST = saved
    il60: dict = defaultdict(int)
    for pid, evs in events.items():
        for ev in evs:
            dt, kind, desc = ev
            if kind == "P" and "60-day" in desc:
                il60[(pid, dt.year)] += 1
    return il, dict(il60), il_coverage(months)


def tj_years() -> dict[int, list[int]]:
    try:
        d = json.loads(TJ_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for mid, rows in (d.get("players") or {}).items():
        try:
            key = int(mid)
        except (TypeError, ValueError):
            continue
        years = sorted(int(r["year"]) for r in rows if r.get("year") is not None)
        if years:
            out[key] = years
    return out


def _vintage_parts(blob: dict, season: int) -> dict[int, dict]:
    """{mlbam: {bat, bsr, fld}} for one season's frozen hitting group, {} when
    the vintage does not carry it."""
    gb = ((blob.get("seasons") or {}).get(str(int(season))) or {}).get("hitting") or {}
    if gb.get("status") != "frozen":
        return {}
    fields = list(gb.get("fields") or [])
    try:
        ib, ir, ifl = fields.index("batting"), fields.index("baseRunning"), fields.index("fielding")
    except ValueError:
        return {}
    out = {}
    for mid, vals in (gb.get("rows") or {}).items():
        out[int(mid)] = {"bat": _f(vals[ib]), "bsr": _f(vals[ir]), "fld": _f(vals[ifl])}
    return out


def _innings(season: int) -> dict[int, float] | None:
    try:
        import proj_components
        fld = proj_components.read_fielding(season)
    except Exception:   # noqa: BLE001 - innings are optional inputs of one curve
        return None
    if fld is None:
        return None
    return {int(m): float(sum((rec.get("inn") or {}).values())) for m, rec in fld.items()}


def build(corpus: dict, *, write: bool = True) -> dict:
    """Build the sidecar for ``corpus`` (its seasons, its signature) and write
    it to ``sidecar_path`` unless ``write`` is False."""
    first, last = int(corpus["first"]), int(corpus["last"])
    # cache-only: the raw season files are read as the corpus was built from
    # them, never refetched here (a refetch would make the corpus stale and the
    # next build_corpus would rewrite .cache/fa_corpus.pkl, which this lane
    # never does); a season absent from the cache is absent from the sidecar.
    import scrapers
    with scrapers.cache_only():
        raw = fa_sources.fetch_statsapi_season_range(first, last)
    blob = fwar_vintage.load()
    il, il60, covered = il_tables()
    covered_set = set(covered)
    rows: dict = {}
    for season in range(first, last + 1):
        hit_ids, pit_ids = set(), set()
        for s in raw.get((season, "hitting"), []):
            st = s.get("stat") or {}
            pa = _f(st.get("plateAppearances"), 0.0)
            mid = (s.get("player") or {}).get("id")
            if not mid or pa <= 0:
                continue
            pos = ((s.get("position") or {}).get("abbreviation") or "").upper() or None
            rec = rows.setdefault((int(mid), season), {})
            rec.update({"pos": pos, "pa": pa, "sb": _f(st.get("stolenBases"), 0.0),
                        "cs": _f(st.get("caughtStealing"), 0.0),
                        "go": _f(st.get("groundOuts"), 0.0), "ao": _f(st.get("airOuts"), 0.0)})
            if pos != "P":
                hit_ids.add(int(mid))
        for s in raw.get((season, "pitching"), []):
            st = s.get("stat") or {}
            bf = _f(st.get("battersFaced"), 0.0)
            mid = (s.get("player") or {}).get("id")
            if not mid or bf <= 0:
                continue
            rec = rows.setdefault((int(mid), season), {})
            rec.update({"gs": _f(st.get("gamesStarted"), 0.0), "g": _f(st.get("gamesPlayed"), 0.0),
                        "ip": fp._ip_to_float(st.get("inningsPitched")), "bf": bf})
            if rec.get("pos") is None:
                rec["pos"] = ((s.get("position") or {}).get("abbreviation") or "").upper() or None
            pit_ids.add(int(mid))
        parts = _vintage_parts(blob, season)
        inn = _innings(season)
        for (mid, s), rec in rows.items():
            if s != season:
                continue
            rec["two_way"] = mid in hit_ids and mid in pit_ids
            p = parts.get(mid) or {}
            rec["bat"], rec["bsr"], rec["fld"] = p.get("bat"), p.get("bsr"), p.get("fld")
            rec["inn"] = (inn.get(mid) if inn is not None else None)
            if season in covered_set:
                d = (il.get(mid) or {}).get(season) or [0.0, 0]
                rec["il_days"], rec["il_stints"] = float(d[0]), int(d[1])
                rec["il60"] = int(il60.get((mid, season), 0))
            else:
                rec["il_days"] = rec["il_stints"] = rec["il60"] = None
    sig = fp._corpus_sig(corpus)
    out = {
        "rows": rows,
        "tj": tj_years(),
        "meta": {"version": SIDECAR_VERSION, "sig": sig, "first": first, "last": last,
                 "vintage_id": blob.get("vintage_id"), "built_at": _dt.date.today().isoformat(),
                 "il_coverage": covered, "n_rows": len(rows),
                 "sources": ["fa_statsapi season cache", "fwar_vintage (run parts)",
                             "proj_components.read_fielding (innings)",
                             "mlb_transactions via tools/pt_risk_lab", "data/tj_surgery.json"]},
    }
    if write:
        CACHE_DIR.mkdir(exist_ok=True)
        with open(sidecar_path(corpus), "wb") as fh:
            pickle.dump(out, fh)
        log.info("aging v3 sidecar written -> %s (%d rows)", sidecar_path(corpus), len(rows))
    return out


def load(corpus: dict, build_if_missing: bool = True) -> dict:
    """The sidecar for ``corpus`` from its cache, built on first use."""
    p = sidecar_path(corpus)
    if p.exists():
        with open(p, "rb") as fh:
            return pickle.load(fh)
    if not build_if_missing:
        raise FileNotFoundError(p)
    return build(corpus, write=True)


def _main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Build the aging v3 sidecar from the caches.")
    ap.add_argument("--fetch", action="store_true",
                    help="fetch missing transaction months first (.cache only; never on a look day)")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with open(fp.CORPUS_CACHE, "rb") as fh:
        corpus = pickle.load(fh)
    if a.fetch:
        print("fetched months:", fetch_missing())
    sc = build(corpus, write=True) if (a.rebuild or not sidecar_path(corpus).exists()) else load(corpus)
    m = sc["meta"]
    rows = sc["rows"]
    n_parts = sum(1 for r in rows.values() if r.get("bsr") is not None)
    n_il = sum(1 for r in rows.values() if r.get("il_days") is not None)
    print(f"sidecar {sidecar_path(corpus).name}: {m['n_rows']} rows, run parts on {n_parts}, "
          f"IL on {n_il}, IL coverage {m['il_coverage'][0] if m['il_coverage'] else None}"
          f"-{m['il_coverage'][-1] if m['il_coverage'] else None}, tj players {len(sc['tj'])}, "
          f"vintage {m['vintage_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
