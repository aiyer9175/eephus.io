# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Record the prospect stat-line look (TL_17_STATLINE_LOOK, one look on holdout H) on
its registry row (idempotent; docs/proj-prospect-2026-10/PROSPECT_STATLINE_GATE.md
Parts 5, 6, 12 and 13).

Reads data/prospect_statline_eval.json, points the mlb_projections_prospects_statline
row's eval_artifact at it and moves the verdict to provisional: L1 stats that PASS are
eligible for TL_18_STATLINE_DISPLAY_FLIP behind SERVE_PROSPECT_STATLINE (default
False), nothing is served by this row's change. Appends one dated note with the
numbers read from the artifact and stamps freshness. Splices only that row and keeps
the file's line endings and indent. Running it twice changes nothing. Then
regenerate MODEL_REGISTRY.md:

    python tools/register_prospect_statline_look.py
    python tools/gen_audit_docs.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "model_registry.json"
ART = ROOT / "data" / "prospect_statline_eval.json"
ROW = "mlb_projections_prospects_statline"
READ_DATE = "2026-10-21"
READ_KIND = "OWNER-WAIVED EARLY READ"
STAT_NAMES = {"k_pct": "K%", "bb_pct": "BB%", "iso": "ISO", "avg": "AVG", "babip": "BABIP",
              "woba": "wOBA", "xwoba": "xwOBA", "hr_bf": "HR per BF"}
SIDE_NAMES = {"hit": "hitter", "pit": "pitcher"}


def _s(v, nd=5):
    return "n/a" if v is None else f"{float(v):+.{nd}f}"


def _n(v, nd=4):
    return "n/a" if v is None else f"{float(v):.{nd}f}"


def passes(res: dict) -> list[tuple[str, str]]:
    return [(side, stat) for side in ("hit", "pit") for stat, e in res["l1"][side].items()
            if e.get("verdict") == "PASS"]


def note_text(art: dict) -> str:
    res = art["results"]
    l2 = res["l2"]
    marker = f"LOOK {READ_DATE} (TL_17_STATLINE_LOOK)"
    parts = [f"{marker}: the one look on holdout H (debut cohorts 2022 to 2024, fit once on 2016 to "
             f"2021), run once, an {READ_KIND} (owner EW3-5), gate sha {art['gate_sha'][:8]}, freeze "
             f"{art['freeze_sha'][:8]}, amendment 2 {art['amendment2_sha'][:8]}; {res['n_scored_rows']} "
             f"scored rows. L1 (exposure-weighted MAE, d = best baseline minus model, lb95 from B 2000 "
             f"player-clustered draws, Holm within side, coverage band 0.75 to 0.85):"]
    for side in ("hit", "pit"):
        for stat, e in res["l1"][side].items():
            name = f"{SIDE_NAMES[side]} {STAT_NAMES.get(stat, stat)}"
            if e.get("verdict") == "NOT COMPUTABLE":
                parts.append(f"{name} n {e.get('n')} NOT COMPUTABLE;")
                continue
            parts.append(f"{name} n {e['n']} model {_n(e['mae_model'], 5)} vs {e['best_baseline']} "
                         f"{_n(e['mae_best_baseline'], 5)}, d {_s(e['d'])}, lb95 {_s(e['d_lb95'])}, "
                         f"coverage {_n(e['coverage_p10_p90'], 3)}, {e['verdict']};")
    parts.append(f"L2 first-three-season fWAR against INC (the served FV-anchored path), n {l2['n']}: MAE "
                 f"model {_n(l2['mae_model'])} vs INC {_n(l2['mae_inc'])} (lb95 of d {_s(l2['d_mae_lb95'], 4)}), "
                 f"within Spearman {_n(l2['rho_model'])} vs {_n(l2['rho_inc'])} (lb95 of d "
                 f"{_s(l2['d_rho_lb95'], 4)}), slope {l2['slope_model']} vs {l2['slope_inc']}; "
                 f"{l2['verdict']}.")
    ps = passes(res)
    parts.append("Part 12: " + (", ".join(f"{SIDE_NAMES[s]} {STAT_NAMES[t]}" for s, t in ps)
                                + " eligible for TL_18 behind SERVE_PROSPECT_STATLINE (default False)"
                                if ps else "no stat passed, nothing served")
                 + "; the WAR cell stays the FV-anchored number. Artifact sha256 recorded in the gate's "
                   "Part 13 entry. " + art["survivorship"])
    return " ".join(parts)


def _row_span(raw: bytes) -> tuple[int, int, bytes]:
    """(start, end, indent) of the row's object, so every other byte stays as it is."""
    m = re.search(rb"\r?\n(\s*)\{\r?\n\s*\"model_id\": \"" + ROW.encode() + rb"\",", raw)
    if m is None:
        raise SystemExit(f"registry carries no {ROW} row")
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


def main() -> int:
    raw = REG.read_bytes()
    crlf = b"\r\n" in raw
    i, j, indent = _row_span(raw)
    row = json.loads(raw[i:j].decode("utf-8"))
    assert row.get("model_id") == ROW
    if not ART.exists():
        print(f"{ART} missing; nothing written")
        return 1
    art = json.loads(ART.read_text(encoding="utf-8"))
    if art.get("role") != "look" or not art.get("spent") or art.get("crashed"):
        print("the artifact carries no completed look record; nothing written")
        return 1
    note = note_text(art)
    marker = note.split(":")[0]
    if marker in (row.get("notes") or ""):
        print("registry already carries the look note; nothing written")
        return 0
    res = art["results"]
    l1h = res["l1"]["hit"]
    ps = passes(res)
    names = " and ".join(STAT_NAMES[t] for _s_, t in ps)
    row["eval_artifact"] = "data/prospect_statline_eval.json"
    row["verdict"] = "provisional"
    row.pop("provisional_kind", None)
    row["registration_status"] = (f"read once: the owner-waived early read of {READ_DATE} (gate Part 13); "
                                  + (f"hitter {names} eligible for TL_18, not served" if ps
                                     else "no stat passed, nothing served"))
    if ps and all(s == "hit" for s, _t in ps):
        n_hit = max(l1h[t]["n"] for _s2, t in ps)
        row["summary"] = (f"Read once {READ_DATE} on holdout H: hitter {names} beat their best baselines "
                          f"(n {n_hit}); ten rates NULL; WAR loses to the FV-anchored path (n {res['l2']['n']}).")
    else:
        row["summary"] = (f"Read once {READ_DATE} on holdout H: "
                          + (f"{len(ps)} rates pass" if ps else "no rate passes")
                          + f"; WAR {res['l2']['verdict']} (n {res['l2']['n']}).")
    row["champion"] = ("none served. Eligible after the one look: "
                       + (f"hitter {names} (L1 PASS) behind SERVE_PROSPECT_STATLINE, default False, "
                          "served only by TL_18's flip" if ps else "nothing")
                       + "; L2 " + res["l2"]["verdict"] + ". The candidate: per stat and side a stacked "
                       "ridge (level 0: TIP_first and TIP_now from tool_implied tables fit inside each fold, "
                       "the milb_translation estimator refit per fold, level-relative ISO and BABIP, "
                       "efv_proxy's estimator refit backward per fold, the aging v2 component delta to 27; "
                       "level 1: a weighted ridge with an intercept and missing indicators, penalty by nested "
                       "forward-chained CV on 10 ** k, k = -3 to 3 by 0.5, ties to the larger penalty); P10 "
                       "to P90 from the inner chain's out-of-fold residuals")
    row["metric"] = re.sub(r"^Registered, not computed on the holdout:", "Read once on holdout H "
                           f"({READ_DATE}):", row.get("metric") or "")
    assert len(row["summary"].split()) <= 30, row["summary"]
    row["notes"] = (row.get("notes") or "").rstrip() + "\n" + note
    gen = datetime.strptime(art["generated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    row["last_checked"] = READ_DATE
    row["stale"] = False
    row["artifact_age_days"] = max(0, (datetime(2026, 10, 22, tzinfo=timezone.utc) - gen).days)
    nl = "\r\n" if crlf else "\n"
    lines = json.dumps(row, indent=1, ensure_ascii=False).split("\n")
    pad = indent.decode("utf-8")
    text = lines[0] + nl + nl.join(pad + ln for ln in lines[1:])
    REG.write_bytes(raw[:i] + text.encode("utf-8") + raw[j:])
    print(f"registry written: {ROW} -> {row['verdict']}, eval_artifact {row['eval_artifact']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
