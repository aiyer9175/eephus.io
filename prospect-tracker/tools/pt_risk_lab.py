# W1 PT-RISK lane lab (pre-registered 2026-07-23, docs/wills-2026-07-23/GATES.md
# section "W1 PT-RISK: injury-history playing-time adjustment in fa_projection PT")
#
# MECHANISM: additive adjustment on the Marcel PT block of
# fa_projection.project_player (pt = w1*e1 + w2*e2 + base + aging delta), behind
# default-OFF env flag EEPHUS_PT_RISK, sidecar data/pt_risk_adjust.json.
# Adjustment = ridge on the PT residual (realized PA - incumbent Marcel PT
# prediction, the incumbent computed point-in-time via fitted_models(corpus, B-1)
# so it is EXACTLY what ships) from the FROZEN feature list:
#   il_days_prior1, il_stints_prior1, career_il_days, career_il_stints,
#   age, age x il_days_prior1
# ARM-H hitters (PA residual), ARM-P pitchers (IP-scale residual; the engine's
# pitcher pt unit is BF = 4.3 * IP, so realized exposure is realized_ip * 4.3
# and the IP-scale residual is realized_ip - pt_proj / 4.3). Judged alone.
#
# ===================== REGISTERED BARS (frozen, hard-coded) =================
# STOP-D  : W1-B AMENDED (GATES.md section "W1-B amendment", registered
#           2026-07-23 after the original W1 STOP-D fired and BEFORE any
#           C-clause ran): reconstructed MLB IL stints 2016-2025 >= 6000 AND
#           per-year placement counts inside the 450-2600 plausibility band
#           (2021 COVID-IL era allowed high); else HALT, verdict STOP-D,
#           artifact written, no model built. The original W1 floor (15000,
#           ~1500-2500/yr band) was mis-scaled vs published IL-record volume
#           (2017: 694 here vs ~700 published; 2018: 730 vs ~737); the
#           amendment re-derives ONLY this floor from the published scale.
#           C1-C4, features, arms, seeds, clamps, dev/holdout split are
#           IDENTICAL to the W1 registration and remain frozen.
# C1      : pooled dev PA MAE strictly improves vs incumbent on identical rows
#           AND pooled holdout PA MAE strictly improves AND player-clustered
#           bootstrap lo95 of the dev MAE improvement > 0
#           (2000 reps, seed 20260723, cluster by mlbam).
# C2      : proj_eval-protocol h1 WAR MAE with the adjustment ON is not worse
#           than OFF by more than +0.005 on dev AND on holdout (absent = 0).
# C3      : |pt_adj| clamped at 150 PA (hit) / 60 IP-equivalent (pit).
#           Round a-priori bounds, never retuned.
# C4      : pt_proj floors at 0; projected league PA (BF) sum moves < 2 percent
#           (judged on dev+holdout pooled; per-pool drift also reported).
# Dev bases {2019, 2021} forward-chained (train 2017..B-1); holdout bases
# {2022, 2023, 2024} touched ONCE (train 2017..B-1). Marginal = FAIL.
#
# ================== A-PRIORI DATA-HANDLING CHOICES (frozen =================
# ================== BEFORE any gate number was computed) ====================
# 1. 2020 EXCLUDED AS A TARGET everywhere (training and scoring): the 60-game
#    season caps realized PA at ~267 while the incumbent Marcel predicts
#    full-season PT, making every regular's residual ~-400 by construction.
#    This mirrors proj_eval's own deliberate COVID gap (default bases
#    "2017,2018,2019,2021"). Dev pool is therefore {2019, 2021}; forward
#    chains skip 2020 rows in training too. 2020 stays as a FEATURE season
#    (prior1 for base 2021) with its mechanically smaller day counts, noted.
# 2. Ridge: alpha = 1.0 on z-standardized features (mu/sigma from the fit's
#    own training rows), NO intercept. With mean-centered columns and no
#    intercept the fitted adjustment is mean-zero over the training
#    population: pure redistribution from injury-prone to durable players,
#    no global recalibration smuggled in. The frozen feature list has no
#    constant term, so none is added.
# 3. IL reconstruction: MLB-team transactions only (toTeam/fromTeam id in the
#    sportId=1 team set; the registered ~1500-2500/yr plausibility scale is
#    the MLB-level scale). Placement = description contains "placed" AND
#    ("injured list" OR "disabled list"). Activation = description contains
#    ("injured list" OR "disabled list") AND ("activated" OR "reinstated" OR
#    "returned"). "Transferred ... to the 60-day injured list" is neither
#    (the stint continues). COVID-19 IL placements match "injured list" and
#    count (they are real PT loss). Duplicate rows dedupe on transaction id
#    then on (person, date, description).
# 4. Stint day-count truncation: a stint closes at the EARLIEST of (next
#    activation for the person) / (next placement for the person) / (the
#    placement season's window end). Season windows: Apr 1 - Oct 1, except
#    2020: Jul 23 - Sep 28. Days = overlap of the stint with the placement
#    year's window; the stint (count 1) attributes to the placement year.
#    Multi-year injuries reappear as fresh placements the following spring
#    (MLB reinstates 60-day IL players each November), so single-season
#    truncation matches roster rules.
# 5. Career features sum all observed seasons < B (substrate floor 2015).
#    Coverage rule for the live hook: covered iff mlbam and age known and
#    target_season - 1 >= 2016.
# 6. Row universe mirrors proj_eval exactly (per base B and side: players
#    with any corpus season in B-1..B-3, an age-carrying row, and a
#    non-None project_player), absent season B = 0 realized PA / IP / WAR.
#    war_actual accumulates over both side lists exactly as proj_eval does
#    (its two-way double-count quirk included; identical ON and OFF).
# 7. The ON path is scored by CALLING THE SHIPPED HOOK: the lab installs
#    point-in-time coefficient blocks into fa_projection._pt_risk_state and
#    flips EEPHUS_PT_RISK=1 around the ON calls, so the gated code path is
#    byte-for-byte the code that would serve.
# 8. h1 WAR prediction mirrors fa_market._decay_path's t=0 cell:
#    round(max(0, war_from_projection(...)), 2), champion path (use_ml False).
#
# Seed 20260723 everywhere. One attempt per arm. Artifact
# data/fa_pt_risk_eval.json is written on ANY verdict (PASS / FAIL / STOP-D).
#
# Usage:
#   python tools/pt_risk_lab.py fetch      (resumable; caches .cache/mlb_transactions/)
#   python tools/pt_risk_lab.py stints     (reconstruct + STOP-D report)
#   python tools/pt_risk_lab.py gate       (THE one registered run; writes artifact)
#   python tools/pt_risk_lab.py finalize   (PASS sides only: fit through 2025,
#                                           write data/pt_risk_adjust.json)

from __future__ import annotations

import calendar
import gzip
import json
import os
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fa_projection as fp  # noqa: E402

TX_DIR = ROOT / ".cache" / "mlb_transactions"
ARTIFACT = ROOT / "data" / "fa_pt_risk_eval.json"
SIDECAR = ROOT / "data" / "pt_risk_adjust.json"

SEED = 20260723
BOOT_REPS = 2000
STOP_D_MIN_STINTS = 6000           # W1-B amended floor, 2016-2025 MLB stints
STOP_D_YEAR_BAND = (450, 2600)     # W1-B amended per-year band, 2016-2025
CLAMP = {"hit": 150.0, "pit": 60.0}  # registered C3 a-priori bounds
RIDGE_ALPHA = 1.0                   # a-priori (header note 2)
DEV_BASES = [2019, 2021]            # 2020 target excluded (header note 1)
HOLDOUT_BASES = [2022, 2023, 2024]
TRAIN_FIRST = 2017
C2_BAR = 0.005
C4_DRIFT_BAR = 0.02
FEATURES = ["il_days_prior1", "il_stints_prior1", "career_il_days",
            "career_il_stints", "age", "age_x_il_days_prior1"]

FETCH_FIRST, FETCH_LAST = (2015, 1), (2026, 7)
IL_WORDS = ("injured list", "disabled list")
ACT_WORDS = ("activated", "reinstated", "returned")


def _season_window(year: int) -> tuple[date, date]:
    if year == 2020:
        return date(2020, 7, 23), date(2020, 9, 28)
    return date(year, 4, 1), date(year, 10, 1)


# ============================================================================
# fetch
# ============================================================================

def _get_json(url: str, tries: int = 3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "eephus-pt-risk-lab"})
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:                              # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {i + 1} after {e}")
            time.sleep(2.0 * (i + 1))


def _months():
    y, m = FETCH_FIRST
    while (y, m) <= FETCH_LAST:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def cmd_fetch() -> None:
    TX_DIR.mkdir(parents=True, exist_ok=True)
    teams_path = TX_DIR / "mlb_teams.json"
    if not teams_path.exists():
        ids = set()
        for season in (2015, 2020, 2025):
            d = _get_json(f"https://statsapi.mlb.com/api/v1/teams?sportId=1&season={season}")
            ids.update(t["id"] for t in d.get("teams", []))
            time.sleep(0.3)
        teams_path.write_text(json.dumps(sorted(ids)), encoding="utf-8")
        print(f"mlb team ids: {len(ids)}")
    for y, m in _months():
        out = TX_DIR / f"tx_{y}_{m:02d}.json.gz"
        if out.exists():
            continue
        last_day = calendar.monthrange(y, m)[1]
        url = (f"https://statsapi.mlb.com/api/v1/transactions"
               f"?startDate={y}-{m:02d}-01&endDate={y}-{m:02d}-{last_day:02d}")
        d = _get_json(url)
        tmp = out.with_suffix(".tmp")
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(d, fh)
        tmp.replace(out)                                    # checkpoint: atomic per month
        print(f"tx {y}-{m:02d}: {len(d.get('transactions', []))}")
        time.sleep(0.3)
    print("fetch complete")


# ============================================================================
# stint reconstruction
# ============================================================================

def _load_events(keep_desc: bool = False):
    # keep_desc=True appends the lowercased description as a third tuple field
    # (aging_v3_sidecar reads the 60-day placements off it); the default path
    # and build_stints are unchanged.
    mlb_ids = set(json.loads((TX_DIR / "mlb_teams.json").read_text(encoding="utf-8")))
    seen_ids, seen_sig = set(), set()
    events = defaultdict(list)          # pid -> [(date, kind)] kind in {P, A}
    counts = {"placed": 0, "activated": 0, "dupes": 0, "no_person": 0, "non_mlb": 0}
    for y, m in _months():
        f = TX_DIR / f"tx_{y}_{m:02d}.json.gz"
        if not f.exists():
            continue
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        for t in d.get("transactions", []):
            desc = (t.get("description") or "").lower()
            if not any(w in desc for w in IL_WORDS):
                continue
            if "placed" in desc:
                kind = "P"
            elif any(w in desc for w in ACT_WORDS):
                kind = "A"
            else:
                continue                                    # transfers etc.
            team_ids = {(t.get("toTeam") or {}).get("id"), (t.get("fromTeam") or {}).get("id")}
            if not (team_ids & mlb_ids):
                counts["non_mlb"] += 1
                continue
            pid = (t.get("person") or {}).get("id")
            if not pid:
                counts["no_person"] += 1
                continue
            tid = t.get("id")
            sig = (pid, t.get("date"), desc[:80])
            if (tid is not None and tid in seen_ids) or sig in seen_sig:
                counts["dupes"] += 1
                continue
            if tid is not None:
                seen_ids.add(tid)
            seen_sig.add(sig)
            ds = t.get("date") or t.get("effectiveDate")
            if not ds:
                continue
            dt = date.fromisoformat(ds[:10])
            events[pid].append((dt, kind, desc) if keep_desc else (dt, kind))
            counts["placed" if kind == "P" else "activated"] += 1
    return events, counts


def build_stints():
    """{pid: {year: [il_days, il_stints]}} + per-year placement counts."""
    events, counts = _load_events()
    il = defaultdict(lambda: defaultdict(lambda: [0.0, 0]))
    per_year = defaultdict(int)
    for pid, evs in events.items():
        evs.sort()
        for i, (dt, kind) in enumerate(evs):
            if kind != "P":
                continue
            year = dt.year
            w_lo, w_hi = _season_window(year)
            close = w_hi
            for dt2, kind2 in evs[i + 1:]:                  # next activation OR placement
                if dt2 > dt:
                    close = min(close, dt2)
                    break
            start = max(dt, w_lo)
            days = max(0, (min(close, w_hi) - start).days) if start <= w_hi else 0
            il[pid][year][0] += float(days)
            il[pid][year][1] += 1
            per_year[year] += 1
    il_plain = {pid: {y: [v[0], v[1]] for y, v in yrs.items()} for pid, yrs in il.items()}
    return il_plain, dict(per_year), counts


def cmd_stints() -> None:
    il, per_year, counts = build_stints()
    total = sum(n for y, n in per_year.items() if 2016 <= y <= 2025)
    print("per-year MLB IL placements:", {y: per_year[y] for y in sorted(per_year)})
    print("event counts:", counts)
    print(f"stints 2016-2025: {total}  (STOP-D bar {STOP_D_MIN_STINTS})")
    print(f"players with any stint: {len(il)}")
    out = TX_DIR / "il_table.json"
    out.write_text(json.dumps({"per_year": per_year, "il": il}), encoding="utf-8")
    print("wrote", out)


# ============================================================================
# gate machinery
# ============================================================================

def _universe(corpus, by_player, war_actual, B, side, curves, war_map, il):
    """proj_eval-mirror rows for one (base, side): list of dicts with
    everything both arms need. The incumbent (OFF) projection is computed
    here; the ON projection is computed by the caller via the shipped hook."""
    league = corpus["league"]
    rows = []
    for mlbam, seasons in by_player[side].items():
        hist = [seasons[t] for t in (B - 1, B - 2, B - 3) if t in seasons]
        if not hist:
            continue
        age_row = next((h for h in hist if h.get("age")), None)
        if age_row is None:
            continue
        age = age_row["age"] + (B - age_row["season"])
        proj = fp.project_player(hist, side, B, curves, league, age)
        if proj is None:
            continue
        cur = seasons.get(B)
        realized = (cur.get("pa") if side == "hit" else cur.get("ip")) if cur else 0.0
        realized = float(realized or 0.0)
        war1 = round(max(0.0, fp.war_from_projection(proj, side, war_map, league, B)), 2)
        rows.append({
            "mlbam": mlbam, "B": B, "hist": hist, "age": age,
            "pt_off": proj["pt_proj"],
            "ip_off": proj.get("ip_proj"),
            "realized": realized,                       # PA (hit) / IP (pit)
            "war_off": war1,
            "war_act": war_actual.get((mlbam, B), 0.0),
            "feats": fp.pt_risk_features(il.get(mlbam) or {}, B, age),
        })
    return rows


def _pt_pred(row, side):
    """Incumbent PT prediction in the arm's unit: PA (hit) / IP (pit)."""
    return row["pt_off"] if side == "hit" else row["pt_off"] / 4.3


def _fit_ridge(rows, side):
    """Ridge (alpha 1.0, standardized, no intercept) on the arm's residual.
    Returns a hook-shaped block dict."""
    X = np.array([r["feats"] for r in rows], dtype=float)
    y = np.array([r["realized"] - _pt_pred(r, side) for r in rows], dtype=float)
    mu = X.mean(axis=0)
    sg = X.std(axis=0)
    sg[sg < 1e-9] = 1.0
    Z = (X - mu) / sg
    A = Z.T @ Z + RIDGE_ALPHA * np.eye(Z.shape[1])
    coef = np.linalg.solve(A, Z.T @ y)
    return {"enabled": True, "features": FEATURES, "alpha": RIDGE_ALPHA,
            "clamp": CLAMP[side], "coef": [round(float(c), 6) for c in coef],
            "mu": [round(float(v), 6) for v in mu],
            "sigma": [round(float(v), 6) for v in sg], "n_train": len(rows)}


def _score_on(rows, side, block, corpus, curves, war_map):
    """Re-project every row THROUGH THE SHIPPED HOOK (flag on, block
    installed) and attach pt_on / war_on."""
    league = corpus["league"]
    fp._pt_risk_state = {"hit": block if side == "hit" else None,
                         "pit": block if side == "pit" else None,
                         "il": _IL_INT}
    fp._pt_risk_loaded = True
    os.environ["EEPHUS_PT_RISK"] = "1"
    try:
        for r in rows:
            proj = fp.project_player(r["hist"], side, r["B"], curves, league, r["age"])
            r["pt_on"] = proj["pt_proj"]
            r["ip_on"] = proj.get("ip_proj")
            r["war_on"] = round(max(0.0, fp.war_from_projection(
                proj, side, war_map, league, r["B"])), 2)
    finally:
        os.environ.pop("EEPHUS_PT_RISK", None)
        fp._pt_risk_state = None
        fp._pt_risk_loaded = False


def _mae_pt(rows, side, on):
    preds = [(r["pt_on"] if side == "hit" else r["pt_on"] / 4.3) if on
             else _pt_pred(r, side) for r in rows]
    return float(np.mean([abs(p - r["realized"]) for p, r in zip(preds, rows)]))


def _mae_war(rows, on):
    return float(np.mean([abs((r["war_on"] if on else r["war_off"]) - r["war_act"])
                          for r in rows]))


def _boot_lo95(rows, side):
    """Player-clustered bootstrap lo95 of the dev PT MAE improvement
    (MAE_off - MAE_on). 2000 reps, seed 20260723."""
    by_pid = defaultdict(list)
    for r in rows:
        e_off = abs(_pt_pred(r, side) - r["realized"])
        e_on = abs((r["pt_on"] if side == "hit" else r["pt_on"] / 4.3) - r["realized"])
        by_pid[r["mlbam"]].append((e_off, e_on))
    pids = sorted(by_pid)
    rng = np.random.default_rng(SEED)
    deltas = []
    for _ in range(BOOT_REPS):
        pick = rng.integers(0, len(pids), len(pids))
        off_s = on_s = n = 0.0
        for i in pick:
            for e_off, e_on in by_pid[pids[i]]:
                off_s += e_off
                on_s += e_on
                n += 1
        deltas.append((off_s - on_s) / n)
    return float(np.percentile(deltas, 2.5))


_IL_INT: dict = {}


def cmd_gate() -> None:
    global _IL_INT
    il_raw = json.loads((TX_DIR / "il_table.json").read_text(encoding="utf-8"))
    per_year = {int(k): v for k, v in il_raw["per_year"].items()}
    _IL_INT = {int(p): {int(y): (v[0], v[1]) for y, v in yrs.items()}
               for p, yrs in il_raw["il"].items()}
    total_stints = sum(n for y, n in per_year.items() if 2016 <= y <= 2025)

    artifact = {
        "generated_at": "2026-07-23",
        "experiment": {
            "registration": "docs/wills-2026-07-23/GATES.md",
            "section": "W1 PT-RISK: injury-history playing-time adjustment in fa_projection PT",
            "seed": SEED, "bootstrap_reps": BOOT_REPS,
            "flag": "EEPHUS_PT_RISK", "sidecar": "data/pt_risk_adjust.json",
            "lab": "tools/pt_risk_lab.py",
            "dev_bases": DEV_BASES, "holdout_bases": HOLDOUT_BASES,
            "train_first": TRAIN_FIRST,
        },
        "a_priori_choices": [
            "2020 excluded as a TARGET in training and scoring (60-game realized PA vs a full-season Marcel prediction is degenerate by construction; mirrors proj_eval's deliberate COVID gap in its default bases), so dev pool = {2019, 2021}; 2020 kept as a FEATURE season",
            "ridge alpha 1.0 on z-standardized features, NO intercept: mean-zero redistribution, no global recalibration (frozen feature list carries no constant)",
            "MLB-team transactions only (sportId=1 team ids); placement = 'placed' + injured/disabled list; activation = activated/reinstated/returned + injured/disabled list; transfers continue the stint",
            "stint closes at earliest of next activation / next placement / placement-season window end (Apr 1 - Oct 1; 2020: Jul 23 - Sep 28); days = window overlap; stint counts to placement year",
            "career features sum all observed seasons < B (substrate floor 2015); hook coverage rule: mlbam + age known and target_season - 1 >= 2016",
            "row universe mirrors proj_eval (hist in B-1..B-3, age row, non-None projection); absent season B = 0 realized PA / IP / WAR; war_actual built exactly as proj_eval builds it",
            "ON path scored through the shipped hook (EEPHUS_PT_RISK=1 with point-in-time blocks installed in fa_projection._pt_risk_state)",
            "h1 WAR pred = round(max(0, war_from_projection), 2), the champion _decay_path t=0 cell",
        ],
        "data_phase": {
            "source": "statsapi /api/v1/transactions 2015-01 .. 2026-07, monthly ranges, cached .cache/mlb_transactions/",
            "per_year_placements": {str(y): per_year[y] for y in sorted(per_year)},
            "stints_2016_2025": total_stints,
            "stop_d_bar": STOP_D_MIN_STINTS,
            "players_with_stints": len(_IL_INT),
        },
    }
    # W1-B: the on-disk artifact PRESERVES the W1 STOP-D record verbatim; when
    # it exists this run keeps every W1 key untouched and only appends "w1b".
    if ARTIFACT.exists():
        artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    band_lo, band_hi = STOP_D_YEAR_BAND
    yr_counts = {y: int(per_year.get(y, 0)) for y in range(2016, 2026)}
    floor_ok = total_stints >= STOP_D_MIN_STINTS
    band_ok = all(band_lo <= n <= band_hi for n in yr_counts.values())
    w1b = {
        "generated_at": "2026-07-23",
        "amendment": ("docs/wills-2026-07-23/GATES.md section 'W1-B amendment': STOP-D floor "
                      "re-derived from the PUBLISHED IL-record scale to 6000 stints 2016-2025 "
                      "with per-year band 450-2600 (2021 COVID-IL era allowed high). C1-C4, the "
                      "frozen feature list, arms, seeds, clamps, and the dev/holdout split are "
                      "IDENTICAL to the W1 registration; the C-clauses never ran under W1 and "
                      "run ONCE here."),
        "stop_d": {
            "bar": (f"reconstructed MLB IL stints 2016-2025 >= {STOP_D_MIN_STINTS} AND "
                    f"per-year placement counts in [{band_lo}, {band_hi}]"),
            "measured_stints_2016_2025": total_stints,
            "per_year_2016_2025": {str(y): yr_counts[y] for y in sorted(yr_counts)},
            "floor_pass": bool(floor_ok),
            "band_pass": bool(band_ok),
            "pass": bool(floor_ok and band_ok),
        },
        "ship_rule": ("per W1 (unchanged): finalize fits the sidecar coefficients through 2025 "
                      "for PASS sides only; the flag flip, served-artifact regens, and the "
                      "registry row fa_pt_risk are executed centrally by the consolidator, "
                      "never by this lane"),
    }
    artifact["w1b"] = w1b

    if not (floor_ok and band_ok):
        clauses = {
            "C1": {"bar": "pooled dev PT MAE strictly improves AND pooled holdout PT MAE strictly improves AND player-clustered bootstrap lo95 of the dev improvement > 0 (2000 reps, seed 20260723)",
                   "measured": None, "status": "NOT-RUN (amended STOP-D halt before any model was built)"},
            "C2": {"bar": "proj_eval-protocol h1 WAR MAE ON not worse than OFF by more than +0.005 on dev AND holdout",
                   "measured": None, "status": "NOT-RUN (amended STOP-D halt before any model was built)"},
            "C3": {"bar": "|pt_adj| clamped at 150 PA (hit) / 60 IP-equivalent (pit), a priori",
                   "measured": None, "status": "NOT-RUN; the clamp constants are nonetheless hard-coded in the shipped hook (fa_projection.PT_RISK_CLAMP)"},
            "C4": {"bar": "pt_proj floors at 0; projected league PT sum moves < 2 percent",
                   "measured": None, "status": "NOT-RUN (amended STOP-D halt before any model was built)"},
        }
        w1b["arms"] = {
            "ARM-H": {"side": "hit", "clauses": clauses, "verdict": "STOP-D"},
            "ARM-P": {"side": "pit", "clauses": clauses, "verdict": "STOP-D"},
        }
        w1b["verdict"] = {"ARM-H": "STOP-D", "ARM-P": "STOP-D"}
        ARTIFACT.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
        print(f"STOP-D (W1-B amended) HALT: stints {total_stints} floor_ok {floor_ok} band_ok {band_ok}")
        print("wrote", ARTIFACT)
        return
    print(f"STOP-D (W1-B amended) CLEAR: {total_stints} >= {STOP_D_MIN_STINTS}; "
          f"per-year 2016-2025 all in [{band_lo}, {band_hi}]")

    corpus = fp.build_corpus()
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual = fp.war_actual_map(corpus)  # the ONE label (809902c6); never sum r['war'] across sides
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r

    all_bases = sorted(set(range(TRAIN_FIRST, 2019)) | set(DEV_BASES) | set(HOLDOUT_BASES))
    fits = {B: fp.fitted_models(corpus, B - 1) for B in all_bases}
    rows = {}                                              # (B, side) -> universe rows
    for B in all_bases:
        curves, war_map = fits[B]
        for side in ("hit", "pit"):
            rows[(B, side)] = _universe(corpus, by_player, war_actual, B, side,
                                        curves, war_map, _IL_INT)
            print(f"universe base {B} {side}: {len(rows[(B, side)])} rows")

    arms = {}
    for side, arm in (("hit", "ARM-H"), ("pit", "ARM-P")):
        unit = "PA" if side == "hit" else "IP"
        # forward-chained: each eval base gets a block trained on 2017..B-1 (no 2020)
        for B in DEV_BASES + HOLDOUT_BASES:
            train = [r for tb in range(TRAIN_FIRST, B) if tb != 2020
                     for r in rows[(tb, side)]]
            block = _fit_ridge(train, side)
            curves, war_map = fits[B]
            _score_on(rows[(B, side)], side, block, corpus, curves, war_map)
            if B == max(DEV_BASES + HOLDOUT_BASES):
                arms.setdefault(arm, {})["last_chain_block"] = {
                    k: block[k] for k in ("coef", "mu", "sigma", "n_train")}
        dev = [r for B in DEV_BASES for r in rows[(B, side)]]
        hold = [r for B in HOLDOUT_BASES for r in rows[(B, side)]]
        both = dev + hold
        mae_dev_off, mae_dev_on = _mae_pt(dev, side, False), _mae_pt(dev, side, True)
        mae_h_off, mae_h_on = _mae_pt(hold, side, False), _mae_pt(hold, side, True)
        lo95 = _boot_lo95(dev, side)
        war_dev_off, war_dev_on = _mae_war(dev, False), _mae_war(dev, True)
        war_h_off, war_h_on = _mae_war(hold, False), _mae_war(hold, True)
        adjs = [(r["pt_on"] - r["pt_off"]) / (1.0 if side == "hit" else 4.3) for r in both]
        pt_sum_off = sum(r["pt_off"] for r in both)
        pt_sum_on = sum(r["pt_on"] for r in both)
        drift = abs(pt_sum_on / pt_sum_off - 1.0) if pt_sum_off else 0.0
        drift_dev = abs(sum(r["pt_on"] for r in dev) / sum(r["pt_off"] for r in dev) - 1.0)
        drift_h = abs(sum(r["pt_on"] for r in hold) / sum(r["pt_off"] for r in hold) - 1.0)
        min_pt = min(r["pt_on"] for r in both)
        c1 = {"bar": f"dev {unit} MAE strictly improves AND holdout {unit} MAE strictly improves AND dev bootstrap lo95 > 0",
              "dev_mae_off": round(mae_dev_off, 4), "dev_mae_on": round(mae_dev_on, 4),
              "dev_improvement": round(mae_dev_off - mae_dev_on, 4),
              "holdout_mae_off": round(mae_h_off, 4), "holdout_mae_on": round(mae_h_on, 4),
              "holdout_improvement": round(mae_h_off - mae_h_on, 4),
              "boot_lo95_dev": round(lo95, 4),
              "pass": bool(mae_dev_on < mae_dev_off and mae_h_on < mae_h_off and lo95 > 0)}
        c2 = {"bar": f"h1 WAR MAE ON-minus-OFF <= +{C2_BAR} on dev AND holdout (absent = 0)",
              "dev_war_mae_off": round(war_dev_off, 4), "dev_war_mae_on": round(war_dev_on, 4),
              "dev_delta": round(war_dev_on - war_dev_off, 4),
              "holdout_war_mae_off": round(war_h_off, 4), "holdout_war_mae_on": round(war_h_on, 4),
              "holdout_delta": round(war_h_on - war_h_off, 4),
              "pass": bool(war_dev_on - war_dev_off <= C2_BAR
                           and war_h_on - war_h_off <= C2_BAR)}
        c3 = {"bar": f"|adj| clamped at {CLAMP[side]} {unit} in code (a priori)",
              "clamp": CLAMP[side], "max_abs_adj_observed": round(max(abs(a) for a in adjs), 2),
              # tolerance 0.05: pt_proj rounds to 0.1 BF in the engine, so a
              # clamped pitcher row can read up to ~0.012 IP past the cap
              "pass": bool(max(abs(a) for a in adjs) <= CLAMP[side] + 0.05)}
        c4 = {"bar": f"pt floors at 0 AND pooled projected league PT sum drift < {C4_DRIFT_BAR}",
              "min_pt_on": round(min_pt, 1), "drift_pooled": round(drift, 5),
              "drift_dev": round(drift_dev, 5), "drift_holdout": round(drift_h, 5),
              "pass": bool(min_pt >= 0.0 and drift < C4_DRIFT_BAR)}
        verdict = "PASS" if all(c["pass"] for c in (c1, c2, c3, c4)) else "FAIL"
        cov = sum(1 for r in both if any(r["feats"][:4])) / len(both)
        arms.setdefault(arm, {}).update({
            "side": side, "unit": unit, "n_dev": len(dev), "n_holdout": len(hold),
            "il_feature_coverage": round(cov, 4),
            "clauses": {"C1": c1, "C2": c2, "C3": c3, "C4": c4},
            "verdict": verdict,
        })
        print(f"\n{arm}: {verdict}")
        for name, c in (("C1", c1), ("C2", c2), ("C3", c3), ("C4", c4)):
            print(" ", name, "PASS" if c["pass"] else "FAIL",
                  {k: v for k, v in c.items() if k not in ("bar", "pass")})

    w1b["join"] = {
        "method": "corpus rows carry mlbam natively (StatsAPI player ids); transactions person.id is the same mlbam space; direct integer join, no crosswalk needed",
        "il_feature_coverage_note": "share of scored rows with any nonzero IL-history feature",
    }
    w1b["arms"] = arms
    w1b["verdict"] = {a: arms[a]["verdict"] for a in arms}
    story = []
    for a in ("ARM-H", "ARM-P"):
        c = arms[a]["clauses"]
        story.append(
            f"{a}: dev {arms[a]['unit']} MAE {c['C1']['dev_mae_off']} -> {c['C1']['dev_mae_on']} "
            f"(lo95 {c['C1']['boot_lo95_dev']}), holdout {c['C1']['holdout_mae_off']} -> "
            f"{c['C1']['holdout_mae_on']}; WAR h1 delta dev {c['C2']['dev_delta']} / "
            f"holdout {c['C2']['holdout_delta']}; verdict {arms[a]['verdict']}.")
    w1b["reading"] = {
        "story": " ".join(story),
        "mechanism": "IL history redistributes projected PT from injury-prone to durable players (mean-zero ridge, no global shift); the incumbent Marcel PT already shrinks toward recent exposure, so the arm only wins where injury history adds signal BEYOND depressed prior-season playing time itself.",
    }
    ARTIFACT.write_text(json.dumps(artifact, indent=1), encoding="utf-8")
    print("\nwrote", ARTIFACT)


def cmd_finalize(sides: list[str]) -> None:
    """PASS sides only (central consolidator or this lane on a PASS verdict):
    fit the shipped coefficient blocks on ALL bases 2017..2025 (no 2020) and
    write the frozen sidecar."""
    global _IL_INT
    il_raw = json.loads((TX_DIR / "il_table.json").read_text(encoding="utf-8"))
    _IL_INT = {int(p): {int(y): (v[0], v[1]) for y, v in yrs.items()}
               for p, yrs in il_raw["il"].items()}
    corpus = fp.build_corpus()
    by_player = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    war_actual = fp.war_actual_map(corpus)  # the ONE label (809902c6); never sum r['war'] across sides
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    out = {"generated_at": "2026-07-23", "fit_through": 2025, "seed": SEED,
           "lab": "tools/pt_risk_lab.py", "features": FEATURES,
           "hit": {"enabled": False}, "pit": {"enabled": False}}
    bases = [b for b in range(TRAIN_FIRST, 2026) if b != 2020]
    for side in sides:
        train = []
        for B in bases:
            curves, war_map = fp.fitted_models(corpus, B - 1)
            train.extend(_universe(corpus, by_player, war_actual, B, side,
                                   curves, war_map, _IL_INT))
        out[side] = _fit_ridge(train, side)
        print(f"{side}: fit on {len(train)} rows, coef {out[side]['coef']}")
    out["il"] = {str(p): {str(y): [v[0], v[1]] for y, v in yrs.items()}
                 for p, yrs in _IL_INT.items()}
    SIDECAR.write_text(json.dumps(out), encoding="utf-8")
    print("wrote", SIDECAR)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "fetch":
        cmd_fetch()
    elif cmd == "stints":
        cmd_stints()
    elif cmd == "gate":
        cmd_gate()
    elif cmd == "finalize":
        cmd_finalize(sys.argv[2:] or ["hit", "pit"])
    else:
        print("usage: pt_risk_lab.py fetch|stints|gate|finalize")
