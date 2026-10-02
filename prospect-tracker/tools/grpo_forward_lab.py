# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""GRPO breakout badge forward read: the lab of docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md.

Built to section 2 of the gate as frozen on 2026-08-19, and nothing more:

  2.1 COHORTS   one cohort per snapshot_date in prospects.db grpo_score_history.
                PRIMARY = the first snapshot_date of each calendar month. Every
                snapshot_date (daily) is a sensitivity read with no verdict weight.
  2.2 FLAG      the top decile by archived score inside a cohort, every tie at the
                boundary included. The 0.55 chip threshold is a sensitivity cut.
  2.3 HIT       consensus FV rises by at least +5.0 (editorial_eval HIT_RULES
                'riser') from the cohort date to maturation, both ends read from
                metric_snapshots. No board row at either end: the player leaves
                numerator and denominator.
  2.4 WINDOWS   30, 60, 90 days. A cohort is matured for W when a board snapshot
                exists on or after cohort_date + W days.
  2.5 CONTROLS  A: 1,000 within-cohort shuffles of the archived scores, the same
                flag rule re-applied, rate = permutation mean, CI = the 2.5 and
                97.5 percentiles. B: the top decile by consensus FV on the cohort
                date, ties broken by consensus board rank.
  2.6 CLAUSES   G-1 badge Wilson 95% CI above the permutation CI with no overlap;
                G-2 badge Wilson 95% CI above the Control B Wilson 95% CI with no
                overlap; the ladder (validated for that window / repackages
                consensus FV / zero information); the kill rule at 6 matured
                monthly cohorts on the 30-day window.

Reads grpo_score_history and metric_snapshots read-only and writes one file,
data/grpo_forward_eval.json (or --out, used only by the dry run). Each window is
recorded once: a window already in the artifact is never recomputed or
rewritten, and a run with no newly matured window refuses to write. Refuses to
run before 2026-09-18 (the first admissible 30-day look) and on a registered look
day of another gate. Never prices anything: bayes_trade_value keeps
grpo_fv_adj = 0.0 whatever this prints (gate section 0).

Run: python -u tools/grpo_forward_lab.py
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import subprocess
import sys
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from editorial_eval import HIT_RULES, V2_BASE_LOOKBACK_DAYS, _wilson  # noqa: E402

GATE_DOC = "docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md"
DB_PATH = ROOT / "prospects.db"
OUT_PATH = ROOT / "data" / "grpo_forward_eval.json"
SCHEMA = "grpo_forward_eval/1"

ARCHIVE_START = "2026-08-19"
FIRST_ADMISSIBLE = "2026-09-18"          # gate section 3: 2026-08-19 + 30 days
WINDOWS = (30, 60, 90)
DECILE = 0.10
CHIP_THRESHOLD = 0.55
HIT_FV_DELTA = float(HIT_RULES["riser"]["fv_delta"])   # +5.0, the template's riser
HIT_EPS = 1e-9                           # float guard on the +5.0 comparison
N_PERM = 1000
SEED = 20260819                          # the archive's first snapshot_date
KILL_MIN_MONTHLY_COHORTS = 6
BASE_LOOKBACK_DAYS = V2_BASE_LOOKBACK_DAYS  # base board night: on the cohort date or up to 3 days before

# Registered look days of other gates; the lab does not run on them.
BLOCKED_DAYS = frozenset({"2026-10-23", "2026-11-06", "2026-11-13",
                          "2026-11-20", "2026-12-01"})

LADDER_VALIDATED = "validated for that window"
LADDER_REPACKAGES = "repackages consensus FV"
LADDER_ZERO = "zero information"
LADDER_NOT_EVALUABLE = "not evaluable (no scoreable flagged rows)"


class LabRefusal(RuntimeError):
    """A protocol refusal: the lab writes nothing."""


class ArchiveIntegrityError(RuntimeError):
    """Two score vectors archived for one snapshot_date."""


# ---------------------------------------------------------------------------
# Inputs (read-only)
# ---------------------------------------------------------------------------

def _connect_ro(db_path: Path) -> sqlite3.Connection:
    if not Path(db_path).exists():
        raise LabRefusal(f"database not found: {db_path}")
    return sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True, timeout=30)


def load_archive(db_path: Path) -> tuple[dict[str, dict[str, float | None]], dict]:
    """{snapshot_date: {player_key: score}} from grpo_score_history, plus counts.

    Asserts the gate's integrity rule: one score per (snapshot_date, player_key).
    A NULL or non-finite score is kept as None and leaves its cohort."""
    con = _connect_ro(db_path)
    try:
        dupes = con.execute(
            "SELECT snapshot_date, player_key, COUNT(*) FROM grpo_score_history "
            "GROUP BY snapshot_date, player_key HAVING COUNT(*) > 1 LIMIT 5").fetchall()
        if dupes:
            raise ArchiveIntegrityError(
                f"two score vectors archived for one snapshot_date: {dupes}")
        rows = con.execute(
            "SELECT snapshot_date, player_key, score FROM grpo_score_history "
            "ORDER BY snapshot_date, player_key").fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, float | None]] = {}
    n_null = 0
    for d, k, s in rows:
        v = None
        if s is not None:
            try:
                v = float(s)
            except (TypeError, ValueError):
                v = None
            if v is not None and not math.isfinite(v):
                v = None
        if v is None:
            n_null += 1
        out.setdefault(str(d), {})[str(k)] = v
    return out, {"rows": len(rows), "null_scores": n_null}


def load_board(db_path: Path) -> tuple[list[str], dict[str, dict[str, tuple]]]:
    """Board nights (sorted) and {night: {player_key: (consensus_fv, overall_rank)}}
    from metric_snapshots, rows with a consensus FV only."""
    con = _connect_ro(db_path)
    try:
        rows = con.execute(
            "SELECT snapshot_date, player_key, consensus_fv, overall_rank "
            "FROM metric_snapshots WHERE consensus_fv IS NOT NULL").fetchall()
    finally:
        con.close()
    nights: dict[str, dict[str, tuple]] = {}
    for d, k, fv, rk in rows:
        try:
            fvf = float(fv)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(fvf):
            continue
        nights.setdefault(str(d), {})[str(k)] = (fvf, rk)
    return sorted(nights), nights


# ---------------------------------------------------------------------------
# Frozen design pieces
# ---------------------------------------------------------------------------

def monthly_cohorts(dates: list[str]) -> list[str]:
    """2.1 PRIMARY: the first snapshot_date of each calendar month present."""
    first: dict[str, str] = {}
    for d in sorted(dates):
        first.setdefault(d[:7], d)
    return [first[m] for m in sorted(first)]


def _decile_k(n: int) -> int:
    return int(math.ceil(DECILE * n)) if n > 0 else 0


def top_decile_mask(values: np.ndarray) -> np.ndarray:
    """2.2: the top decile by score, every tie at the boundary included.
    k = ceil(0.10 * n); flagged = score >= the k-th highest score."""
    n = values.size
    k = _decile_k(n)
    if k == 0:
        return np.zeros(n, dtype=bool)
    thr = np.partition(values, n - k)[n - k]
    return values >= thr


def chip_mask(values: np.ndarray) -> np.ndarray:
    """2.2 sensitivity cut: the served chip threshold, score >= 0.55."""
    return values >= CHIP_THRESHOLD


def base_night(nights: list[str], cohort_date: str) -> str | None:
    """The board night on the cohort date, else the latest one at most
    BASE_LOOKBACK_DAYS earlier; None when the board was not written close enough."""
    i = bisect_right(nights, cohort_date) - 1
    if i < 0:
        return None
    gap = (date.fromisoformat(cohort_date) - date.fromisoformat(nights[i])).days
    return nights[i] if gap <= BASE_LOOKBACK_DAYS else None


def end_night(nights: list[str], cohort_date: str, window: int) -> str | None:
    """2.4: the first board night on or after cohort_date + window; None while
    the window has not closed."""
    target = (date.fromisoformat(cohort_date) + timedelta(days=window)).isoformat()
    i = bisect_left(nights, target)
    return nights[i] if i < len(nights) else None


def is_hit(fv_base: float | None, fv_end: float | None) -> bool | None:
    """2.3: +5.0 or more; None (excluded) when either end has no board row."""
    if fv_base is None or fv_end is None:
        return None
    return (fv_end - fv_base) >= HIT_FV_DELTA - HIT_EPS


def fv_top_decile(keys: list[str], board_base: dict[str, tuple]) -> list[str]:
    """2.5 CONTROL B: the cohort's players with a base-date consensus FV, ranked
    by FV descending, ties by consensus board rank (missing rank last, then key),
    top ceil(0.10 * n)."""
    pool = [k for k in keys if k in board_base]
    def _rk(k):
        r = board_base[k][1]
        return (r is None, r if r is not None else 0, k)
    pool.sort(key=lambda k: (-board_base[k][0],) + _rk(k))
    return pool[:_decile_k(len(pool))]


def ladder(g1: bool, g2: bool, scoreable: int) -> str:
    if scoreable == 0:
        return LADDER_NOT_EVALUABLE
    if g1 and g2:
        return LADDER_VALIDATED
    if g1:
        return LADDER_REPACKAGES
    return LADDER_ZERO


# ---------------------------------------------------------------------------
# One window over a set of cohorts
# ---------------------------------------------------------------------------

def _cohort_frame(scores: dict[str, float | None], nights: list[str],
                  board: dict[str, dict[str, tuple]], cohort_date: str, window: int):
    """Arrays for one cohort at one window, or a reason string when it cannot be
    scored (not matured, or no base board night)."""
    b = base_night(nights, cohort_date)
    e = end_night(nights, cohort_date, window)
    if e is None:
        return "not matured"
    if b is None:
        return "no base board night"
    keys = sorted(k for k, v in scores.items() if v is not None)
    vals = np.array([scores[k] for k in keys], dtype=float)
    bb, eb = board[b], board[e]
    outcome = np.full(len(keys), -1, dtype=np.int8)     # -1 excluded, 0 miss, 1 hit
    for i, k in enumerate(keys):
        h = is_hit(bb[k][0] if k in bb else None, eb[k][0] if k in eb else None)
        if h is not None:
            outcome[i] = 1 if h else 0
    return {"keys": keys, "vals": vals, "outcome": outcome,
            "base": b, "end": e, "n_null": sum(1 for v in scores.values() if v is None)}


def _rate(hits: int, n: int) -> dict:
    p, lo, hi = _wilson(hits, n)
    return {"hits": int(hits), "n": int(n), "rate": p if n else None,
            "ci95": [lo, hi] if n else None}


def evaluate_window(archive: dict[str, dict[str, float | None]], cohort_dates: list[str],
                    nights: list[str], board: dict[str, dict[str, tuple]], window: int,
                    flag_rule, rng_key: tuple) -> dict:
    """Badge, Control A and Control B for one flag rule over the matured cohorts."""
    per_cohort, frames = [], []
    for c in cohort_dates:
        fr = _cohort_frame(archive.get(c, {}), nights, board, c, window)
        if isinstance(fr, str):
            per_cohort.append({"cohort": c, "status": fr})
            continue
        mask = flag_rule(fr["vals"])
        out = fr["outcome"]
        f_hits = int(((out == 1) & mask).sum())
        f_n = int(((out >= 0) & mask).sum())
        bb = board[fr["base"]]
        ctl_b = set(fv_top_decile(fr["keys"], bb))
        bmask = np.array([k in ctl_b for k in fr["keys"]], dtype=bool)
        b_hits = int(((out == 1) & bmask).sum())
        b_n = int(((out >= 0) & bmask).sum())
        per_cohort.append({
            "cohort": c, "status": "matured", "base_night": fr["base"],
            "end_night": fr["end"], "archived": len(fr["keys"]),
            "null_scores": fr["n_null"], "flagged": int(mask.sum()),
            "flagged_scoreable": f_n, "flagged_hits": f_hits,
            "control_b_flagged": int(bmask.sum()), "control_b_scoreable": b_n,
            "control_b_hits": b_hits})
        frames.append((fr, mask))
    matured = [p for p in per_cohort if p["status"] == "matured"]
    res = {"window_days": window, "cohorts": per_cohort,
           "cohorts_matured": len(matured)}
    if not matured:
        res["status"] = "not matured"
        return res
    hits = sum(p["flagged_hits"] for p in matured)
    n = sum(p["flagged_scoreable"] for p in matured)
    res["status"] = "matured"
    res["flagged_n"] = sum(p["flagged"] for p in matured)
    res["badge"] = _rate(hits, n)
    # CONTROL A: shuffle the archived scores within each cohort, re-apply the rule.
    rng = np.random.default_rng([SEED, *rng_key])
    perm_rates = np.full(N_PERM, np.nan)
    for r in range(N_PERM):
        ph = pn = 0
        for fr, _ in frames:
            pm = flag_rule(rng.permutation(fr["vals"]))
            o = fr["outcome"]
            ph += int(((o == 1) & pm).sum())
            pn += int(((o >= 0) & pm).sum())
        if pn:
            perm_rates[r] = ph / pn
    finite = perm_rates[np.isfinite(perm_rates)]
    if finite.size:
        res["control_a"] = {
            "permutations": N_PERM, "rate": round(float(finite.mean()), 4),
            "ci95": [round(float(np.percentile(finite, 2.5)), 4),
                     round(float(np.percentile(finite, 97.5)), 4)]}
    else:
        res["control_a"] = {"permutations": N_PERM, "rate": None, "ci95": None}
    res["control_b"] = _rate(sum(p["control_b_hits"] for p in matured),
                             sum(p["control_b_scoreable"] for p in matured))
    bci, aci, cci = res["badge"]["ci95"], res["control_a"]["ci95"], res["control_b"]["ci95"]
    g1 = bool(bci and aci and bci[0] > aci[1])
    g2 = bool(bci and cci and bci[0] > cci[1])
    res["g1_clears_control_a"] = g1
    res["g2_clears_control_b"] = g2
    res["ladder"] = ladder(g1, g2, n)
    return res


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _fmt_rate(r: dict | None) -> str:
    if not r or r.get("rate") is None:
        return "n/a (no scoreable rows)"
    lo, hi = r["ci95"]
    extra = f"{r['hits']}/{r['n']}" if "hits" in r else f"{r['permutations']} permutations"
    return f"{r['rate']:.4f} [{lo:.4f}, {hi:.4f}] ({extra})"


def _yn(b: bool) -> str:
    return "CLEARED" if b else "not cleared"


def report_window(label: str, res: dict, verdict_weight: bool) -> list[str]:
    tag = "" if verdict_weight else " (sensitivity, no verdict weight)"
    lines = [f"{label}{tag}, {res['window_days']}-day window:"]
    for p in res["cohorts"]:
        if p["status"] != "matured":
            lines.append(f"  cohort {p['cohort']}: {p['status']}")
            continue
        lines.append(
            f"  cohort {p['cohort']}: base {p['base_night']}, end {p['end_night']}, "
            f"archived {p['archived']}, null scores {p['null_scores']}, "
            f"flagged {p['flagged']} (scoreable {p['flagged_scoreable']}, hits {p['flagged_hits']}), "
            f"Control B {p['control_b_flagged']} (scoreable {p['control_b_scoreable']}, "
            f"hits {p['control_b_hits']})")
    if res["status"] != "matured":
        lines.append("  window: not matured, no verdict")
        return lines
    lines.append(f"  cohorts matured: {res['cohorts_matured']}; flagged n: {res['flagged_n']}")
    lines.append(f"  badge hit rate:     {_fmt_rate(res['badge'])}")
    lines.append(f"  Control A (shuffle): {_fmt_rate(res['control_a'])}")
    lines.append(f"  Control B (FV only): {_fmt_rate(res['control_b'])}")
    lines.append(f"  G-1 vs Control A: {_yn(res['g1_clears_control_a'])}; "
                 f"G-2 vs Control B: {_yn(res['g2_clears_control_b'])}")
    lines.append(f"  ladder: {res['ladder']}" + ("" if verdict_weight else " (sensitivity only)"))
    return lines


def kill_rule_status(matured_monthly_30: int, g1_30: bool | None) -> str:
    if matured_monthly_30 < KILL_MIN_MONTHLY_COHORTS:
        return (f"not yet evaluable ({matured_monthly_30} of {KILL_MIN_MONTHLY_COHORTS} "
                "matured monthly cohorts on the 30-day window)")
    if g1_30 is None:
        return (f"evaluable ({matured_monthly_30} matured monthly cohorts on the 30-day "
                "window); the 30-day window is recorded once here, so the kill read "
                "needs its own registration")
    return ("KILL: G-1 fails with 6 or more matured monthly cohorts; recommend de-list "
            "the badge or re-label it descriptive") if not g1_30 else "not triggered"


def _head(root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=root,
                             capture_output=True, text=True, check=False)
        return out.stdout.strip() or "unknown"
    except (OSError, FileNotFoundError):
        return "unknown"


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def run(db_path: Path = DB_PATH, out_path: Path = OUT_PATH, today: str | None = None,
        head: str | None = None, emit=print) -> dict:
    today = today or date.today().isoformat()
    if today < FIRST_ADMISSIBLE:
        raise LabRefusal(f"refused: {today} is before the first admissible look "
                         f"{FIRST_ADMISSIBLE} (gate section 3)")
    if today in BLOCKED_DAYS:
        raise LabRefusal(f"refused: {today} is a registered look day of another gate")
    out_path = Path(out_path)
    prior: dict | None = None
    if out_path.exists():
        prior = json.loads(out_path.read_text(encoding="utf-8"))
    recorded = set((prior or {}).get("looks", {}))

    archive, counts = load_archive(db_path)
    nights, board = load_board(db_path)
    dates = sorted(archive)
    monthly = monthly_cohorts(dates)
    last_night = nights[-1] if nights else None

    # Windows open for this look: matured on the primary read and not yet recorded.
    first_matured = {}
    for w in WINDOWS:
        first_matured[w] = any(end_night(nights, c, w) is not None for c in monthly)
    to_record = [w for w in WINDOWS if first_matured[w] and str(w) not in recorded]
    if not to_record:
        held = ", ".join(f"{w}-day" for w in WINDOWS if str(w) in recorded) or "none"
        raise LabRefusal(
            "refused: no newly matured window to record (recorded already: "
            f"{held}); a second write of a recorded window is not allowed")

    head = head or _head(ROOT)
    lines = [
        "GRPO forward read (docs/grpo-2026-08-19/GRPO_FORWARD_GATE.md, section 2 frozen 2026-08-19)",
        f"run date {today}, HEAD {head}, seed {SEED}, permutations {N_PERM}",
        f"archive: {counts['rows']} rows, {len(dates)} snapshot dates "
        f"({dates[0] if dates else 'none'} to {dates[-1] if dates else 'none'}), "
        f"null scores {counts['null_scores']}",
        f"board: {len(nights)} metric_snapshots nights, latest {last_night}",
        f"monthly cohorts (primary): {', '.join(monthly) or 'none'}",
        f"hit rule: consensus FV +{HIT_FV_DELTA:.1f} or more, base night on the cohort date "
        f"or up to {BASE_LOOKBACK_DAYS} days before, end night first on or after cohort + W",
        "",
    ]
    look = {"run_date": today, "head": head, "windows_recorded": to_record,
            "windows": {}, "chip_sensitivity": {}, "daily_sensitivity": {}}
    g1_30 = None
    matured_monthly_30 = 0
    for w in WINDOWS:
        if str(w) in recorded:
            lines.append(f"PRIMARY, {w}-day window: recorded in the look of "
                         f"{prior['looks'][str(w)]['run_date']}, not recomputed")
            lines.append("")
            continue
        prim = evaluate_window(archive, monthly, nights, board, w, top_decile_mask, (w, 1))
        lines += report_window("PRIMARY (monthly cohorts, top decile)", prim, True)
        if w == 30:
            matured_monthly_30 = prim["cohorts_matured"]
            if prim["status"] == "matured":
                g1_30 = prim["g1_clears_control_a"]
        if prim["status"] == "matured" and w in to_record:
            chip = evaluate_window(archive, monthly, nights, board, w, chip_mask, (w, 2))
            daily = evaluate_window(archive, dates, nights, board, w, top_decile_mask, (w, 3))
            lines += report_window("SENSITIVITY chip cut (monthly cohorts, score >= 0.55)",
                                   chip, False)
            lines += report_window("SENSITIVITY daily cohorts (top decile)", daily, False)
            look["windows"][str(w)] = prim
            look["chip_sensitivity"][str(w)] = chip
            look["daily_sensitivity"][str(w)] = daily
        lines.append("")
    if matured_monthly_30 == 0 and "30" in recorded:
        matured_monthly_30 = sum(1 for c in monthly if end_night(nights, c, 30) is not None)
    kill = kill_rule_status(matured_monthly_30, g1_30)
    look["kill_rule"] = kill
    lines.append(f"kill rule: {kill}")
    lines.append("pricing: grpo_fv_adj stays 0.0 (gate section 0); this read moves no served number")
    for ln in lines:
        emit(ln)

    doc = prior or {"schema": SCHEMA, "gate": GATE_DOC, "seed": SEED,
                    "permutations": N_PERM, "decile": DECILE,
                    "chip_threshold": CHIP_THRESHOLD, "hit_fv_delta": HIT_FV_DELTA,
                    "base_lookback_days": BASE_LOOKBACK_DAYS, "looks": {}}
    for w in to_record:
        rec = dict(look)
        rec["window"] = w
        rec["primary"] = look["windows"][str(w)]
        rec["chip_sensitivity"] = look["chip_sensitivity"][str(w)]
        rec["daily_sensitivity"] = look["daily_sensitivity"][str(w)]
        rec.pop("windows", None)
        rec["stdout"] = lines
        doc["looks"][str(w)] = rec
    doc["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["as_of"] = today
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    emit(f"wrote {out_path.name}: windows recorded {', '.join(f'{w}-day' for w in to_record)}")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, default=DB_PATH,
                    help="dry run only: a fixture database")
    ap.add_argument("--out", type=Path, default=OUT_PATH,
                    help="dry run only: a temp artifact path")
    a = ap.parse_args(argv)
    try:
        run(a.db, a.out)
    except LabRefusal as exc:
        print(str(exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
