"""Build the tools/ reference graph and emit a dead-tool candidate list.

A tool is KEPT when either
  (a) its module stem is named by any file OUTSIDE tools/ (direct reference), or
  (b) it is named by another tool that is itself kept (transitive pin), computed
      to a fixed point, or
  (c) it is on the hand-maintained KNOWN_LIVE allowlist (tools the reference graph
      cannot see, e.g. invoked by subprocess with a constructed path).

Everything else is a delete CANDIDATE.

One deliberate exception to (a): a purge PLAN that enumerates its own delete
targets would otherwise immunise every stem it names. Files listed in PLAN_DOCS
are therefore excluded from the direct-reference corpus, and any stem whose only
outside citer was a plan doc is reported under "cited_by_plan_doc_only" so the
call stays visible rather than silent. Pass --count-plan-docs to disable.

Each kept tool carries the STRONGEST reason it was kept, so a lab pinned by
data/model_registry.json (the standing "every model gets a registry row" rule)
is distinguishable from one mentioned once in a narrative doc.

Matching is token-exact, not substring: every scanned file is split into
identifier-like tokens ([A-Za-z_][A-Za-z0-9_]*) and intersected with the stem
set. A path such as "tools/foo_bar.py" tokenises to {tools, foo_bar, py}, so a
stem is matched whether it is cited as an import, a path, or bare prose. The
failure direction is deliberately conservative: a stem that collides with a
common English word (storage, config, gate) will look referenced and be kept.

Usage:
    python tools/dead_code_scan.py [--out PATH]

Read-only. Deletes nothing; it only writes the JSON report.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

# Directories never scanned as reference sources.
PRUNE_DIRS = {
    ".git", ".cache", "__pycache__", "node_modules", ".pytest_cache",
    ".ruff_cache", ".venv", "venv", ".mypy_cache",
}

# Extensions scanned for references. Wider than strictly needed on purpose:
# an extra hit only ever KEEPS a tool.
SCAN_EXTS = {
    ".py", ".sh", ".md", ".yaml", ".yml", ".txt", ".json", ".toml",
    ".cfg", ".ini", ".bat", ".ps1", ".js", ".html", ".css",
}

# Files above this size are skipped and reported; the big ones in this repo are
# generated data blobs (timeseries.json and friends) that never cite a tool stem.
MAX_BYTES = 20 * 1024 * 1024

# Tools the graph cannot see. Sourced from the 2026-08-04 master plan section A8
# "FALSE POSITIVES that look dead but are LIVE".
KNOWN_LIVE = {
    "archetype_comps_export",
    "statcast_aaa_hitters",
    "aaa_physics_export",
    "player_news",
    "savant_arm_strength",
    "farm_grade_backtest",
    "fix_encoding",
    "dead_code_scan",  # this scanner
}

# Subdirectories under tools/ that are kept regardless of the stem graph, with
# the reason. Their contents also act as pinning sources.
KEEP_DIRS = {
    "bucket_age_head": "model-registry-cited",
    "pitcher_label_candidates": "docs-cited",
    "pbust_thin": "production-docstring-cited (efv_score.py, efv_ungraded.py)",
}

# The 12 transitive pins the 2026-08-04 scan reported. Re-checked here so drift
# is visible rather than silent.
PRIOR_EXCLUSIONS = {
    "_am_crossmodel_lab", "_am_fa_gate2", "_fa_tj_pt", "_frontier_ablate",
    "efv_cohort_lambda_lab", "efv_pitcher_label_harness", "ifa_pedigree_lab",
    "offline_leverage", "pwoba_ev_arm_lab", "star_mean_head_backtest",
    "win_prob_walker", "xwoba_projection_blend_lab",
}

# Purge plans that enumerate their own delete targets. Excluded from the
# direct-reference corpus (see module docstring).
PLAN_DOCS = {
    "docs/master-plan-2026-08-04d-omnibus.md",
}

# Citers that make a tool a HARD keep: the model registry and its eval artifacts.
# Repo standing rule: every model gets a registry row + eval artifact, so a lab
# named by one of these cannot be deleted without orphaning that row.
REGISTRY_FILES = {"data/model_registry.json", "MODEL_REGISTRY.md"}
EVAL_ARTIFACT_RE = re.compile(r"^data/[^/]*eval[^/]*\.json$")

CODE_EXTS = {".py", ".sh", ".bat", ".ps1", ".js"}
DOC_EXTS = {".md", ".txt"}

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _citer_class(rel: str) -> str:
    """Classify one citing file. Strongest class wins when a stem has several."""
    if rel in PLAN_DOCS:
        return "plan_doc"
    if rel in REGISTRY_FILES or EVAL_ARTIFACT_RE.match(rel):
        return "registry"
    ext = ("." + rel.rsplit(".", 1)[-1]).lower() if "." in rel else ""
    if ext in CODE_EXTS:
        return "code"
    if ext in DOC_EXTS:
        return "doc"
    return "data"


# strongest first
_CLASS_RANK = ["registry", "code", "data", "doc", "plan_doc"]


def _iter_files(base: Path):
    """Yield scannable files under base, pruning generated/vendor trees."""
    stack = [base]
    while stack:
        cur = stack.pop()
        try:
            entries = list(cur.iterdir())
        except (OSError, PermissionError):
            continue
        for p in entries:
            if p.is_dir():
                if p.name not in PRUNE_DIRS:
                    stack.append(p)
            elif p.suffix.lower() in SCAN_EXTS:
                yield p


def _tokens(path: Path, skipped: list[str]) -> set[str]:
    try:
        if path.stat().st_size > MAX_BYTES:
            skipped.append(str(path.relative_to(ROOT)).replace("\\", "/"))
            return set()
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return set()
    return set(TOKEN_RE.findall(text))


def _tracked_tool_stems() -> set[str] | None:
    """Stems of tools/*.py that git tracks. None when git is unavailable.

    An UNTRACKED tool is either brand new (possibly written minutes ago by a
    concurrent agent) or was never meant to be committed. Either way the
    reference graph cannot judge it, so it must not be deleted unattended.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "tools/*.py"], cwd=ROOT,
            capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return {Path(line).stem for line in out.stdout.splitlines() if line.strip()}


def _dir_size(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="JSON report path")
    ap.add_argument("--count-plan-docs", action="store_true",
                    help="let PLAN_DOCS citations count as real references")
    args = ap.parse_args()
    plan_docs = set() if args.count_plan_docs else PLAN_DOCS

    # ---- universe: top-level tools/*.py --------------------------------------
    tool_paths = {p.stem: p for p in sorted(TOOLS.glob("*.py"))}
    stems = set(tool_paths)

    # subdirectories under tools/ are their own units
    subdirs = sorted(p for p in TOOLS.iterdir() if p.is_dir()
                     and p.name not in PRUNE_DIRS)

    # ---- pass 1: direct references from outside tools/ -----------------------
    skipped_big: list[str] = []
    direct: dict[str, list[str]] = {}
    subdir_direct: dict[str, list[str]] = {}
    subdir_named: dict[str, list[str]] = {}
    subdir_names = {d.name for d in subdirs}
    # a subdir is referenced if its own name, or any .py stem inside it, is cited
    subdir_stem_owner: dict[str, str] = {}
    for d in subdirs:
        subdir_stem_owner[d.name] = d.name
        for f in d.rglob("*.py"):
            subdir_stem_owner.setdefault(f.stem, d.name)

    outside_scanned = 0
    for f in _iter_files(ROOT):
        try:
            rel = f.relative_to(ROOT)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "tools":
            continue
        outside_scanned += 1
        toks = _tokens(f, skipped_big)
        rels = str(rel).replace("\\", "/")
        for s in toks & stems:
            direct.setdefault(s, []).append(rels)
        for s in toks & set(subdir_stem_owner):
            owner = subdir_stem_owner[s]
            subdir_direct.setdefault(owner, []).append(rels)
        # citations of the DIRECTORY NAME itself. Member-stem matches inflate the
        # count badly for dirs holding generically named members (pbust_thin has
        # cohort.py / score.py / gate.py), so the dir-name count is the honest one.
        for s in toks & subdir_names:
            subdir_named.setdefault(s, []).append(rels)

    # split the plan doc back out: a purge plan naming its own targets is not
    # evidence the target is live.
    plan_only: dict[str, list[str]] = {}
    real_direct: dict[str, list[str]] = {}
    for s, citers in direct.items():
        keep_citers = [c for c in citers if c not in plan_docs]
        if keep_citers:
            real_direct[s] = keep_citers
        else:
            plan_only[s] = sorted(set(citers))
    direct = real_direct
    subdir_direct = {k: [c for c in v if c not in plan_docs]
                     for k, v in subdir_direct.items()}
    subdir_direct = {k: v for k, v in subdir_direct.items() if v}
    subdir_named = {k: [c for c in v if c not in plan_docs]
                    for k, v in subdir_named.items()}
    subdir_named = {k: v for k, v in subdir_named.items() if v}

    # ---- pass 2: transitive pins from kept tools -----------------------------
    # token cache for every tool file (top level + subdir members)
    # This scanner names tool stems in PRIOR_EXCLUSIONS / KNOWN_LIVE, so letting
    # it act as a pin source would immunise exactly the stems it audits.
    self_stem = Path(__file__).stem
    tool_tokens: dict[str, set[str]] = {}
    for s, p in tool_paths.items():
        tool_tokens[s] = set() if s == self_stem else _tokens(p, skipped_big)

    subdir_tokens: dict[str, set[str]] = {}
    for d in subdirs:
        acc: set[str] = set()
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() in SCAN_EXTS:
                acc |= _tokens(f, skipped_big)
        subdir_tokens[d.name] = acc

    kept: set[str] = set(direct) | (stems & KNOWN_LIVE)
    pinned_by: dict[str, list[str]] = {}

    # kept subdirs pin top-level tools too
    kept_subdirs = set(KEEP_DIRS) | set(subdir_direct)
    kept_subdirs &= subdir_names
    for name in sorted(kept_subdirs):
        for s in (subdir_tokens.get(name, set()) & stems) - kept:
            kept.add(s)
            pinned_by.setdefault(s, []).append(f"tools/{name}/")

    changed = True
    while changed:
        changed = False
        for holder in sorted(kept):
            toks = tool_tokens.get(holder)
            if not toks:
                continue
            for s in (toks & stems) - kept - {holder}:
                kept.add(s)
                pinned_by.setdefault(s, []).append(f"tools/{holder}.py")
                changed = True

    candidates = sorted(stems - kept)
    exclusions = sorted(s for s in kept if s not in direct
                        and s not in KNOWN_LIVE)

    # ---- why each kept tool is kept (strongest citer class wins) -------------
    def _strongest(citers: list[str]) -> str:
        classes = {_citer_class(c) for c in citers}
        for c in _CLASS_RANK:
            if c in classes:
                return c
        return "data"

    keep_reasons: dict[str, dict] = {}
    for s in sorted(kept):
        if s in direct:
            citers = sorted(set(direct[s]))
            cls = _strongest(citers)
            keep_reasons[s] = {
                "reason": f"cited outside tools/ ({cls})",
                "class": cls,
                "citers": citers[:6],
                "citer_count": len(citers),
            }
        elif s in KNOWN_LIVE:
            keep_reasons[s] = {"reason": "KNOWN_LIVE allowlist",
                               "class": "allowlist", "citers": [],
                               "citer_count": 0}
        else:
            keep_reasons[s] = {
                "reason": "pinned by a kept tool",
                "class": "tool_pin",
                "citers": sorted(set(pinned_by.get(s, []))),
                "citer_count": len(set(pinned_by.get(s, []))),
            }

    registry_kept = sorted(s for s, r in keep_reasons.items()
                           if r["class"] == "registry")

    # ---- orphan _*_out dirs whose whole lab family is a candidate ------------
    cand_set = set(candidates)
    orphan_out_dirs = []
    for d in subdirs:
        if d.name in KEEP_DIRS or d.name in subdir_direct:
            continue
        base = d.name[:-4] if d.name.endswith("_out") else None
        if base is None:
            continue
        fam = sorted(s for s in stems if s == base or s.startswith(base + "_"))
        if fam and all(s in cand_set for s in fam):
            orphan_out_dirs.append({
                "dir": f"tools/{d.name}/",
                "bytes": _dir_size(d),
                "lab_family_all_candidates": fam,
            })

    # ---- drift checks --------------------------------------------------------
    drift = {
        "prior_exclusions_still_excluded": sorted(PRIOR_EXCLUSIONS & set(exclusions)),
        "prior_exclusions_now_directly_referenced": sorted(
            s for s in PRIOR_EXCLUSIONS if s in direct),
        "prior_exclusions_now_delete_candidates": sorted(
            PRIOR_EXCLUSIONS & cand_set),
        "prior_exclusions_missing_from_disk": sorted(PRIOR_EXCLUSIONS - stems),
        "new_exclusions_not_in_prior_list": sorted(
            set(exclusions) - PRIOR_EXCLUSIONS),
        "prior_exclusions_keep_reason_now": {
            s: keep_reasons.get(s, {"reason": "DELETE CANDIDATE"})
            for s in sorted(PRIOR_EXCLUSIONS)
        },
        "keep_dirs": {
            name: {
                "reason": reason,
                "present": name in subdir_names,
                "cited_by_dir_name": sorted(set(subdir_named.get(name, [])))[:8],
                "dir_name_citation_count": len(set(subdir_named.get(name, []))),
                "any_member_stem_citation_count": len(set(subdir_direct.get(name, []))),
            }
            for name, reason in KEEP_DIRS.items()
        },
    }

    tracked = _tracked_tool_stems()
    untracked_candidates = (sorted(set(candidates) - tracked)
                            if tracked is not None else [])

    cand_bytes = 0
    cand_rows = []
    for s in candidates:
        try:
            n = tool_paths[s].stat().st_size
        except OSError:
            n = 0
        cand_bytes += n
        row = {"stem": s, "path": f"tools/{s}.py", "bytes": n}
        if s in plan_only:
            row["cited_by_plan_doc_only"] = plan_only[s]
        if s in untracked_candidates:
            row["untracked_do_not_delete"] = True
        cand_rows.append(row)

    report = {
        "generated_from": str(ROOT).replace("\\", "/"),
        "universe": "tools/*.py (top level)",
        "counts": {
            "total_tools": len(stems),
            "directly_referenced_outside_tools": len(direct),
            "known_live_allowlist": len(stems & KNOWN_LIVE),
            "registry_or_eval_artifact_cited": len(registry_kept),
            "cited_only_by_a_purge_plan_doc": len(plan_only),
            "transitive_pin_exclusions": len(exclusions),
            "delete_candidates": len(candidates),
            "candidates_untracked_do_not_delete": len(untracked_candidates),
            "delete_candidates_tracked": len(candidates) - len(untracked_candidates),
            "candidate_bytes": cand_bytes,
            "tools_subdirs": len(subdirs),
            "files_scanned_outside_tools": outside_scanned,
            "files_skipped_over_size_cap": len(set(skipped_big)),
        },
        "delete_candidates": cand_rows,
        "exclusions_pinned_by_kept_tool": [
            {"stem": s, "path": f"tools/{s}.py",
             "pinned_by": sorted(set(pinned_by.get(s, [])))}
            for s in exclusions
        ],
        "known_live_allowlist": sorted(stems & KNOWN_LIVE),
        "candidates_untracked_do_not_delete": untracked_candidates,
        "keep_reasons": keep_reasons,
        "registry_or_eval_artifact_cited": registry_kept,
        "cited_only_by_a_purge_plan_doc": plan_only,
        "subdirs": [
            {
                "dir": f"tools/{d.name}/",
                "bytes": _dir_size(d),
                "keep_reason": KEEP_DIRS.get(d.name),
                "cited_by_dir_name": len(set(subdir_named.get(d.name, []))),
                "cited_by_any_member_stem": len(set(subdir_direct.get(d.name, []))),
                "verdict": ("KEEP" if d.name in KEEP_DIRS
                            else "referenced" if d.name in subdir_named
                            else "candidate"),
                # only the orphan list is safe to delete unattended: an _*_out
                # dir whose whole lab family is itself a candidate.
                "safe_orphan": any(o["dir"] == f"tools/{d.name}/"
                                   for o in orphan_out_dirs),
            }
            for d in subdirs
        ],
        "orphan_out_dirs": orphan_out_dirs,
        "drift_vs_2026_08_04_scan": drift,
        "skipped_over_size_cap": sorted(set(skipped_big)),
    }

    out = Path(args.out) if args.out else (ROOT / "data" / "dead_tools.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1), encoding="utf-8")

    c = report["counts"]
    print(f"wrote {out}")
    print(f"  total tools/*.py ............ {c['total_tools']}")
    print(f"  directly referenced ......... {c['directly_referenced_outside_tools']}")
    print(f"    of which registry/eval .... {c['registry_or_eval_artifact_cited']}")
    print(f"  known-live allowlist ........ {c['known_live_allowlist']}")
    print(f"  pinned-by-kept-tool ......... {c['transitive_pin_exclusions']}")
    print(f"  plan-doc-only citations ..... {c['cited_only_by_a_purge_plan_doc']}"
          f" (not counted as references)")
    print(f"  DELETE CANDIDATES ........... {c['delete_candidates']}"
          f" ({c['candidate_bytes'] / 1e6:.2f} MB)")
    print(f"    tracked, safe to purge .... {c['delete_candidates_tracked']}")
    print(f"    UNTRACKED, do not delete .. {c['candidates_untracked_do_not_delete']}")
    print(f"  tools/ subdirs .............. {c['tools_subdirs']}")
    print(f"  files scanned outside tools/. {c['files_scanned_outside_tools']}"
          f" (skipped {c['files_skipped_over_size_cap']} over size cap)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
