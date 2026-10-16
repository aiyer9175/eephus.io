#!/usr/bin/env python3
# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""build_pitch_ledger - the pitch-level run value attribution ledger (pitch_ledger_v1).

docs/ewar/PITCH_LEDGER_GATE.md. Reads, never writes:
  .cache/pbp_corpus pitches, plays, events            (the corpus)
  .cache/pbp_runners                                  (eBR's runner record)
  .cache/ewar_innovate_ledger/feed_extract/<Y>        (tools/extract_feed_fielders.py)
  data/count_value.json                               (RE288 and RE24 per season)
  data/_labs/abs_ledger/mlb_2026.json                 (2026 challenges)
Writes:
  .cache/ewar_innovate_ledger/ledger/<Y>.parquet      (one row per step, wide components)
  data/_labs/ewar_innovate/pitch_ledger_receipts.json (invariants, counts, league sums)

Modes:
  --select-sigma   the one 2018 sigma selection of gate part 4.2 (writes its log only)
  --planted        gate invariant I5 on a simulated copy of 2018
  (default)        build the seasons; refuses while pitch_ledger.SIGMA holds a None
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

import count_value as cv  # noqa: E402
import pitch_ledger as pl  # noqa: E402
from build_count_value import _arrays, _slices, _value, load_season  # noqa: E402

CORPUS = ROOT / ".cache" / "pbp_corpus"
FEED = ROOT / ".cache" / "ewar_innovate_ledger" / "feed_extract"
OUT_DIR = ROOT / ".cache" / "ewar_innovate_ledger" / "ledger"
COUNT_VALUE = ROOT / "data" / "count_value.json"
ABS = ROOT / "data" / "_labs" / "abs_ledger" / "mlb_2026.json"
RECEIPTS = ROOT / "data" / "_labs" / "ewar_innovate" / "pitch_ledger_receipts.json"
SIGMA_LOG = ROOT / "data" / "_labs" / "ewar_innovate" / "pitch_ledger_sigma_selection.json"
SEASONS = (2018, 2019, 2021, 2022, 2023, 2024, 2025, 2026)


class LedgerRefusal(RuntimeError):
    pass


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------
def load(season: int) -> dict:
    import pandas as pd
    d = load_season(season)
    d["pitches"] = pd.read_parquet(CORPUS / "pitches" / str(season) / f"pitches-{season}.parquet",
                                   columns=["game_pk", "at_bat_index", "pitch_number", "play_id",
                                            "call_code", "pitch_type", "plate_x", "plate_z",
                                            "sz_top", "sz_bot", "home_plate_umpire_id"])
    d["events"] = pd.read_parquet(CORPUS / "events" / str(season) / f"events-{season}.parquet",
                                  columns=["game_pk", "at_bat_index", "index", "type",
                                           "event_type", "description"])
    d["cplays"] = pd.read_parquet(CORPUS / "plays" / str(season) / f"plays-{season}.parquet",
                                  columns=["game_pk", "at_bat_index", "batter_id", "pitcher_id",
                                           "bat_side", "pitch_hand", "trajectory", "bunted"])
    d["feed"] = pd.read_parquet(FEED / f"{season}.parquet")
    return d


def tables(doc: dict, season: int):
    blk = doc["by_season"][str(season)]
    return blk["re288"], blk["re24"]


def ball_strike_values(t288: dict, re24: dict):
    """VB[b,s,bits,o], VS[b,s,bits,o]: state value after a ball / strike (with runs)."""
    T = lambda b, s, base, o: t288[cv.cell(b, s, base, o)]  # noqa: E731
    R = lambda base, o: re24[f"{base}|{o}"]  # noqa: E731
    VB = np.zeros((4, 3, 8, 3))
    VS = np.zeros((4, 3, 8, 3))
    for b in range(4):
        for s in range(3):
            for base in range(8):
                for o in range(3):
                    if b >= 3:
                        nb, r = cv.forced_walk(base)
                        VB[b, s, base, o] = r + R(nb, o)
                    else:
                        VB[b, s, base, o] = cv.state_value(T, R, (b + 1, s, base, o, False))
                    if s >= 2:
                        VS[b, s, base, o] = 0.0 if o + 1 >= 3 else R(base, o + 1)
                    else:
                        VS[b, s, base, o] = cv.state_value(T, R, (b, s + 1, base, o, False))
    return VB, VS


# --------------------------------------------------------------------------
# the tagged walk
# --------------------------------------------------------------------------
def walk_tagged(d: dict) -> dict:
    """Every step of every play with its kind and row pointers (gate part 2)."""
    pa = d["pa"]
    pit = d["pitches"].sort_values(["game_pk", "at_bat_index", "pitch_number"], kind="stable").reset_index(drop=True)
    ev = d["events"].sort_values(["game_pk", "at_bat_index", "index"], kind="stable").reset_index(drop=True)
    d["pitches"], d["events"] = pit, ev
    psl = _slices(pit["game_pk"].to_numpy(), pit["at_bat_index"].to_numpy())
    esl = _slices(ev["game_pk"].to_numpy(), ev["at_bat_index"].to_numpy())
    codes = pit["call_code"].to_numpy(dtype=object)
    e_idx = ev["index"].to_numpy()
    e_type = ev["type"].to_numpy(dtype=object)
    e_desc = ev["description"].to_numpy(dtype=object)
    import ebr
    start_bits = ebr.base_code(pa).to_numpy()
    g_arr = pa["game_pk"].to_numpy(dtype=np.int64)
    a_arr = pa["at_bat_index"].to_numpy(dtype=np.int64)
    o_arr = pa["outs_before"].to_numpy()
    s_arr = pa["states_json"].to_numpy(dtype=object)
    rows = []          # (play j, kind, pitch row, event row, step index, b,s,bits,o,ended, b,s,bits,o,ended, runs)
    breaks = 0
    for j in range(len(pa)):
        gk, ab = int(g_arr[j]), int(a_arr[j])
        key = gk * 10000 + ab
        a, b = psl.get(key, (0, 0))
        pcodes = list(codes[a:b])
        ea, eb = esl.get(key, (0, 0))
        evs = [(int(e_idx[k]), e_type[k], e_desc[k]) for k in range(ea, eb)]
        sj = s_arr[j]
        states = json.loads(sj) if isinstance(sj, str) and sj else []
        w = cv.walk_play(int(start_bits[j]), int(o_arr[j]), pcodes, evs, states)
        p_idx = cv.pitch_indices(len(pcodes), [e[0] for e in evs])
        kinds: dict = {}
        for n, i in enumerate(p_idx):
            kinds[i] = ("p", a + n, -1)
        for n, (i, _, _) in enumerate(evs):
            kinds[i] = ("e", -1, ea + n)
        for st in states:
            i = -1 if st[0] is None else int(st[0])
            kinds.setdefault(i, ("g", -1, -1))
        keys = sorted(kinds)
        if len(keys) != len(w["steps"]):
            breaks += 1
            continue
        for i, (bf, af, r) in zip(keys, w["steps"]):
            k, pr, er = kinds[i]
            rows.append((j, k, pr, er, i, bf[0], bf[1], bf[2], bf[3], int(bf[4]),
                         af[0], af[1], af[2], af[3], int(af[4]), r))
    import pandas as pd
    st = pd.DataFrame(rows, columns=["play", "kind", "prow", "erow", "idx", "b0", "s0c", "bits0", "o0", "end0",
                                     "b1", "s1c", "bits1", "o1", "end1", "runs"])
    return {"steps": st, "walk_breaks": breaks}


# --------------------------------------------------------------------------
# one season
# --------------------------------------------------------------------------
def abs_calls(season: int) -> dict:
    """(game_pk, at_bat_index, pitch_number) -> (s0, s1, side, challenger_id) for zone rows."""
    if season != 2026 or not ABS.exists():
        return {}
    doc = json.loads(ABS.read_text(encoding="utf-8"))
    f = doc["fields"]
    ix = {k: f.index(k) for k in ("game_pk", "at_bat_index", "pitch_number", "kind", "original_call",
                                  "final_call", "challenge_side", "challenger_id", "role")}
    out = {}
    for r in doc["rows"]:
        if r[ix["kind"]] != "zone" or r[ix["pitch_number"]] is None:
            continue
        oc, fc = r[ix["original_call"]], r[ix["final_call"]]
        if oc not in ("B", "C") or fc not in ("B", "C"):
            continue
        out[(int(r[ix["game_pk"]]), int(r[ix["at_bat_index"]]), int(r[ix["pitch_number"]]))] = (
            1 if oc == "C" else 0, 1 if fc == "C" else 0, r[ix["challenge_side"]], r[ix["challenger_id"]],
            r[ix["role"]])
    return out


def prepare(season: int, doc: dict, log=print) -> dict:
    """Load, walk, value and annotate one season (no person-effect fit yet)."""
    import pandas as pd
    ts = time.time()
    d = load(season)
    wt = walk_tagged(d)
    st = wt["steps"]
    t288, re24 = tables(doc, season)
    T, R = _arrays(t288, re24)
    for c in ("b0", "s0c", "bits0", "o0", "end0", "b1", "s1c", "bits1", "o1", "end1", "runs"):
        st[c] = st[c].astype(np.int64)
    vb = _value(T, R, st.b0.to_numpy(), st.s0c.to_numpy(), st.bits0.to_numpy(), st.o0.to_numpy(), st.end0.to_numpy())
    va = _value(T, R, st.b1.to_numpy(), st.s1c.to_numpy(), st.bits1.to_numpy(), st.o1.to_numpy(), st.end1.to_numpy())
    st["v_before"] = vb
    st["dre"] = va - vb + st.runs.to_numpy()
    pa = d["pa"]
    play = st.play.to_numpy()
    st["game_pk"] = pa["game_pk"].to_numpy(dtype=np.int64)[play]
    st["at_bat_index"] = pa["at_bat_index"].to_numpy(dtype=np.int64)[play]
    st["bat_team_id"] = pa["bat_team_id"].astype("float").to_numpy()[play]
    st["fld_team_id"] = pa["fld_team_id"].astype("float").to_numpy()[play]
    cp = d["cplays"].set_index(["game_pk", "at_bat_index"])
    key = pd.MultiIndex.from_arrays([st.game_pk, st.at_bat_index])
    cpj = cp.reindex(key)
    st["batter_id"] = pd.to_numeric(cpj["batter_id"], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    st["pitcher_id_play"] = pd.to_numeric(cpj["pitcher_id"], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    st["hit_location"] = pa["hit_location"].to_numpy(dtype=object)[play]
    st["bat_side"] = cpj["bat_side"].to_numpy()
    st["pitch_hand"] = cpj["pitch_hand"].to_numpy()
    st["trajectory"] = cpj["trajectory"].to_numpy()
    st["bunted"] = cpj["bunted"].fillna(False).to_numpy().astype(bool)
    # pitch attributes
    pit = d["pitches"]
    pr = st.prow.to_numpy()
    isp = pr >= 0
    for c in ("call_code", "pitch_type", "play_id"):
        v = np.full(len(st), None, dtype=object)
        v[isp] = pit[c].to_numpy(dtype=object)[pr[isp]]
        st[c] = v
    for c in ("plate_x", "plate_z", "sz_top", "sz_bot", "pitch_number"):
        v = np.full(len(st), np.nan)
        v[isp] = pit[c].to_numpy(dtype=float)[pr[isp]]
        st[c] = v
    # event attributes
    ev = d["events"]
    er = st.erow.to_numpy()
    ise = er >= 0
    for c in ("type", "event_type"):
        v = np.full(len(st), None, dtype=object)
        v[ise] = ev[c].to_numpy(dtype=object)[er[ise]]
        st["ev_" + c] = v
    # feed: pitches by play_id, events by (game, ab, index)
    fd = d["feed"]
    fcols = ["catcher_id", "pitcher_id", "hp_umpire_id", "launch_speed", "launch_angle", "hc_x", "hc_y",
             "first_fielder_id"]
    fp = fd[fd.is_pitch & fd.play_id.notna()].drop_duplicates("play_id").set_index("play_id")[fcols]
    fpj = fp.reindex(st["play_id"].where(isp, None))
    fe = fd.drop_duplicates(["game_pk", "at_bat_index", "index"]).set_index(["game_pk", "at_bat_index", "index"])[fcols]
    fej = fe.reindex(pd.MultiIndex.from_arrays([st.game_pk, st.at_bat_index, st.idx]))
    for c in fcols:
        a1 = fpj[c].to_numpy(dtype=float, na_value=np.nan)
        a2 = fej[c].to_numpy(dtype=float, na_value=np.nan)
        st[c] = np.where(isp, a1, a2)
    # carry the catcher, pitcher and umpire through steps with none (group-only steps)
    for c in ("catcher_id", "pitcher_id", "hp_umpire_id"):
        st[c] = st.groupby("play")[c].ffill()
        st[c] = st.groupby("play")[c].bfill()
    st["pitcher_id"] = st["pitcher_id"].fillna(st["pitcher_id_play"])
    # the play's first credited fielder (constant within a play)
    st["fielder_id"] = st.groupby("play")["first_fielder_id"].transform("first")
    log(f"  {season}: walked {len(st):,} steps ({wt['walk_breaks']} plays not walked), {time.time() - ts:.1f}s")
    import ebr
    fit = np.asarray(ebr.fit_mask(pa), dtype=bool)
    sb = ebr.base_code(pa).to_numpy()
    eb = (pa["end_on_first"].notna().astype(int) + 2 * pa["end_on_second"].notna().astype(int)
          + 4 * pa["end_on_third"].notna().astype(int)).to_numpy()
    so = pa["outs_before"].to_numpy(dtype=float)
    eo = pa["end_outs"].to_numpy(dtype=float, na_value=3.0)
    rn = pa["runs_scored_on_play"].to_numpy(dtype=float, na_value=0.0)
    so_ = np.minimum(so, 3).astype(int)
    eo_ = np.minimum(eo, 3).astype(int)
    change = rn + np.where(eo_ >= 3, 0.0, R[eb, np.minimum(eo_, 3)]) - np.where(so_ >= 3, 0.0, R[sb, so_])
    sums = np.bincount(st.play.to_numpy(), weights=st.dre.to_numpy(), minlength=len(pa))
    err = np.abs(sums - change)[fit]
    i2 = {"fit_plays": int(fit.sum()), "share": float((err <= 1e-6).mean()) if fit.any() else None,
          "max_abs": float(err.max()) if fit.any() else None}
    return {"steps": st, "t288": t288, "re24": re24, "walk_breaks": wt["walk_breaks"],
            "n_pitches_corpus": int(len(pit)), "I2": i2}


def called_frame(st, season: int):
    """The called pitches of gate part 3.1 with location, and their model inputs."""
    import pandas as pd
    code = st["call_code"].to_numpy(dtype=object)
    take = np.array([c in pl.TAKE_CODES for c in code])
    valid = (st.kind.to_numpy() == "p") & take & (st.end0.to_numpy() == 0) & (st.o0.to_numpy() < 3)
    s1 = np.array([1.0 if c == pl.CALLED_STRIKE else 0.0 for c in code])
    s0 = s1.copy()
    side = np.full(len(st), None, dtype=object)
    chal = np.full(len(st), np.nan)
    chrole = np.full(len(st), None, dtype=object)
    found = 0
    ab = abs_calls(season)
    mism = 0
    if ab:
        keys = list(zip(st.game_pk.to_numpy(), st.at_bat_index.to_numpy(),
                        np.nan_to_num(st.pitch_number.to_numpy(), nan=-1).astype(int)))
        for i, k in enumerate(keys):
            r = ab.get((int(k[0]), int(k[1]), int(k[2])))
            if r is None or st.kind.iat[i] != "p":
                continue
            found += 1
            if r[1] != s1[i]:
                mism += 1
            s0[i] = r[0]
            side[i] = r[2]
            chal[i] = float(r[3]) if r[3] is not None else np.nan
            chrole[i] = r[4]
    xm = pl.mirrored_x(st.plate_x.to_numpy(), st.bat_side.to_numpy())
    zn = pl.zone_height(st.plate_z.to_numpy(), st.sz_bot.to_numpy(), st.sz_top.to_numpy())
    z = pl.rulebook_strike(xm, st.plate_z.to_numpy(), st.sz_bot.to_numpy(), st.sz_top.to_numpy())
    has_loc = np.isfinite(xm) & np.isfinite(zn) & np.isfinite(z)
    hand = np.array([pl.hand_key(b, p) for b, p in zip(st.bat_side.to_numpy(), st.pitch_hand.to_numpy())])
    cg = np.array([pl.count_group(int(b), int(s)) for b, s in zip(st.b0.to_numpy(), st.s0c.to_numpy())])
    return {"valid": valid, "model": valid & has_loc, "s0": s0, "s1": s1, "z": z, "xm": xm, "zn": zn,
            "hand": hand, "cg": cg, "side": side, "challenger": chal, "chrole": chrole,
            "abs_found": found, "abs_rows": len(ab), "abs_mismatch": mism, "has_loc": has_loc}


def person_codes(st, m):
    ids = {"catcher": st.catcher_id.to_numpy()[m], "pitcher": st.pitcher_id.to_numpy()[m],
           "batter": st.batter_id.to_numpy(dtype=float)[m], "umpire": st.hp_umpire_id.to_numpy(dtype=float)[m]}
    idx, uniq = {}, {}
    for g, a in ids.items():
        a = np.where(np.isfinite(a), a, -1.0)
        idx[g], uniq[g] = pl.encode(a)
    return idx, uniq


def assemble(prep: dict, cf: dict, lm, b0: float, eff: dict, idx: dict, season: int) -> dict:
    """Gate part 3: every component on every step, the cell models of part 5."""
    st = prep["steps"]
    n = len(st)
    comp = {c: np.zeros(n) for c in pl.COMPONENTS}
    dre = st.dre.to_numpy()
    kind = st.kind.to_numpy()
    VB, VS = ball_strike_values(prep["t288"], prep["re24"])
    b0a, s0a, bt0, o0 = (st[c].to_numpy() for c in ("b0", "s0c", "bits0", "o0"))
    ok_state = (o0 < 3) & (st.end0.to_numpy() == 0)
    bi, si, oi = np.minimum(b0a, 3), np.minimum(s0a, 2), np.minimum(o0, 2)
    vball = VB[bi, si, bt0, oi]
    vstrk = VS[bi, si, bt0, oi]
    vbef = st.v_before.to_numpy()
    # part 3.1, called pitches
    called = cf["valid"]
    mod = cf["model"]
    L0 = np.full(n, np.nan)
    L0[mod] = pl.logit(lm.predict(cf["xm"][mod], cf["zn"][mod], cf["hand"][mod], cf["cg"][mod])) + b0
    parts = {}
    for g in pl.GROUPS:
        a = np.zeros(n)
        a[mod] = eff[g][idx[g]]
        parts[g] = a
    d = {g: np.zeros(n) for g in pl.GROUPS}
    if mod.any():
        sh, _ = pl.shares(L0[mod], {g: parts[g][mod] for g in pl.GROUPS})
        for g in pl.GROUPS:
            d[g][mod] = sh[g]
    z = np.where(mod, cf["z"], cf["s0"])
    cc = pl.called_components(vbef[called], vball[called], vstrk[called], z[called], cf["s0"][called],
                              cf["s1"][called], d["catcher"][called], d["pitcher"][called],
                              d["batter"][called], dre[called])
    for c, v in cc.items():
        comp[c][called] = v
    # part 3.2, other pitches
    code = st["call_code"].to_numpy(dtype=object)
    isp = kind == "p"
    inplay = isp & ~called & np.array([c in pl.IN_PLAY_CODES for c in code]) & ok_state
    other_p = isp & ~called & ~inplay
    comp["x_duel"][other_p] = dre[other_p]
    ls, la, hx, hy = (st[c].to_numpy(dtype=float) for c in ("launch_speed", "launch_angle", "hc_x", "hc_y"))
    traj = st.trajectory.to_numpy(dtype=object)
    hloc = st.hit_location.to_numpy(dtype=object)
    cells = [pl.contact_cell(ls[i], la[i], hx[i], hy[i], traj[i], hloc[i]) for i in np.flatnonzero(inplay)]
    bo = list(zip(bt0[inplay], o0[inplay]))
    xx, xshift = pl.expected_contact(cells, bo, dre[inplay])
    comp["x_x"][inplay] = xx
    comp["x_fld"][inplay] = dre[inplay] - xx
    # part 3.3 and 5.2, blocking
    etype = st["ev_event_type"].to_numpy(dtype=object)
    etyp0 = st["ev_type"].to_numpy(dtype=object)
    is_e = kind == "e"
    wp = is_e & np.array([t in pl.WPPB for t in etype])
    comp["x_blk"][wp] = dre[wp]
    # followed-by flag: a WP/PB step after this pitch and before the next pitch of the play
    play = st.play.to_numpy()
    follow = np.zeros(n, dtype=bool)
    last_pitch = -1
    for i in range(n):
        if i > 0 and play[i] != play[i - 1]:
            last_pitch = -1
        if isp[i]:
            last_pitch = i
        elif wp[i] and last_pitch >= 0:
            follow[last_pitch] = True
    elig = isp & ok_state & (bt0 > 0)
    pg = np.array([pl.pitch_group(t) for t in st.pitch_type.to_numpy(dtype=object)])
    xm_all = pl.mirrored_x(st.plate_x.to_numpy(), st.bat_side.to_numpy())
    zn_all = pl.zone_height(st.plate_z.to_numpy(), st.sz_bot.to_numpy(), st.sz_top.to_numpy())
    eix = np.flatnonzero(elig)
    bkeys = [pl.blocking_cell(zn_all[i], xm_all[i], pg[i], bt0[i]) for i in eix]
    fm = pl.cell_means(bkeys, follow[eix].astype(float))
    cbo = pl.cell_means(list(zip(bt0[wp], o0[wp])), dre[wp])
    craw = np.array([fm[k][1] * cbo.get((bt0[i], o0[i]), (0, 0.0))[1] for k, i in zip(bkeys, eix)])
    tot_wp = float(dre[wp].sum())
    lam = tot_wp / float(craw.sum()) if craw.sum() > 0 else 0.0
    e = craw * lam
    comp["x_bexp"][eix] = e
    comp["x_babs"][eix] = -e
    # part 3.4 and 5.3, steals; pickoffs and balks
    stl = is_e & np.array([t in pl.STEAL for t in etype])
    sk = [(pl.STEAL[etype[i]], bt0[i], o0[i]) for i in np.flatnonzero(stl)]
    sm = pl.cell_means(sk, dre[stl])
    es = np.array([sm[k][1] for k in sk])
    comp["x_sexp"][stl] = es
    comp["x_sres"][stl] = dre[stl] - es
    pk = is_e & ~wp & ~stl & (np.array([t in pl.PICKOFF for t in etype]) | (etyp0 == "pickoff"))
    comp["x_pk"][pk] = dre[pk]
    # part 3.5, everything else
    rest = ~called & ~inplay & ~other_p & ~wp & ~stl & ~pk
    comp["x_oth"][rest] = dre[rest]
    return {"comp": comp, "d": d, "L0": L0, "z": z, "vball": vball, "vstrk": vstrk,
            "x_shift": xshift, "wp_lambda": lam, "called": called, "inplay": inplay, "wp": wp,
            "steal": stl, "pickoff": pk, "rest": rest, "other_p": other_p, "follow": follow}


def fit_season(prep: dict, cf: dict, sigma: dict, season: int, log=print):
    st = prep["steps"]
    m = cf["model"]
    lm = pl.fit_league(cf["xm"][m], cf["zn"][m], cf["hand"][m], cf["cg"][m], cf["s1"][m])
    L0 = pl.logit(lm.predict(cf["xm"][m], cf["zn"][m], cf["hand"][m], cf["cg"][m]))
    idx, uniq = person_codes(st, m)
    t = time.time()
    b0, eff, info = pl.fit_effects(L0, cf["s1"][m], idx, sigma)
    log(f"  {season}: effects fitted in {time.time() - t:.1f}s ({info['iterations']} iterations, "
        f"converged {info['converged']})")
    return lm, L0, b0, eff, idx, uniq, info


# --------------------------------------------------------------------------
# the sigma selection (gate part 4.2), once, on 2018
# --------------------------------------------------------------------------
def select_sigma(doc: dict, log=print) -> dict:
    prep = prepare(2018, doc, log)
    st = prep["steps"]
    cf = called_frame(st, 2018)
    m = cf["model"]
    odd = (st.game_pk.to_numpy() % 2 == 1)
    tr, te = m & odd, m & ~odd
    lm = pl.fit_league(cf["xm"][tr], cf["zn"][tr], cf["hand"][tr], cf["cg"][tr], cf["s1"][tr])
    Ltr = pl.logit(lm.predict(cf["xm"][tr], cf["zn"][tr], cf["hand"][tr], cf["cg"][tr]))
    Lte = pl.logit(lm.predict(cf["xm"][te], cf["zn"][te], cf["hand"][te], cf["cg"][te]))
    idx_tr, uniq_tr = person_codes(st, tr)
    idx_te, uniq_te = person_codes(st, te)
    known = {}
    for g in pl.GROUPS:
        pos = {v: i for i, v in enumerate(uniq_tr[g])}
        known[g] = np.array([pos.get(v, -1) for v in uniq_te[g]])[idx_te[g]]
    base_ll = pl.heldout_loglik(Lte, cf["s1"][te], {g: idx_te[g] for g in pl.GROUPS}, 0.0,
                                {g: np.zeros(len(uniq_tr[g])) for g in pl.GROUPS}, known)
    grid = {}
    chosen = {}
    for g in pl.GROUPS:
        grid[g] = {}
        for sgm in pl.SIGMA_GRID:
            sig = {h: pl.SIGMA_HOLD for h in pl.GROUPS}
            sig[g] = sgm
            b0, eff, info = pl.fit_effects(Ltr, cf["s1"][tr], idx_tr, sig)
            ll = pl.heldout_loglik(Lte, cf["s1"][te], idx_te, b0, eff, known)
            grid[g][str(sgm)] = round(ll, 8)
            log(f"  sigma {g} {sgm}: held-out mean log-likelihood {ll:.6f}")
        chosen[g] = float(max(grid[g], key=lambda k: grid[g][k]))
    out = {"season": 2018, "rule": "gate part 4.2", "fit_rows": int(tr.sum()), "heldout_rows": int(te.sum()),
           "league_only_heldout_loglik": round(base_ll, 8), "grid": grid, "chosen": chosen,
           "generated_at": _now()}
    _write_json(SIGMA_LOG, out)
    return out


# --------------------------------------------------------------------------
# invariant I5 on a simulated copy of 2018
# --------------------------------------------------------------------------
def planted(doc: dict, sigma: dict, log=print, seed: int = 20261016) -> dict:
    prep = prepare(2018, doc, log)
    st = prep["steps"]
    cf = called_frame(st, 2018)
    m = cf["model"]
    lm = pl.fit_league(cf["xm"][m], cf["zn"][m], cf["hand"][m], cf["cg"][m], cf["s1"][m])
    L0 = pl.logit(lm.predict(cf["xm"][m], cf["zn"][m], cf["hand"][m], cf["cg"][m]))
    idx, uniq = person_codes(st, m)
    rng = np.random.default_rng(seed)
    nC = len(uniq["catcher"])
    cnt = np.bincount(idx["catcher"], minlength=nC)
    true = rng.normal(0.0, 0.15, nC)
    big = np.flatnonzero(cnt >= 3000)
    star = int(big[np.argmin(np.abs(cnt[big] - 3000))]) if len(big) else int(np.argmax(cnt))
    true[star] = 0.30
    res = {}
    for label, eff_true in (("planted", true), ("null", np.zeros(nC))):
        y = (rng.random(len(L0)) < pl.expit(L0 + eff_true[idx["catcher"]])).astype(float)
        b0, eff, info = pl.fit_effects(L0, y, idx, sigma)
        fc = eff["catcher"]
        w = cnt > 0
        res[label] = {"sd_fitted": float(np.std(fc[w])), "r_true": (float(np.corrcoef(fc[w], eff_true[w])[0, 1])
                                                                    if label == "planted" else None),
                      "star_fitted": float(fc[star]), "star_n": int(cnt[star])}
    ok = (0.20 <= res["planted"]["star_fitted"] <= 0.40 and res["planted"]["r_true"] >= 0.5
          and res["null"]["sd_fitted"] < res["planted"]["sd_fitted"] / 3.0)
    res["pass"] = bool(ok)
    return res


# --------------------------------------------------------------------------
# the build
# --------------------------------------------------------------------------
def build(seasons=SEASONS, log=print) -> dict:
    import pandas as pd
    if any(v is None for v in pl.SIGMA.values()):
        raise LedgerRefusal("pitch_ledger.SIGMA is not frozen: run --select-sigma first (gate part 4.2)")
    doc = json.loads(COUNT_VALUE.read_text(encoding="utf-8"))
    rec = {"version": pl.PITCH_LEDGER_VERSION, "gate_doc": pl.GATE_DOC, "generated_at": _now(),
           "sigma": dict(pl.SIGMA), "count_value_sha256": _sha_file(COUNT_VALUE), "seasons": {}}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in seasons:
        ts = time.time()
        prep = prepare(s, doc, log)
        st = prep["steps"]
        cf = called_frame(st, s)
        lm, L0m, b0, eff, idx, uniq, info = fit_season(prep, cf, pl.SIGMA, s, log)
        A = assemble(prep, cf, lm, b0, eff, idx, s)
        comp = A["comp"]
        dre = st.dre.to_numpy()
        # I1
        ident = pl.identity_ok(comp, dre)
        # I2: per play, steps sum to the RE24 change
        play = st.play.to_numpy()
        sums = np.bincount(play, weights=dre)
        pa_steps = np.bincount(play)
        # I3
        blk_net = comp["x_babs"].sum() + comp["x_blk"].sum()
        # p0 calibration on modelled called pitches
        mod = cf["model"]
        p0 = pl.expit(A["L0"][mod] - b0)  # league model alone
        p_full = pl.expit(A["L0"][mod] + sum(eff[g][idx[g]] for g in pl.GROUPS))
        # I4
        isp = st.kind.to_numpy() == "p"
        join_c = float(np.isfinite(st.catcher_id.to_numpy()[isp]).mean())
        loc_share = float(cf["has_loc"][cf["valid"]].mean()) if cf["valid"].any() else None
        r = {
            "steps": int(len(st)), "plays_not_walked": int(prep["walk_breaks"]),
            "corpus_pitches": prep["n_pitches_corpus"], "pitch_steps": int(isp.sum()),
            "called_pitches": int(cf["valid"].sum()), "called_modelled": int(mod.sum()),
            "I2_telescope": prep["I2"],
            "I1_identity_share": float(ident.mean()), "I1_max_abs": float(np.max(np.abs(
                sum(comp[c] for c in pl.COMPONENTS) - dre))),
            "I3_fielders_sum": float(comp["x_fld"].sum()), "I3_blocking_net_sum": float(blk_net),
            "I3_throwing_sum": float(comp["x_sres"].sum()),
            "I3_p0_calibration_gap": float(p0.sum() - cf["s1"][mod].sum()),
            "p_full_calibration_gap": float(p_full.sum() - cf["s1"][mod].sum()),
            "I4_catcher_join_share": join_c, "I4_called_location_share": loc_share,
            "I6_abs_rows": cf["abs_rows"], "I6_abs_found": cf["abs_found"], "I6_abs_call_mismatch": cf["abs_mismatch"],
            "effects": {"intercept": b0, "fit": info,
                        "n_persons": {g: int(len(uniq[g])) for g in pl.GROUPS},
                        "sd": {g: float(np.std(eff[g])) for g in pl.GROUPS}},
            "league_p0_mean": float(p0.mean()) if len(p0) else None,
            "x_shift": A["x_shift"], "wp_lambda": A["wp_lambda"],
            "component_sums": {c: round(float(comp[c].sum()), 4) for c in pl.COMPONENTS},
            "component_abs_sums": {c: round(float(np.abs(comp[c]).sum()), 4) for c in pl.COMPONENTS},
            "dre_sum": round(float(dre.sum()), 4),
            "rows": {k: int(A[k].sum()) for k in ("called", "inplay", "wp", "steal", "pickoff", "rest", "other_p")},
            "x_oth_nonzero_on_called": int((np.abs(comp["x_oth"][A["called"]]) > 1e-9).sum()),
            "steps_per_play_max": int(pa_steps.max()) if len(pa_steps) else 0,
        }
        bad = []
        if r["I1_identity_share"] < 1.0:
            bad.append("I1")
        if abs(r["I3_fielders_sum"]) > 1e-6 or abs(r["I3_blocking_net_sum"]) > 1e-6 or abs(r["I3_throwing_sum"]) > 1e-6:
            bad.append("I3")
        if prep["I2"]["share"] is not None and prep["I2"]["share"] < 0.999:
            bad.append("I2")
        if join_c < 0.995 or (loc_share is not None and loc_share < 0.99):
            bad.append("I4")
        if s == 2026 and (cf["abs_found"] != cf["abs_rows"] or cf["abs_mismatch"]):
            bad.append("I6")
        r["refused"] = bad
        rec["seasons"][str(s)] = r
        if bad:
            log(f"  {s}: REFUSED {bad}")
            _write_json(RECEIPTS, rec)
            raise LedgerRefusal(f"season {s}: {bad}")
        # write the step table
        keep = ["game_pk", "at_bat_index", "idx", "kind", "call_code", "pitch_type", "ev_event_type", "ev_type",
                "batter_id", "pitcher_id", "catcher_id", "fielder_id", "hp_umpire_id", "bat_team_id",
                "fld_team_id", "b0", "s0c", "bits0", "o0", "dre", "plate_x", "plate_z", "sz_top", "sz_bot",
                "bat_side", "pitch_hand", "pitch_number"]
        out = st[keep].copy()
        out["season"] = s
        for c in pl.COMPONENTS:
            out[c] = comp[c]
        out["called"] = A["called"]
        out["modelled"] = cf["model"]
        out["L_full_minus_effects"] = A["L0"]
        for g in pl.GROUPS:
            out["d_" + g] = A["d"][g]
        out["s0_call"] = cf["s0"]
        out["s1_call"] = cf["s1"]
        out["z_call"] = A["z"]
        out["v_called"] = A["vball"] - A["vstrk"]
        out["v_before"] = st.v_before.to_numpy()
        out["challenge_side"] = cf["side"]
        out["challenger_id"] = cf["challenger"]
        out["challenger_role"] = cf["chrole"]
        out["follow_wppb"] = A["follow"]
        for c in ("challenge_side", "challenger_role", "call_code", "pitch_type", "ev_event_type", "ev_type",
                  "bat_side", "pitch_hand"):
            out[c] = out[c].astype("string")
        out.to_parquet(OUT_DIR / f"{s}.parquet", index=False)
        # per-person effects with exposure (for downstream registered reads)
        pe = {g: {"ids": [float(x) for x in uniq[g]], "effects": [float(x) for x in eff[g]],
                  "n": [int(x) for x in np.bincount(idx[g], minlength=len(uniq[g]))]} for g in pl.GROUPS}
        pe["intercept"] = b0
        (OUT_DIR / f"{s}_effects.json").write_text(json.dumps(pe), encoding="utf-8")
        log(f"  {s}: ledger written ({len(out):,} steps), {time.time() - ts:.1f}s")
    _write_json(RECEIPTS, rec)
    return rec


# --------------------------------------------------------------------------
# gate part 8.1: descriptive agreement (same season; never a gate)
# --------------------------------------------------------------------------
def fg_framing(season: int) -> dict:
    """{mlbam: frm} from the cached StatsAPI sabermetrics file (read only, never fetched)."""
    import saber_feed
    f = ROOT / ".cache" / f"{saber_feed.cache_key(season)}.json"
    if not f.exists():
        return {}
    stats = json.loads(f.read_text(encoding="utf-8")).get("stats") or []
    splits = (stats[0].get("splits") or []) if stats else []
    rows, _, _ = saber_feed.resolve_groups(splits, require="fielding")
    out = {}
    for pid, row in rows.items():
        v = saber_feed.framing_residual(row.get("stat") or {})
        if v is not None:
            out[int(pid)] = float(v)
    return out


def savant_blocking(season: int) -> dict:
    import csv
    f = ROOT / ".cache" / "savant_catcher" / f"blocking_{season}.csv"
    if not f.exists():
        return {}
    out = {}
    with open(f, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                out[int(r["player_id"])] = float(r["catcher_blocking_runs"])
            except (KeyError, ValueError):
                pass
    return out


def describe(seasons=SEASONS, floor: int = 2000) -> dict:
    import pandas as pd
    res = {}
    for s in seasons:
        df = pd.read_parquet(OUT_DIR / f"{s}.parquet",
                             columns=["catcher_id", "batter_id", "pitcher_id", "fielder_id", "called",
                                      "x_frm", "x_babs", "x_blk", "x_sres", "x_duel", "x_x", "x_fld", "x_ump",
                                      "hp_umpire_id"])
        g = df.groupby("catcher_id")
        cat = pd.DataFrame({"called": g["called"].sum(), "frm": -g["x_frm"].sum(),
                            "blk": -(g["x_babs"].sum() + g["x_blk"].sum()), "thr": -g["x_sres"].sum()})
        cat = cat[cat.called >= floor]
        fg = fg_framing(s)
        j = cat.copy()
        j["fg_frm"] = [fg.get(int(i)) for i in j.index]
        jj = j.dropna(subset=["fg_frm"])
        r_frm = float(np.corrcoef(jj.frm, jj.fg_frm)[0, 1]) if len(jj) > 2 else None
        sb = savant_blocking(s)
        jb = j.copy()
        jb["sv_blk"] = [sb.get(int(i)) for i in jb.index]
        jb = jb.dropna(subset=["sv_blk"])
        r_blk = float(np.corrcoef(jb.blk, jb.sv_blk)[0, 1]) if len(jb) > 2 else None
        bat = -df.groupby("batter_id")["x_duel"].sum() * -1
        pit = -(df.groupby("pitcher_id")["x_duel"].sum() + df.groupby("pitcher_id")["x_x"].sum())
        fld = -df.groupby("fielder_id")["x_fld"].sum()
        ump = df.groupby("hp_umpire_id")["x_ump"].sum()
        res[str(s)] = {
            "catchers_at_floor": int(len(cat)), "fg_frm_joined": int(len(jj)),
            "r_framing_vs_fangraphs_frm": r_frm,
            "savant_blocking_joined": int(len(jb)), "r_blocking_vs_savant": r_blk,
            "sd_runs": {"framing": float(cat.frm.std()), "blocking": float(cat.blk.std()),
                        "throwing": float(cat.thr.std()), "batter_duel": float(bat.std()),
                        "pitcher_duel_and_contact": float(pit.std()), "fielder": float(fld.std()),
                        "umpire": float(ump.std())},
        }
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default=",".join(str(s) for s in SEASONS))
    ap.add_argument("--select-sigma", action="store_true")
    ap.add_argument("--planted", action="store_true")
    ap.add_argument("--describe", action="store_true")
    a = ap.parse_args(argv)
    doc = json.loads(COUNT_VALUE.read_text(encoding="utf-8"))
    if a.select_sigma:
        print(json.dumps(select_sigma(doc), indent=1))
        return 0
    if a.planted:
        if any(v is None for v in pl.SIGMA.values()):
            raise LedgerRefusal("SIGMA not frozen")
        res = planted(doc, dict(pl.SIGMA))
        if RECEIPTS.exists():
            rec = json.loads(RECEIPTS.read_text(encoding="utf-8"))
            res["bound_null_sd"] = res["planted"]["sd_fitted"] / 3.0
            res["clauses"] = {"planted_star_in_0.20_0.40": 0.20 <= res["planted"]["star_fitted"] <= 0.40,
                              "planted_r_at_least_0.5": res["planted"]["r_true"] >= 0.5,
                              "null_sd_below_one_third": res["null"]["sd_fitted"] < res["bound_null_sd"]}
            rec["I5_simulated_2018"] = res
            _write_json(RECEIPTS, rec)
        print(json.dumps(res, indent=1))
        return 0 if res["pass"] else 2
    seasons = [int(x) for x in a.seasons.split(",") if x]
    if a.describe:
        rec = json.loads(RECEIPTS.read_text(encoding="utf-8"))
        rec["descriptive_agreement"] = describe(seasons)
        _write_json(RECEIPTS, rec)
        print(json.dumps(rec["descriptive_agreement"], indent=1))
        return 0
    build(seasons)
    return 0


if __name__ == "__main__":
    sys.exit(main())
