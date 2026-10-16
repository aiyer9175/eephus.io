#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""talent_ewar_lab - talent eWAR's constants and its two reads.

docs/ewar/TALENT_EWAR_GATE.md. Reads the frozen fWAR vintage, the cached StatsAPI season
pitching lines, Baseball-Reference's cached war_daily (runs_field, WAR) and league constants.
Writes data/_labs/ewar_innovate/talent_ewar_fit.json (--fit) and talent_ewar_eval.json (the
read); per-player values under .cache/ewar_innovate_ledger/talent_ewar/.

  --fit       gate part 2.2's constants and B1's k, once, on 2010 to 2015 pairs
  --dry-run   the scoring path on a synthetic fixture with nulls (planted WIN, all-zero never)
  (default)   T1, T2 and the secondary block on predictor seasons 2016 to 2018, once
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
import time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for p in (str(ROOT), str(TOOLS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import numpy as np  # noqa: E402

import talent_ewar as te  # noqa: E402

VINTAGE = ROOT / "data" / "fwar_vintage.json"
WAR_DAILY = ROOT / ".cache" / "war_daily" / "bat.parquet"
WAR_DAILY_PIT = ROOT / ".cache" / "war_daily" / "pit.parquet"
FIT_LOG = ROOT / "data" / "_labs" / "ewar_innovate" / "talent_ewar_fit.json"
OUT = ROOT / "data" / "_labs" / "ewar_innovate" / "talent_ewar_eval.json"
OUT_CACHE = ROOT / ".cache" / "ewar_innovate_ledger" / "talent_ewar"
SEED = 20261016
BOOT = 2000


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True, default=float) + "\n", encoding="utf-8")
    tmp.replace(path)


# --------------------------------------------------------------------------
# loading (caches only)
# --------------------------------------------------------------------------
def load_vintage(seasons) -> dict:
    v = json.loads(VINTAGE.read_text(encoding="utf-8"))
    fh, fp = v["fields"]["hitting"], v["fields"]["pitching"]
    ih = {k: fh.index(k) for k in ("war", "batting", "baseRunning", "fielding", "positional", "plateAppearances")}
    ip = {k: fp.index(k) for k in ("war", "ra9War")}
    out = {"vintage_id": v["vintage_id"]}
    for s in seasons:
        blk = v["seasons"][str(s)]
        hit = {}
        for mid, row in blk["hitting"]["rows"].items():
            pa = row[ih["plateAppearances"]]
            if pa is None:
                continue
            hit[int(mid)] = {"pa": float(pa), "war": float(row[ih["war"]] or 0.0),
                             "BAT": float(row[ih["batting"]] or 0.0), "BR": float(row[ih["baseRunning"]] or 0.0),
                             "FLD": float(row[ih["fielding"]] or 0.0), "POS": float(row[ih["positional"]] or 0.0)}
        pit = {}
        for mid, row in blk["pitching"]["rows"].items():
            pit[int(mid)] = {"war": float(row[ip["war"]] or 0.0), "ra9war": float(row[ip["ra9War"]] or 0.0)}
        out[s] = {"hit": hit, "pit": pit}
    return out


def load_pitch_lines(season: int) -> dict:
    doc = json.loads((ROOT / ".cache" / f"fa_statsapi_pitching_{int(season)}.json").read_text(encoding="utf-8"))
    out = {}
    for sp in (doc.get("stats") or [{}])[0].get("splits") or []:
        st = sp.get("stat") or {}
        try:
            mid = int(sp["player"]["id"])
            tbf = float(st.get("battersFaced") or 0)
            outs = float(st.get("outs") or 0)
        except (TypeError, ValueError, KeyError):
            continue
        row = {"tbf": tbf, "ip": outs / 3.0, "K": float(st.get("strikeOuts") or 0),
               "BH": float(st.get("baseOnBalls") or 0) + float(st.get("hitBatsmen") or 0),
               "HR": float(st.get("homeRuns") or 0)}
        if mid not in out or row["tbf"] > out[mid]["tbf"]:
            out[mid] = row
    return out


def load_bref() -> tuple[dict, dict, dict]:
    import pandas as pd
    b = pd.read_parquet(WAR_DAILY, columns=["mlb_ID", "year_ID", "runs_field", "WAR", "pitcher"])
    b = b[b["mlb_ID"].notna()]
    b["mlb_ID"] = pd.to_numeric(b["mlb_ID"], errors="coerce")
    b = b[b["mlb_ID"].notna()]
    for c in ("runs_field", "WAR"):
        b[c] = pd.to_numeric(b[c], errors="coerce").fillna(0.0)
    g = b.groupby(["mlb_ID", "year_ID"])
    rf = g["runs_field"].sum().to_dict()
    war = g["WAR"].sum().to_dict()
    meta = {"sha256": hashlib.sha256(WAR_DAILY.read_bytes()).hexdigest(),
            "modified": _dt.datetime.fromtimestamp(WAR_DAILY.stat().st_mtime, _dt.timezone.utc).isoformat()}
    return ({(int(k[0]), int(k[1])): float(v) for k, v in rf.items()},
            {(int(k[0]), int(k[1])): float(v) for k, v in war.items()}, meta)


def rpw(season: int) -> float:
    import league_constants as lc
    return float(lc.league_totals(int(season))["rpw"])


# --------------------------------------------------------------------------
# season frames
# --------------------------------------------------------------------------
def hit_means(hit: dict) -> dict:
    n = sum(r["pa"] for r in hit.values() if r["pa"] >= 1)
    return {c: sum(r[c] for r in hit.values() if r["pa"] >= 1) / n for c in te.HIT_PARTS}


def pit_means(lines: dict) -> dict:
    n = sum(r["tbf"] for r in lines.values() if r["tbf"] >= 1)
    return {c: sum(r[c] for r in lines.values() if r["tbf"] >= 1) / n for c in te.PIT_PARTS}


def season_hit_talent(hit: dict, frozen: dict, season: int) -> dict:
    ids = sorted(m for m, r in hit.items() if r["pa"] >= 1)
    n = np.array([hit[m]["pa"] for m in ids])
    means = hit_means(hit)
    rates = {c: np.array([hit[m][c] / hit[m]["pa"] for m in ids]) for c in te.HIT_PARTS}
    d = te.hitter_departures(n, rates, means, frozen)
    sd = te.hitter_band_sd(n, frozen, rpw(season))
    return {m: {"d": float(sum(d[c][i] for c in te.HIT_PARTS)), "d_parts": {c: float(d[c][i]) for c in te.HIT_PARTS},
                "band_sd": float(sd[i])} for i, m in enumerate(ids)}


def season_pit_talent(lines: dict, frozen: dict, season: int) -> dict:
    ids = sorted(m for m, r in lines.items() if r["tbf"] >= 1)
    n = np.array([lines[m]["tbf"] for m in ids])
    ip = np.array([lines[m]["ip"] for m in ids])
    means = pit_means(lines)
    rates = {c: np.array([lines[m][c] / lines[m]["tbf"] for m in ids]) for c in te.PIT_PARTS}
    D = te.pitcher_departure(n, ip, rates, means, frozen, rpw(season))
    sd = te.pitcher_band_sd(n, frozen, rpw(season))
    return {m: {"D": float(D[i]), "band_sd": float(sd[i])} for i, m in enumerate(ids)}


# --------------------------------------------------------------------------
# --fit (gate 2.2 and B1)
# --------------------------------------------------------------------------
def fit(log=print) -> dict:
    seasons = sorted(set(te.FIT_SEASONS) | {s + 1 for s in te.FIT_SEASONS})
    V = load_vintage(seasons)
    L = {s: load_pitch_lines(s) for s in seasons}
    rf, _bw, meta = load_bref()
    out = {"rule": "gate part 2.2", "fit_seasons": list(te.FIT_SEASONS), "vintage_id": V["vintage_id"],
           "war_daily": meta, "parts": {}, "b1": {}, "generated_at": _now()}
    for c in te.HIT_PARTS:
        x0, x1, n0, n1 = [], [], [], []
        for y in te.FIT_SEASONS:
            a, b = V[y]["hit"], V[y + 1]["hit"]
            ma, mb = hit_means(a), hit_means(b)
            for m, r in a.items():
                if m in b and r["pa"] >= te.FIT_FLOOR["hit"] and b[m]["pa"] >= te.FIT_FLOOR["hit"]:
                    x0.append(r[c] / r["pa"] - ma[c])
                    x1.append(b[m][c] / b[m]["pa"] - mb[c])
                    n0.append(r["pa"])
                    n1.append(b[m]["pa"])
        out["parts"][c] = te.fit_part(x0, x1, n0, n1)
    for c in te.PIT_PARTS:
        x0, x1, n0, n1 = [], [], [], []
        for y in te.FIT_SEASONS:
            a, b = L[y], L[y + 1]
            ma, mb = pit_means(a), pit_means(b)
            for m, r in a.items():
                if m in b and r["tbf"] >= te.FIT_FLOOR["pit"] and b[m]["tbf"] >= te.FIT_FLOOR["pit"]:
                    x0.append(r[c] / r["tbf"] - ma[c])
                    x1.append(b[m][c] / b[m]["tbf"] - mb[c])
                    n0.append(r["tbf"])
                    n1.append(b[m]["tbf"])
        out["parts"][c] = te.fit_part(x0, x1, n0, n1)
    # B1: one k per side, the swar_lab.fit_b1 rule against the side's target (gate 3.1)
    for side in ("hit", "pit"):
        x0, x1, hm = [], [], []
        for y in te.FIT_SEASONS:
            if side == "hit":
                a, b = V[y]["hit"], V[y + 1]["hit"]
                for m, r in a.items():
                    if m in b and r["pa"] >= te.READ_FLOOR["hit"] and b[m]["pa"] >= te.READ_FLOOR["hit"] \
                            and (m, y + 1) in rf:
                        x0.append((r["BAT"] + r["BR"] + r["FLD"]) / r["pa"])
                        x1.append((b[m]["BAT"] + b[m]["BR"] + rf[(m, y + 1)]) / b[m]["pa"])
                        hm.append(2.0 / (1.0 / r["pa"] + 1.0 / b[m]["pa"]))
            else:
                a, b = V[y]["pit"], V[y + 1]["pit"]
                for m, r in a.items():
                    la, lb = L[y].get(m), L[y + 1].get(m)
                    if m in b and la and lb and la["ip"] >= te.READ_FLOOR["pit"] and lb["ip"] >= te.READ_FLOOR["pit"]:
                        x0.append(r["war"] / la["ip"])
                        x1.append(b[m]["ra9war"] / lb["ip"])
                        hm.append(2.0 / (1.0 / la["ip"] + 1.0 / lb["ip"]))
        r_raw = float(np.corrcoef(x0, x1)[0, 1])
        r = min(max(r_raw, te.R_CLAMP[0]), te.R_CLAMP[1])
        out["b1"][side] = {"n_pairs": len(x0), "r_raw": r_raw, "r": r, "hm": float(np.mean(hm)),
                           "k": float(np.mean(hm)) * (1.0 - r) / r}
    _write(FIT_LOG, out)
    log(json.dumps(out, indent=1))
    return out


# --------------------------------------------------------------------------
# scoring (T1)
# --------------------------------------------------------------------------
def score_side(frame: dict, boot: int = BOOT, seed: int = SEED) -> dict:
    """frame arrays: R_rate, D_rate (departure per exposure), n, tgt_rate, tgt_tot, b1_rate,
    season (predictor), players; plus sec_rate, sec_tot (secondary target)."""
    import swar_lab as sl
    req = ("R_rate", "D_rate", "n", "tgt_rate", "tgt_tot", "b1_rate", "sec_rate", "sec_tot")
    ok = np.ones(len(frame["n"]), dtype=bool)
    for k in req:
        ok &= np.isfinite(np.asarray(frame[k], dtype=float))
    dropped = int((~ok).sum())
    frame = {k: np.asarray(v)[ok] for k, v in frame.items()}
    n = np.asarray(frame["n"], dtype=float)
    R = np.asarray(frame["R_rate"], dtype=float)
    D = np.asarray(frame["D_rate"], dtype=float)
    seasons = np.asarray(frame["season"])
    players = list(frame["players"])
    # twin: D permuted within (season, exposure decile)
    rng = np.random.default_rng(seed)
    Dt = D.copy()
    for s in np.unique(seasons):
        m = np.flatnonzero(seasons == s)
        q = np.quantile(n[m], np.linspace(0, 1, 11))
        dec = np.clip(np.searchsorted(q, n[m], side="right") - 1, 0, 9)
        for k in range(10):
            ix = m[dec == k]
            if len(ix) > 1:
                Dt[ix] = D[rng.permutation(ix)]
    series_rate = {"test": R + D, "b0": R, "b1": np.asarray(frame["b1_rate"], dtype=float), "twin": R + Dt}
    series_tot = {k: v * n for k, v in series_rate.items()}
    out = {"n_pairs": int(len(n)), "n_players": int(len(set(players))), "dropped_nonfinite": dropped}
    draws2 = sl.cluster_draws(players, list(seasons), boot, seed)
    draws1 = sl.iid_draws(len(n), boot, seed)
    outcome_season = seasons + 1
    cells = {}
    for cell, series, tkey in (("rate", series_rate, "tgt_rate"), ("total", series_tot, "tgt_tot"),
                               ("secondary rate", series_rate, "sec_rate"), ("secondary total", series_tot, "sec_tot")):
        t_raw = np.asarray(frame[tkey], dtype=float)
        t2 = sl.zscore_within(list(outcome_season), t_raw)
        d2 = sl.rho_draws(series, t2, draws2)
        d1 = sl.rho_draws({"test": series["test"], "b0": series["b0"]}, t_raw, draws1)
        g = sl.gap_summary(d2["test"], d2["b0"])
        gb1 = sl.gap_summary(d2["test"], d2["b1"])
        gtw = sl.gap_summary(d2["twin"], d2["b0"])
        g1 = sl.gap_summary(d1["test"], d1["b0"])
        rho = {k: sl.spearman(v, t2) for k, v in series.items()}
        gap = rho["test"] - rho["b0"]
        v1gap = sl.spearman(series["test"], t_raw) - sl.spearman(series["b0"], t_raw)
        cells[cell] = {"floors": {"sd": g["sd"], "half_width95": g["half_width95"], "mde95": g["mde95"]},
                       "rho": rho, "gap": gap, "lo95": g["lo95"], "hi95": g["hi95"], "lo90": g["lo90"],
                       "hi90": g["hi90"], "p_one_sided": g["p_one_sided"],
                       "gap_b1": rho["test"] - rho["b1"], "b1_lo95": gb1["lo95"], "b1_hi95": gb1["hi95"],
                       "twin_gap": rho["twin"] - rho["b0"], "twin_lo95": gtw["lo95"], "twin_hi95": gtw["hi95"],
                       "v1_gap": v1gap, "v1_lo95": g1["lo95"], "v1_hi95": g1["hi95"],
                       "v1_sign_agrees": bool((v1gap > 0) == (gap > 0) and v1gap != 0 and gap != 0)}
    for fam in (("rate", "total"), ("secondary rate", "secondary total")):
        h = sl.holm({k: cells[k]["p_one_sided"] for k in fam})
        for k in fam:
            c = cells[k]
            c["holm_reject"] = bool(h[k])
            c["disposition"] = te.disposition(h[k], c["gap"], c["lo95"], c["hi95"], c["lo90"], c["hi90"],
                                              c["b1_lo95"], c["twin_lo95"], c["v1_sign_agrees"])
    out["cells"] = cells
    return out


# --------------------------------------------------------------------------
# frames for the read
# --------------------------------------------------------------------------
def build_frames(V, L, rf, bw, frozen, b1k):
    hit_f = {k: [] for k in ("R_rate", "D_rate", "n", "tgt_rate", "tgt_tot", "b1_rate", "season", "players",
                             "sec_rate", "sec_tot", "bwar_rate")}
    pit_f = {k: [] for k in hit_f}
    band = {"hit": {c: [] for c in te.HIT_PARTS}, "pit": {c: [] for c in te.PIT_PARTS}}
    per_player = []
    for y in te.READ_SEASONS:
        a, b = V[y]["hit"], V[y + 1]["hit"]
        tal = season_hit_talent(a, frozen, y)
        ma, mb = hit_means(a), hit_means(b)
        # B1 target mean m at the floor
        fl = [r for r in a.values() if r["pa"] >= te.READ_FLOOR["hit"]]
        m_b1 = sum(r["BAT"] + r["BR"] + r["FLD"] for r in fl) / sum(r["pa"] for r in fl)
        for m, r in sorted(a.items()):
            if m not in b or r["pa"] < te.READ_FLOOR["hit"] or b[m]["pa"] < te.READ_FLOOR["hit"] or (m, y + 1) not in rf:
                continue
            n0, n1 = r["pa"], b[m]["pa"]
            R0 = r["BAT"] + r["BR"] + r["FLD"]
            hit_f["R_rate"].append(R0 / n0)
            hit_f["D_rate"].append(tal[m]["d"] / n0)
            hit_f["n"].append(n0)
            tgt = b[m]["BAT"] + b[m]["BR"] + rf[(m, y + 1)]
            hit_f["tgt_rate"].append(tgt / n1)
            hit_f["tgt_tot"].append(tgt)
            hit_f["b1_rate"].append((R0 + m_b1 * b1k["hit"]) / (n0 + b1k["hit"]))
            hit_f["season"].append(y)
            hit_f["players"].append(m)
            hit_f["sec_rate"].append(b[m]["war"] / n1)
            hit_f["sec_tot"].append(b[m]["war"])
            hit_f["bwar_rate"].append(bw.get((m, y), np.nan) / n0)
            for c in te.HIT_PARTS:
                band["hit"][c].append((n0, n1, r[c] / n0 - ma[c], b[m][c] / n1 - mb[c]))
            per_player.append({"side": "hit", "season": y, "mlbam": m, "fwar": r["war"],
                               "talent_ewar": r["war"] + tal[m]["d"] / rpw(y), "band_sd": tal[m]["band_sd"]})
        la, lb = L[y], L[y + 1]
        tp = season_pit_talent(la, frozen, y)
        pa_, pb_ = V[y]["pit"], V[y + 1]["pit"]
        pma, pmb = pit_means(la), pit_means(lb)
        flp = [(pa_[m]["war"], la[m]["ip"]) for m in pa_ if m in la and la[m]["ip"] >= te.READ_FLOOR["pit"]]
        m_b1p = sum(w for w, _ in flp) / sum(i for _, i in flp)
        for m, r in sorted(pa_.items()):
            if m not in pb_ or m not in la or m not in lb or m not in tp:
                continue
            i0, i1 = la[m]["ip"], lb[m]["ip"]
            if i0 < te.READ_FLOOR["pit"] or i1 < te.READ_FLOOR["pit"]:
                continue
            pit_f["R_rate"].append(r["war"] / i0)
            pit_f["D_rate"].append(tp[m]["D"] / i0)
            pit_f["n"].append(i0)
            pit_f["tgt_rate"].append(pb_[m]["ra9war"] / i1)
            pit_f["tgt_tot"].append(pb_[m]["ra9war"])
            pit_f["b1_rate"].append((r["war"] + m_b1p * b1k["pit"]) / (i0 + b1k["pit"]))
            pit_f["season"].append(y)
            pit_f["players"].append(m)
            pit_f["sec_rate"].append(pb_[m]["war"] / i1)
            pit_f["sec_tot"].append(pb_[m]["war"])
            pit_f["bwar_rate"].append(np.nan)
            for c in te.PIT_PARTS:
                band["pit"][c].append((la[m]["tbf"], lb[m]["tbf"], la[m][c] / la[m]["tbf"] - pma[c],
                                       lb[m][c] / lb[m]["tbf"] - pmb[c]))
            per_player.append({"side": "pit", "season": y, "mlbam": m, "fwar": r["war"],
                               "talent_ewar": r["war"] + tp[m]["D"], "band_sd": tp[m]["band_sd"]})
    return ({k: np.asarray(v) for k, v in hit_f.items()}, {k: np.asarray(v) for k, v in pit_f.items()},
            band, per_player)


def band_coverage(band: dict, frozen: dict) -> dict:
    out = {}
    for side, parts in band.items():
        out[side] = {}
        for c, rows in parts.items():
            a = np.asarray(rows, dtype=float)
            n0, n1, d0, d1 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
            post = te.posterior_mean_dev(n0, d0, frozen[c]["K"])
            sd = te.predictive_sd(n0, n1, frozen[c])
            cov = float((np.abs(d1 - post) <= te.BAND_Z * sd).mean())
            out[side][c] = {"n": int(len(a)), "coverage_80": cov, "inside": bool(0.75 <= cov <= 0.85)}
        out[side]["passes"] = all(v["inside"] for k, v in out[side].items() if isinstance(v, dict))
    return out


# --------------------------------------------------------------------------
# fixture
# --------------------------------------------------------------------------
def fixture_frame(planted: bool, seed: int = 5) -> dict:
    rng = np.random.default_rng(seed)
    n_p = 400
    rows = {k: [] for k in ("R_rate", "D_rate", "n", "tgt_rate", "tgt_tot", "b1_rate", "season", "players",
                            "sec_rate", "sec_tot")}
    talent = rng.normal(0, 0.01, n_p)
    for y in (2016, 2017, 2018):
        for i in range(n_p):
            if rng.random() < 0.3:
                continue
            n0 = float(rng.integers(200, 700))
            n1 = float(rng.integers(200, 700))
            R = talent[i] + rng.normal(0, 0.02)
            t = talent[i] + rng.normal(0, 0.02)
            D = 0.5 * (t - R) if planted else 0.0
            rows["R_rate"].append(R)
            rows["D_rate"].append(D)
            rows["n"].append(n0)
            rows["tgt_rate"].append(t)
            rows["tgt_tot"].append(t * n1)
            rows["b1_rate"].append(R * n0 / (n0 + 300.0))
            rows["season"].append(y)
            rows["players"].append(i)
            rows["sec_rate"].append(t)
            rows["sec_tot"].append(t * n1)
    rows["tgt_rate"][0] = float("nan")            # a null: the row is dropped and counted
    return {k: np.asarray(v) for k, v in rows.items()}


def dry_run(log=print) -> dict:
    res = {}
    for planted in (True, False):
        r = score_side(fixture_frame(planted), boot=300)
        res["planted" if planted else "null"] = {k: r["cells"][k]["disposition"] for k in ("rate", "total")}
    res["dry_run_pass"] = bool(res["planted"]["rate"].startswith("WIN") and not res["null"]["rate"].startswith("WIN"))
    log(json.dumps(res, indent=1))
    return res


# --------------------------------------------------------------------------
# the read
# --------------------------------------------------------------------------
def run(log=print) -> dict:
    if te.FROZEN is None or te.B1_K is None:
        raise SystemExit("constants not frozen: run --fit first")
    t0 = time.time()
    dr = dry_run(log=lambda *a: None)
    if not dr["dry_run_pass"]:
        raise SystemExit("dry run failed")
    seasons = sorted(set(te.READ_SEASONS) | {s + 1 for s in te.READ_SEASONS})
    V = load_vintage(seasons)
    L = {s: load_pitch_lines(s) for s in seasons}
    rf, bw, meta = load_bref()
    log(f"  war_daily sha256 {meta['sha256']}, modified {meta['modified']}")
    hit, pit, band, per = build_frames(V, L, rf, bw, te.FROZEN, te.B1_K)
    res = {"schema": 1, "version": te.TALENT_EWAR_VERSION, "gate_doc": te.GATE_DOC, "generated_at": _now(),
           "vintage_id": V["vintage_id"], "war_daily": meta, "frozen": te.FROZEN, "b1_k": te.B1_K,
           "seed": SEED, "boot": BOOT, "dry_run": dr}
    for side, fr in (("hitters", hit), ("pitchers", pit)):
        sc = score_side(fr)
        for k in ("rate", "total", "secondary rate", "secondary total"):
            c = sc["cells"][k]
            log(f"  {side} {k}: floors sd {c['floors']['sd']:.4f} MDE95 {c['floors']['mde95']:.4f}")
        for k in ("rate", "total", "secondary rate", "secondary total"):
            c = sc["cells"][k]
            log(f"  {side} {k}: gap {c['gap']:+.4f} [{c['lo95']:+.4f}, {c['hi95']:+.4f}] vs B1 {c['gap_b1']:+.4f} "
                f"(lo95 {c['b1_lo95']:+.4f}); twin lo95 {c['twin_lo95']:+.4f}; v1 {c['v1_gap']:+.4f} -> {c['disposition']}")
        if side == "hitters":
            ok = np.isfinite(fr["bwar_rate"])
            import swar_lab as sl
            t2 = sl.zscore_within(list(fr["season"][ok] + 1), fr["tgt_rate"][ok])
            sc["reference_bwar_rate_rho"] = sl.spearman(fr["bwar_rate"][ok], t2)
        res[side] = sc
    res["band"] = band_coverage(band, te.FROZEN)
    for side, key in (("hit", "hitters"), ("pit", "pitchers")):
        c = res[key]["cells"]
        res[key]["dev_pass"] = bool(c["rate"]["disposition"] == "WIN (components)"
                                    and c["total"]["disposition"] != "LOSS" and res["band"][side]["passes"])
        log(f"  band {side}: " + ", ".join(f"{k} {v['coverage_80']:.3f}" for k, v in res["band"][side].items()
                                          if isinstance(v, dict)) + f" -> {'passes' if res['band'][side]['passes'] else 'fails'}")
        log(f"  {key}: {'DEV PASS' if res[key]['dev_pass'] else 'NOT VALIDATED'}")
    res["seconds"] = round(time.time() - t0, 1)
    OUT_CACHE.mkdir(parents=True, exist_ok=True)
    (OUT_CACHE / "players.json").write_text(json.dumps(per), encoding="utf-8")
    _write(OUT, res)
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.dry_run:
        return 0 if dry_run()["dry_run_pass"] else 2
    if a.fit:
        fit()
        return 0
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
