# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Record the team gate's GATE look in the registry (idempotent; task
TM_4_TEAM_LOOK_2026, docs/TEAM_PROJECTIONS_GATE.md section 5.2).

Reads team_projection_gate.gate_2026 from data/team_outlook_eval.json and
writes, with every number read from that block:
- team_win_distribution: eval_artifact the artifact, verdict provisional
  (whatever the outcome; the gate's own words), summary, registration_status
  and one dated note with TM-A's result;
- team_run_projection: the same with TM-C's result;
- team_win_projections: one dated note with TM-B's result, nothing else.
Keeps the file's line endings (CRLF) and its one-space indent; every other
byte of the file stays as it is. Running it twice changes nothing.

    python tools/register_team_look.py [--artifact PATH] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART_DEFAULT = ROOT / "data" / "team_outlook_eval.json"
ART_REL = "data/team_outlook_eval.json"
TASK = "TM_4_TEAM_LOOK_2026"


def _f(v, nd=3, sign=False):
    if v is None:
        return "n/a"
    try:
        return f"{float(v):+.{nd}f}" if sign else f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return str(v)


def _cov(c: dict | None) -> str:
    if not c or c.get("rate") is None:
        return "n/a"
    w = c.get("wilson95") or {}
    return f"{_f(c['rate'])} ({c['k']} of {c['n']}; Wilson {_f(w.get('lo'))} to {_f(w.get('hi'))})"


def _marker(block: dict, suffix: str = "") -> str:
    return f"LOOK {block['look_date']} ({TASK}{suffix})"


def _early(block: dict) -> str:
    """The block's early-read note as a clause: first letter lowered, no final stop."""
    s = str(block.get("early_read_note") or "").strip().rstrip(".")
    return (s[:1].lower() + s[1:]) if s else "on the registered terms"


def note_tm_a(block: dict) -> str:
    a, b = block["tm_a"], block["tm_a"]["bootstrap"]
    dc = a.get("dev_coverage80") or {}
    return (f"{_marker(block)}: the one GATE read of TM-A on the {block['season']} club season "
            f"({b.get('n')} clubs; {_early(block)}). Frozen params sha256 "
            f"{block['params_sha256']}, n_sims {a['n_sims']}, simulator seed {a['sim_seed']}, home edge "
            f"{a['home_edge']}, bracket off, bootstrap B {block['bootstrap']['B']} seed {block['bootstrap']['seed']}. "
            f"Candidate (sigma_T {_f(a['sigma_T'], 4)}) mean CRPS {_f(a['candidate']['crps_mean'])} against the "
            f"schedule-only incumbent {_f(a['incumbent']['crps_mean'])}; paired delta {_f(b.get('mean'))}, "
            f"ub95 {_f(b.get('ub95'), sign=True)}: {a['verdict']}"
            f"{' (ub95 at or above 0)' if a['verdict'] == 'FAIL' else ''}. 80% coverage candidate "
            f"{_cov(a['candidate']['coverage80'])}, incumbent {_cov(a['incumbent']['coverage80'])}; DEV coverage "
            f"beside: candidate in-sample {_cov(dc.get('candidate_in_sample'))}, incumbent {_cov(dc.get('incumbent'))}. "
            f"Win sd per club: candidate {_f(a['candidate']['win_sd_mean'], 2)}, incumbent "
            f"{_f(a['incumbent']['win_sd_mean'], 2)}. TEAM_TALENT_RANGE_LIVE "
            f"{'eligible (the flip is its own commit on TM-Q1)' if block['flags_eligible'].get('TEAM_TALENT_RANGE_LIVE') else 'not eligible; the schedule-only band stays served'}. "
            f"Nothing served moves at the look; the 2027 re-read (TM_9) is a veto only for a served flag and never "
            f"makes an unserved flag eligible (gate 3.5).")


def note_tm_c(block: dict) -> str:
    c = block["tm_c"]
    meta = c.get("meta") or {}
    pf = meta.get("park_factor") or {}
    parts = [f"{_marker(block)}: the one GATE read of TM-C on {block['season']} ({c['rs']['n']} clubs RS, "
             f"{c['ra']['n']} clubs RA; {_early(block)}). Constants at "
             f"{meta.get('constants_season')}, park factors {pf.get('file')} ({pf.get('column')}), PJ-C params "
             f"sha256 {meta.get('pj_params_sha256')}, bootstrap B {block['bootstrap']['B']} seed "
             f"{block['bootstrap']['seed']}."]
    for side, label in (("rs", "RS"), ("ra", "RA")):
        s = c[side]
        seg = [f"{label} MAE {_f(s['mae'], 1)} runs"]
        for comp, name in (("vs_carry_forward", "carry-forward"), ("vs_league_avg", "league average")):
            cc = s.get(comp)
            if cc:
                seg.append(f"vs {name} (comparator MAE {_f(cc['comparator_mae'], 1)}) delta "
                           f"{_f(cc['bootstrap'].get('mean'), 2)} ub95 {_f(cc['bootstrap'].get('ub95'), 2, sign=True)}")
            else:
                seg.append(f"vs {name} null (no prior)")
        parts.append("; ".join(seg) + f": {s['verdict']}.")
    sw = c.get("served_wins_same_clubs") or {}
    parts.append(f"Pythagenpat wins MAE {_f(c['pythag_wins']['mae'], 2)} beside served wins "
                 f"{_f(sw.get('mae'), 2)} on the same clubs (no verdict).")
    li = c.get("league_identity") or {}
    if li.get("rs_minus_ra") is not None:
        parts.append(f"League identity: sum RS minus sum RA {_f(li['rs_minus_ra'], 1)} runs (RS "
                     f"{_f(li.get('rs_minus_league'), 1)} and RA {_f(li.get('ra_minus_league'), 1)} against 30 x the "
                     f"league mean), {'within' if li.get('within_tol') else 'outside'} the 1% tolerance, reported "
                     f"and not corrected (gate section 7).")
    ok = block["flags_eligible"].get("TEAM_RUNS_LIVE")
    parts.append("RS, RA and run differential serve together only if both sides pass (gate 3.3): TEAM_RUNS_LIVE "
                 + ("eligible (the flip is its own commit)." if ok else "not eligible; nothing served moves."))
    return " ".join(parts)


def note_tm_b(block: dict) -> str:
    b, boot = block["tm_b"], block["tm_b"]["bootstrap"]
    return (f"{_marker(block, ', TM-B')}: the one GATE read of the T2 club PA and IP budget "
            f"({_f(b['budget']['pa'], 1)} PA, {_f(b['budget']['ip'], 1)} IP per 162) against served_recentered on the "
            f"{block['season']} club season ({boot.get('n')} clubs; {_early(block)}), the retro "
            f"design's point-in-time projection (inputs through {block['season'] - 1}), paired abs-error bootstrap B "
            f"{block['bootstrap']['B']} seed {block['bootstrap']['seed']}: budgeted wins MAE {_f(b['budgeted']['mae'])} "
            f"(bias {_f(b['budgeted']['bias'], sign=True)}, r {_f(b['budgeted']['r'])}) against served "
            f"{_f(b['served_recentered']['mae'])} (bias {_f(b['served_recentered']['bias'], sign=True)}, r "
            f"{_f(b['served_recentered']['r'])}); delta {_f(boot.get('mean'))}, ub95 {_f(boot.get('ub95'), sign=True)}: "
            f"{b['verdict']}"
            f"{' by the registered rule (ub95 at or above 0); the registered expectation was unresolvable (A13)' if b['verdict'] == 'FAIL' else ''}. "
            f"{b['clubs_over_budget']['pa']} clubs over the PA budget, {b['clubs_over_budget']['ip']} over the IP "
            f"budget. TEAM_PT_BUDGET_LIVE "
            f"{'eligible (the flip is its own commit on TM-Q1)' if block['flags_eligible'].get('TEAM_PT_BUDGET_LIVE') else 'not eligible; the served roll-up stays'}. "
            f"The served_recentered MAE here scores the retro design on a completed season, not the served export's "
            f"forward_gate (that frame is the Opening Day 2027 freeze).")


def summary_tm_a(block: dict) -> str:
    a, b = block["tm_a"], block["tm_a"]["bootstrap"]
    return (f"Read once on {block['season']}, not served: TM-A {a['verdict']}, candidate CRPS "
            f"{_f(a['candidate']['crps_mean'])} vs incumbent {_f(a['incumbent']['crps_mean'])}, delta "
            f"{_f(b.get('mean'))}, ub95 {_f(b.get('ub95'), sign=True)}; coverage "
            f"{_f(a['candidate']['coverage80'].get('rate'))} vs {_f(a['incumbent']['coverage80'].get('rate'))}.")


def summary_tm_c(block: dict) -> str:
    c = block["tm_c"]
    return (f"Read once on {block['season']}, not served: TM-C RS {c['rs']['verdict']} (MAE {_f(c['rs']['mae'], 1)}), "
            f"RA {c['ra']['verdict']} (MAE {_f(c['ra']['mae'], 1)}); Pythag wins MAE "
            f"{_f(c['pythag_wins']['mae'], 2)}.")


def _row_span(raw: bytes, row_id: str) -> tuple[int, int, bytes]:
    """(start, end, indent) of one row's bytes: the '{' that opens it through
    the '}' that closes it, so every other byte of the file stays as it is."""
    m = re.search(rb"\r?\n(\s*)\{\r?\n\s*\"model_id\": \"" + row_id.encode() + rb"\",", raw)
    if m is None:
        raise SystemExit(f"registry carries no {row_id} row")
    i = raw.index(b"{", m.start())
    depth, j, in_str, esc = 0, i, False, False
    while True:
        c = raw[j:j + 1]
        if in_str:
            if esc:
                esc = False
            elif c == b"\\":
                esc = True
            elif c == b'"':
                in_str = False
        elif c == b'"':
            in_str = True
        elif c == b"{":
            depth += 1
        elif c == b"}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return i, j + 1, m.group(1)


def _write_row(raw: bytes, row_id: str, update) -> tuple[bytes, bool]:
    """Apply ``update(row) -> bool`` (True when it changed the row) and splice
    the row back with the file's own endings and indent."""
    crlf = b"\r\n" in raw
    i, j, indent = _row_span(raw, row_id)
    row = json.loads(raw[i:j].decode("utf-8"))
    assert row.get("model_id") == row_id
    if not update(row):
        return raw, False
    nl = "\r\n" if crlf else "\n"
    lines = json.dumps(row, indent=1, ensure_ascii=False).split("\n")
    pad = indent.decode("utf-8")
    text = lines[0] + nl + nl.join(pad + ln for ln in lines[1:])
    return raw[:i] + text.encode("utf-8") + raw[j:], True


def plan(block: dict) -> list[tuple[str, dict]]:
    """[(row_id, fields)]: the fields each row takes, every number from the block."""
    status = f"read once: the GATE look of {block['look_date']} (gate section 4.1); no flip"
    return [
        ("team_win_distribution", {"eval_artifact": ART_REL, "verdict": "provisional",
                                   "registration_status": status, "summary": summary_tm_a(block),
                                   "note": note_tm_a(block), "marker": _marker(block)}),
        ("team_run_projection", {"eval_artifact": ART_REL, "verdict": "provisional",
                                 "registration_status": status, "summary": summary_tm_c(block),
                                 "note": note_tm_c(block), "marker": _marker(block)}),
        ("team_win_projections", {"note": note_tm_b(block), "marker": _marker(block, ", TM-B")}),
    ]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--artifact", type=Path, default=ART_DEFAULT)
    ap.add_argument("--dry-run", action="store_true", help="print the rows' new fields; write nothing")
    args = ap.parse_args(argv)
    if not args.artifact.exists():
        print(f"{args.artifact} missing; nothing written")
        return 1
    art = json.loads(args.artifact.read_text(encoding="utf-8"))
    block = (art.get("team_projection_gate") or {}).get("gate_2026")
    if not block:
        print("the artifact carries no team_projection_gate.gate_2026 block; nothing written")
        return 1
    for k in ("tm_a", "tm_b", "tm_c", "verdicts", "flags_eligible", "look_date"):
        if k not in block:
            print(f"the gate block carries no {k}; nothing written")
            return 1
    raw = REG.read_bytes()
    changed_rows = []
    for row_id, fields in plan(block):
        if args.dry_run:
            print(f"--- {row_id}")
            for k, v in fields.items():
                print(f"{k}: {v}")
            if "summary" in fields:
                assert len(fields["summary"].split()) <= 30, fields["summary"]
            continue

        def update(row, fields=fields):
            if fields["marker"] in (row.get("notes") or ""):
                return False
            for k in ("eval_artifact", "verdict", "registration_status", "summary"):
                if k in fields:
                    row[k] = fields[k]
            if "summary" in fields:
                assert len(row["summary"].split()) <= 30, row["summary"]
            row["notes"] = (row.get("notes") or "").rstrip() + " " + fields["note"]
            return True

        raw, changed = _write_row(raw, row_id, update)
        if changed:
            changed_rows.append(row_id)
    if args.dry_run:
        return 0
    if not changed_rows:
        print("registry already carries the look notes; nothing written")
        return 0
    REG.write_bytes(raw)
    print(f"registry written: {', '.join(changed_rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
