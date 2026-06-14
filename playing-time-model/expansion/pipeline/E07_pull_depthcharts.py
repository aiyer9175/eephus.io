# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026
"""
Expansion E07 — Historical depth-chart pull (Wayback mlb.com).

mlb.com depth charts are FACTUAL team-published role info (not a projection):
per-position tables, players in DEPTH ORDER (starter first). Validated: the
Apr-2023 Yankees chart correctly lists rookie Anthony Volpe as #1 SS — the
role-resolution signal our model lacks. statsapi serves only the current chart
(date param ignored), so history = Wayback captures of the rendered pages,
which pandas.read_html parses cleanly.

For each team x target year (2023-25): the capture nearest Opening Day (~Apr 1,
within Feb-May = preseason role plan, timestamp-valid). Extract
depth_rank_at_position (1 = projected starter). Name -> MLBAM bridge.

Output: data/processed/depth_rank.parquet (mlbam_id, target_year, dc_position,
        depth_rank), data/raw/E07.log
"""
import io
import re
import time
import unicodedata

import pandas as pd
import requests

PT = "/Users/willcahoon/playing_time_model"
OUT = f"{PT}/expansion/data"
H = {"User-Agent": "Mozilla/5.0"}
SLUGS = ["angels", "astros", "athletics", "bluejays", "braves", "brewers",
         "cardinals", "cubs", "dbacks", "dodgers", "giants", "guardians",
         "mariners", "marlins", "mets", "nationals", "orioles", "padres",
         "phillies", "pirates", "rangers", "rays", "reds", "redsox", "rockies",
         "royals", "tigers", "twins", "whitesox", "yankees"]
YEARS = [2023, 2024, 2025]
POSMAP = {"Catcher": "C", "First Base": "1B", "Second Base": "2B",
          "Third Base": "3B", "Shortstop": "SS", "Left Field": "LF",
          "Center Field": "CF", "Right Field": "RF", "Designated Hitter": "DH"}


def norm(name):
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s.lower())
    return re.sub(r"[^a-z ]", "", s).strip()


def cdx(slug):
    url = (f"http://web.archive.org/cdx/search/cdx?url=mlb.com/{slug}/roster/"
           f"depth-chart&output=text&fl=timestamp,original&from=20230101"
           f"&to=20250601&filter=statuscode:200&collapse=timestamp:8")
    for a in range(4):
        try:
            r = requests.get(url, timeout=40); r.raise_for_status()
            return [ln.split(" ", 1) for ln in r.text.strip().splitlines() if ln]
        except Exception:
            if a == 3:
                return []
            time.sleep(6)


def best(caps, year):
    tgt = pd.Timestamp(f"{year}-04-01")
    win = [(ts, u) for ts, u in caps
           if pd.Timestamp(f"{year}-02-01") <= pd.to_datetime(ts[:8]) <= pd.Timestamp(f"{year}-05-20")]
    return min(win, key=lambda x: abs((pd.to_datetime(x[0][:8]) - tgt).days)) if win else None


def fetch(ts, url):
    wb = f"https://web.archive.org/web/{ts}id_/{url}"
    for a in range(4):
        try:
            r = requests.get(wb, timeout=60, headers=H)
            if r.ok and len(r.content) > 20000:
                return r.text
        except Exception:
            pass
        time.sleep(5 * (a + 1))
    return None


def parse(html, slug, year):
    rows = []
    try:
        tabs = pd.read_html(io.StringIO(html))
    except ValueError:
        return rows
    for t in tabs:
        pos = str(t.columns[0])
        if pos not in POSMAP or t.shape[1] < 2:
            continue
        for rank, cell in enumerate(t.iloc[:, 1].tolist(), start=1):
            name = re.split(r"\s{2,}", str(cell).strip())[0]
            if name and name.lower() != "nan":
                rows.append({"slug": slug, "target_year": year,
                             "dc_position": POSMAP[pos], "depth_rank": rank,
                             "name": name})
    return rows


def main():
    allrows = []
    for slug in SLUGS:
        caps = cdx(slug)
        for y in YEARS:
            b = best(caps, y)
            if not b:
                print(f"{slug} {y}: no capture", flush=True)
                continue
            html = fetch(*b)
            if not html:
                print(f"{slug} {y}: fetch fail", flush=True)
                continue
            r = parse(html, slug, y)
            allrows.extend(r)
            print(f"{slug} {y}: {len(r)} rows (cap {b[0][:8]})", flush=True)
            time.sleep(2)
    raw = pd.DataFrame(allrows)
    raw.to_parquet(f"{OUT}/raw/depth_charts_raw.parquet", index=False)
    print("raw depth rows:", raw.shape, flush=True)

    # name -> mlbam bridge
    uh = pd.read_parquet(f"{PT}/data/raw/usage_hitting.parquet")[["mlbam_id", "player_name"]].dropna().drop_duplicates()
    uh["nm"] = uh.player_name.map(norm)
    bridge = uh.drop_duplicates("nm").set_index("nm").mlbam_id
    raw["nm"] = raw.name.map(norm)
    raw["mlbam_id"] = raw.nm.map(bridge)
    m = raw.dropna(subset=["mlbam_id"]).copy()
    m["mlbam_id"] = m.mlbam_id.astype(int)
    # a player can be listed at multiple positions; keep his BEST (min) depth rank
    m = m.sort_values("depth_rank").drop_duplicates(["mlbam_id", "target_year"], keep="first")
    m[["mlbam_id", "target_year", "dc_position", "depth_rank"]].to_parquet(
        f"{OUT}/processed/depth_rank.parquet", index=False)
    print(f"matched {len(m)}/{len(raw)} ({len(m)/max(len(raw),1):.0%}); "
          f"depth_rank saved {m.shape}; starters (rank1): {(m.depth_rank==1).sum()}")


if __name__ == "__main__":
    main()
