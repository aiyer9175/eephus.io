# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ Module 01 — Reliability of public defensive metrics (Part 1).
Question: which metrics are stable talent signals vs noise, and how much
sample do they need? First cut = adjacent-year (t -> t+1) Pearson r among
players qualified in both seasons, position-specific where possible, plus a
low/high-sample split to expose sample-dependence.

Sources confirmed reachable (Module 00): Baseball Savant only. FG is 403-blocked.
"""
import os, time, warnings, requests, re, json
from io import StringIO
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
pd.set_option("display.width", 220)

ROOT = os.path.expanduser("~/defense_plus")
RAW = os.path.join(ROOT, "data/raw"); REP = os.path.join(ROOT, "reports")
os.makedirs(RAW, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
YEARS = [2021, 2022, 2023, 2024, 2025]

def get_csv(url, cache):
    fp = os.path.join(RAW, cache)
    if os.path.exists(fp):
        return pd.read_csv(fp)
    r = requests.get(url, headers=H, timeout=60); r.raise_for_status()
    df = pd.read_csv(StringIO(r.text)); df.to_csv(fp, index=False); time.sleep(0.3)
    return df

def pull_oaa(year, pos):  # pos in {'if','of'} ; unified OAA leaderboard, position-labelled
    url = (f"https://baseballsavant.mlb.com/leaderboard/outs_above_average?type=Fielder"
           f"&startYear={year}&endYear={year}&split=no&team=&range=year&min=q&pos={pos}"
           f"&roles=&viz=show&csv=true")
    return get_csv(url, f"oaa_{pos}_{year}.csv")

def pull_framing(year):
    # /leaderboard/catcher-framing CSV ignores year; the /catcher_framing PAGE is
    # year-sensitive with the grid embedded as `data = [...]`. Parse that.
    fp = os.path.join(RAW, f"framing_{year}.csv")
    if os.path.exists(fp):
        return pd.read_csv(fp)
    t = requests.get(f"https://baseballsavant.mlb.com/catcher_framing?year={year}&team=&min=q&type=catcher",
                     headers=H, timeout=60).text
    arr = json.loads(re.search(r'\bdata\s*=\s*(\[\{.*?\}\])\s*;', t, re.DOTALL).group(1))
    df = pd.DataFrame(arr)[["id", "name", "rv_tot", "pct_tot", "pitches"]]
    df.to_csv(fp, index=False); time.sleep(0.3)
    return df

def pull_poptime(year):
    url = (f"https://baseballsavant.mlb.com/leaderboard/poptime?year={year}"
           f"&team=&min2b=5&min3b=0&csv=true")
    return get_csv(url, f"poptime_{year}.csv")

def pull_arm(year):
    url = (f"https://baseballsavant.mlb.com/leaderboard/arm-strength?type=player"
           f"&year={year}&minThrows=50&csv=true")   # 'year' is respected; 'season' is ignored
    return get_csv(url, f"arm_{year}.csv")

# ---------- build long tables: [player_id, year, pos, value, sample] ----------
def long_oaa():
    rows = []
    for y in YEARS:
        for pos in ("if", "of"):
            try: d = pull_oaa(y, pos)
            except Exception as e: print("oaa fail", y, pos, str(e)[:60]); continue
            d = d.rename(columns={"player_id": "id"})
            samp = "attempts" if "attempts" in d.columns else None
            for _, r in d.iterrows():
                rows.append(dict(id=int(r["id"]), year=y,
                                 pos=str(r.get("primary_pos_formatted", pos)).strip(),
                                 value=r.get("outs_above_average"),
                                 frp=r.get("fielding_runs_prevented"),
                                 sample=(r.get(samp) if samp else np.nan)))
    return pd.DataFrame(rows)

def long_simple(puller, idcol, valcol, sampcol, posname):
    rows = []
    for y in YEARS:
        try: d = puller(y)
        except Exception as e: print(posname, "fail", y, str(e)[:60]); continue
        for _, r in d.iterrows():
            if pd.isna(r.get(valcol)): continue
            rows.append(dict(id=int(r[idcol]), year=y, pos=posname,
                             value=r.get(valcol), frp=np.nan,
                             sample=r.get(sampcol) if sampcol else np.nan))
    return pd.DataFrame(rows)

# ---------- reliability computation ----------
def adjacent_r(df, label):
    """pool t->t+1 pairs within same pos; return r, n, and low/high-sample split."""
    out = []
    for pos, g in df.groupby("pos"):
        pairs = []
        for y in YEARS[:-1]:
            a = g[g.year == y][["id", "value", "sample"]]
            b = g[g.year == y + 1][["id", "value"]].rename(columns={"value": "value2"})
            m = a.merge(b, on="id")
            pairs.append(m)
        P = pd.concat(pairs) if pairs else pd.DataFrame()
        P = P.dropna(subset=["value", "value2"])
        if len(P) < 25:  # too few to trust
            if len(P) >= 8:
                out.append((label, pos, len(P), round(P["value"].corr(P["value2"]), 3), np.nan, np.nan))
            continue
        r_all = P["value"].corr(P["value2"])
        r_lo = r_hi = np.nan
        if P["sample"].notna().sum() > 20:
            med = P["sample"].median()
            lo = P[P["sample"] <= med]; hi = P[P["sample"] > med]
            if len(lo) >= 10: r_lo = lo["value"].corr(lo["value2"])
            if len(hi) >= 10: r_hi = hi["value"].corr(hi["value2"])
        out.append((label, pos, len(P), round(r_all, 3),
                    round(r_lo, 3) if pd.notna(r_lo) else np.nan,
                    round(r_hi, 3) if pd.notna(r_hi) else np.nan))
    return out

print("pulling OAA (IF/OF)...");    oaa = long_oaa()
print("pulling framing...");        fram = long_simple(pull_framing, "id", "rv_tot", "pitches", "C-framing")
print("pulling poptime...");        pop = long_simple(pull_poptime, "player_id", "pop_2b_sba", "pop_2b_sba_count", "C-poptime") \
                                          if False else None
# poptime column names vary; resolve dynamically
def long_poptime():
    rows = []
    for y in YEARS:
        try: d = pull_poptime(y)
        except Exception as e: print("poptime fail", y, str(e)[:60]); continue
        idc = "player_id" if "player_id" in d.columns else ("entity_id" if "entity_id" in d.columns else d.columns[1])
        valc = "pop_2b_sba" if "pop_2b_sba" in d.columns else None
        sampc = "pop_2b_sba_count" if "pop_2b_sba_count" in d.columns else None
        if valc is None: print("poptime cols:", list(d.columns)); continue
        for _, r in d.iterrows():
            if pd.isna(r.get(valc)): continue
            rows.append(dict(id=int(r[idc]), year=y, pos="C-poptime",
                             value=r.get(valc), frp=np.nan, sample=r.get(sampc)))
    return pd.DataFrame(rows)
pop = long_poptime()

def long_arm():
    rows = []
    for y in YEARS:
        try: d = pull_arm(y)
        except Exception as e: print("arm fail", y, str(e)[:60]); continue
        idc = "player_id"
        for _, r in d.iterrows():
            ov = r.get("arm_overall")
            if pd.isna(ov): continue
            rows.append(dict(id=int(r[idc]), year=y, pos="arm-"+str(r.get("primary_position","?")),
                             value=ov, frp=np.nan, sample=r.get("total_throws")))
    return pd.DataFrame(rows)
arm = long_arm()

results = []
results += adjacent_r(oaa, "OAA")
# FRP reliability (infield runs prevented)
oaa_frp = oaa.dropna(subset=["frp"]).copy(); oaa_frp["value"] = oaa_frp["frp"]
results += adjacent_r(oaa_frp, "FRP")
results += adjacent_r(fram, "Framing-RV")
results += adjacent_r(pop, "PopTime")
results += adjacent_r(arm, "ArmStrength")

R = pd.DataFrame(results, columns=["metric","pos","n_pairs","r_yoy","r_lowsample","r_highsample"])
R = R[R.n_pairs >= 8].sort_values(["metric","pos"]).reset_index(drop=True)
R.to_csv(os.path.join(REP, "01_reliability.csv"), index=False)
print("\n================ YEAR-TO-YEAR RELIABILITY (t -> t+1) ================")
print(R.to_string(index=False))
print(f"\nwrote {os.path.join(REP,'01_reliability.csv')}")
