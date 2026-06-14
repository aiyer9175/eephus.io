# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E06 — Historical contract pull (Cot's bot-walled -> Wayback Spotrac).

Cot's is behind an Anubis bot wall; Spotrac /yearly/ team payroll pages are
captured on Wayback and parse cleanly with pandas.read_html (player, pos, age,
salary-by-year with $ / UFA / ARB). For each team x target year (2023-25) we
take the capture nearest Opening Day and extract contract status AS OF the
preseason of that year (timestamp-valid: known when projecting that season).

Per player-target_year features:
  cur_salary            this-year cap figure ($)
  total_remaining_guar  sum of guaranteed $ this year + future years
  years_remaining_guar  # future years with a guaranteed $
  walk_year             1 if UFA next year (free-agent-to-be)
  is_arb                arbitration this year
  guaranteed_multiyr    signed beyond this season

Name -> MLBAM via normalized-name bridge from usage_hitting.

Output: data/raw/contracts_raw.parquet, data/processed/contract_features.parquet
"""
import io
import re
import time
import unicodedata

import pandas as pd
import requests

PT = "/Users/willcahoon/playing_time_model"
OUT = f"{PT}/expansion/data"
TEAMS = ['arizona-diamondbacks', 'atlanta-braves', 'baltimore-orioles',
         'boston-red-sox', 'chicago-cubs', 'chicago-white-sox',
         'cincinnati-reds', 'cleveland-guardians', 'colorado-rockies',
         'detroit-tigers', 'houston-astros', 'kansas-city-royals',
         'los-angeles-angels', 'los-angeles-dodgers', 'miami-marlins',
         'milwaukee-brewers', 'minnesota-twins', 'new-york-mets',
         'new-york-yankees', 'philadelphia-phillies', 'pittsburgh-pirates',
         'san-diego-padres', 'seattle-mariners', 'san-francisco-giants',
         'st-louis-cardinals', 'tampa-bay-rays', 'texas-rangers',
         'toronto-blue-jays', 'washington-nationals', 'athletics', 'oakland-athletics']
YEARS = [2023, 2024, 2025]
H = {"User-Agent": "Mozilla/5.0"}


def norm(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s.lower())
    return re.sub(r"[^a-z ]", "", s).strip()


def dollars(x):
    m = re.search(r"\$([0-9,]+)", str(x))
    return int(m.group(1).replace(",", "")) if m else None


def captures(team):
    url = (f"http://web.archive.org/cdx/search/cdx?url=spotrac.com/mlb/{team}/yearly"
           f"&matchType=prefix&output=text&fl=timestamp,original&from=20230101"
           f"&to=20250701&filter=statuscode:200&collapse=timestamp:8")
    for a in range(4):
        try:
            r = requests.get(url, timeout=40); r.raise_for_status(); break
        except Exception:
            if a == 3:
                return []
            time.sleep(5)
    rows = [ln.split(" ", 1) for ln in r.text.strip().splitlines() if ln]
    # prefer the bare /yearly or /yearly/ page (full roster), not sorted views
    return [(ts, u) for ts, u in rows if re.search(r"/yearly/?$", u)] or rows


def best(caps, year):
    target = pd.Timestamp(f"{year}-04-01")
    same = [(ts, u) for ts, u in caps
            if abs((pd.to_datetime(ts[:8]) - target).days) <= 200]
    if not same:
        return None
    return min(same, key=lambda x: abs((pd.to_datetime(x[0][:8]) - target).days))


def parse_page(html, year):
    out = []
    try:
        tabs = pd.read_html(io.StringIO(html))
    except ValueError:
        return out
    ycols = [str(y) for y in range(year, year + 12)]
    for t in tabs:
        cols = [str(c) for c in t.columns]
        pcol = next((c for c in t.columns if str(c).startswith("Player")), None)
        if pcol is None or str(year) not in cols:
            continue
        fut = [c for c in cols if c.isdigit() and int(c) > year]
        for _, r in t.iterrows():
            raw = str(r[pcol])
            parts = re.split(r"\s{2,}", raw.strip())
            name = parts[-1] if parts else raw
            if not name or name.lower() == "nan":
                continue
            cur = r[str(year)] if str(year) in r else None
            cur_sal = dollars(cur)
            future_vals = [r[c] for c in fut if c in r]
            yrs_guar = sum(1 for v in future_vals if dollars(v) is not None)
            tot = (cur_sal or 0) + sum(dollars(v) or 0 for v in future_vals)
            nxt = r[fut[0]] if fut else None
            walk = 1 if (nxt is not None and "UFA" in str(nxt).upper()) else 0
            is_arb = 1 if "ARB" in str(cur).upper() else 0
            out.append({"name": name, "target_year": year, "cur_salary": cur_sal,
                        "total_remaining_guar": tot if tot > 0 else None,
                        "years_remaining_guar": yrs_guar, "walk_year": walk,
                        "is_arb": is_arb,
                        "guaranteed_multiyr": int(yrs_guar >= 1)})
    return out


def fetch(ts, url):
    wb = f"https://web.archive.org/web/{ts}id_/{url}"
    for a in range(4):
        try:
            r = requests.get(wb, timeout=60, headers=H)
            if r.ok and len(r.content) > 5000:
                return r.text
        except Exception:
            pass
        time.sleep(5)
    return None


rows = []
seen = set()
for team in TEAMS:
    caps = captures(team)
    for y in YEARS:
        b = best(caps, y)
        if not b:
            print(f"{team} {y}: no capture", flush=True)
            continue
        ts, url = b
        if (team, y) in seen:
            continue
        html = fetch(ts, url)
        if not html:
            print(f"{team} {y}: fetch fail", flush=True)
            continue
        recs = parse_page(html, y)
        for rr in recs:
            rr["team"] = team
        rows.extend(recs)
        seen.add((team, y))
        print(f"{team} {y}: {len(recs)} players (cap {ts[:8]})", flush=True)
        time.sleep(1)

raw = pd.DataFrame(rows)
raw.to_parquet(f"{OUT}/raw/contracts_raw.parquet", index=False)
print("raw contracts:", raw.shape, flush=True)

# name -> mlbam bridge from usage_hitting
uh = pd.read_parquet(f"{PT}/data/raw/usage_hitting.parquet")[["mlbam_id", "player_name"]].dropna().drop_duplicates()
uh["nm"] = uh.player_name.map(norm)
bridge = uh.drop_duplicates("nm").set_index("nm").mlbam_id
raw["nm"] = raw.name.map(norm)
raw["mlbam_id"] = raw.nm.map(bridge)
matched = raw.dropna(subset=["mlbam_id"]).copy()
matched["mlbam_id"] = matched.mlbam_id.astype(int)
# dedupe (player on 2 team pages same year -> keep max total)
matched = matched.sort_values("total_remaining_guar").drop_duplicates(
    ["mlbam_id", "target_year"], keep="last")
import numpy as np
matched["log_cur_salary"] = np.log1p(matched.cur_salary.fillna(0))
matched["log_total_guar"] = np.log1p(matched.total_remaining_guar.fillna(0))
feat = matched[["mlbam_id", "target_year", "log_cur_salary", "log_total_guar",
                "years_remaining_guar", "walk_year", "is_arb",
                "guaranteed_multiyr"]]
feat.to_parquet(f"{OUT}/processed/contract_features.parquet", index=False)
print(f"matched {len(matched)}/{len(raw)} ({len(matched)/len(raw):.0%}); "
      f"contract_features {feat.shape}")
