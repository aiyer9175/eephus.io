# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Overseas translation-factor refit (model-audit Phase 4b, WS-8).

The LEAGUE_CONTEXT factors in overseas_export.py are hand-set constants
("Longenhagen 2024 primer" provenance) that were never fit to data. This
tool measures the actual NPB/KBO -> MLB transition cohort 2015-2026 and
refits the factors that are RAW (league-context-free) by construction:

  pitcher_era_factor   MLBe ERA = league ERA x factor. Measured per
                       transition: first-MLB-season ERA / final-foreign-
                       season ERA, aggregated as an IP-weighted ratio of
                       means (robust to small-denominator blowups),
                       shrunk toward the incumbent with k=8 pseudo-obs.
  hitter_k_pct_delta   MLBe K% = league K% + delta. Measured: first-MLB
                       K% - final-foreign K%, PA-weighted mean, shrunk
                       toward the incumbent (k=8).

What is MEASURED but NOT shipped (documented data lifts):
  hitter_wrc_factor    wRC+ is league-relative; the raw OPS ratio is
                       reported per cohort as the analog, but shipping
                       it as a wRC+ multiplier needs per-season NPB/KBO
                       league offense context (a register league-page
                       scrape) — factor stays prior.
  fb_velo_delta        no historical foreign pitch-velocity source.
  CPBL / CUBA / NPBF   cohorts too small (plan: stay prior).

DATA       transition list = curated ledger (committed in the artifact;
           owner-extendable, the deferrals.json pattern). Foreign-side
           stats: Baseball-Reference register pages (rate-limited,
           cached). MLB-side: StatsAPI season stats (milb_history sport
           1 cache) via people/search mlbam resolution. Players whose
           pages fail to resolve/parse are EXCLUDED AND COUNTED — the
           coverage audit ships in the artifact.

Artifact: data/overseas_translation_eval.json. Factor updates land in
overseas_export.LEAGUE_CONTEXT with the eval as provenance.

Run: python tools/refit_overseas_factors.py  (one-time fit + rare refits)
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "overseas_translation_eval.json"
CACHE_DIR = ROOT / ".cache" / "bref_register"

BREF_DELAY_S = 3.5          # B-Ref rate limit: stay under ~20 req/min
SHRINK_K = 8.0              # pseudo-observations toward the incumbent
MIN_FOREIGN_IP, MIN_MLB_IP = 40.0, 25.0
MIN_FOREIGN_PA, MIN_MLB_PA = 150, 100

# Curated transition ledger: (display name, league, side, mlb_entry_year).
# mlb_entry_year = first MLB season after the foreign stint; the final
# foreign season is discovered from the register page (last qualifying
# season strictly before entry). MLB->KBO->MLB returnees are valid factor
# observations (flagged "returnee" for the artifact).
TRANSITIONS: list[dict] = [
    # NPB pitchers
    {"name": "Kenta Maeda", "league": "NPB", "side": "pit", "entry": 2016},
    {"name": "Shohei Ohtani", "league": "NPB", "side": "pit", "entry": 2018},
    {"name": "Miles Mikolas", "league": "NPB", "side": "pit", "entry": 2018, "returnee": True},
    {"name": "Yoshihisa Hirano", "league": "NPB", "side": "pit", "entry": 2018},
    {"name": "Yusei Kikuchi", "league": "NPB", "side": "pit", "entry": 2019},
    {"name": "Shun Yamaguchi", "league": "NPB", "side": "pit", "entry": 2020},
    {"name": "Kohei Arihara", "league": "NPB", "side": "pit", "entry": 2021},
    {"name": "Hirokazu Sawamura", "league": "NPB", "side": "pit", "entry": 2021},
    {"name": "Kodai Senga", "league": "NPB", "side": "pit", "entry": 2023},
    {"name": "Shintaro Fujinami", "league": "NPB", "side": "pit", "entry": 2023},
    {"name": "Yoshinobu Yamamoto", "league": "NPB", "side": "pit", "entry": 2024},
    {"name": "Shota Imanaga", "league": "NPB", "side": "pit", "entry": 2024},
    {"name": "Yuki Matsui", "league": "NPB", "side": "pit", "entry": 2024},
    {"name": "Naoyuki Uwasawa", "league": "NPB", "side": "pit", "entry": 2024},
    {"name": "Tomoyuki Sugano", "league": "NPB", "side": "pit", "entry": 2025},
    {"name": "Roki Sasaki", "league": "NPB", "side": "pit", "entry": 2025},
    # NPB hitters
    {"name": "Shohei Ohtani", "league": "NPB", "side": "hit", "entry": 2018},
    {"name": "Yoshi Tsutsugo", "league": "NPB", "side": "hit", "entry": 2020},
    {"name": "Shogo Akiyama", "league": "NPB", "side": "hit", "entry": 2020},
    {"name": "Seiya Suzuki", "league": "NPB", "side": "hit", "entry": 2022},
    {"name": "Masataka Yoshida", "league": "NPB", "side": "hit", "entry": 2023},
    {"name": "Munetaka Murakami", "league": "NPB", "side": "hit", "entry": 2026},
    # KBO pitchers (incl. MLB returnees)
    {"name": "Seunghwan Oh", "league": "KBO", "side": "pit", "entry": 2016},
    {"name": "Merrill Kelly", "league": "KBO", "side": "pit", "entry": 2019, "returnee": True},
    {"name": "Kwang Hyun Kim", "league": "KBO", "side": "pit", "entry": 2020},
    {"name": "Brooks Raley", "league": "KBO", "side": "pit", "entry": 2020, "returnee": True},
    {"name": "Chris Flexen", "league": "KBO", "side": "pit", "entry": 2021, "returnee": True},
    {"name": "Drew Rucinski", "league": "KBO", "side": "pit", "entry": 2023, "returnee": True},
    {"name": "Erick Fedde", "league": "KBO", "side": "pit", "entry": 2024, "returnee": True},
    # KBO hitters
    {"name": "Byung Ho Park", "league": "KBO", "side": "hit", "entry": 2016},
    {"name": "Hyun Soo Kim", "league": "KBO", "side": "hit", "entry": 2016},
    {"name": "Jae-gyun Hwang", "league": "KBO", "side": "hit", "entry": 2017},
    {"name": "Ha-Seong Kim", "league": "KBO", "side": "hit", "entry": 2021},
    {"name": "Jung Hoo Lee", "league": "KBO", "side": "hit", "entry": 2024},
]

# B-Ref register "Lg" labels per platform league
_LG_LABELS = {"NPB": {"JPPL", "JPCL", "NPB"}, "KBO": {"KBO"}}
_last_bref_fetch = 0.0


def _bref_get(url: str, cache_name: str) -> str | None:
    global _last_bref_fetch
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    wait = BREF_DELAY_S - (time.time() - _last_bref_fetch)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 "
                                 "(Windows NT 10.0; Win64; x64) Chrome/120.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as e:                                    # noqa: BLE001
        log.warning("bref fetch failed %s: %s", url, e)
        return None
    finally:
        _last_bref_fetch = time.time()
    path.write_text(text, encoding="utf-8")
    return text


def register_page(name: str) -> str | None:
    """Search B-Ref for the player, follow to the MLB page, return the
    register page HTML (where NPB/KBO seasons live)."""
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower())
    q = urllib.parse.quote(name)
    search = _bref_get(f"https://www.baseball-reference.com/search/search.fcgi?search={q}",
                       f"search_{slug}.html")
    if not search:
        return None
    m = re.search(r'/register/player\.fcgi\?id=[\w.-]+', search)
    if not m:
        # search page (not a redirect) — follow the first MLB player hit
        pm = re.search(r'href="(/players/\w/[\w.]+\.shtml)"', search)
        if not pm:
            return None
        page = _bref_get("https://www.baseball-reference.com" + pm.group(1),
                         f"mlb_{slug}.html")
        if not page:
            return None
        m = re.search(r'/register/player\.fcgi\?id=[\w.-]+', page)
        if not m:
            return None
    return _bref_get("https://www.baseball-reference.com" + m.group(0),
                     f"register_{slug}.html")


def _rows_from_table(html: str, table_id: str) -> list[dict]:
    """Parse a B-Ref stats table (register pages keep them in plain DOM;
    fall back to comment-wrapped copies)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=table_id)
    if table is None:
        for c in soup.find_all(string=lambda t: isinstance(t, str)
                               and table_id in t and "<table" in t):
            sub = BeautifulSoup(str(c), "html.parser")
            table = sub.find("table", id=table_id)
            if table is not None:
                break
    if table is None:
        return []
    out = []
    for tr in table.find_all("tr"):
        row = {}
        th = tr.find("th", {"data-stat": True})
        if th is not None:
            row[th["data-stat"]] = th.get_text(strip=True)
        for td in tr.find_all("td", {"data-stat": True}):
            row[td["data-stat"]] = td.get_text(strip=True)
        if row:
            out.append(row)
    return out


def _f(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def final_foreign_line(reg_html: str, league: str, side: str,
                       entry: int) -> dict | None:
    """Last qualifying NPB/KBO season strictly before MLB entry."""
    table_id = "standard_pitching" if side == "pit" else "standard_batting"
    rows = _rows_from_table(reg_html, table_id)
    labels = _LG_LABELS[league]
    best = None
    for r in rows:
        yr = _f(r.get("year_ID") or r.get("year"))
        lg = (r.get("lg_ID") or r.get("comp_name_abbr") or "").strip()
        if yr is None or int(yr) >= entry or lg not in labels:
            continue
        if side == "pit":
            ip = _f(r.get("IP") or r.get("p_ip"))
            era = _f(r.get("earned_run_avg") or r.get("p_earned_run_avg"))
            so = _f(r.get("SO") or r.get("p_so"))
            bf = _f(r.get("batters_faced") or r.get("p_bfp"))
            if ip is None or era is None or ip < MIN_FOREIGN_IP:
                continue
            cand = {"season": int(yr), "era": era, "ip": ip, "so": so, "bf": bf}
        else:
            pa = _f(r.get("PA") or r.get("b_pa"))
            ops = _f(r.get("onbase_plus_slugging") or r.get("b_onbase_plus_slugging"))
            so = _f(r.get("SO") or r.get("b_so"))
            if pa is None or ops is None or pa < MIN_FOREIGN_PA:
                continue
            cand = {"season": int(yr), "ops": ops, "pa": pa, "so": so,
                    "k_pct": (so / pa) if so is not None and pa else None}
        if best is None or cand["season"] > best["season"]:
            best = cand
    return best


def _mlbam_for(name: str) -> int | None:
    q = urllib.parse.quote(name)
    url = f"https://statsapi.mlb.com/api/v1/people/search?names={q}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read())
    except Exception:                                          # noqa: BLE001
        return None
    people = d.get("people") or []
    return int(people[0]["id"]) if people else None


def first_mlb_line(mlbam: int, side: str, entry: int) -> dict | None:
    import milb_history as mh
    group = "pitching" if side == "pit" else "hitting"
    for season in range(entry, min(entry + 2, 2027)):
        rows = [r for r in (mh.player_index(season, group).get(mlbam) or [])
                if r.get("level") == "MLB"]
        if not rows:
            continue
        r = rows[0]
        if side == "pit":
            ip = _f(r.get("ip"))
            era = _f(r.get("era"))
            bf = _f(r.get("bf"))
            so = _f(r.get("so"))
            if ip is None or era is None or ip < MIN_MLB_IP:
                continue
            return {"season": season, "era": era, "ip": ip, "so": so, "bf": bf}
        pa = _f(r.get("pa"))
        ops = _f(r.get("ops"))
        so = _f(r.get("so"))
        if pa is None or ops is None or pa < MIN_MLB_PA:
            continue
        return {"season": season, "ops": ops, "pa": pa, "so": so,
                "k_pct": (so / pa) if so is not None and pa else None}
    return None


def _shrunk(measured: float, n: float, prior: float, k: float = SHRINK_K) -> float:
    return (n * measured + k * prior) / (n + k)


def run(persist: bool = True) -> dict:
    from overseas_export import LEAGUE_CONTEXT
    cohort = []
    acct = {"listed": len(TRANSITIONS), "resolved": 0,
            "no_register_page": 0, "no_foreign_line": 0, "no_mlb_line": 0}
    for t in TRANSITIONS:
        reg = register_page(t["name"])
        if not reg:
            acct["no_register_page"] += 1
            cohort.append({**t, "status": "no_register_page"})
            continue
        foreign = final_foreign_line(reg, t["league"], t["side"], t["entry"])
        if not foreign:
            acct["no_foreign_line"] += 1
            cohort.append({**t, "status": "no_foreign_line"})
            continue
        mlbam = _mlbam_for(t["name"])
        mlb = first_mlb_line(mlbam, t["side"], t["entry"]) if mlbam else None
        if not mlb:
            acct["no_mlb_line"] += 1
            cohort.append({**t, "status": "no_mlb_line", "foreign": foreign})
            continue
        acct["resolved"] += 1
        cohort.append({**t, "status": "resolved", "foreign": foreign, "mlb": mlb})

    factors: dict[str, dict] = {}
    for lg in ("NPB", "KBO"):
        inc = LEAGUE_CONTEXT[lg]
        pit = [c for c in cohort if c["league"] == lg and c["side"] == "pit"
               and c["status"] == "resolved"]
        # ratio of IP-weighted means (not mean of ratios — a 1.80-ERA
        # foreign season would otherwise dominate)
        w = sum(min(c["foreign"]["ip"], c["mlb"]["ip"]) for c in pit)
        era_for = (sum(c["foreign"]["era"] * min(c["foreign"]["ip"], c["mlb"]["ip"])
                       for c in pit) / w) if w else None
        era_mlb = (sum(c["mlb"]["era"] * min(c["foreign"]["ip"], c["mlb"]["ip"])
                       for c in pit) / w) if w else None
        era_ratio = (era_mlb / era_for) if era_for else None
        hit = [c for c in cohort if c["league"] == lg and c["side"] == "hit"
               and c["status"] == "resolved"
               and c["foreign"].get("k_pct") is not None
               and c["mlb"].get("k_pct") is not None]
        wpa = sum(min(c["foreign"]["pa"], c["mlb"]["pa"]) for c in hit)
        k_delta = (sum((c["mlb"]["k_pct"] - c["foreign"]["k_pct"])
                       * min(c["foreign"]["pa"], c["mlb"]["pa"])
                       for c in hit) / wpa) if wpa else None
        ops_ratio = (sum(c["mlb"]["ops"] * min(c["foreign"]["pa"], c["mlb"]["pa"])
                         for c in hit)
                     / sum(c["foreign"]["ops"] * min(c["foreign"]["pa"], c["mlb"]["pa"])
                           for c in hit)) if hit else None
        factors[lg] = {
            "n_pitchers": len(pit), "n_hitters": len(hit),
            "measured_era_ratio": round(era_ratio, 3) if era_ratio else None,
            "incumbent_era_factor": inc["pitcher_era_factor"],
            "shipped_era_factor": (round(_shrunk(era_ratio, len(pit),
                                                 inc["pitcher_era_factor"]), 3)
                                   if era_ratio else inc["pitcher_era_factor"]),
            "measured_k_pct_delta": round(k_delta, 4) if k_delta is not None else None,
            "incumbent_k_pct_delta": inc["hitter_k_pct_delta"],
            "shipped_k_pct_delta": (round(_shrunk(k_delta, len(hit),
                                                  inc["hitter_k_pct_delta"]), 3)
                                    if k_delta is not None else inc["hitter_k_pct_delta"]),
            "measured_raw_ops_ratio_NOT_SHIPPED": round(ops_ratio, 3) if ops_ratio else None,
            "incumbent_wrc_factor_retained": inc["hitter_wrc_factor"],
        }

    out = {
        "generated_at": date.today().isoformat(),
        "conventions": {
            "cohort": "curated NPB/KBO -> MLB transitions 2015-2026 (returnees flagged); foreign side = last qualifying season pre-entry (B-Ref register); MLB side = first season >= entry with min exposure (StatsAPI)",
            "era_factor": f"IP-weighted ratio of means, shrunk k={SHRINK_K} toward incumbent",
            "k_pct_delta": f"PA-weighted mean delta, shrunk k={SHRINK_K}",
            "not_shipped": "hitter_wrc_factor (needs per-season foreign league context — raw OPS ratio reported as analog), fb_velo_delta (no source), CPBL/CUBA/NPBF (n too small, stay prior)",
            "exclusions": "players whose pages fail to resolve/parse are excluded and counted — the ledger is owner-extendable",
        },
        "accounting": acct,
        "factors": factors,
        "cohort": cohort,
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    print("accounting:", rep["accounting"])
    for lg, f in rep["factors"].items():
        print(lg, json.dumps(f))
