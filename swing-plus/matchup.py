# Copyright (C) 2026 Will Cahoon (@willcolqhn) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Will Cahoon (@willcolqhn), 2026

"""
matchup.py — grade a HITTER vs a PITCHER's arsenal (v2, grounded).

v1 projected whiff from the swing-PATH model on an averaged pitch. That was badly
broken (Skubal's 48%-whiff changeup came out ~9-13%) for two reasons: averaging a
pitcher's pitches collapses their nastiness, and the whiff model reads most of its
signal off the *realized* swing path — feed it a clean mean path and it predicts
almost no whiffs, because timing/deception (the whole point of a changeup) isn't a
path feature.

v2 is built on EMPIRICAL rates combined with the log5 / odds-ratio method (the
standard batter-vs-pitcher formula):
  whiff:  proj_logit = logit(pitcher's actual whiff on that pitch)
                       + [logit(hitter whiff vs that group) - logit(league group whiff)]
  damage: proj_xwOBAcon = pitcher's actual xwOBAcon allowed on that pitch
                       + [hitter xwOBAcon vs that group - league group]
All hitter/pitcher rates are reliability-shrunk toward league by sample size (so a
504-swing rookie isn't taken at face value). The grade standardizes the hitter's
expected run value vs the average hitter on that same arsenal.

Decision layer: blends the hitter's Decision+ / chase-avoidance (from decision_plus)
against how much the pitcher lives out of the zone, so discipline counts — that's the
Soto-over-a-free-swinger gap the path model can't see.
"""
import warnings; warnings.filterwarnings("ignore")
import json
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).parent
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
HALVES = ["2023_H2", "2024_H1", "2024_H2", "2025_H1", "2025_H2", "2026_H1"]
ARSENAL = PROC / "pitcher_arsenal.parquet"
HITTER = PROC / "hitter_skill.parquet"
LEAGUE = PROC / "matchup_league.json"
SCALE = PROC / "matchup_scale.json"

SW = {"hit_into_play", "foul", "swinging_strike", "swinging_strike_blocked", "foul_tip"}
WH = {"swinging_strike", "swinging_strike_blocked", "foul_tip"}
GROUP = {"FF": "Fastball", "SI": "Fastball", "FC": "Fastball",
         "SL": "Breaking", "ST": "Breaking", "CU": "Breaking", "KC": "Breaking",
         "SV": "Breaking", "CS": "Breaking", "KN": "Breaking",
         "CH": "Offspeed", "FS": "Offspeed", "FO": "Offspeed", "SC": "Offspeed"}
TYPE_LABEL = {"FF": "4-Seam", "SI": "Sinker", "FC": "Cutter", "SL": "Slider",
              "ST": "Sweeper", "CU": "Curveball", "KC": "Knuckle-Curve", "SV": "Slurve",
              "CS": "Slow Curve", "KN": "Knuckleball", "CH": "Changeup", "FS": "Splitter",
              "FO": "Forkball", "SC": "Screwball"}
MIN_PITCHES = 25
KP_WH, KP_CON = 40, 25       # pitcher shrink (swings / BIP)
KH_WH, KH_CON = 150, 60      # hitter shrink


def _logit(p): p = np.clip(p, 1e-4, 1 - 1e-4); return np.log(p / (1 - p))
def _inv(x): return 1 / (1 + np.exp(-x))
def _scout(x, mu, sd):
    """20-90 scouting scale: 50 = average matchup, each 10 points = 1 SD."""
    return round(float(np.clip(50 + 10 * (x - mu) / sd, 20, 90)), 1)


HALFLIFE_DAYS = 240   # ~one season; recent form decays toward older performance
def _load_raw():
    cols = ["pitcher", "batter", "player_name", "p_throws", "stand", "pitch_type",
            "description", "events", "estimated_woba_using_speedangle",
            "plate_x", "plate_z", "sz_top", "sz_bot", "release_speed", "game_date"]
    d = pd.concat([pd.read_parquet(RAW / f"statcast_{h}.parquet", columns=cols)
                   for h in HALVES if (RAW / f"statcast_{h}.parquet").exists()], ignore_index=True)
    d = d[d["pitch_type"].isin(GROUP)]
    d["group"] = d["pitch_type"].map(GROUP)
    d["sw"] = d["description"].isin(SW)
    gd = pd.to_datetime(d["game_date"]); maxd = gd.max()
    d["w"] = np.power(0.5, (maxd - gd).dt.days / HALFLIFE_DAYS)   # recency weight
    d["whiff"] = d["description"].isin(WH)
    z = (d["plate_z"] >= d["sz_bot"]) & (d["plate_z"] <= d["sz_top"]) & (d["plate_x"].abs() <= 0.83)
    d["ooz"] = ~z
    return d


def _flip(n):
    return f"{n.split(',',1)[1].strip()} {n.split(',',1)[0].strip()}" if isinstance(n, str) and "," in n else n


def build_all():
    d = _load_raw()
    sw = d[d["sw"]]
    bip = d[(d["description"] == "hit_into_play") & d["estimated_woba_using_speedangle"].notna()]

    # ---- league baselines (per type, per group, overall) ----
    L = {"whiff_type": sw.groupby("pitch_type")["whiff"].mean().to_dict(),
         "whiff_group": sw.groupby("group")["whiff"].mean().to_dict(),
         "whiff_all": float(sw["whiff"].mean()),
         "con_type": bip.groupby("pitch_type")["estimated_woba_using_speedangle"].mean().to_dict(),
         "con_group": bip.groupby("group")["estimated_woba_using_speedangle"].mean().to_dict(),
         "con_all": float(bip["estimated_woba_using_speedangle"].mean())}
    LEAGUE.write_text(json.dumps(L))

    # ---- pitcher arsenal (empirical) ----
    g = sw.groupby(["pitcher", "stand", "pitch_type"])
    ars = pd.DataFrame({"n_sw": g.size(), "whiff": g["whiff"].mean(),
                        "velo": g["release_speed"].mean()}).reset_index()
    bg = bip.groupby(["pitcher", "stand", "pitch_type"])
    con = pd.DataFrame({"n_bip": bg.size(), "xwobacon": bg["estimated_woba_using_speedangle"].mean()}).reset_index()
    ars = ars.merge(con, on=["pitcher", "stand", "pitch_type"], how="left")
    ars = ars[ars["n_sw"] >= MIN_PITCHES]
    ars["usage"] = ars["n_sw"] / ars.groupby(["pitcher", "stand"])["n_sw"].transform("sum")
    ooz = d.groupby(["pitcher", "stand"])["ooz"].mean().rename("ooz_rate")
    meta = d.groupby("pitcher").agg(p_throws=("p_throws", lambda s: s.mode().iloc[0]),
                                    name=("player_name", "first"))
    ars = ars.merge(ooz, on=["pitcher", "stand"], how="left").merge(meta, on="pitcher", how="left")
    ars["name"] = ars["name"].apply(_flip)
    ars.to_parquet(ARSENAL, index=False)

    # ---- hitter skill (per group + overall): CAREER (flat) and RECENT (recency-weighted) ----
    def wmean(v, w): return float(np.average(v, weights=w)) if len(v) and w.sum() > 0 else np.nan
    rows = []
    for (b, st), gg in sw.groupby(["batter", "stand"]):
        rec = {"batter": b, "stand": st, "n_sw": len(gg), "whiff": gg["whiff"].mean(),
               "rwhiff": wmean(gg["whiff"].values, gg["w"].values)}
        for grp in ["Fastball", "Breaking", "Offspeed"]:
            sub = gg[gg["group"] == grp]
            rec[f"whiff_{grp}"] = sub["whiff"].mean() if len(sub) else np.nan
            rec[f"nsw_{grp}"] = len(sub)
            rec[f"rwhiff_{grp}"] = wmean(sub["whiff"].values, sub["w"].values) if len(sub) else np.nan
            rec[f"rnsw_{grp}"] = float(sub["w"].sum())     # effective recent sample
        rows.append(rec)
    hs = pd.DataFrame(rows)
    rows2 = []
    for (b, st), gg in bip.groupby(["batter", "stand"]):
        rec = {"batter": b, "stand": st, "n_bip": len(gg),
               "xwobacon": gg["estimated_woba_using_speedangle"].mean()}
        for grp in ["Fastball", "Breaking", "Offspeed"]:
            sub = gg[gg["group"] == grp]
            rec[f"con_{grp}"] = sub["estimated_woba_using_speedangle"].mean() if len(sub) else np.nan
            rec[f"nbip_{grp}"] = len(sub)
            rec[f"rcon_{grp}"] = wmean(sub["estimated_woba_using_speedangle"].values, sub["w"].values) if len(sub) else np.nan
            rec[f"rnbip_{grp}"] = float(sub["w"].sum())
        rows2.append(rec)
    hs = hs.merge(pd.DataFrame(rows2), on=["batter", "stand"], how="left")
    hs.to_parquet(HITTER, index=False)
    print(f"built arsenal ({len(ars)} rows, {ars.pitcher.nunique()} pitchers), "
          f"hitter_skill ({len(hs)}), league baselines")
    return ars, hs, L


def search_pitchers(q, limit=12):
    ars = pd.read_parquet(ARSENAL, columns=["pitcher", "name", "p_throws", "n_sw"])
    g = ars.groupby(["pitcher", "name", "p_throws"])["n_sw"].sum().reset_index()
    g = g[g["name"].str.contains(q, case=False, na=False)].sort_values("n_sw", ascending=False)
    return [{"pitcher": int(r.pitcher), "name": r.name, "throws": r.p_throws} for r in g.head(limit).itertuples()]


_C = {}
def _league():
    if "L" not in _C:
        _C["L"] = json.loads(LEAGUE.read_text())
    return _C["L"]


def _hitter_row(batter, stand):
    if "hs" not in _C:
        _C["hs"] = pd.read_parquet(HITTER)
    h = _C["hs"]; d = h[h["batter"] == batter]
    if stand and (d["stand"] == stand).any():
        d = d[d["stand"] == stand]
    return d.iloc[0] if len(d) else None


def _decision(batter, stand):
    # MLB-native decision (698-hitter coverage); falls back to external projected_k%
    p = PROC / "mlb_decision.parquet"
    if "md" not in _C and p.exists():
        _C["md"] = pd.read_parquet(p).drop_duplicates("batter").set_index("batter")
    dpm = None
    if "md" in _C and batter in _C["md"].index:
        dpm = float(_C["md"].loc[batter, "decision_plus_mlb"])
    if "at" not in _C:
        _C["at"] = pd.read_parquet(PROC / "leaderboard_alltime.parquet")
    at = _C["at"]; d = at[at["batter"] == batter]
    if stand and (d["stand"] == stand).any():
        d = d[d["stand"] == stand]
    pk = float(d.iloc[0]["projected_k_pct"]) if len(d) and pd.notna(d.iloc[0].get("projected_k_pct")) else None
    if dpm is None:
        return None
    return {"decision_plus_mlb": dpm, "projected_k_pct": pk}


def matchup(batter, pitcher, stand=None, form="career"):
    L = _league()
    h = _hitter_row(batter, stand)
    if h is None:
        return None
    stand = h["stand"]
    ars = pd.read_parquet(ARSENAL)
    a = ars[(ars["pitcher"] == pitcher) & (ars["stand"] == stand)].copy()
    if a.empty:
        return None
    p_throws = a["p_throws"].iloc[0]
    rec = form == "recent"   # recency-weighted hitter rates

    def hit_whiff(grp):
        wpre = "rwhiff_" if rec else "whiff_"; npre = "rnsw_" if rec else "nsw_"
        r, n = h.get(f"{wpre}{grp}"), h.get(f"{npre}{grp}", 0)
        Lg = L["whiff_group"][grp]
        if pd.isna(r) or not n: r, n = (h.get("rwhiff") if rec else h["whiff"]), h["n_sw"]
        if pd.isna(r): r = Lg
        return (n * r + KH_WH * Lg) / (n + KH_WH)

    def hit_con(grp):
        cpre = "rcon_" if rec else "con_"; npre = "rnbip_" if rec else "nbip_"
        r, n = h.get(f"{cpre}{grp}"), h.get(f"{npre}{grp}", 0)
        Lg = L["con_group"][grp]
        if pd.isna(n): n = 0
        if pd.isna(r) or n == 0:
            r = h["xwobacon"] if pd.notna(h.get("xwobacon")) else Lg
            n = h.get("n_bip", 0); n = 0 if pd.isna(n) else n
        if pd.isna(r): r = Lg
        return (n * r + KH_CON * Lg) / (n + KH_CON)

    pitches, raws, wts = [], [], []
    p_whs, p_cos, x_rvs = [], [], []
    for r in a.itertuples():
        grp = GROUP[r.pitch_type]
        Lt_wh, Lg_wh = L["whiff_type"].get(r.pitch_type, L["whiff_all"]), L["whiff_group"][grp]
        Lt_co = L["con_type"].get(r.pitch_type, L["con_all"]); Lg_co = L["con_group"][grp]
        p_wh = (r.n_sw * r.whiff + KP_WH * Lt_wh) / (r.n_sw + KP_WH)
        nb = r.n_bip if not pd.isna(r.n_bip) else 0
        p_co = (nb * r.xwobacon + KP_CON * Lt_co) / (nb + KP_CON) if nb else Lt_co
        proj_wh = float(_inv(_logit(p_wh) + _logit(hit_whiff(grp)) - _logit(Lg_wh)))
        proj_co = float(np.clip(p_co + (hit_con(grp) - Lg_co), 0.150, 0.750))
        xrv = (1 - proj_wh) * proj_co
        base = (1 - p_wh) * p_co
        pitches.append({"pitch_type": r.pitch_type, "label": TYPE_LABEL.get(r.pitch_type, r.pitch_type),
                        "group": grp, "usage": round(float(r.usage) * 100, 1),
                        "velo": round(float(r.velo), 1), "n": int(r.n_sw),
                        "pitch_whiff": round(float(r.whiff) * 100, 0),     # league hitter vs this pitch
                        "whiff_prob": round(proj_wh * 100, 0),            # THIS hitter
                        "xwobacon": round(proj_co, 3)})
        raws.append(xrv - base); wts.append(float(r.usage))
        p_whs.append(proj_wh); p_cos.append(proj_co); x_rvs.append(xrv)
    sc = _scale()
    for p, rw in zip(pitches, raws):
        p["grade"] = _scout(rw, sc["mu"], sc["sd"])
    pitches.sort(key=lambda x: -x["usage"])
    w = np.array(wts)
    raw_overall = np.average(raws, weights=w)
    swing_fit = _scout(raw_overall, sc["mu_ov"], sc["sd_ov"])
    # ---- projected matchup stats (the ones with signal at small sample) ----
    proj_whiff = float(np.average(p_whs, weights=w))
    proj_xwobacon = float(np.average(p_cos, weights=w))
    proj_xwoba_sw = float(np.average(x_rvs, weights=w))     # expected wOBA value per swing

    # ---- decision/discipline blend ----
    dec = _decision(batter, stand)
    ooz = float(a["ooz_rate"].iloc[0])
    dec_grade = None
    if dec and dec.get("decision_plus_mlb") is not None:
        dec_grade = float(np.clip(50 + (dec["decision_plus_mlb"] - 100), 20, 90))   # SD 10 -> 10 pts
    if dec_grade is not None:
        w_dec = float(np.clip(0.30 * (ooz / 0.50), 0.15, 0.45))
        overall = round((1 - w_dec) * swing_fit + w_dec * dec_grade, 1)
    else:
        w_dec, overall = 0.0, round(swing_fit, 1)

    return {"batter": int(batter), "stand": stand, "pitcher": int(pitcher),
            "pitcher_name": a["name"].iloc[0], "throws": p_throws,
            "overall_grade": overall, "swing_fit": round(swing_fit, 1),
            "decision_grade": round(dec_grade, 1) if dec_grade is not None else None,
            "ooz_rate": round(ooz * 100, 0), "dec_weight": round(w_dec, 2),
            "proj_whiff": round(proj_whiff * 100, 1), "proj_xwobacon": round(proj_xwobacon, 3),
            "proj_xwoba_swing": round(proj_xwoba_sw, 3),
            "projected_k_pct": round(dec["projected_k_pct"], 1) if dec and dec.get("projected_k_pct") is not None else None,
            "pitches": pitches}


_SC = None
def _scale():
    global _SC
    if _SC is None:
        if SCALE.exists():
            _SC = json.loads(SCALE.read_text())
        else:
            _SC = compute_scale()
    return _SC


def compute_scale():
    """Standardize swing-fit over the population of matchups: 50 = average hitter vs
    average pitcher. mu/sd from per-pitch raw (xrv - pitch baseline), usage-weighted."""
    L = _league(); hs = pd.read_parquet(HITTER); ars = pd.read_parquet(ARSENAL)
    rng = np.random.default_rng(0)
    hsr = hs.sample(min(250, len(hs)), random_state=0)
    raws, wts, overall = [], [], []   # per-pitch raws (+weights) and per-matchup overall raws
    for hrow in hsr.itertuples():
        st = hrow.stand
        a = ars[ars.stand == st]
        if a.empty: continue
        ps = rng.choice(a.pitcher.unique(), size=min(12, a.pitcher.nunique()), replace=False)
        for pid in ps:
            ap = a[a.pitcher == pid]
            mraw, mw = [], []
            for r in ap.itertuples():
                grp = GROUP[r.pitch_type]
                Lt_wh = L["whiff_type"].get(r.pitch_type, L["whiff_all"]); Lg_wh = L["whiff_group"][grp]
                Lt_co = L["con_type"].get(r.pitch_type, L["con_all"]); Lg_co = L["con_group"][grp]
                hw, nhw = getattr(hrow, f"whiff_{grp}", np.nan), getattr(hrow, f"nsw_{grp}", 0)
                if pd.isna(hw): hw, nhw = hrow.whiff, hrow.n_sw
                hw = (nhw * hw + KH_WH * Lg_wh) / (nhw + KH_WH)
                hc, nhc = getattr(hrow, f"con_{grp}", np.nan), getattr(hrow, f"nbip_{grp}", 0)
                if pd.isna(hc) or not nhc: hc, nhc = Lg_co, 0
                hc = (nhc * hc + KH_CON * Lg_co) / (nhc + KH_CON)
                p_wh = (r.n_sw * r.whiff + KP_WH * Lt_wh) / (r.n_sw + KP_WH)
                nb = r.n_bip if not pd.isna(r.n_bip) else 0
                p_co = (nb * r.xwobacon + KP_CON * Lt_co) / (nb + KP_CON) if nb else Lt_co
                proj_wh = _inv(_logit(p_wh) + _logit(hw) - _logit(Lg_wh))
                proj_co = np.clip(p_co + (hc - Lg_co), 0.150, 0.750)
                rw = (1 - proj_wh) * proj_co - (1 - p_wh) * p_co
                raws.append(rw); wts.append(float(r.usage)); mraw.append(rw); mw.append(float(r.usage))
            if mraw:
                overall.append(np.average(mraw, weights=mw))
    raw = np.array(raws); w = np.array(wts); ov = np.array(overall)
    mu = float(np.average(raw, weights=w)); sd = float(np.sqrt(np.average((raw - mu) ** 2, weights=w)))
    scale = {"mu": mu, "sd": sd, "mu_ov": float(ov.mean()), "sd_ov": float(ov.std())}
    SCALE.write_text(json.dumps(scale))
    print(f"wrote {SCALE}: {scale}  (n_pitch={len(raw)}, n_matchup={len(ov)})")
    return scale


if __name__ == "__main__":
    build_all()
    _C.clear(); globals()["_SC"] = None
    compute_scale()
    _C.clear(); globals()["_SC"] = None
    for nm, bid in [("Cruz", 665833), ("Kwan", 665742), ("Mayer", 691785), ("Judge", 592450)]:
        r = matchup(bid, 669373, None)  # vs Skubal
        if r:
            ch = next((p for p in r["pitches"] if p["pitch_type"] == "CH"), None)
            print(f"{nm:6s} vs Skubal: overall {r['overall_grade']} (swing-fit {r['swing_fit']}, "
                  f"dec {r['decision_grade']}) | CH whiff {ch['whiff_prob'] if ch else '–'}%")
