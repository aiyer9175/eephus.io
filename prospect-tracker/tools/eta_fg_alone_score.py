# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""FanGraphs-alone ETA score on the 2024 frame (registered 2026-10-22).

Registration: docs/eta-2026-09-25/ETA_FG_ALONE_SCORE.md (committed alone before
this lab existed). Owner answer SWEEP-Q3 (2026-10-22): one score of FanGraphs'
published eta_year alone against the served blend (eta_fg_blend, arm B of
docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md), on that gate's 2024 frame, debut
years only, run once.

  arm F  max(V, FG(V))                                   FanGraphs alone
  arm B  eta.fg_blend_eta_year(CH40, FG, V, on40, "B")   the served blend

The frame is the gate's own construction, called unchanged from
tools/eta_fg_blend_gate.py. Scored rows: debuted rows with a C5-clean FanGraphs
year and a CH40 year (the gate's C1 frame). No overdue count, no censored row's
outcome, no eFV, consensus-FV, source-rank or realized-WAR quantity, and no cut
by consensus-FV level.

Modes (run from prospect-tracker/):
  python tools/eta_fg_alone_score.py --run --cache-dir DIR   the ONE registered run
  python tools/eta_fg_alone_score.py --dry-run               synthetic rows, no read, no write
  python tools/eta_fg_alone_score.py --reprint               re-print the stored run

The run writes only the block fg_blend_gate_fg_alone_2026_10_22 into
data/eta_eval.json (read-modify-write; the fg_blend_gate_ prefix is one
eta_backtest.run() carries forward). It never touches eta.ETA_FG_BLEND_ARM or
the registry.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REG_DOC = "docs/eta-2026-09-25/ETA_FG_ALONE_SCORE.md"
BLOCK = "fg_blend_gate_fg_alone_2026_10_22"
LOOK_BLOCK = "fg_blend_gate_2026_09_25"
ARTIFACT = ROOT / "data" / "eta_eval.json"


def _gate():
    """The gate lab, loaded from its file (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "eta_fg_blend_gate", ROOT / "tools" / "eta_fg_blend_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = _gate()


def _rnd(x: float) -> int:
    """Round half up (the gate's rnd), never banker's rounding."""
    return int(math.floor(x + 0.5))


def arm_f(r: dict) -> int:
    """FanGraphs alone: max(V, FG(V)). Only called on C5-clean rows."""
    return max(int(r["vintage"]), int(r["fg"]))


def arm_b(r: dict) -> int | None:
    """The served blend, by the function the served path calls."""
    return G.arm_year(r, "B")


def planted_better(r: dict) -> int:
    return _rnd(0.5 * arm_b(r) + 0.5 * r["actual"])


def planted_worse(r: dict) -> int:
    b = arm_b(r)
    return b + 1 if b >= r["actual"] else b - 1


def _ci_verdict(bt: dict) -> str:
    lo, hi = bt["ci_dMAE"]
    if lo > 0:
        return "F_BEATS_B"
    if hi < 0:
        return "B_BEATS_F"
    return "TIES"


def score_rows(rows: list[dict], log, *, stored: dict | None = None) -> dict:
    """Score arm F against arm B on the gate's C1 rows. Reads `actual` only on
    debuted rows; a censored or washed-out row contributes only to the frame
    count printed for reproduction."""
    for r in rows:
        r["c5_ok"] = G.c5_clean(r)
    frame = [r for r in rows if r["ch40"] is not None]
    deb = [r for r in frame if r["outcome"] == "debuted"]
    n_cens = sum(1 for r in frame if r["outcome"] == "censored_active")
    scored = [r for r in deb if r["c5_ok"]]
    n = {"rows": len(frame), "debuted": len(deb), "censored_active": n_cens,
         "fg_debuted_c5_clean": len(scored)}
    log(f"frame: rows={n['rows']} debuted={n['debuted']} censored_active={n['censored_active']} "
        f"fg_debuted_c5_clean={n['fg_debuted_c5_clean']}")
    ch = lambda r: r["ch40"]                                        # noqa: E731
    s_ch = G.score([(ch(r), r["actual"]) for r in scored])
    s_b = G.score([(arm_b(r), r["actual"]) for r in scored])
    repro = {"now": {**n, "CH40_mae": s_ch.get("mae"), "B_mae": s_b.get("mae")}}
    if stored:
        repro["stored"] = stored
        diffs = sorted(k for k, v in stored.items() if repro["now"].get(k) != v)
        repro["identical"] = not diffs
        repro["differs_on"] = diffs
        log(f"reproduction vs the 2026-09-30 look: {'IDENTICAL' if not diffs else 'DIFFERS on ' + ', '.join(diffs)}; "
            f"stored {json.dumps(stored, sort_keys=True)}")
    log(f"row-matched (n={len(scored)}): CH40 {s_ch.get('mae')} B {s_b.get('mae')}")

    pb = G.paired_boot(scored, arm_b, planted_better)
    pw = G.paired_boot(scored, arm_b, planted_worse)
    inst_ok = pb["ci_dMAE"][0] > 0 and pw["ci_dMAE"][1] < 0
    instrument = {"planted_better": pb, "planted_worse": pw, "verdict": "PASS" if inst_ok else "FAIL"}
    log(f"instrument: planted-better dMAE {pb['dMAE']:+.4f} CI95 [{pb['ci_dMAE'][0]:+.4f}, {pb['ci_dMAE'][1]:+.4f}]; "
        f"planted-worse dMAE {pw['dMAE']:+.4f} CI95 [{pw['ci_dMAE'][0]:+.4f}, {pw['ci_dMAE'][1]:+.4f}] -> "
        f"{instrument['verdict']}")

    s_f = G.score([(arm_f(r), r["actual"]) for r in scored])
    bt_fb = G.paired_boot(scored, arm_b, arm_f)
    bt_fc = G.paired_boot(scored, ch, arm_f)
    verdict = _ci_verdict(bt_fb) if inst_ok else "VOID"
    moved = {"rows": sum(1 for r in scored if arm_f(r) != arm_b(r)),
             "earlier": sum(1 for r in scored if arm_f(r) < arm_b(r)),
             "later": sum(1 for r in scored if arm_f(r) > arm_b(r))}
    floor_at_v = sum(1 for r in scored if int(r["fg"]) < int(r["vintage"]))
    log(f"F (FanGraphs alone) vs B (served blend): n={bt_fb['n']} B {s_b.get('mae')} vs F {s_f.get('mae')}; "
        f"dMAE {bt_fb['dMAE']:+.4f} CI95 [{bt_fb['ci_dMAE'][0]:+.4f}, {bt_fb['ci_dMAE'][1]:+.4f}]; "
        f"within-1y B {s_b.get('within_1y')} vs F {s_f.get('within_1y')} d {bt_fb['dW1']:+.4f} "
        f"CI95 [{bt_fb['ci_dW1'][0]:+.4f}, {bt_fb['ci_dW1'][1]:+.4f}]")
    log(f"reported: bias CH40 {s_ch.get('bias')} B {s_b.get('bias')} F {s_f.get('bias')}; "
        f"F vs CH40 dMAE {bt_fc['dMAE']:+.4f} CI95 [{bt_fc['ci_dMAE'][0]:+.4f}, {bt_fc['ci_dMAE'][1]:+.4f}]; "
        f"F differs from B on {moved['rows']} rows ({moved['earlier']} earlier, {moved['later']} later); "
        f"floor at V moved {floor_at_v}")
    log(f"VERDICT: {verdict} (adjudicates nothing served; the blend stays served)")
    return {"n": n, "reproduction": repro,
            "scores": {"CH40": s_ch, "B": s_b, "F": s_f},
            "boot_F_vs_B": bt_fb, "boot_F_vs_CH40": bt_fc,
            "instrument": instrument, "moved_vs_B": moved, "floor_at_V": floor_at_v,
            "verdict": verdict}


def stored_look() -> dict:
    """The look's frame counts and row-matched MAE, from the stored block."""
    blk = _read_artifact().get(LOOK_BLOCK) or {}
    n = blk.get("n") or {}
    rm = ((blk.get("clauses") or {}).get("B") or {}).get("row_matched") or {}
    return {"rows": n.get("rows"), "debuted": n.get("debuted"),
            "censored_active": n.get("censored_active"),
            "fg_debuted_c5_clean": n.get("fg_debuted_c5_clean"),
            "CH40_mae": (rm.get("CH40") or {}).get("mae"), "B_mae": (rm.get("B") or {}).get("mae")}


def _read_artifact() -> dict:
    try:
        return json.loads(ARTIFACT.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def run_allowed(artifact: dict) -> tuple[bool, str]:
    if (artifact.get(BLOCK) or {}).get("run"):
        return False, "the registered run already happened; use --reprint"
    return True, "ok"


def _private_cache(cache_dir: Path) -> Path:
    """Copy the gate's roster cache so the run never writes the shared .cache."""
    dst = Path(cache_dir) / "eta_fg_blend"
    if not dst.exists():
        src = ROOT / ".cache" / "eta_fg_blend"
        if src.exists():
            shutil.copytree(src, dst)
        else:
            dst.mkdir(parents=True)
    return dst


def run_once(cache_dir: Path) -> int:
    art = _read_artifact()
    ok, why = run_allowed(art)
    if not ok:
        print(f"REFUSED: {why}")
        return 2
    G.CACHE = _private_cache(cache_dir)
    lines: list[str] = []

    def log(s: str) -> None:
        lines.append(s)
        print(s, flush=True)

    G.assert_frame_vintages((G.FRAME_V,))
    rows, acct = G.build_rows((G.FRAME_V,), washed_before=G.ACTIVE_FROM,
                              last_full_season=G.LAST_SEASON)
    rows = G.attach_outcomes_2024(rows, acct)
    log(f"cohort 2024: {json.dumps(acct, sort_keys=True)}")
    out = score_rows(rows, log, stored=stored_look())
    stamp = date.today().isoformat()
    art = _read_artifact()
    art[BLOCK] = {"registration": REG_DOC, "run": stamp, "frame": "list vintage 2024",
                  "outcome_cutoff": G.OUTCOME_CUTOFF, "seed": G.SEED, "B": G.B,
                  "arms": {"F": "max(V, FG(V)), FanGraphs alone",
                           "B": "eta.fg_blend_eta_year arm B, the served blend"},
                  "scored_rows": "debuted rows with a C5-clean FanGraphs year and a CH40 year",
                  "accounting": acct, **out, "verbatim": lines}
    # keep the file's own line endings (a CRLF checkout stays CRLF)
    crlf = ARTIFACT.exists() and b"\r\n" in ARTIFACT.read_bytes()[:4096]
    with open(ARTIFACT, "w", encoding="utf-8", newline="\r\n" if crlf else "\n") as fh:
        fh.write(json.dumps(art, indent=1))
    print(f"wrote {BLOCK} into {ARTIFACT.name}")
    return 0


def run_reprint() -> int:
    blk = _read_artifact().get(BLOCK) or {}
    if not blk.get("run"):
        print("no registered run on record")
        return 1
    print("\n".join(blk.get("verbatim") or []))
    return 0


def synthetic_rows(n_players: int = 120, seed: int = 7) -> list[dict]:
    """Fixture rows for the dry run: no file, database or network is read."""
    import random
    rng = random.Random(seed)
    rows = []
    for i in range(n_players):
        outcome = ("debuted", "censored_active", "washed_out")[i % 3]
        ch40 = 2024 + rng.randint(0, 4)
        fg = 2024 + rng.randint(0, 4) if i % 5 else None
        r = {"player_key": f"p{i}", "vintage": 2024, "level": None, "ch40": ch40,
             "fg": fg, "fg_date": "2024-02-01" if fg else None, "on40": i % 7 == 0,
             "outcome": outcome, "debut_date": None}
        if outcome == "debuted":
            r["actual"] = 2024 + rng.randint(0, 2)
            r["debut_date"] = f"{r['actual']}-06-01"
        rows.append(r)
    return rows


def run_dry() -> int:
    print("DRY RUN on synthetic rows (no frame read, nothing written)")
    score_rows(synthetic_rows(), print, stored={"rows": 0})
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--run", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--reprint", action="store_true")
    ap.add_argument("--cache-dir", type=Path)
    a = ap.parse_args(argv)
    if a.reprint:
        return run_reprint()
    if a.dry_run:
        return run_dry()
    if not a.cache_dir:
        ap.error("--run needs --cache-dir (a private copy of the roster cache)")
    return run_once(a.cache_dir)


if __name__ == "__main__":
    sys.exit(main())
