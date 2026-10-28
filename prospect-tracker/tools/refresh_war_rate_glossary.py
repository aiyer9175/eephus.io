# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Proprietary and confidential
"""Re-derive the six WAR-rate glossary entries' quoted figures from
data/war_rate_plus_eval.json (task EVAL_FOLLOWUPS_REFREEZE, 2026-10-28).

tools/port_red_tests_glossary_registry.py (2026-10-22) re-derived the same six entries
through a table of literal old-to-new strings, so it stopped matching the moment the
artifact was regenerated again (2244c6be9, 2026-10-26, the park-matched xHEM+ flip moved
the hit pool) and test_claims_freshness::test_glossary_numbers_match_artifacts went red on
war_pa_plus and war_pa_plus_3yr. This script matches the SHAPE of each sentence (the same
patterns the test pins) and writes the artifact's value into it, so any later regeneration
is one re-run away.

Every figure is read off the artifact (v2 convention, the pinned one): the forward rho, the
plain-WAR and unstandardized-rate baselines, the zero-information control, the pair count,
the season span, and the window-gate pair. The qualitative words beside the numbers ("it
lost", "ahead of ... paired gap floor above zero", "neither paired gap clears zero", "the
paired gap does not clear zero") are CHECKED against the artifact's gap intervals and the
script refuses to write when one no longer holds, printing the sentence to rewrite by hand:
a reading is the owner's to change, a number is not.

Idempotent: a second run rewrites nothing. Keeps the file's line endings and the glossary's
json.dumps(indent=1) layout, and refuses to write if the file no longer round-trips.

Run: python tools/refresh_war_rate_glossary.py [--check]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "data" / "glossary.json"
ARTIFACT = ROOT / "data" / "war_rate_plus_eval.json"
FIELDS = ("definition", "methodology", "formula", "example")


def _f4(x: float) -> str:
    """Four decimals with no trailing zeros past the first: the copy's own style."""
    s = f"{x:.4f}".rstrip("0")
    return s if s[-1] != "." else s + "0"


def _figures(a: dict, pool: str) -> dict:
    p = a["pools"][pool]
    v2 = p["results_by_convention"]["v2"]
    gap = v2["gap_ci_primary_minus_baseline"]
    w = p["window_gate"]["results_by_convention"]["v2"]
    return {
        "rho": v2["rho_primary"], "war_total": v2["rho_baselines"]["war_total"],
        "rate": v2["rho_baselines"]["rate"], "placebo": v2["rho_baselines"]["placebo"],
        "gap_war_total": gap["war_total"], "gap_rate": gap["rate"],
        "n": p["n_forward_pairs"], "first": p["pred_seasons"][0], "last": p["out_seasons"][-1],
        "window": w["rho_window"], "one": w["rho_one_season"],
        "gap_window": w["gap_ci_window_minus_one"], "window_n": p["window_gate"]["n_forward_pairs"],
    }


def _sub_once(entry: dict, pattern: str, repl, label: str, changed: list) -> None:
    """Apply `pattern` -> `repl` across the entry's text fields; exactly one match in all."""
    rx = re.compile(pattern)
    hits = 0
    for k in FIELDS:
        v = entry.get(k)
        if not isinstance(v, str):
            continue
        new, n = rx.subn(repl, v)
        hits += n
        if n and new != v:
            entry[k] = new
            changed.append(f"{entry['id']}: {label}")
    assert hits == 1, f"{entry['id']}: pattern for {label} matched {hits} times, expected 1"


def _clears_zero_above(g: dict) -> bool:
    return g["lo95"] > 0


def _clears_zero(g: dict) -> bool:
    return g["lo95"] > 0 or g["hi95"] < 0


def apply(doc: dict, a: dict) -> tuple[list[str], list[str]]:
    by = {e["id"]: e for e in doc["entries"]}
    changed: list[str] = []
    readings: list[str] = []
    h, s, r = _figures(a, "hit"), _figures(a, "SP"), _figures(a, "RP")

    # war_pa_plus: "and it lost" means plain season WAR beats the rate index and the
    # paired gap clears zero below; the index must still trail its best baseline.
    if not (h["war_total"] > h["rho"] and h["gap_war_total"]["hi95"] < 0):
        readings.append("war_pa_plus: 'Forward-checked out of sample, and it lost' no longer holds "
                        f"(rho {h['rho']} vs plain WAR {h['war_total']}, gap {h['gap_war_total']})")
    e = by["war_pa_plus"]
    _sub_once(e, r"(Over )\d{4}-\d{4}( \(ex-2020\) and )\d+( year-to-year pairs)",
              lambda m: f"{m.group(1)}{h['first']}-{h['last']}{m.group(2)}{h['n']}{m.group(3)}",
              "span and pairs", changed)
    _sub_once(e, r"(Spearman correlation of )0\.\d+", lambda m: f"{m.group(1)}{_f4(h['rho'])}", "rho", changed)
    _sub_once(e, r"(predicts the same thing at )0\.\d+", lambda m: f"{m.group(1)}{_f4(h['war_total'])}",
              "plain WAR baseline", changed)
    _sub_once(e, r"(control on the same pairs scores )-?0\.\d+", lambda m: f"{m.group(1)}{_f4(h['placebo'])}",
              "zero-information control", changed)

    # war_ip_plus_sp: ahead of plain WAR (gap floor above zero), level with the raw rate
    # (gap floor below zero).
    if not _clears_zero_above(s["gap_war_total"]):
        readings.append(f"war_ip_plus_sp: 'ahead of plain season WAR (..., paired gap floor above zero)' "
                        f"no longer holds (gap {s['gap_war_total']})")
    if s["gap_rate"]["lo95"] > 0:
        readings.append(f"war_ip_plus_sp: 'level with the same rate left unstandardized (..., gap floor "
                        f"below zero)' no longer holds (gap {s['gap_rate']})")
    e = by["war_ip_plus_sp"]
    _sub_once(e, r"(Over )\d{4}-\d{4}( \(ex-2020\) and )\d+( pairs)",
              lambda m: f"{m.group(1)}{s['first']}-{s['last']}{m.group(2)}{s['n']}{m.group(3)}",
              "span and pairs", changed)
    _sub_once(e, r"(Spearman correlation of )0\.\d+", lambda m: f"{m.group(1)}{_f4(s['rho'])}", "rho", changed)
    _sub_once(e, r"(plain season WAR \()0\.\d+", lambda m: f"{m.group(1)}{_f4(s['war_total'])}",
              "plain WAR baseline", changed)
    _sub_once(e, r"(unstandardized \()0\.\d+", lambda m: f"{m.group(1)}{_f4(s['rate'])}", "rate baseline", changed)
    _sub_once(e, r"(control on the same pairs scores )-?0\.\d+", lambda m: f"{m.group(1)}{_f4(s['placebo'])}",
              "zero-information control", changed)

    # war_ip_plus_rp: level with both baselines, neither paired gap clears zero.
    if _clears_zero(r["gap_war_total"]) or _clears_zero(r["gap_rate"]):
        readings.append(f"war_ip_plus_rp: 'neither paired gap clears zero' no longer holds "
                        f"(plain WAR {r['gap_war_total']}, rate {r['gap_rate']})")
    e = by["war_ip_plus_rp"]
    _sub_once(e, r"(Over )\d{4}-\d{4}( \(ex-2020\) and )\d+( pairs)",
              lambda m: f"{m.group(1)}{r['first']}-{r['last']}{m.group(2)}{r['n']}{m.group(3)}",
              "span and pairs", changed)
    _sub_once(e, r"(Spearman correlation of )0\.\d+", lambda m: f"{m.group(1)}{_f4(r['rho'])}", "rho", changed)
    _sub_once(e, r"(plain season WAR \()0\.\d+", lambda m: f"{m.group(1)}{_f4(r['war_total'])}",
              "plain WAR baseline", changed)
    _sub_once(e, r"(unstandardized \()0\.\d+", lambda m: f"{m.group(1)}{_f4(r['rate'])}", "rate baseline", changed)
    _sub_once(e, r"(control on the same pairs scores )-?0\.\d+", lambda m: f"{m.group(1)}{_f4(r['placebo'])}",
              "zero-information control", changed)

    # The three-year companions quote the window gate: window rho against the one-season
    # rho on the same players. hit says the gap floor is above zero; SP and RP say it does
    # not clear zero.
    if not _clears_zero_above(h["gap_window"]):
        readings.append(f"war_pa_plus_3yr: 'gap confidence floor above zero' no longer holds ({h['gap_window']})")
    if _clears_zero(s["gap_window"]):
        readings.append(f"war_ip_plus_sp_3yr: 'the paired gap does not clear zero' no longer holds ({s['gap_window']})")
    if _clears_zero(r["gap_window"]):
        readings.append(f"war_ip_plus_rp_3yr: 'the paired gap does not clear zero' no longer holds ({r['gap_window']})")
    for gid, fig in (("war_pa_plus_3yr", h), ("war_ip_plus_sp_3yr", s), ("war_ip_plus_rp_3yr", r)):
        e = by[gid]
        _sub_once(e, r"(over )\d+( pairs the three-year read)",
                  lambda m, fig=fig: f"{m.group(1)}{fig['window_n']}{m.group(2)}", "window pairs", changed)
        _sub_once(e, r"(Spearman correlation of )0\.\d+( against )0\.\d+( for one season)",
                  lambda m, fig=fig: f"{m.group(1)}{_f4(fig['window'])}{m.group(2)}{_f4(fig['one'])}{m.group(3)}",
                  "window rho against one season", changed)
    return changed, readings


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    raw = GLOSSARY.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    doc = json.loads(text)
    assert json.dumps(doc, ensure_ascii=False, indent=1) + "\n" == text, \
        "data/glossary.json no longer round-trips through json.dumps(indent=1); not rewriting it"
    a = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    changed, readings = apply(doc, a)
    for line in changed:
        print("derived", line)
    if readings:
        for line in readings:
            print("OWNER QUESTION (reading no longer holds):", line)
        print("not writing: a qualitative reading beside the numbers no longer matches the artifact")
        return 2
    out = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    if crlf:
        out = out.replace("\n", "\r\n")
    differs = out.encode("utf-8") != raw.encode("utf-8")
    if differs and not check:
        GLOSSARY.write_bytes(out.encode("utf-8"))
    print(("would change" if check else "changed") if differs else "unchanged", GLOSSARY.name,
          f"({a.get('generated_at')}, provider {a.get('war_provider')})")
    return 1 if (check and differs) else 0


if __name__ == "__main__":
    raise SystemExit(main())
