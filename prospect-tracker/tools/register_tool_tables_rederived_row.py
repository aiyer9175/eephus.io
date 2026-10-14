"""Register the tool_tables_rederived row in data/model_registry.json (idempotent).

Writes, once, the row docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md Part
T.9 names for TL_21_TOOL_TABLE_REDERIVE_LOOK: provisional whatever the outcome,
eval artifact data/tool_tables_rederived_eval.json (a registry eval artifact
that ships, never listed in deploy/data_exclude.txt), with one dated note
listing each primary cell's verdict and its numbers read from the artifact.
Every number in the row is copied from the artifact; nothing is computed here.
Keeps the file's line endings (CRLF) and its one-space indent. Running it twice
changes nothing. Then regenerate MODEL_REGISTRY.md:

    python tools/register_tool_tables_rederived_row.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "tool_tables_rederived_eval.json"
ROW_ID = "tool_tables_rederived"
GATE = "docs/tools-2026-10/TOOL_IMPLIED_PRODUCTION_GATE.md"

# cell key -> (reader name, unit, decimals)
CELLS = {
    "game_pwr__hr_per600": ("game power to HR per 600 PA", "HR", 4),
    "game_pwr__iso": ("game power to ISO", "", 6),
    "hit__avg": ("hit to AVG", "", 6),
    "hit__k_pct": ("hit to K%", "points", 4),
    "speed__sb_per600": ("speed to SB per 600 PA", "SB", 4),
    "cmd__bb_pct_sp": ("command to BB% (SP)", "points", 4),
    "fb__velo_sp": ("fastball to velocity (SP)", "mph", 4),
}
SHORT = {
    "game_pwr__hr_per600": "HR per 600", "game_pwr__iso": "ISO", "hit__avg": "AVG",
    "hit__k_pct": "K%", "speed__sb_per600": "SB per 600", "cmd__bb_pct_sp": "BB% (SP)",
    "fb__velo_sp": "velocity (SP)",
}
SECONDARY = {
    "raw_pwr__ev_avg": "raw power to exit velocity",
    "speed__sprint": "speed to sprint speed",
    "field__oaa_per1000": "field to OAA per 1,000 innings",
    "cmd__bb_pct_rp": "command to BB% (RP)",
    "fb__velo_rp": "fastball to velocity (RP)",
}


def _f(v, nd=4):
    return "n/a" if v is None else f"{float(v):.{nd}f}"


def _date(art: dict) -> str:
    return str(art.get("generated_at", ""))[:10]


def note_text(art: dict) -> str:
    d = _date(art)
    res = art["result"]
    sha = art.get("inputs_sha256_start") or {}
    marker = f"LOOK {d} (TL_21_TOOL_TABLE_REDERIVE_LOOK)"
    parts = [
        f"{marker}: look T of gate Part T run once, as tools/tool_accuracy_lab.py --look T --registration "
        f"{str(art.get('registration_sha', ''))[:8]} --mde {str(art.get('mde_sha', ''))[:8]}, after the fixture dry run "
        f"with None values completed; an OWNER-WAIVED EARLY READ under the owner's EW3-5 waiver of 2026-10-14 "
        f"(T.7 registers the first free day after TL_4 with T.10 on a calendar day before the look; T.10 landed "
        f"earlier on {d}, and MDE95 is copied from it, never computed in the look session). "
        f"HOLDOUT: the final 2026 regular season lines, .cache/fa_statsapi_hitting_2026.json sha256 "
        f"{sha.get('.cache/fa_statsapi_hitting_2026.json')}, .cache/fa_statsapi_pitching_2026.json sha256 "
        f"{sha.get('.cache/fa_statsapi_pitching_2026.json')}, .cache/velo_arsenal_2026.json sha256 "
        f"{sha.get('.cache/velo_arsenal_2026.json')}; frozen grade rows sha256 "
        f"{sha.get('data/_labs/tool_tables_rederived/grade_rows_frozen.json')}; every input sha256 identical at "
        f"start and end. Statistic T.5: PA- or BF-weighted MAE on the holdout rows, delta = candidate minus "
        f"incumbent, paired bootstrap over players B 2000 seed 20261028, UB95 the 95th percentile, margin "
        f"max(MDE95, 5 percent of the incumbent MAE), Holm across the 7 computable primary cells at alpha 0.05. "
        f"Verdicts read from the artifact:"
    ]
    for key, (name, unit, nd) in CELLS.items():
        c = res["primary"].get(key) or {}
        v = c.get("verdict")
        if v == "NOT COMPUTABLE":
            parts.append(f"{name} NOT COMPUTABLE ({c.get('reason')}).")
            continue
        cl = c.get("clauses") or {}
        why = []
        if not cl.get("1_ub95_below_0"):
            why.append("UB95 not below 0")
        if not cl.get("2_margin"):
            why.append("improvement short of the margin")
        if not cl.get("3_holm"):
            why.append("Holm not rejected")
        u = f" {unit}" if unit else ""
        parts.append(
            f"{name} {v} (n {c.get('n')}, MAE candidate {_f(c.get('mae_candidate'), nd)} vs incumbent "
            f"{_f(c.get('mae_incumbent'), nd)}{u}, delta {_f(c.get('delta'), nd)}, UB95 {_f(c.get('ub95'), nd)}, "
            f"p {_f(c.get('p'), 5)}, MDE95 {_f(c.get('mde95'), nd)}, margin {_f(c.get('margin_required'), nd)}, "
            f"Holm step {(c.get('holm') or {}).get('step')}"
            + ("; " + "; ".join(why) if why else "") + ")."
        )
    beside = [f"{CELLS[k][0]}: {c['beside']['source']} MAE {_f(c['beside'].get('mae'), 4)}"
              for k, c in res["primary"].items() if c.get("beside")]
    if beside:
        parts.append("Beside, no verdict: " + "; ".join(beside) + ".")
    sens = [f"{CELLS[k][0]} delta {_f((c.get('sensitivity') or {}).get('delta'), 4)} "
            f"(FIT players without a holdout row, n {(c.get('sensitivity') or {}).get('n_fit_disjoint')})"
            for k, c in res["primary"].items() if c.get("sensitivity")]
    if sens:
        parts.append("Sensitivity T.11 (b), no verdict: " + "; ".join(sens) + ".")
    sec = []
    for key, name in SECONDARY.items():
        c = res["secondary"].get(key) or {}
        if c.get("n"):
            sec.append(f"{name} n {c.get('n')} delta {_f(c.get('delta'), 4)}")
        else:
            sec.append(f"{name} NOT COMPUTABLE ({c.get('reason')})")
    parts.append("Secondary T.4, no verdict: " + "; ".join(sec)
                 + ". The real look path loads no Statcast, sprint or innings line, so the three Statcast-unit "
                   "secondary cells are NOT COMPUTABLE at this look (a lab build gap, reported only; the look "
                   "is spent and is not rerun).")
    parts.append(str(res.get("survivorship", "")).strip())
    parts.append("What T.6 licenses: a PASSING cell may print on the /scouting/ tool-tier column (TL_23) as "
                 "measured on debuted players' MLB seasons beside the FanGraphs estimate, with its n and interval; "
                 "a FAIL cell prints the FanGraphs framework estimate; copy never says our table is more accurate "
                 "for a cell that did not pass. Nothing served moves at this look: no grade, consensus weight, "
                 "eFV input or TIP table of look P or look W.")
    return " ".join(parts)


def summary_text(art: dict) -> str:
    res = art["result"]["primary"]
    passed = [SHORT[k] for k in CELLS if (res.get(k) or {}).get("verdict") == "PASS"]
    failed = [SHORT[k] for k in CELLS if (res.get(k) or {}).get("verdict") == "FAIL"]
    nc = [SHORT[k] for k in CELLS if (res.get(k) or {}).get("verdict") == "NOT COMPUTABLE"]

    def join(xs):
        return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]

    groups = []
    if passed:
        groups.append(f"{join(passed)} pass")
    if failed:
        groups.append(f"{join(failed)} fail")
    if nc:
        groups.append(f"{join(nc)} not computable")
    s = "Read once on the 2026 holdout, not served: " + "; ".join(groups) + "; nothing served moves."
    assert len(s.split()) <= 30, s
    return s


def build_row(art: dict) -> dict:
    d = _date(art)
    return {
        "model_id": ROW_ID,
        "summary": summary_text(art),
        "surface": ("None served: data/tool_tables_rederived_eval.json, the look T artifact of gate Part T; "
                    "TL_23 may print a PASSING cell on /scouting/ by T.6, and nothing on the site reads it at this commit"),
        "predicts": ("The MLB stat a tool grade implies on debuted players' seasons, one candidate table per primary cell "
                     "(game power to HR per 600 PA and ISO, hit to AVG and K%, speed to SB per 600 PA, command to BB% and "
                     "fastball to velocity for starters), fit by the TIP_mat rule on FIT seasons 2015 to 2025 without 2020 "
                     "and scored on the 2026 holdout"),
        "champion": ("none - a measurement against the published FanGraphs-framework estimates: a PASS licenses only the "
                     "/scouting/ print of T.6, a FAIL cell keeps the published estimate, and no served number reads a table"),
        "baseline": ("The published FanGraphs-framework tables read by T.1 (S3 2014 for HR per 600, AVG and velocity; Mark "
                     "Smith W2 2013 for ISO, SB and SP BB%) and, for K%, the grade-blind 2026 league line over qualified rows"),
        "metric": ("PA- or BF-weighted MAE on the 2026 holdout rows, delta candidate minus incumbent, paired bootstrap over "
                   "players (B 2000, seed 20261028) UB95, margin max(MDE95 from T.10, 5 percent of the incumbent MAE), "
                   "Holm across the computable primary cells at alpha 0.05; secondary, beside and sensitivity reads never decide"),
        "eval_artifact": "data/tool_tables_rederived_eval.json",
        "verdict": "provisional",
        "provisional_kind": "measured_not_adopted",
        "registration_status": f"read once: look T of {d} (gate Part T.12, an owner-waived early read); no served change",
        "notes": (
            f"Registered 2026-10-09 in {GATE} Part T (TL_19_TOOL_TABLE_REDERIVE_REGISTRATION, PLAN Part 9 section 9.4.8, "
            "owner message 3 of 2026-10-01). Row written by TL_21_TOOL_TABLE_REDERIVE_LOOK with the look. "
            "No FV cell is read, grouped or labelled anywhere (docs/PROSPECT_ANCHOR_GATE.md); the bins are tool grade bins; "
            "no R-LV grade point (2020, 2021) and no R-VM debut (2025 on) enters a row; no 2026 line enters a FIT row. "
            + note_text(art)
        ),
    }


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    doc = json.loads(raw.decode("utf-8"))
    rows = doc["models"]
    if any(r.get("model_id") == ROW_ID for r in rows):
        print("registry already carries the tool_tables_rederived row; nothing written")
        return 0
    if not ART.exists():
        print(f"{ART} missing; nothing written")
        return 1
    art = json.loads(ART.read_text(encoding="utf-8"))
    if art.get("look") != "T" or "result" not in art:
        print("the artifact carries no look T result; nothing written")
        return 1
    row = build_row(art)
    # insert after power_composite_v2 so the tool rows sit together
    idx = next((i for i, r in enumerate(rows) if r.get("model_id") == "power_composite_v2"), len(rows) - 1)
    rows.insert(idx + 1, row)
    text = json.dumps(doc, indent=1, ensure_ascii=False)
    if crlf:
        text = text.replace("\n", "\r\n")
    REG.write_bytes(text.encode("utf-8"))
    print("registry written: tool_tables_rederived (provisional, eval_artifact data/tool_tables_rederived_eval.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
