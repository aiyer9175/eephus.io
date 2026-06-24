# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
Defense+ — add FanGraphs as a 4th evaluable grading source and compare to MLB Pipeline.
FG "The Board" grades (Fld/Spd/Arm) from historical boards (2018-2021, graduated prospects),
mapped FG playerId -> MLBAM via Chadwick, joined to realized MLB defense (OAA-z + arm mph).
"""
import os, json, time, warnings
import numpy as np, pandas as pd, requests
warnings.filterwarnings("ignore"); pd.set_option("display.width", 200)
HOME = os.path.expanduser("~"); RAW = os.path.join(HOME, "defense_plus/data/raw")
H = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

def board(year):
    fp = os.path.join(RAW, f"fg_board_{year}.parquet")
    if os.path.exists(fp): return pd.read_parquet(fp)
    t = requests.get(f"https://www.fangraphs.com/prospects/the-board/{year}-prospect-list/summary", headers=H, timeout=40).text
    i = t.find('id="__NEXT_DATA__"'); j = t.find('>', i) + 1; k = t.find('</script>', j)
    data = json.loads(t[j:k])["props"]["pageProps"]["dehydratedState"]["queries"][0]["state"]["data"]
    d = pd.DataFrame(data)
    keep = [c for c in ["playerName", "PlayerId", "Position", "fFld", "fSpd", "pArm", "Arm"] if c in d.columns]
    d = d[keep].copy(); d.to_parquet(fp); time.sleep(0.5); return d

fg = []
for y in range(2018, 2022):
    try: fg.append(board(y).assign(byear=y))
    except Exception as e: print("board", y, "fail", str(e)[:50])
FG = pd.concat(fg, ignore_index=True)
FG["fg"] = pd.to_numeric(FG["PlayerId"], errors="coerce")
for c in ["fFld", "fSpd", "pArm"]:
    if c in FG.columns: FG[c] = pd.to_numeric(FG[c], errors="coerce")
FG = FG.sort_values("byear").groupby("fg").first().reset_index()   # earliest board per player

# map FG -> MLBAM
import pybaseball as pb
ch = pb.chadwick_register()[["key_fangraphs", "key_mlbam"]].dropna()
FG = FG.merge(ch, left_on="fg", right_on="key_fangraphs", how="left").dropna(subset=["key_mlbam"])
FG["mlbam_id"] = FG["key_mlbam"].astype(int)

# outcomes: MLB OAA-z (within pos, Inn-wt) + arm strength
fr = []
for y in range(2016, 2026):
    f = os.path.join(RAW, f"fg_field_full_{y}.csv")
    if os.path.exists(f):
        d = pd.read_csv(f).rename(columns={"xMLBAMID": "id"})
        for c in ["id", "OAA", "Inn"]: d[c] = pd.to_numeric(d[c], errors="coerce")
        d["year"] = y; fr.append(d[["id", "Pos", "year", "OAA", "Inn"]])
Fd = pd.concat(fr); Fd = Fd[Fd.Inn >= 300].dropna(subset=["OAA"])
Fd["oaa_z"] = Fd.groupby(["Pos", "year"])["OAA"].transform(lambda x: (x - x.mean()) / x.std())
q = Fd.groupby("id").apply(lambda x: np.average(x.oaa_z, weights=x.Inn)).rename("oaa_z").reset_index().rename(columns={"id": "mlbam_id"})
A = pd.concat([pd.read_csv(os.path.join(RAW, f"arm_{y}.csv")).rename(columns={"player_id": "mlbam_id"}) for y in range(2020, 2026)])
arm = A.groupby("mlbam_id")["arm_overall"].apply(lambda x: pd.to_numeric(x, errors="coerce").mean()).rename("arm").reset_index()

E = FG.merge(q, on="mlbam_id", how="left").merge(arm, on="mlbam_id", how="left")
def corr(a, b):
    s = E.dropna(subset=[a, b]); return (s[a].corr(s[b]), len(s)) if len(s) >= 10 else (np.nan, len(s))
fo, nf = corr("fFld", "oaa_z"); so, ns = corr("fSpd", "oaa_z"); aa, na = corr("pArm", "arm")
print(f"FG board prospects mapped: {len(FG)} | graduated w/ MLB OAA: {E.oaa_z.notna().sum()}\n")
print("=== GRADING-SOURCE accuracy head-to-head (defensive grades -> realized MLB defense) ===")
print(f"{'source':14}{'field→OAA r':>13}{'n':>5}{'speed→OAA r':>13}{'n':>5}{'arm/throw→arm r':>17}{'n':>5}")
print(f"{'MLB Pipeline':14}{0.32:>13.2f}{214:>5}{0.25:>13.2f}{214:>5}{0.47:>17.2f}{292:>5}")
print(f"{'FanGraphs':14}{fo:>13.2f}{nf:>5}{so:>13.2f}{ns:>5}{aa:>17.2f}{na:>5}")
E[["mlbam_id", "playerName", "Position", "fFld", "fSpd", "pArm", "oaa_z", "arm"]].to_csv(os.path.join(REP if (REP:=os.path.join(HOME,"defense_plus/reports")) else ".", "27_fg_grade_eval.csv"), index=False)
print(f"\nwrote reports/27_fg_grade_eval.csv")
