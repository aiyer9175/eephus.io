# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""One-time backfill of data/efv_progress.json from git history (EV-00,
docs/efv-v2/PROGRAM.md s5.1 item 4). Run ONCE, committed once.

It walks every committed version of the head-to-head verdict and emits a
`backfill` row wherever a version carries one, dated by its commit. A version
without a verdict yields no row, and every backfilled `ci95` is null: an
interval is not recomputable from a committed number, and this layer computes
nothing.

TWO PATHS ARE WALKED, AND WHY. The program names data/source_backtest.json,
but that file is gitignored (.gitignore, "Source-vs-source backtest output")
and has never been committed, so its history is empty. The verdict it writes,
accuracy.head_to_head_verdict, is copied VERBATIM into the tracked
data/xfv_scoreboard_eval.json as head_to_head.verdict_vs_consensus, so that
file's history is the committed record of the same numbers. Both walks run
and both are reported; per-source rater values are taken from a scoreboard
version only when its `vs` block sits on the verdict's own frame (vs_frame
matches), because the older versions scored the sources on a different frame.

A historical version whose verdict equals the live one (same basis, n and both
Spearman values) is skipped: the live row, written by efv_progress.update,
carries the same numbers plus the interval.

Run:  python tools/efv_progress_backfill.py [--force]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import efv_progress as P  # noqa: E402

SB_PATH = "data/source_backtest.json"
SC_PATH = "data/xfv_scoreboard_eval.json"


def _git(*args: str) -> str:
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                         text=True, encoding="utf-8", check=False)
    return out.stdout if out.returncode == 0 else ""


def versions(path: str) -> list[tuple[str, str]]:
    """[(commit sha, commit date YYYY-MM-DD)] oldest first."""
    rows = []
    for ln in _git("log", "--format=%H %cs", "--", path).splitlines():
        parts = ln.split()
        if len(parts) == 2:
            rows.append((parts[0], parts[1]))
    return list(reversed(rows))


def show(sha: str, path: str):
    txt = _git("show", f"{sha}:./{path}")
    if not txt:
        return None
    try:
        return json.loads(txt)
    except ValueError:
        return None


def _verdict_of(doc: dict, path: str) -> tuple[dict | None, dict]:
    """(verdict, context) for one committed version of either artifact."""
    if path == SB_PATH:
        acc = (doc or {}).get("accuracy") or {}
        return acc.get("head_to_head_verdict"), {"sb": doc}
    h2h = (doc or {}).get("head_to_head") or {}
    return h2h.get("verdict_vs_consensus"), {"sc": doc}


def _frame_of(basis: str | None) -> str | None:
    if not basis:
        return None
    if basis in P.BASIS_TO_FRAME:
        return P.BASIS_TO_FRAME[basis]
    # The 2026-08-07 scoreboard wrote "pooled_efv_common (identical rows)".
    head = basis.split(" ")[0]
    return P.BASIS_TO_FRAME.get(head)


def row_from_version(doc: dict, path: str, sha: str, day: str) -> dict | None:
    """One backfill row, or None when the version carries no verdict."""
    hv, ctx = _verdict_of(doc, path)
    if not hv or hv.get("delta") is None:
        return None
    frame = _frame_of(hv.get("basis"))
    if frame is None:
        return None
    meta = P.FRAMES[frame]
    raters = {"efv": {"spearman": hv.get("xfv_spearman"), "auc": None, "n": hv.get("n")},
              "prospx_consensus": {"spearman": hv.get("consensus_spearman"),
                                   "auc": None, "n": hv.get("n")}}
    deltas = {"vs_prospx_consensus": {"spearman": {
        "delta": hv.get("delta"), "ci95": None, "mde95": hv.get("mde95"),
        "mde95_estimator": "E_refit", "ci95_estimator": None,
        "resolvable": hv.get("resolvable"),
        "key": ("accuracy.head_to_head_verdict" if path == SB_PATH
                else "head_to_head.verdict_vs_consensus")}}}
    gen = None
    if path == SC_PATH:
        sc = ctx["sc"]
        h2h = sc.get("head_to_head") or {}
        gen = ((sc.get("source_backtest_freshness") or {}).get("artifact_generated_at")
               or sc.get("generated_at"))
        on_frame = (h2h.get("vs_frame") == P.BY_FRAME_KEY.get(frame))
        if on_frame:
            for src, cell in (h2h.get("vs") or {}).items():
                sp, au = cell.get("spearman") or {}, cell.get("auc_contributor") or {}
                if sp.get("n") != hv.get("n"):
                    continue
                raters[src] = {"spearman": sp.get("consensus"), "auc": au.get("consensus"),
                                "n": sp.get("n")}
                raters["efv"]["auc"] = au.get("efv", raters["efv"]["auc"])
                if src == "prospx_consensus":
                    continue
                deltas[f"vs_{src}"] = {
                    "spearman": {"delta": sp.get("margin"), "ci95": None, "mde95": None,
                                 "key": f"head_to_head.vs.{src}.spearman.margin"},
                    "auc": {"delta": au.get("margin"), "ci95": None, "mde95": None,
                            "key": f"head_to_head.vs.{src}.auc_contributor.margin"}}
    else:
        gen = ctx["sb"].get("generated_at")
    row = {"run_id": None, "date": day, "trigger": "backfill",
           "model_id": P.MODEL_ID,
           "model_version": {"fingerprint": None, "commit": sha[:8], "label": None,
                             "resolved_through": None},
           "frame": frame, "frame_version": P.DEFAULT_FRAME_VERSION.get(frame),
           "role": meta["role"], "tilted": bool(meta["tilted"]),
           "window": None, "n": hv.get("n"), "n_by_side": None,
           "raters": raters, "deltas": deltas,
           "resolvable": hv.get("resolvable"), "verdict": hv.get("verdict"),
           "share": None,
           "sources": [{"path": path, "commit": sha[:8], "generated_at": gen,
                        "sha256": None}],
           "note": ((hv.get("basis_note")
                     or f"published as the headline basis on {day}; classified as "
                        "tilted by docs/efv-2026-08-13/HEADTOHEAD_FRAME_GATE.md")
                    if meta["tilted"] else ""),
           "last_verified_at": None}
    row["content_hash"] = P.content_hash(row)
    row["run_id"] = f"{gen or day}|{frame}|{row['content_hash'][:8]}"
    return row


def _same_numbers(a: dict, live: dict | None) -> bool:
    if not live:
        return False
    return (a.get("basis", "").split(" ")[0] == live.get("basis")
            and a.get("n") == live.get("n")
            and a.get("xfv_spearman") == live.get("xfv_spearman")
            and a.get("consensus_spearman") == live.get("consensus_spearman"))


def build(live_verdict: dict | None) -> tuple[list[dict], dict]:
    rows, receipt = [], {"paths": {}, "skipped_as_live": []}
    for path in (SB_PATH, SC_PATH):
        vers = versions(path)
        n_rows, n_none = 0, 0
        for sha, day in vers:
            doc = show(sha, path)
            hv, _ = _verdict_of(doc or {}, path)
            if hv and _same_numbers(hv, live_verdict):
                receipt["skipped_as_live"].append(f"{path}@{sha[:8]}")
                continue
            r = row_from_version(doc or {}, path, sha, day)
            if r is None:
                n_none += 1
                continue
            rows.append(r)
            n_rows += 1
        note = ""
        if not vers:
            note = ("no committed versions: the file is gitignored and has never "
                    "been committed")
        receipt["paths"][path] = {"versions": len(vers), "rows": n_rows,
                                  "versions_without_verdict": n_none, "note": note}
    rows.sort(key=lambda r: r["date"])
    return rows, receipt


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--force", action="store_true",
                    help="run even though backfill rows already exist")
    args = ap.parse_args(argv)
    prev = P.load() or {}
    if any(r.get("trigger") == "backfill" for r in prev.get("rows") or []) and not args.force:
        print("backfill rows already present; this tool runs once (use --force)")
        return 1
    sb = P._load_json(P.DATA_DIR / P.SB_NAME) or {}
    live = (sb.get("accuracy") or {}).get("head_to_head_verdict")
    rows, receipt = build(live)
    receipt["ran_at"] = P._now_iso()
    receipt["rows_emitted"] = len(rows)
    res = P.commit_rows(rows, sb=sb or None, backfill_receipt=receipt)
    print(json.dumps(receipt, indent=1))
    print(f"appended {len(res['appended'])} row(s); {res['n_rows']} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
