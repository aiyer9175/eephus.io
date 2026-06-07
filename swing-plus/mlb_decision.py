# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
mlb_decision.py — MLB-native, swing-TAILORED swing-decision RUN-VALUE model.

v2: full base-out-count context via Statcast `delta_run_exp` (MLBAM's per-pitch run
value, already conditioned on base state, outs, and count). Every swing/take is valued
in RUNS in its real game state — a chase with two outs and a runner on third is costed
correctly, a 3-1 take with the bases loaded is valued correctly, etc.

For each pitch (state = base-out × count):
  EV_take  = P(called strike|loc)·RE_strike(state) + (1-P)·RE_ball(state)
  EV_swing = whiff·RE_strike + foul·RE_foul + inplay·RE_bip(hitter, base-out)   # his rates
  decision_rv = (swung - P_swing_league(zone,count)) · (EV_swing - EV_take)
Summed per hitter -> decision run value (runs), scaled to Decision+ (100±10) and 20-90.

The swing value is PERSONAL (his whiff/foul/contact rates + his contact run value), so a
hitter is graded on selecting pitches HIS swing handles. Every component sanity-checked.
"""
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
OUT = PROC / "mlb_decision.parquet"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2", "2026_H1"]
SWING = {"hit_into_play", "foul", "foul_tip", "swinging_strike", "swinging_strike_blocked", "foul_bunt", "bunt_foul_tip"}
WHIFF = {"swinging_strike", "swinging_strike_blocked", "foul_tip", "bunt_foul_tip"}
FOUL = {"foul", "foul_bunt"}
INPLAY = {"hit_into_play"}
STRIKE_TK = {"called_strike", "automatic_strike"}
BALL_TK = {"ball", "blocked_ball", "automatic_ball", "pitchout", "hit_by_pitch"}
GROUP = {"FF": "FB", "SI": "FB", "FC": "FB", "SL": "BR", "ST": "BR", "CU": "BR", "KC": "BR",
         "SV": "BR", "CS": "BR", "KN": "BR", "CH": "OFF", "FS": "OFF", "FO": "OFF", "SC": "OFF"}
def _shrink(r, n, p, k): return (n * r + k * p) / (n + k)


def _load():
    cols = ["batter", "stand", "pitch_type", "balls", "strikes", "description", "game_date",
            "plate_x", "plate_z", "sz_top", "sz_bot", "delta_run_exp", "on_1b", "on_2b", "on_3b", "outs_when_up"]
    d = pd.concat([pd.read_parquet(f"data/raw/statcast_{h}.parquet", columns=cols).assign(half=h)
                   for h in HALVES if (ROOT / f"data/raw/statcast_{h}.parquet").exists()], ignore_index=True)
    d = d[d["pitch_type"].isin(GROUP)].dropna(subset=["plate_x", "plate_z", "balls", "strikes", "delta_run_exp"]).copy()
    d = d[(d.balls <= 3) & (d.strikes <= 2) & (d.outs_when_up <= 2)]
    d["grp"] = d.pitch_type.map(GROUP)
    d["swung"] = d.description.isin(SWING).astype(int)
    d["zone"] = (np.where(d.plate_x < -0.3, 0, np.where(d.plate_x > 0.3, 2, 1)) * 3
                 + np.where(d.plate_z < 2.2, 0, np.where(d.plate_z > 3.0, 2, 1)))
    szt = d.sz_top.fillna(3.4); szb = d.sz_bot.fillna(1.6)
    d["inzone"] = (d.plate_x.abs() <= 0.83) & (d.plate_z >= szb) & (d.plate_z <= szt)
    d["bases"] = (d.on_1b.notna().astype(int) + d.on_2b.notna().astype(int) * 2 + d.on_3b.notna().astype(int) * 4)
    d["outs"] = d.outs_when_up.astype(int)
    return d


def score(verbose=True):
    d = _load()
    dre = "delta_run_exp"
    # ---- (1) base-out-count run value of a STRIKE / BALL / FOUL (from delta_run_exp) ----
    def state_table(mask, name, k=300):
        sub = d[mask]
        marg = sub.groupby(["balls", "strikes"])[dre].mean()           # count-only fallback
        cell = sub.groupby(["bases", "outs", "balls", "strikes"])[dre].agg(["mean", "size"])
        tab = {}
        for (ba, ou, b, s), r in cell.iterrows():
            tab[(ba, ou, b, s)] = _shrink(r["mean"], r["size"], marg.loc[(b, s)], k)
        return tab, marg
    RE_strike, ms = state_table(d.description.isin(STRIKE_TK | WHIFF), "strike")
    RE_ball, mb = state_table(d.description.isin(BALL_TK), "ball")
    RE_foul, mf = state_table(d.description.isin(FOUL), "foul")
    if verbose:
        print("=== (1) Run value (delta_run_exp) of strike/ball by count, bases empty/0 outs ===")
        for b, s in [(0,0),(0,2),(3,0),(3,2)]:
            print(f"  {b}-{s}: strike {RE_strike.get((0,0,b,s),ms.loc[(b,s)]):+.3f}  ball {RE_ball.get((0,0,b,s),mb.loc[(b,s)]):+.3f}")
        print(f"  walk leverage check 3-2 bases-loaded ball: {RE_ball.get((7,0,3,2),mb.loc[(3,2)]):+.3f} (should be large +)")

    # ---- (2) BIP run value by base-out (league) + hitter contact offset (tailored) ----
    bip = d[d.description.isin(INPLAY)]
    bip_lg_overall = float(bip[dre].mean())
    bip_lg = bip.groupby(["bases", "outs"])[dre].mean().to_dict()
    h_bip = bip.groupby("batter")[dre].agg(["mean", "size"])
    h_off = {b: _shrink(r["mean"], r["size"], bip_lg_overall, 120) - bip_lg_overall for b, r in h_bip.iterrows()}
    # zone-specific damage offset (for the DAMAGE-AWARE variant): how much better/worse his
    # contact run value is by pitch-group x zone vs league there (base-out-neutral as a difference)
    Lz_dre = bip.groupby(["grp", "zone"])[dre].mean().to_dict()
    hz_bip = bip.groupby(["batter", "grp", "zone"])[dre].agg(["mean", "size"])
    zone_off = {}
    for (bt, g, z), r in hz_bip.iterrows():
        lz = Lz_dre.get((g, z), bip_lg_overall)
        zone_off[(bt, g, z)] = _shrink(r["mean"], r["size"], lz, 40) - lz
    if verbose:
        print("\n=== (2) BIP run value by base-out (league) — rises with runners on ===")
        print(f"  empty/0out {bip_lg.get((0,0),0):+.3f}   1st/0out {bip_lg.get((1,0),0):+.3f}   "
              f"2nd&3rd/0out {bip_lg.get((6,0),0):+.3f}   loaded/2out {bip_lg.get((7,2),0):+.3f}")

    # ---- (3) called-strike model (location) ----
    tk = d[d.description.isin(STRIKE_TK | BALL_TK)].copy(); tk["cs"] = tk.description.isin(STRIKE_TK).astype(int)
    tk["gx"] = np.clip(np.round(tk.plate_x / 0.2), -8, 8).astype(int); tk["gz"] = np.clip(np.round(tk.plate_z / 0.2), 2, 22).astype(int)
    csg = tk.groupby(["gx", "gz"]).cs.agg(["mean", "size"]); cs_lk = {k: (v["mean"] if v["size"] >= 20 else np.nan) for k, v in csg.iterrows()}
    def cs_prob_arr(px, pz):
        gx = np.clip(np.round(px / 0.2), -8, 8).astype(int); gz = np.clip(np.round(pz / 0.2), 2, 22).astype(int)
        out = np.array([cs_lk.get((x, z), np.nan) for x, z in zip(gx, gz)])
        fb = np.where((np.abs(px) <= 0.83) & (pz >= 1.6) & (pz <= 3.5), 0.88, 0.04)
        return np.where(np.isnan(out), fb, out)

    # ---- (4) league swing prob (zone,count) + hitter swing-outcome rates (grp,zone) ----
    psw = d.groupby(["zone", "balls", "strikes"]).swung.mean()
    sw = d[d.swung == 1].copy()
    sw["whiff"] = sw.description.isin(WHIFF).astype(int); sw["foul"] = sw.description.isin(FOUL).astype(int); sw["inplay"] = sw.description.isin(INPLAY).astype(int)
    Lgz = sw.groupby(["grp", "zone"]).agg(whiff=("whiff","mean"), foul=("foul","mean"), inplay=("inplay","mean"))
    hgz = sw.groupby(["batter","grp","zone"]).agg(whiff=("whiff","mean"),foul=("foul","mean"),inplay=("inplay","mean"),n=("whiff","size"))
    KH = 60
    # vectorized per-pitch (dict fallbacks — pandas .loc per-row is pathologically slow)
    b = d.balls.values; s = d.strikes.values; ba = d.bases.values; ou = d.outs.values
    msd, mbd, mfd = ms.to_dict(), mb.to_dict(), mf.to_dict()
    sre = np.array([RE_strike.get((ba[i],ou[i],b[i],s[i]), msd[(b[i],s[i])]) for i in range(len(d))])
    bre = np.array([RE_ball.get((ba[i],ou[i],b[i],s[i]), mbd[(b[i],s[i])]) for i in range(len(d))])
    fre = np.array([RE_foul.get((ba[i],ou[i],b[i],s[i]), mfd[(b[i],s[i])]) for i in range(len(d))])
    cs = cs_prob_arr(d.plate_x.values, d.plate_z.values)
    ev_take = cs * sre + (1 - cs) * bre
    # hitter outcomes
    def hrates(batter, g, z):
        lg = Lgz.loc[(g, z)] if (g, z) in Lgz.index else pd.Series({"whiff":sw.whiff.mean(),"foul":sw.foul.mean(),"inplay":sw.inplay.mean()})
        if (batter, g, z) in hgz.index:
            r = hgz.loc[(batter, g, z)]; n = r["n"]
            wh=_shrink(r["whiff"],n,lg["whiff"],KH); fo=_shrink(r["foul"],n,lg["foul"],KH); ip=_shrink(r["inplay"],n,lg["inplay"],KH)
        else: wh,fo,ip = lg["whiff"],lg["foul"],lg["inplay"]
        t=wh+fo+ip; return wh/t,fo/t,ip/t
    keys=list(d.groupby(["batter","grp","zone"]).groups.keys()); hr={k:hrates(*k) for k in keys}
    kk=list(zip(d.batter.values,d.grp.values,d.zone.values))
    wh=np.array([hr[k][0] for k in kk]); fo=np.array([hr[k][1] for k in kk]); ip=np.array([hr[k][2] for k in kk])
    bo_base=np.array([bip_lg.get((ba[i],ou[i]),bip_lg_overall) for i in range(len(d))])
    bipv=bo_base + np.array([h_off.get(bt,0.0) for bt in d.batter.values])              # flat damage (Decision+)
    zoff=np.array([zone_off.get((bt,g,z),0.0) for bt,g,z in zip(d.batter.values,d.grp.values,d.zone.values)])
    bipv_zone=bo_base + zoff                                                              # zone-specific damage (damage-aware)
    ev_swing=wh*sre+fo*fre+ip*bipv
    ev_swing_dmg=wh*sre+fo*fre+ip*bipv_zone
    # generic (league outcomes, no hitter contact offset)
    Lgd=Lgz.to_dict("index"); _wm,_fm,_im=sw.whiff.mean(),sw.foul.mean(),sw.inplay.mean()
    gz=list(zip(d.grp.values,d.zone.values))
    lw=np.array([Lgd.get((g,z),{}).get("whiff",_wm) for g,z in gz])
    lf=np.array([Lgd.get((g,z),{}).get("foul",_fm) for g,z in gz])
    li=np.array([Lgd.get((g,z),{}).get("inplay",_im) for g,z in gz])
    lt=lw+lf+li; lw,lf,li=lw/lt,lf/lt,li/lt
    bipv_lg=np.array([bip_lg.get((ba[i],ou[i]),bip_lg_overall) for i in range(len(d))])
    ev_swing_g=lw*sre+lf*fre+li*bipv_lg
    pswd=psw.to_dict(); _swmean=d.swung.mean()
    psw_arr=np.array([pswd.get((z,bb,ss),_swmean) for z,bb,ss in zip(d.zone.values,b,s)])
    d=d.copy()
    d["ev_swing"]=ev_swing; d["ev_take"]=ev_take; d["p_swing_lg"]=psw_arr; d["ev_diff"]=ev_swing-ev_take
    d["drv_tailored"]=(d.swung.values-psw_arr)*(ev_swing-ev_take)
    d["drv_generic"]=(d.swung.values-psw_arr)*(ev_swing_g-ev_take)
    d["drv_damage"]=(d.swung.values-psw_arr)*(ev_swing_dmg-ev_take)
    if verbose:
        print("\n=== (3) called-strike calibration (decile pred/actual %) ===")
        cc=tk.assign(p=cs_prob_arr(tk.plate_x.values,tk.plate_z.values)); cc["db"]=pd.qcut(cc.p,10,labels=False,duplicates="drop")
        cal=cc.groupby("db").agg(p=("p","mean"),a=("cs","mean")); print("  "+"  ".join(f"{p*100:.0f}/{a*100:.0f}" for p,a in zip(cal.p,cal.a)))

    # driver decomposition: chase-avoidance (out-of-zone) vs in-zone attack, and 2-strike management
    d["drv_chase"]=np.where(~d.inzone.values, d.drv_tailored.values, 0.0)
    d["drv_zone"]=np.where(d.inzone.values, d.drv_tailored.values, 0.0)
    d["drv_2k"]=np.where(d.strikes.values==2, d.drv_tailored.values, 0.0)
    d["drv_early"]=np.where(d.strikes.values<2, d.drv_tailored.values, 0.0)
    agg=d.groupby("batter").agg(pitches=("swung","size"),drv_t=("drv_tailored","mean"),
        drv_g=("drv_generic","mean"),drv_d=("drv_damage","mean"),
        drv_chase=("drv_chase","mean"),drv_zone=("drv_zone","mean"),
        drv_2k=("drv_2k","mean"),drv_early=("drv_early","mean")).reset_index()
    agg=agg[agg.pitches>=100]
    for c in ["drv_chase","drv_zone","drv_2k","drv_early"]:
        agg[c.replace("drv","dec100")]=agg[c]*100   # additive components of dec_rv100 (runs/100 pitches)
    agg["dec_rv100_tailored"]=agg.drv_t*100; agg["dec_rv100_generic"]=agg.drv_g*100; agg["dec_rv100_damage"]=agg.drv_d*100
    mu,sd=agg.dec_rv100_tailored.mean(),agg.dec_rv100_tailored.std()
    agg["decision_plus_mlb"]=(100+(agg.dec_rv100_tailored-mu)/sd*10).round(1)
    agg["decision_scout"]=np.clip(50+(agg.dec_rv100_tailored-mu)/sd*10,20,90).round(1)
    mud,sdd=agg.dec_rv100_damage.mean(),agg.dec_rv100_damage.std()
    agg["damage_decision_plus"]=(100+(agg.dec_rv100_damage-mud)/sdd*10).round(1)
    agg["damage_decision_scout"]=np.clip(50+(agg.dec_rv100_damage-mud)/sdd*10,20,90).round(1)
    nm=pd.read_parquet(PROC/"leaderboard_alltime.parquet")[["batter","name"]].drop_duplicates("batter")
    agg=agg.merge(nm,on="batter",how="left")
    agg.to_parquet(OUT,index=False)
    if verbose: print(f"\n=== built base-out Decision for {len(agg)} hitters -> {OUT} ===")
    return agg,d


DCOLS = ["decision_plus_mlb", "decision_scout", "dec_rv100_tailored", "damage_decision_plus", "damage_decision_scout",
         "dec100_chase", "dec100_zone", "dec100_2k", "dec100_early"]
def add_to_boards(board: pd.DataFrame) -> pd.DataFrame:
    if not OUT.exists(): return board
    md = pd.read_parquet(OUT)[["batter"] + DCOLS]
    return board.merge(md, on="batter", how="left")


if __name__ == "__main__":
    agg, d = score()
