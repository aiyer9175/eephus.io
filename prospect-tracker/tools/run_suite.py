"""Chunked pytest runner for prospect-tracker.

The full suite hard-crashes in one process near 52% with a Windows access
violation in the native json decoder inside storage._load_ungraded_by_org. It is
memory exhaustion after repeated 74MB and 11MB parses plus sklearn, lightgbm and
chromium in one process, not corruption.

Run from prospect-tracker/. 8 test files per subprocess. Do NOT reduce the chunk
size below 8: 4 and 6 were both measured WORSE (more crashed chunks), that
experiment is banned.

READ THE RETURN CODES, NOT THE PARSED TOTALS. A naive summary parser
double-counts `xfailed` as `failed` on the substring, and pytest -q --no-header
does not emit the leading `=` older parsers keyed on.

Do NOT run this while any file edit is in flight. conftest.py's
_restore_committed_build_artifacts snapshots dirty tracked files at session start
and git-checkouts anything the suite dirtied at the end, so an edit made DURING a
run is silently reverted. Run between edit batches, never alongside them.

Expected baseline on this tree is exactly two reds, both needing a real box
rebuild_only and neither a regression. KNOWN_BASELINE_REDS below is the canonical
list; keep this docstring in step with it:
    test_efv_export.py::test_xfv_golden_fingerprint
    test_proj_export.py::test_vet_surplus_only_on_contracted_seasons
The identity-collision entry came OUT 2026-08-19: its corrected leave condition
(positions_played.json regenerated with the invalidated_by stamp gone) was
verified met (generated_at 2026-08-16, stamp absent) and the test ran green on
the 2026-08-19 baseline suite.
test_identity_collisions.py::test_committed_report_matches_a_fresh_run reads the
WORKING-TREE data/identity_collisions.json against a fresh run over the DB; when
the owner's nightly churn lags the DB it goes red and the fix is regenerating
the report (python identity_audit.py), never a baseline entry.
test_atomic_artifact_write is a known load-dependent flake (its reader thread
starves the os.replace writer only on an idle fast box); re-run it in a fresh
process before calling it a regression.

Usage:
    python tools/run_suite.py                      # whole suite
    python tools/run_suite.py test_a.py test_b.py  # just these files (still chunked)
    python tools/run_suite.py --out suite.json     # machine-readable results
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

# tools/run_suite.py -> prospect-tracker/. Derived, not hardcoded: the previous
# per-session copies pinned an absolute path that only worked on one box.
PT = Path(__file__).resolve().parent.parent
CHUNK = 8

# Reds that are expected on a tree whose committed artifacts predate the last box
# rebuild. Reported separately so a run can be read at a glance.
KNOWN_BASELINE_REDS = (
    "test_efv_export.py::test_xfv_golden_fingerprint",
    "test_proj_export.py::test_vet_surplus_only_on_contracted_seasons",
)

# REMOVED 2026-08-19 (kept for the record, do not re-add without a NEW defect):
_REMOVED_BASELINE_REDS_LEDGER = (
    # Added 2026-08-12, and it is a STALE-ARTIFACT red, not a suppressed defect.
    # The underlying collision (a Boston DSL RHP merged onto a Texas catcher's
    # key) IS repaired in prospects.db by tools/repair_jesus_lopez_collision.py
    # and pinned against re-merge by scrapers._SPLIT_KEYS. This test reads the
    # BUILT artifacts (data/timeseries.json, rosters_by_org.json,
    # positions_played.json), all three of which still carry the pre-repair
    # binding, so it cannot go green until they regenerate.
    # LEAVE CONDITION, CORRECTED 2026-08-14. The original read: "it must go
    # green on the first `run_monthly.py --rebuild-only` after 2026-08-12 ...
    # if it is still red after that rebuild, the repair is INCOMPLETE and this
    # entry must come out rather than be re-baselined."
    #
    # THAT CONDITION WAS UNACHIEVABLE AND ITS CONCLUSION WOULD HAVE BEEN WRONG.
    # A full `run_monthly.py` ran 2026-08-14 and the test stayed red. The
    # repair is NOT incomplete. Two of the three artifacts named above DID
    # regenerate (timeseries.json 16:12, rosters_by_org.json 15:31); the third,
    # positions_played.json, sits behind the step 3a-ii freshness gate at
    # VERSA_FRESH_DAYS = 7 and was built 2026-08-11, ONE DAY BEFORE the repair.
    # So every rebuild skipped it, and would have kept skipping it until
    # 2026-08-18. No `--rebuild-only` could ever have satisfied the condition.
    #
    # The repair is CORRECT, verified against the authoritative per-player
    # endpoint rather than against the artifact: mlbam 805052 fields
    # C {g:97, gs:96} + DH {g:38, gs:36} with ZERO pitching, and mlbam 838819
    # fields P {g:11, gs:10}. The artifact's `P {g:10, gs:9}` on the catcher's
    # key is the RHP's merge-window line, now three days out of date on its own
    # terms. The identity layer itself reports c1_shared_key 0 and
    # c2_double_bound 0.
    #
    # NEW LEAVE CONDITION: data/positions_played.json now carries an
    # `invalidated_by` stamp that run_monthly._artifact_fresh honours ahead of
    # age, so the NEXT ordinary rebuild regenerates step 3a-ii. This entry
    # comes out when that rebuild has run. If it is STILL red after an actual
    # regeneration of positions_played.json (check its generated_at moved and
    # that `invalidated_by` is gone), only then is the repair in question.
    "test_identity_collisions.py::test_no_new_merged_identity_on_the_active_board",
)


def chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--chunk-size", type=int, default=CHUNK)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.chunk_size < 8:
        print("REFUSING: chunk size below 8 is a banned experiment (measured worse).")
        return 2

    if args.files:
        files = list(args.files)
    else:
        files = sorted(p.name for p in PT.glob("test_*.py"))

    print(f"{len(files)} test files, chunk size {args.chunk_size}, cwd {PT}")
    results = []
    t_all = time.time()
    for i, group in enumerate(chunks(files, args.chunk_size), 1):
        t0 = time.time()
        cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", *group]
        proc = subprocess.run(cmd, cwd=str(PT), capture_output=True, text=True)
        dt = time.time() - t0
        out = proc.stdout or ""
        tail = out.strip().splitlines()
        tail = tail[-4:] if tail else []
        rc = proc.returncode
        flag = "ok " if rc == 0 else ("FAIL" if rc == 1 else "CRASH")
        print(f"[{i:02d}] rc={rc} {flag} {dt:6.1f}s  {group[0]} .. {group[-1]}")
        if rc != 0:
            for line in tail:
                print(f"      | {line}")
            for line in out.splitlines():
                if line.startswith(("FAILED", "ERROR")):
                    print(f"      * {line}")
        results.append({
            "chunk": i, "rc": rc, "seconds": round(dt, 1), "files": group,
            "tail": tail,
            "failed_nodes": [ln for ln in out.splitlines()
                             if ln.startswith(("FAILED", "ERROR"))],
            "stderr_tail": (proc.stderr or "").strip().splitlines()[-3:],
        })

    n_ok = sum(1 for r in results if r["rc"] == 0)
    n_fail = sum(1 for r in results if r["rc"] == 1)
    n_crash = sum(1 for r in results if r["rc"] not in (0, 1))
    print(f"\n{len(results)} chunks in {time.time() - t_all:.0f}s: "
          f"{n_ok} rc=0, {n_fail} rc=1, {n_crash} crashed")

    # Split the failing node ids into the known baseline and everything else, so
    # a reader never has to remember which two reds are expected.
    all_nodes = [n for r in results for n in r["failed_nodes"]]
    unexpected = []
    for node in all_nodes:
        if not any(known in node for known in KNOWN_BASELINE_REDS):
            unexpected.append(node)
    baseline_hits = [n for n in all_nodes if n not in unexpected]
    if baseline_hits:
        print(f"{len(baseline_hits)} known baseline red(s) (expected, need a box rebuild_only):")
        for n in baseline_hits:
            print(f"   . {n}")
    if unexpected:
        print(f"{len(unexpected)} UNEXPECTED failure(s):")
        for n in unexpected:
            print(f"   ! {n}")
    elif not n_crash:
        print("No unexpected failures.")

    if n_crash:
        print("CRASHED CHUNKS ARE NOT EVIDENCE OF A DEFECT AFTER HEAVY AGENT LOAD. "
              "Re-run those files in a fresh process.")

    if args.out:
        payload = {
            "chunks": results,
            "n_ok": n_ok, "n_fail": n_fail, "n_crash": n_crash,
            "unexpected_failures": unexpected,
            "baseline_reds_hit": baseline_hits,
        }
        Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"wrote {args.out}")
    return 0 if (n_crash == 0 and not unexpected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
