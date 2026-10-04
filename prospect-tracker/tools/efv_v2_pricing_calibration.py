# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""EFV3_C05: the MC-5 pricing read (position family and age at the read on the WAR line).

A DEVELOPMENT, MAE-ONLY read of efv_v2_candidates.fit_mc5_pricing (EFV3_C02) against the
unextended pricing line efv_v2_model.fit_war_map, on the DS-16 development folds and
nothing else (docs/efv-v2/MODEL_CLASS_SCREEN.md, "MC-5, pricing calibration by position and
age"; SP/efv3/EFV3_PLAN.md s5.2):

    lv_dev   F-LV at list vintages 2017 to 2019 (W3 label), the rows the DS-16 read scores
             (tools/efv_v2_dev_read.v2_lv_dev's selection), each fold fitted on labelled
             F-LV rows at earlier vintages with every V-frame player left out.
    vm_dev   the vintage-matched frame at frame version vm2 (career WAR to date), the rows
             tools/efv_v2_dev_read.v2_vm_dev builds, each decision year fitted on earlier
             matrix rows (efv_v2_model.v2_vm_scores, timing-pinned).

Per fold the base is the fold's own V2 model (efv_v2_model.fit_v2, whose war_map is
fit_war_map on the fold's training rows) and the new line is fit_mc5_pricing on the SAME
training rows with each row's family and age at its read. Both price the SAME eFV grade
(predict_v2's output map); only efv_war differs, so order_idx, the heads, the weights and
the comparator are untouched (asserted per fold, bit for bit, and pinned by
test_efv_v2_pricing_calibration.py). Under the registered within (side, vintage) statistic
the term therefore moves the rank by exactly zero: this is a PRICING item, never a rank
item, and MAE is a labelled diagnostic (docs/EFV_GATE_STANDARD.md s4), never an accuracy
claim.

THE COVARIATES, every one dated at or before the row's read:

    position   the latest LISTED position (prospects.db `snapshots`, real graders only)
               dated inside the row's frame window [window start, window end) on lv, and
               inside the VM_LISTING_LOOKBACK_DAYS ending on the read date on vm; the
               first token of a compound listing ("SS/2B" reads SS), mapped by
               efv_v2_candidates.position_family. Never the record's `position`, which is
               the latest listing on file (positions move after the read and after
               debut): the frame row's and the matrix row's `position` field carries no
               date, so it is not read (the artifact counts how often it differs).
    role       pitchers: the in-window MiLB role, the share of games started over games
               in the last MiLB season that had ended by the read (StatsAPI cache only,
               no fetch; up to ROLE_LOOKBACK_SEASONS back), "rp" below RP_GS_SHARE; with
               no MiLB line, a relief token in the in-window listing; else unknown, which
               fit_mc5_pricing reads as the reference family.
    age        (read date minus birth date) in years; the read date is the row's as-of
               point (lv: the latest in-window point; vm training rows: the matrix row's
               as-of; vm scored rows: the pinned preseason read). Missing birth dates are
               imputed at the training mean by fit_mc5_pricing, with no indicator.

STRATA: position family and age band (efv_strata.age_band) are the only strata. Nothing is
grouped, counted or averaged by consensus-FV or eFV grade level (docs/PROSPECT_ANCHOR_GATE.md).

INTERVAL: delta = MAE(new) - MAE(base) on identical rows, paired, player-clustered bootstrap
(source_backtest._cluster_layout / _cluster_draw), B 2000, seed 20260906, E_cond.

NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025 and later debut cohorts (R-VM).
The guards run before any fit; a violation raises (guard_lv_folds, guard_vm_years and
efv_v2_candidates.guard_training_rows on every fold's training rows).

LABEL: the read runs on the frozen fWAR label (after EPOCH_RUN's step Z). The artifact
stamps the label provider and refuses to write on any other provider unless --exploratory.

Run once:  python tools/efv_v2_pricing_calibration.py            (writes the artifact and
                                                                  appends the ledger rows)
           python tools/efv_v2_pricing_calibration.py --check    (frames, coverage and
                                                                  counts only, no MAE)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_labels as L  # noqa: E402
import efv_strata as ST  # noqa: E402
import efv_v2_candidates as C  # noqa: E402
import efv_v2_model as H  # noqa: E402
import efv_vintage_frame as F  # noqa: E402
import source_backtest as SB  # noqa: E402

OUT_PATH = ROOT / "data" / "efv_v2_pricing_calibration_eval.json"
DB_PATH = ROOT / "prospects.db"
MODEL_ID = "efv_v2_pricing_pos_age"
NOTE = "pricing calibration, MAE diagnostic, no rank claim; order_idx unchanged"
FROZEN_PROVIDER = "fwar"
B = SB._CLAIM_BOOT_B
SEED = SB._CLAIM_SEED
#: Graders whose listed position is read. Rank-only feeds, ingest helpers and the
#: tracker's own auto-detect are not listings.
LISTING_SOURCES: tuple[str, ...] = ("mlb_pipeline", "fangraphs", "baseballamerica", "espn",
                                    "just_baseball", "mlb_pipeline_international")
#: vm rows: a listing counts when dated inside this many days ending on the read date.
VM_LISTING_LOOKBACK_DAYS = 365
#: pitchers: "rp" when games started over games is below this share in the role season.
RP_GS_SHARE = 0.5
#: pitchers: how many MiLB seasons back from the last ended one the role read walks.
ROLE_LOOKBACK_SEASONS = 3
FRAMES = ("lv_dev", "vm_dev")


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------

def guard_lv_folds(folds) -> list[int]:
    """The lv development folds after the reserved guard: a reserved list vintage, or one
    at or after the first reserved one, raises."""
    out = [int(v) for v in folds]
    for v in out:
        F.guard_score_request(v, purpose="MC-5 pricing read")
        if v in F.RESERVED_LV or v >= min(F.RESERVED_LV):
            raise F.ReservedFrameError(f"lv fold {v} reaches R-LV")
    return out


def guard_vm_years(years) -> list[int]:
    """The vm decision years after the reserved guard: a 2025+ year raises."""
    out = H._check_years(years)
    if any(y >= F.R_VM_FIRST_DEBUT_YEAR for y in out):
        raise F.ReservedFrameError(f"vm years {out} reach R-VM")
    return out


# ---------------------------------------------------------------------------
# the covariates (every one dated at or before the read)
# ---------------------------------------------------------------------------

def _d10(v) -> str:
    return str(v or "")[:10]


def load_listings(db_path: Path | None = None) -> dict[str, list[tuple[str, str, str]]]:
    """{player_key: [(snapshot_date, source, position), ...]} from the snapshots table,
    real graders only, positions present. Read-only."""
    p = Path(db_path or DB_PATH)
    con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
    try:
        q = ("SELECT player_key, snapshot_date, source, position FROM snapshots "
             "WHERE position IS NOT NULL AND position != '' AND source IN (%s)"
             % ",".join("?" * len(LISTING_SOURCES)))
        out: dict[str, list[tuple[str, str, str]]] = {}
        for pk, sd, src, pos in con.execute(q, LISTING_SOURCES):
            out.setdefault(pk, []).append((_d10(sd), src, str(pos)))
    finally:
        con.close()
    return out


def listing_at(listings: dict, player_key: str, lo: str, hi: str) -> dict | None:
    """The latest listing dated in [lo, hi): {"position", "date", "source"}; a same-day tie
    goes to the earlier source in LISTING_SOURCES. None when no listing is in range."""
    best, best_key = None, None
    for sd, src, pos in listings.get(player_key) or ():
        if not (lo <= sd < hi):
            continue
        key = (sd, -LISTING_SOURCES.index(src))
        if best_key is None or key > best_key:
            best, best_key = {"position": pos, "date": sd, "source": src}, key
    return best


def primary_token(position) -> str:
    return str(position or "").upper().split("/")[0].strip()


class MilbRoles:
    """Pitcher role from the MiLB pitching cache (no fetch), memoized per season."""

    def __init__(self) -> None:
        self._idx: dict[int, dict] = {}

    def _season(self, season: int) -> dict:
        if season not in self._idx:
            import milb_history as mh
            try:
                self._idx[season] = mh.player_index(season, "pitching", fetch=False)
            except Exception:                                   # noqa: BLE001
                self._idx[season] = {}
        return self._idx[season]

    def role(self, mlbam, read_date: str) -> dict | None:
        """{"family", "season", "g", "gs"} from the last MiLB season that had ended by the
        read (a season ends for this purpose on October 1, efv_dataset._milb_features'
        rule), walking back ROLE_LOOKBACK_SEASONS; None without a line."""
        try:
            mid = int(mlbam)
        except (TypeError, ValueError):
            return None
        rd = _d10(read_date)
        if len(rd) < 7 or not rd[:4].isdigit():
            return None
        y, m = int(rd[:4]), int(rd[5:7])
        last = y if m >= 10 else y - 1
        for season in range(last, last - ROLE_LOOKBACK_SEASONS, -1):
            rows = [r for r in (self._season(season).get(mid) or [])
                    if r.get("level") != "MLB"]
            g = sum(int(r.get("g") or 0) for r in rows)
            if g <= 0:
                continue
            gs = sum(int(r.get("gs") or 0) for r in rows)
            fam = "rp" if gs / g < RP_GS_SHARE else "sp"
            return {"family": fam, "season": season, "g": g, "gs": gs}
        return None


def age_at(birth_date, read_date) -> float | None:
    try:
        b = date.fromisoformat(_d10(birth_date))
        r = date.fromisoformat(_d10(read_date))
    except ValueError:
        return None
    return (r - b).days / 365.25


def covariates(side: str, *, player_key: str, mlbam, birth_date, read_date: str,
               lo: str, hi: str, listings: dict, roles: MilbRoles) -> dict:
    """The row's family and age at its read. `lo`/`hi` bound the listing date [lo, hi);
    the caller passes hi at or before the day after the read, so nothing later is read."""
    lst = listing_at(listings, player_key, lo, hi)
    how = "none"
    fam = None
    if side == "pit":
        rl = roles.role(mlbam, read_date)
        if rl is not None:
            fam, how = rl["family"], "milb_gs_share"
        elif lst is not None:
            fam, how = C.position_family(lst["position"], "pit"), "listing"
    elif lst is not None:
        fam, how = C.position_family(primary_token(lst["position"]), "hit"), "listing"
    return {"family": fam, "family_how": how, "age": age_at(birth_date, read_date),
            "listing": lst, "read_date": _d10(read_date), "window": [lo, hi]}


def _next_day(d: str) -> str:
    return (date.fromisoformat(_d10(d)) + timedelta(days=1)).isoformat()


def lv_covariates(frame_row: dict, listings: dict, roles: MilbRoles) -> dict:
    """lv: the listing inside the frame window [window start, window end), the role and
    the age at the row's as-of point (the latest in-window point)."""
    lo, hi = frame_row["window"]
    return covariates(frame_row["side"], player_key=frame_row["player_key"],
                      mlbam=frame_row.get("mlbam_id"),
                      birth_date=frame_row.get("birth_date"),
                      read_date=frame_row["asof_date"], lo=_d10(lo), hi=_d10(hi),
                      listings=listings, roles=roles)


def vm_covariates(side: str, raw: dict, read_date: str, listings: dict,
                  roles: MilbRoles) -> dict:
    """vm: the listing inside the VM_LISTING_LOOKBACK_DAYS ending on the read date."""
    rd = _d10(read_date)
    try:
        lo = (date.fromisoformat(rd) - timedelta(days=VM_LISTING_LOOKBACK_DAYS)).isoformat()
    except ValueError:
        return {"family": None, "family_how": "none", "age": None, "listing": None,
                "read_date": rd, "window": None}
    return covariates(side, player_key=raw["player_key"], mlbam=raw.get("mlbam_id"),
                      birth_date=raw.get("birth_date"), read_date=rd, lo=lo,
                      hi=_next_day(rd), listings=listings, roles=roles)


# ---------------------------------------------------------------------------
# the folds
# ---------------------------------------------------------------------------

def _pricing_receipt(model: dict, pricing: dict | None) -> dict:
    wm = model.get("war_map") or {}
    p = pricing or {}
    return {"base": {"a": wm.get("a"), "b": wm.get("b"), "n": wm.get("n")},
            "position_age": None if pricing is None else {
                "a": p["a"], "b": p["b"], "reference_family": p["reference_family"],
                "family_shift": p["family"], "age_slope": p["age"],
                "age_used": p["age_used"], "age_mean": p["age_mean"],
                "age_observed": p["age_observed"], "n": p["n"], "columns": p["columns"]}}


def _order_identical(base: list[dict], new: list[dict]) -> bool:
    a = np.array([o["order_idx"] for o in base], dtype=np.float64)
    b = np.array([o["order_idx"] for o in new], dtype=np.float64)
    return a.shape == b.shape and a.tobytes() == b.tobytes() and all(
        x["efv_grade"] == y["efv_grade"] and x["player_key"] == y["player_key"]
        for x, y in zip(base, new))


def lv_rows(weights: dict, listings: dict, roles: MilbRoles) -> tuple[list[dict], dict]:
    """lv_dev: the DS-16 row set, base and MC-5 prices per fold."""
    import efv_v2_assemble as ASM
    frames = ASM.build_frames()          # guards every development vintage it builds
    folds = guard_lv_folds([v for v in F.DEV_VINTAGES if v >= H.V2_FIRST_SCORED_YEAR])
    cons = SB.CONSENSUS_KEY
    out, per = [], []
    for side in F.SIDES:
        cov = {}
        for V, (rows, _labs) in frames[side].items():
            for r in rows:
                cov[(r["player_key"], int(V))] = lv_covariates(dict(r, side=side),
                                                               listings, roles)
        train_all = H.lv_training_rows(side, frames[side])
        mat = H.training_rows(side)
        for V in folds:
            rows, labs = frames[side][V]
            test = H.lv_v2_rows(side, V, rows)
            in_frame = {r["player_key"] for r in rows}
            tr = [r for r in train_all if r["decision_year"] < V
                  and r["player_key"] not in in_frame]
            C.guard_training_rows(tr, "lv")
            model = H.fit_v2(tr, side, frame="lv", weights=weights)
            tcov = [cov[(r["player_key"], int(r["decision_year"]))] for r in tr]
            pricing = C.fit_mc5_pricing(tr, [c["family"] for c in tcov],
                                        [c["age"] for c in tcov], side=side)
            ecov = [cov[(r["player_key"], V)] for r in test]
            base = H.predict_v2(model, test)
            new = C.predict_mc5(C.attach_mc5(model, pricing), test,
                                [c["family"] for c in ecov], [c["age"] for c in ecov])
            if not _order_identical(base, new):
                raise AssertionError(f"order_idx moved on lv {side} {V}")
            by_key = {o["player_key"]: (o, ecov[i]) for i, o in enumerate(new)}
            sc1 = H.lv_scores(side, V, rows, data=mat)
            fr = {"side": side, "vintage": V, "n_train": len(tr), "n_scored": 0,
                  "order_idx_bit_identical": True, **_pricing_receipt(model, pricing)}
            for r, lab in zip(rows, labs):
                k = r["player_key"]
                if ((r.get("grades") or {}).get(cons) is None or lab.get("w3") is None
                        or k not in by_key or k not in sc1["v1"]):
                    continue
                if lab.get("status") == "reserved_vm":
                    dy = lab.get("debut_year")
                    if lab["w3"] != 0.0 or (dy is not None and dy <= V + L.W_DEBUT_WINDOW):
                        raise F.ReservedFrameError(f"reserved_vm row in window: {k} {V}")
                o, c = by_key[k]
                out.append({"key": k, "side": side, "year": V, "y": float(lab["w3"]),
                            "war_base": o["efv_war_v2"], "war_new": o["efv_war"],
                            "cov": c, "record_position": r.get("position"),
                            "birth_date": r.get("birth_date")})
                fr["n_scored"] += 1
            per.append(fr)
    return out, {"folds": folds, "per_fold": per}


def vm_rows(data_dir: Path, weights: dict, listings: dict,
            roles: MilbRoles) -> tuple[list[dict], dict]:
    """vm_dev at vm2: the DS-16 row set, base and MC-5 prices per decision year."""
    import efv_v2_dev_read as DR
    frame, meta = DR.v2_vm_dev(data_dir, weights)
    fold_years = guard_vm_years(meta["fold_years"])
    guard_vm_years(meta["years"])
    prices: dict = {}
    per = []
    for side in F.SIDES:
        mat = H.matrix_training_rows(side)
        raw = {r["player_key"]: r for r in json.loads(
            H._matrix_path(side).read_text(encoding="utf-8"))}
        rec: dict = {}
        res = H.v2_vm_scores(side, weights=weights, years=fold_years, timing_pin=True,
                             data=mat, receipts=rec)
        for yr, blk in sorted(res.items()):
            tr = [r for r in mat if r["decision_year"] < yr]
            C.guard_training_rows(tr, "vm")
            model = blk["model"]
            if H.fit_war_map(tr) != model["war_map"]:
                raise AssertionError(f"vm {side} {yr}: training rows differ from the fold's")
            tcov = [vm_covariates(side, raw[r["player_key"]],
                                  raw[r["player_key"]].get("asof_date"), listings, roles)
                    for r in tr]
            pricing = C.fit_mc5_pricing(tr, [c["family"] for c in tcov],
                                        [c["age"] for c in tcov], side=side)
            outs = blk["rows"]
            ecov = [vm_covariates(side, raw[o["player_key"]],
                                  rec[o["player_key"]]["asof_date"], listings, roles)
                    for o in outs]
            war = C.mc5_war(pricing, [o["efv_grade"] for o in outs],
                            [c["family"] for c in ecov], [c["age"] for c in ecov])
            for i, o in enumerate(outs):
                prices[o["player_key"]] = (yr, o["efv_war"], float(war[i]), ecov[i],
                                           raw[o["player_key"]])
            per.append({"side": side, "year": yr, "n_train": len(tr), "n_scored": len(outs),
                        "order_idx_bit_identical": True, **_pricing_receipt(model, pricing)})
    out = []
    for c in frame:
        yr, wb, wn, cv, rw = prices[c["key"]]
        if yr != c["year"]:
            raise AssertionError(f"vm row {c['key']} priced at {yr}, framed at {c['year']}")
        out.append({"key": c["key"], "side": c["side"], "year": c["year"],
                    "y": float(c["outcome"]["war"]), "war_base": wb, "war_new": wn,
                    "cov": cv, "record_position": rw.get("position"),
                    "birth_date": rw.get("birth_date")})
    return out, {"folds": fold_years, "per_fold": per, "window": meta["window"],
                 "dropped": meta["dropped"]}


# ---------------------------------------------------------------------------
# the statistics (MAE and mean residual; no rank statistic)
# ---------------------------------------------------------------------------

def mae_delta(keys, err_base, err_new, *, B: int = B, seed: int = SEED) -> dict:
    """MAE(new) - MAE(base) on identical rows, with a paired player-clustered CI95."""
    eb = np.abs(np.asarray(err_base, dtype=np.float64))
    en = np.abs(np.asarray(err_new, dtype=np.float64))
    ids = {k: i for i, k in enumerate(dict.fromkeys(keys))}
    order, starts, lens = SB._cluster_layout(np, [ids[k] for k in keys])
    rng = np.random.default_rng(seed)
    d = np.empty(int(B), dtype=np.float64)
    for b in range(int(B)):
        idx = SB._cluster_draw(np, rng, order, starts, lens)
        d[b] = en[idx].mean() - eb[idx].mean()
    q = np.quantile(d, [0.025, 0.975])
    return {"mae_base": round(float(eb.mean()), 4), "mae_position_age": round(float(en.mean()), 4),
            "delta": round(float(en.mean() - eb.mean()), 4),
            "ci95": [round(float(q[0]), 4), round(float(q[1]), 4)],
            "sd": round(float(d.std(ddof=1)), 5), "B": int(B), "seed": int(seed),
            "n_clusters": len(ids), "estimator": "E_cond, paired, player-clustered"}


def _cell(rows: list[dict]) -> dict:
    y = np.array([r["y"] for r in rows], dtype=np.float64)
    pb = np.array([r["war_base"] for r in rows], dtype=np.float64)
    pn = np.array([r["war_new"] for r in rows], dtype=np.float64)
    return {"n": len(rows),
            "mean_resid_base": round(float((y - pb).mean()), 4),
            "mean_resid_new": round(float((y - pn).mean()), 4),
            "mae_base": round(float(np.abs(y - pb).mean()), 4),
            "mae_new": round(float(np.abs(y - pn).mean()), 4)}


def _strata(rows: list[dict], key) -> dict:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    return {g: _cell(rr) for g, rr in sorted(groups.items())}


def family_label(r: dict) -> str:
    return f"{r['side']}:{r['cov']['family'] or ST.UNKNOWN}"


def age_band_label(r: dict) -> str:
    return f"{r['side']}:{ST.age_band({'birth_date': r.get('birth_date')}, None, r['year'])}"


def coverage(rows: list[dict]) -> dict:
    hows: dict = {}
    for r in rows:
        k = f"{r['side']}:{r['cov']['family_how']}"
        hows[k] = hows.get(k, 0) + 1
    hit = [r for r in rows if r["side"] == "hit"]
    differs = sum(1 for r in hit if r["cov"]["listing"] is not None
                  and primary_token(r["cov"]["listing"]["position"])
                  != primary_token(r.get("record_position")))
    return {"family_source": dict(sorted(hows.items())),
            "age_observed": sum(1 for r in rows if r["cov"]["age"] is not None),
            "hitters_with_listing": sum(1 for r in hit if r["cov"]["listing"] is not None),
            "hitters_record_position_differs_from_listing": differs}


def frame_block(rows: list[dict], meta: dict, **extra) -> dict:
    keys = [r["key"] for r in rows]
    eb = [r["y"] - r["war_base"] for r in rows]
    en = [r["y"] - r["war_new"] for r in rows]
    d = mae_delta(keys, eb, en)
    by_side: dict = {}
    for r in rows:
        by_side[r["side"]] = by_side.get(r["side"], 0) + 1
    overall = _cell(rows)
    return {**extra, "n": len(rows), "n_by_side": by_side, "n_players": len(set(keys)),
            "mae_base": d["mae_base"], "mae_position_age": d["mae_position_age"],
            "delta": d["delta"], "ci95": d["ci95"], "sd": d["sd"],
            "n_clusters": d["n_clusters"],
            "mean_resid_base": overall["mean_resid_base"],
            "mean_resid_new": overall["mean_resid_new"],
            "verdict": "MAE diagnostic, development only, not a claim",
            "per_side": _strata(rows, lambda r: r["side"]),
            "per_family": _strata(rows, family_label),
            "per_age_band": _strata(rows, age_band_label),
            "coverage": coverage(rows), "per_fold": meta["per_fold"]}


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def run(data_dir: Path | None = None, *, check: bool = False,
        exploratory: bool = False) -> dict:
    import efv_v2_dev_read as DR
    t0 = time.time()
    data_dir = Path(data_dir) if data_dir is not None else H.DATA_DIR
    provider = L.provider()
    if provider != FROZEN_PROVIDER and not exploratory:
        raise RuntimeError(f"label provider is {provider!r}, not the frozen "
                           f"{FROZEN_PROVIDER!r}: the read runs after EPOCH_RUN")
    guards = DR._ds16_guards()
    weights = H.load_weights()
    listings = load_listings()
    roles = MilbRoles()
    lv, lv_meta = lv_rows(weights, listings, roles)
    vm, vm_meta = vm_rows(data_dir, weights, listings, roles)
    read_lv = sorted({r["year"] for r in lv})
    read_vm = sorted({r["year"] for r in vm})
    guard_lv_folds(read_lv)
    guard_vm_years(read_vm)
    guards.update(lv_vintages_read=read_lv, vm_years_read=read_vm)
    if check:
        return {"check": True, "guards": guards, "lv_n": len(lv), "vm_n": len(vm),
                "lv_coverage": coverage(lv), "vm_coverage": coverage(vm)}
    frames = {
        "lv_dev": frame_block(lv, lv_meta, frame_version="lv1_v2",
                              window=[min(read_lv), max(read_lv)],
                              outcome=("W3 (WAR over the first three MLB seasons, 0 if no "
                                       "debut within three seasons of V)")),
        "vm_dev": frame_block(vm, vm_meta, frame_version="vm2", window=vm_meta["window"],
                              outcome="career WAR to date", dropped=vm_meta["dropped"]),
    }
    return {
        "item": "EFV3_C05",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_id": MODEL_ID,
        "arm": "MC-5 (docs/efv-v2/MODEL_CLASS_SCREEN.md), outside the Holm family",
        "role": "development",
        "metric": "mae",
        "adjudicates": False,
        "selects": False,
        "exploratory": bool(exploratory),
        "note": NOTE,
        "label": {"provider": provider, "resolved_through": L.resolved_through(),
                  "id": DR._label_id()},
        "code": {"commit": DR._commit(), "tool": "tools/efv_v2_pricing_calibration.py",
                 "efv_v2_candidates_sha256": _sha(ROOT / "efv_v2_candidates.py"),
                 "efv_v2_model_sha256": _sha(ROOT / "efv_v2_model.py")},
        "assembly_sha256": _sha(H.ASSEMBLY_PATH),
        "statistic": {"primary": "MAE of efv_war against the frame's outcome, a labelled "
                                 "diagnostic (docs/EFV_GATE_STANDARD.md s4), not a claim",
                      "delta": "MAE(position_age) minus MAE(base) on identical rows; "
                               "negative is a smaller error",
                      "calibration": "mean residual (outcome minus efv_war), overall, per "
                                     "position family and per age band",
                      "rank": ("none: order_idx and the eFV grade are bit-identical with "
                               "and without the term, so every Spearman and AUC delta is 0")},
        "definitions": {
            "base": "efv_v2_model.fit_war_map: WLS of the training target on [1, consensus FV]",
            "position_age": ("efv_v2_candidates.fit_mc5_pricing: WLS on [1, consensus FV, "
                             "family dummies, age at read], fitted per fold on the fold's "
                             "training rows, priced at the same eFV grade"),
            "families": {s: list(v) for s, v in C.MC5_FAMILIES.items()},
            "hitter_positions": dict(C.MC5_POSITIONS),
            "listing_sources": list(LISTING_SOURCES),
            "listing_window": {"lv": "[frame window start, frame window end)",
                               "vm": f"the {VM_LISTING_LOOKBACK_DAYS} days ending on the read"},
            "pitcher_role": (f"MiLB games started over games in the last season ended by "
                             f"the read (up to {ROLE_LOOKBACK_SEASONS} back), rp below "
                             f"{RP_GS_SHARE}; else a relief token in the listing"),
            "age": "read date minus birth date, years; imputed at the training mean",
            "strata": "position family and age band (efv_strata.age_band) only"},
        "bootstrap": {"B": B, "seed": SEED, "estimator": "E_cond", "unit": "player cluster"},
        "reserved_guard": guards,
        "frames": frames,
        "elapsed_s": round(time.time() - t0, 1),
    }


def write(doc: dict, path: Path | None = None) -> Path:
    p = Path(path or OUT_PATH)
    p.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="build the frames and print coverage and counts; no MAE")
    ap.add_argument("--no-ledger", action="store_true",
                    help="write the artifact but do not append the ledger rows")
    ap.add_argument("--exploratory", action="store_true",
                    help="allow a label other than the frozen fWAR label; never written")
    a = ap.parse_args(argv)
    doc = run(check=a.check, exploratory=a.exploratory)
    if a.check:
        print(json.dumps(doc, indent=1, default=str))
        return 0
    if a.exploratory:
        print(json.dumps({k: doc[k] for k in ("label", "frames")}, indent=1, default=str))
        return 0
    write(doc)
    for fid in FRAMES:
        f = doc["frames"][fid]
        print(f"{fid}: n {f['n']}, MAE base {f['mae_base']}, position_age "
              f"{f['mae_position_age']}, delta {f['delta']} CI {f['ci95']}")
    if not a.no_ledger:
        import efv_progress as P
        print(P.summary_line(P.update_pricing(trigger="efv_change")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
