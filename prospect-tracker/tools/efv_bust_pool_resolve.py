# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Outcome-blind ids for the bust pool (EFV3 lane A, G7; EFV3_PLAN.md section 3,
LANE_A.md section 1.6; owner answer lane A E3-Q4 = A, dev-only behind a flag with the
symmetry receipt).

    python tools/efv_bust_pool_resolve.py            # dry run: counts to stdout, no file
    python tools/efv_bust_pool_resolve.py --write    # data/efv_bust_pool_ids.json and the receipt
    python tools/efv_bust_pool_resolve.py ledger     # one development row in data/efv_progress.json

WHY. data/inactive.json holds 2,337 never-reached rows, 1,303 of them with no mlbam_id
(the null test: every row holds the key). Without an id a row reads no MiLB block in the
training matrices and efv_labels.reached_class can only resolve it by the stale-list rule
(last list year at or before RESOLVED_THROUGH - 5), so 381 censored-never rows wait for
the calendar (140 flip at RT 2026, 163 at 2027, 199 at 2028) and 918 never rows carry no
block at all. The 2026-07-24 asset data/sources/mlbam_id_overrides_busts.json joins 0 of
the 1,303 keys: every one of its 283 ids already sits on its row and in player_photos.

THE RESOLVER is efv_identity's, unchanged, read on one input the list-vintage frame does
not have: the row's LAST LIST YEAR. A pool row is resolved from its printed name, its side
(efv_dataset._side_match, the frame's own routing) and the read year last list year + 1,
so the candidates are the people with an affiliated minor league line or a June draft
selection through the last list year, and the SIDE and RECENCY tiebreaks read those same
pre-read minor league lines. Nothing else is read on the resolver path: no debut date, no
major league line, no WAR, no stored id, no birth date. A row without a list point has no
read year and stays unresolved (how "no_list_year"). test_efv_bust_pool_resolve.py pins
the path by AST and by behaviour (a row's id does not move when its outcome fields
change). The resolver NEVER calls /people/search on a debut date.

THE RECEIPT (data/efv_bust_pool_receipt.json) reads outcomes, which the resolver may not:
for every pool row the BUST2 class before and after the id (efv_labels.reached_class on
the record with and without the resolved id), counted per class and last list year; the
SYMMETRY CLAUSE, the 2026-07-24 revival condition: id coverage of the debuted rows
(debuts.json) and the bust rows (inactive.json) under the SAME resolver, side by side per
side, a gap above SYMMETRY_MAX_GAP_POINTS blocking any use of the ids in a training
matrix; the retired asset's join count; and the one validity read, the style of
tools/efv_identity_balance.py: on lv_dev (development vintages only) the W3 > 0 share of
the pool rows the resolver resolved against the pool rows it did not, with the partial
coefficient and its player-clustered CI95. Counts and class flips only; no score.

WHERE THE IDS GO. Nowhere by default. efv_dataset.BUST_POOL_IDS (False) is the flag the
matrix builder reads: off, the builder never opens the id file and the matrices are the
incumbent byte for byte; on, a never-MLB row with no stored id takes the pool id before
_milb_features and before Arm R's never rule, and the builder refuses the file when its
symmetry block is blocked. The fWAR epoch's part 6 ride list is frozen without this
factor, so the flag flips only after epoch step Z and under Arm R's own clauses
(docs/efv-2026-10-02/BUST2_GATE.md). The full_pool cut stays inadmissible for any claim
(docs/EFV_GATE_STANDARD.md, the missing-block proxy).

NEVER READ: list vintages 2020 and 2021 (R-LV) and the 2025+ debut cohorts (R-VM) are
outside every read here; nothing is grouped by any grade (docs/PROSPECT_ANCHOR_GATE.md).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import efv_dataset as D  # noqa: E402
import efv_identity as ID  # noqa: E402

DATA = ROOT / "data"
INACTIVE = DATA / "inactive.json"
DEBUTS = DATA / "debuts.json"
IDS_OUT = DATA / "efv_bust_pool_ids.json"
RECEIPT_OUT = DATA / "efv_bust_pool_receipt.json"
RETIRED_ASSET = DATA / "sources" / "mlbam_id_overrides_busts.json"
EPOCH_GATE = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"

SCHEMA = "efv_bust_pool_ids/1"
RECEIPT_SCHEMA = "efv_bust_pool_receipt/1"
MODEL_ID = "efv_bust_pool_ids"
LEDGER_FRAME = "lv_dev"
PROBE_TAG = "G7:balance.bust_id_resolved"
#: The symmetry clause: debuted and bust coverage under the same resolver may differ
#: by at most this many percentage points on a side, or the ids are not used.
SYMMETRY_MAX_GAP_POINTS = 10.0
SEED = 20261002
HOW_NO_LIST_YEAR = "no_list_year"
#: The functions of the outcome-blind path; the AST test scans exactly these.
RESOLVER_PATH = ("last_list_year", "side_of", "read_year", "resolve_row", "resolve_pool")


# ---------------------------------------------------------------------------
# the resolver path: printed name, last list year, side; nothing else
# ---------------------------------------------------------------------------

def last_list_year(rec: dict) -> int | None:
    """The latest snapshot year on the record's points, or None without a point."""
    years = []
    for p in rec.get("points") or []:
        s = str(p.get("snapshot_date") or "")[:4]
        if s.isdigit():
            years.append(int(s))
    return max(years) if years else None


def side_of(rec: dict) -> str | None:
    """The side the frame would route the row to, or None when it is unknown."""
    if D._side_match(rec, "pit"):
        return "pit"
    if D._side_match(rec, "hit"):
        return "hit"
    return None


def read_year(last_year: int | None) -> int | None:
    """The read is the season after the last list year: candidates must be in
    affiliated ball through that year, and the tiebreaks read lines through it."""
    return None if last_year is None else int(last_year) + 1


def resolve_row(rec: dict, index: ID.NameIndex) -> dict:
    """One pool row from its printed name, its last list year and its side."""
    last = last_list_year(rec)
    side = side_of(rec)
    V = read_year(last)
    if V is None:
        return {"player_key": rec.get("player_key"), "person_id": None,
                "how": HOW_NO_LIST_YEAR, "n_candidates": 0,
                "last_list_year": None, "read_year": None, "side": side}
    res = ID.resolve(rec.get("player_name"), V, index, side)
    return {"player_key": rec.get("player_key"), "person_id": res.person_id,
            "how": res.how, "n_candidates": res.n_candidates,
            "last_list_year": last, "read_year": V, "side": side}


def resolve_pool(records: list[dict], index: ID.NameIndex | None = None) -> list[dict]:
    """resolve_row over a list of records, in their order."""
    if index is None:
        index = ID.build_index(D.CURRENT_SEASON)
    return [resolve_row(rec, index) for rec in records]


# ---------------------------------------------------------------------------
# the receipt: outcomes may be read here, never above
# ---------------------------------------------------------------------------

def _load(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError:
        return None


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short=8", "HEAD"],
                             capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _has_stored_id(rec: dict) -> bool:
    return bool(rec.get("mlbam_id"))


def coverage(records: list[dict], resolutions: list[dict]) -> dict:
    """Resolved share per side over all rows and over the rows with no stored id."""
    out = {}
    for side in ("hit", "pit", "none"):
        pairs = [(rec, r) for rec, r in zip(records, resolutions)
                 if (r["side"] or "none") == side]
        n = len(pairs)
        got = sum(1 for _rec, r in pairs if r["person_id"] is not None)
        sub = [(rec, r) for rec, r in pairs if not _has_stored_id(rec)]
        sub_got = sum(1 for _rec, r in sub if r["person_id"] is not None)
        out[side] = {"rows": n, "resolved": got,
                     "share": round(100.0 * got / n, 2) if n else None,
                     "no_stored_id_rows": len(sub), "no_stored_id_resolved": sub_got,
                     "no_stored_id_share": (round(100.0 * sub_got / len(sub), 2)
                                            if sub else None),
                     "by_how": dict(collections.Counter(r["how"] for _rec, r in pairs))}
    return out


def symmetry(debuted_cov: dict, bust_cov: dict,
             max_gap: float = SYMMETRY_MAX_GAP_POINTS) -> dict:
    """The clause: per side (hit, pit), the debuted share minus the bust share under the
    same resolver; any side above max_gap in absolute value blocks the ids."""
    per_side = {}
    blocked = False
    for side in ("hit", "pit"):
        d, b = debuted_cov[side]["share"], bust_cov[side]["share"]
        gap = None if d is None or b is None else round(d - b, 2)
        over = gap is not None and abs(gap) > max_gap
        blocked = blocked or over
        per_side[side] = {"debuted_share": d, "bust_share": b, "gap_points": gap,
                          "over_limit": over}
    return {"rule": ("id coverage of debuted rows (debuts.json) and bust rows "
                     "(inactive.json) under the same resolver, all rows, per side; a "
                     "gap above max_gap_points on either side blocks any use of the "
                     "ids in a training matrix"),
            "max_gap_points": max_gap, "by_side": per_side, "blocked": blocked,
            "verdict": "SYMMETRY_BLOCKED" if blocked else "SYMMETRY_OK"}


def bust2_flips(inactive: list[dict], resolutions: list[dict], war: dict) -> dict:
    """efv_labels.reached_class on every pool row with no stored id, before and after
    the resolved id, counted per (before, after) class and per last list year."""
    import efv_labels as L
    pairs = collections.Counter()
    by_year: dict[str, collections.Counter] = {}
    per_row = {}
    for rec, r in zip(inactive, resolutions):
        if _has_stored_id(rec):
            continue
        seasons = war.get(rec.get("player_key"))
        before = L.reached_class(rec, seasons)
        after = before
        if r["person_id"] is not None:
            after = L.reached_class(dict(rec, mlbam_id=int(r["person_id"])), seasons)
        key = f"{before}->{after}"
        pairs[key] += 1
        y = str(r["last_list_year"] or "none")
        by_year.setdefault(key, collections.Counter())[y] += 1
        per_row[rec["player_key"]] = (before, after)
    return {"classifier": "efv_labels.reached_class (BUST2)",
            "resolved_through": int(L.resolved_through()),
            "latest_milb_seasons": list(L.latest_milb_seasons(2)),
            "rows": sum(pairs.values()),
            "by_before_after": dict(sorted(pairs.items())),
            "by_before_after_and_last_list_year": {
                k: dict(sorted(v.items())) for k, v in sorted(by_year.items())},
            "before": dict(collections.Counter(b for b, _a in per_row.values())),
            "after": dict(collections.Counter(a for _b, a in per_row.values()))}, per_row


def agreement(records: list[dict], resolutions: list[dict]) -> dict:
    """On the records that carry a stored id: does the same resolver, which never reads
    that id, land on it? Counts per route; a validity read of the rule, not of the
    outcome (the stored id travels with the debut, which is why the resolver may not
    read it, and why agreement on debuted and never-reached rows is reported apart)."""
    c = collections.Counter()
    by_how: dict[str, collections.Counter] = {}
    for rec, r in zip(records, resolutions):
        if not _has_stored_id(rec):
            continue
        if r["person_id"] is None:
            c["unresolved"] += 1
            continue
        k = "agree" if int(rec["mlbam_id"]) == int(r["person_id"]) else "disagree"
        c[k] += 1
        by_how.setdefault(r["how"], collections.Counter())[k] += 1
    n_res = c["agree"] + c["disagree"]
    return {"rows_with_stored_id": sum(c.values()), "agree": c["agree"],
            "disagree": c["disagree"], "unresolved": c["unresolved"],
            "agree_share_of_resolved": round(100.0 * c["agree"] / n_res, 2) if n_res else None,
            "by_how": {h: dict(v) for h, v in sorted(by_how.items())}}


def reached_timing(inactive: list[dict], resolutions: list[dict], per_row: dict) -> dict:
    """For the no-id rows whose resolved id carries a major league line: the first
    major league season minus the last list year, counted. A row filed as a bust whose
    id reached within a season of its last list is the upstream debut-detector miss the
    F1 bust-loop guard already names; a line years before the last list would be a
    name collision. Counts only."""
    import efv_labels as L
    diff = collections.Counter()
    by_how = collections.Counter()
    for rec, r in zip(inactive, resolutions):
        if _has_stored_id(rec) or r["person_id"] is None:
            continue
        before, after = per_row[rec["player_key"]]
        if after != "reached" or before == "reached":
            continue
        fy = L.first_mlb_line(r["person_id"])
        d = None if fy is None or r["last_list_year"] is None else int(fy) - int(r["last_list_year"])
        diff["none" if d is None else str(d)] += 1
        by_how[r["how"]] += 1
    return {"rows": sum(diff.values()),
            "first_mlb_season_minus_last_list_year": dict(
                sorted(diff.items(), key=lambda kv: (kv[0] == "none", int(kv[0]) if kv[0] != "none" else 0))),
            "by_how": dict(by_how),
            "matrix_effect": ("with the flag on these rows leave the bust pool through "
                              "the F1 guard (bust_mlb_exposure_dropped, or rerouted when "
                              "career_war holds their seasons); never a 0.0 label")}


def retired_asset(inactive: list[dict], debuts: list[dict], null_keys: set[str]) -> dict:
    """What the 2026-07-24 asset joins today: its keys against the null-id pool and
    against every record, and whether its ids already sit on those records."""
    try:
        asset = _load(RETIRED_ASSET)
    except (OSError, ValueError):
        return {"path": "data/sources/mlbam_id_overrides_busts.json", "present": False}
    try:
        live = (_load(DATA / "timeseries.json") or {}).get("players") or []
    except (OSError, ValueError):
        live = []
    rec_ids = {}
    for rec in inactive + debuts + list(live):
        rec_ids[rec.get("player_key")] = rec.get("mlbam_id")
    same = sum(1 for k, v in asset.items() if rec_ids.get(k) == v)
    on_record = sum(1 for k in asset if k in rec_ids)
    return {"path": "data/sources/mlbam_id_overrides_busts.json", "present": True,
            "keys": len(asset),
            "joins_null_id_pool": sum(1 for k in asset if k in null_keys),
            "keys_on_a_record": on_record,
            "records_read": "inactive.json, debuts.json, timeseries.json players",
            "keys_whose_id_is_already_on_the_record": same,
            "disposition": ("retired as a bust-pool input: every key is a current key "
                            "whose id already sits on the record, so there is nothing "
                            "to re-key; the file stays as war_source.mlbam_index's "
                            "third fallback binding (an identity map, never deleted) "
                            "and this tool does not read it")}


def balance_read(pool_keys: set[str], resolved_keys: set[str]) -> dict:
    """The one validity read, tools/efv_identity_balance.py style: on lv_dev, over the
    frame rows whose record is a pool row (inactive.json, no stored id), the W3 > 0
    share of the rows the resolver resolved against those it did not, by side, with the
    partial coefficient on the within-(side, vintage) consensus percentile and its
    player-clustered CI95. Development vintages only; the reserved guard runs first."""
    import numpy as np

    import efv_identity_balance as TB
    import efv_labels as L
    import efv_vintage_frame as F
    import source_backtest as SB

    guards = TB._guards()
    universe = F.load_universe()
    war = L.war_seasons_table()
    frame_rows, rows = [], []
    receipt = {"frame_rows": 0, "pool_rows_on_frame": 0, "no_consensus": 0,
               "label_none": 0, "dropped_rvm_players": 0}
    rvm = set()
    for V in F.DEV_VINTAGES:
        F.guard_score_request(V, purpose="bust pool id balance")
        for side in F.SIDES:
            frame = F.build_frame(side, V, universe=universe)
            receipt["frame_rows"] += len(frame)
            labs = L.labels_for_frame(frame, universe=universe, war=war)
            for r, lab in zip(frame, labs):
                if lab.get("debut_year") is not None and \
                        int(lab["debut_year"]) >= F.R_VM_FIRST_DEBUT_YEAR:
                    rvm.add(r["player_key"])
                    continue
                c = (r.get("grades") or {}).get(SB.CONSENSUS_KEY)
                if c is None:
                    receipt["no_consensus"] += 1
                    continue
                if lab.get("w3") is None:
                    receipt["label_none"] += 1
                    continue
                row = {"pk": r["player_key"], "V": V, "side": side, "fv": float(c),
                       "w3": float(lab["w3"]), "r3": lab.get("r3"),
                       "bust_id_resolved": float(r["player_key"] in resolved_keys)}
                frame_rows.append(row)
                if r["player_key"] in pool_keys:
                    rows.append(row)
    receipt["dropped_rvm_players"] = len(rvm)
    receipt["pool_rows_on_frame"] = len(rows)
    receipt["rows_read"] = len(rows)
    receipt["rows_read_by_side"] = {s: sum(1 for r in rows if r["side"] == s)
                                    for s in F.SIDES}
    receipt["frame_rows_read"] = len(frame_rows)
    indicator = (("bust_id_resolved", "pool row resolved by the outcome-blind resolver"),)
    rng = np.random.default_rng(SEED)
    bal = TB.balance(rows, rng, indicator)
    sides = {}
    for s in F.SIDES:
        blk = dict(bal[s]["bust_id_resolved"])
        y = [r["w3"] > 0 for r in rows if r["side"] == s]
        if y and (all(y) or not any(y)):
            # The outcome does not vary on this side: a partial of 0 with a CI of
            # [0, 0] is not balance, it is no information. Named as such.
            blk.update({"verdict": "CONSTANT", "constant_outcome": True,
                        "w3_pos_share": float(all(y))})
        sides[s] = blk
    read = {s: v for s, v in sides.items() if v["verdict"] != "CONSTANT"}
    verdict = ("CONSTANT" if not read else
               "BALANCED" if all(v["verdict"] == "BALANCED" for v in read.values())
               else "IMBALANCED")
    reason = None
    if verdict == "CONSTANT":
        reason = ("W3 > 0 does not vary over the pool rows on lv_dev: an F-LV label "
                  "reads the record's own id and career_war row, never a pool id, so "
                  "every pool row keeps W3 0 whether or not the resolver found it; "
                  "the read carries no information about the ids and says so")
    probe = {"tag": PROBE_TAG, "verdict": verdict,
             "indicator": "bust_id_resolved on the lv_dev pool rows (no stored id)",
             "reason": reason,
             "rows_with": {s: sides[s]["n_with"] for s in F.SIDES},
             "rows_without": {s: sides[s]["n_without"] for s in F.SIDES},
             "w3_pos_share_with": {s: sides[s].get("w3_pos_share_with") for s in F.SIDES},
             "w3_pos_share_without": {s: sides[s].get("w3_pos_share_without")
                                      for s in F.SIDES},
             "partial": {s: sides[s].get("partial") for s in F.SIDES},
             "ci95": {s: sides[s].get("ci95") for s in F.SIDES}}
    # Context, not a probe: the same indicator over the whole frame compares the pool
    # rows to the debuted rows and reads the label by construction.
    whole = TB.balance(frame_rows, np.random.default_rng(SEED), indicator)
    context = {s: {k: whole[s]["bust_id_resolved"].get(k) for k in
                   ("n", "n_with", "n_without", "w3_pos_share_with",
                    "w3_pos_share_without", "w3_pos_gap")} for s in F.SIDES}
    return {"frame": "lv_dev (F-LV, development vintages), W3 on the label provider "
                     "stamped below; the population is the frame rows whose record is "
                     "an inactive.json row with no stored id",
            "guards": guards, "rows": receipt, "by_side": sides, "verdict": verdict,
            "reason": reason, "seed": SEED, "B": TB.B_BAL,
            "whole_frame_context": {
                "not_a_probe": ("over the whole frame the indicator marks never-reached "
                                "rows against debuted rows and reads the label by "
                                "construction; shown so the gap is visible, never "
                                "counted"),
                "by_side": context},
            "probes": {PROBE_TAG: probe}}


def matrix_preview(ids: dict[str, int]) -> dict:
    """Counts from one in-process build with the flag ON, kept out of data/: how many
    never-MLB rows take an id and gain a MiLB block, and how many the F1 guard
    reroutes or drops once the id shows major league exposure. The flag is restored
    before returning whatever happens."""
    old_flag, old_loader = D.BUST_POOL_IDS, D.bust_pool_ids
    out = {}
    try:
        for flag in (False, True):
            D.BUST_POOL_IDS = flag
            D.bust_pool_ids = (lambda path=None: dict(ids)) if flag else old_loader
            per = {}
            for side in ("hit", "pit"):
                rows, acct = D.build_matrix(side)
                busts = [r for r in rows if r.get("kind") == "bust"]
                per[side] = {"rows": len(rows), "bust_rows": len(busts),
                             "bust_rows_with_id": sum(1 for r in busts if r.get("mlbam_id")),
                             "bust_rows_with_milb_block": sum(1 for r in busts if r.get("milb")),
                             "bust_pool_id_applied": acct.get("bust_pool_id_applied", 0),
                             "bust_mlb_exposure_rerouted": acct.get("bust_mlb_exposure_rerouted", 0),
                             "bust_mlb_exposure_dropped": acct.get("bust_mlb_exposure_dropped", 0),
                             "bust_recent_flagged": acct.get("bust_recent_flagged", 0)}
            out["flag_on" if flag else "flag_off"] = per
    finally:
        D.BUST_POOL_IDS, D.bust_pool_ids = old_flag, old_loader
    return out


def epoch_stamp() -> dict:
    """The label epoch's state at the receipt: provider, RESOLVED_THROUGH and whether
    FWAR_LABEL_EPOCH_GATE.md part 9 holds a step Z entry."""
    import efv_labels as L
    text = EPOCH_GATE.read_text(encoding="utf-8") if EPOCH_GATE.exists() else ""
    tail = text.split("## 9. Results", 1)[1] if "## 9. Results" in text else ""
    empty = "EMPTY AT REGISTRATION" in tail
    return {"provider": L.provider(), "resolved_through": int(L.resolved_through()),
            "fwar_epoch_gate": "docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md",
            "part_9_empty": bool(empty),
            "reading": ("pre-epoch: the label is the retiring provider; the balance "
                        "read is re-run on the frozen label at the flag's flip"
                        if empty else "the epoch has written results; the label is "
                        "the provider stamped here")}


def build(*, preview: bool = True) -> tuple[dict, dict]:
    """(ids document, receipt document)."""
    import efv_labels as L
    inactive = _load(INACTIVE)
    debuts = _load(DEBUTS)
    index = ID.build_index(D.CURRENT_SEASON)
    res_in = resolve_pool(inactive, index)
    res_de = resolve_pool(debuts, index)
    null_keys = {rec["player_key"] for rec in inactive if not _has_stored_id(rec)}
    war = L.war_seasons_table()
    flips, per_row = bust2_flips(inactive, res_in, war)
    cov_bust, cov_deb = coverage(inactive, res_in), coverage(debuts, res_de)
    sym = symmetry(cov_deb, cov_bust)
    ids = {r["player_key"]: int(r["person_id"]) for rec, r in zip(inactive, res_in)
           if not _has_stored_id(rec) and r["person_id"] is not None}
    entries = []
    for rec, r in zip(inactive, res_in):
        if _has_stored_id(rec):
            continue
        before, after = per_row[rec["player_key"]]
        entries.append({"player_key": rec["player_key"], "person_id": r["person_id"],
                        "how": r["how"], "n_candidates": r["n_candidates"],
                        "last_list_year": r["last_list_year"], "read_year": r["read_year"],
                        "side": r["side"], "bust2_before": before, "bust2_after": after})
    stamp = epoch_stamp()
    commit = _git_commit()
    bal = balance_read(null_keys, set(ids))
    prev = matrix_preview(ids) if preview else None
    generated = _now_iso()
    ids_doc = {
        "schema": SCHEMA, "generated_at": generated,
        "produced_by": "tools/efv_bust_pool_resolve.py", "role": "development",
        "resolver": {"module": "efv_identity.py", "sha256": _sha(ROOT / "efv_identity.py"),
                     "inputs": "printed name, last list year (read year = last list year "
                               "+ 1), side (efv_dataset._side_match); SIDE then RECENCY "
                               "tiebreaks on pre-read minor league lines",
                     "never_reads": "debut date, major league line, WAR, stored id, "
                                    "birth date; never /people/search"},
        "flag": {"module": "efv_dataset", "name": "BUST_POOL_IDS", "default": False,
                 "reads_blocked": "the builder refuses this file while symmetry.blocked"},
        "label_epoch": stamp, "code": {"commit": commit},
        "pool": {"records": len(inactive), "no_stored_id": len(null_keys),
                 "resolved": len(ids),
                 "by_how": dict(collections.Counter(e["how"] for e in entries))},
        "symmetry": sym,
        "rows": entries,
    }
    receipt = {
        "schema": RECEIPT_SCHEMA, "generated_at": generated,
        "produced_by": "tools/efv_bust_pool_resolve.py", "role": "development",
        "adjudicates": "nothing; counts, class flips and one balance probe, no score",
        "ids_file": {"path": "data/efv_bust_pool_ids.json", "resolved": len(ids)},
        "label_epoch": stamp, "code": {"commit": commit,
                                       "tool_sha256": _sha(Path(__file__)),
                                       "resolver_sha256": _sha(ROOT / "efv_identity.py")},
        "pool": ids_doc["pool"],
        "bust2": flips,
        "coverage": {"bust_rows": cov_bust, "debuted_rows": cov_deb,
                     "note": "the same resolver on every record of each file, the stored "
                             "id ignored; no_stored_id_* restricts to records without one"},
        "symmetry": sym,
        "agreement_with_stored_id": {"bust_rows": agreement(inactive, res_in),
                                     "debuted_rows": agreement(debuts, res_de)},
        "reached_flips": reached_timing(inactive, res_in, per_row),
        "retired_asset": retired_asset(inactive, debuts, null_keys),
        "balance": bal,
        "matrix_preview": prev,
        "probes": bal["probes"], "n_probes": len(bal["probes"]),
        "bans": ("no read of R-LV or R-VM; no statistic by consensus-FV cell; no closed "
                 "arm re-run; the full_pool cut stays inadmissible for any claim"),
        "not_in_efv_progress_chart": ("no eFV and no candidate is scored here; the "
                                      "development row records counts only"),
    }
    return ids_doc, receipt


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")


def ledger_row(receipt: dict, path: Path, *, now_iso: str) -> dict:
    """The one development row for data/efv_progress.json: counts, resolvable None."""
    import efv_progress as P
    import efv_vintage_frame as F
    bal = receipt["balance"]
    sym = receipt["symmetry"]
    row = {"run_id": None, "date": receipt["generated_at"][:10], "trigger": "efv_change",
           "model_id": MODEL_ID,
           "model_version": {"fingerprint": None, "commit": receipt["code"].get("commit"),
                             "label": receipt["label_epoch"]["provider"],
                             "resolved_through": receipt["label_epoch"]["resolved_through"],
                             "provider": receipt["label_epoch"]["provider"]},
           "frame": LEDGER_FRAME, "frame_version": None,
           "role": P.FRAMES[LEDGER_FRAME]["role"],
           "tilted": bool(P.FRAMES[LEDGER_FRAME]["tilted"]),
           "window": [min(F.DEV_VINTAGES), max(F.DEV_VINTAGES)],
           "n": bal["rows"]["rows_read"], "n_by_side": dict(bal["rows"]["rows_read_by_side"]),
           "raters": {}, "deltas": {}, "resolvable": None,
           "verdict": "bust pool ids, counts only, no score", "share": None,
           "sources": [{"path": P._rel(Path(path)), "generated_at": receipt["generated_at"],
                        "sha256": P._sha256(path)}],
           "note": (f"outcome-blind ids for {receipt['pool']['resolved']} of "
                    f"{receipt['pool']['no_stored_id']} no-id bust rows; symmetry "
                    f"{sym['verdict']} (hit gap {sym['by_side']['hit']['gap_points']}, "
                    f"pit gap {sym['by_side']['pit']['gap_points']} points); balance "
                    f"probe {bal['verdict']}; flag efv_dataset.BUST_POOL_IDS off; no score"),
           "last_verified_at": now_iso}
    row["content_hash"] = P.content_hash(row)
    row["run_id"] = f"{receipt['generated_at']}|{LEDGER_FRAME}|{row['content_hash'][:8]}"
    return row


def append_ledger(path: Path = RECEIPT_OUT, *, ledger_path=None) -> dict:
    import efv_progress as P
    receipt = _load(path)
    now_iso = P._now_iso()
    sb_path = P.DATA_DIR / P.SB_NAME
    sb = P._load_json(sb_path) if sb_path.exists() else None
    row = ledger_row(receipt, path, now_iso=now_iso)
    return P.commit_rows([row], ledger_path=ledger_path, sb=sb, now_iso=now_iso)


def summary(ids_doc: dict, receipt: dict) -> dict:
    return {"pool": ids_doc["pool"], "bust2": receipt["bust2"]["by_before_after"],
            "coverage": {k: {s: v[s]["share"] for s in ("hit", "pit")}
                         for k, v in receipt["coverage"].items() if isinstance(v, dict)},
            "symmetry": receipt["symmetry"]["verdict"],
            "agreement_with_stored_id": {
                k: v["agree_share_of_resolved"]
                for k, v in receipt["agreement_with_stored_id"].items()},
            "reached_flips": receipt["reached_flips"]["rows"],
            "retired_asset_joins_null_id_pool": receipt["retired_asset"].get("joins_null_id_pool"),
            "balance": {"verdict": receipt["balance"]["verdict"],
                        "rows": receipt["balance"]["rows"]},
            "matrix_preview": receipt["matrix_preview"]}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["ledger"]:
        print(json.dumps({"ledger": append_ledger()}, indent=1))
        return 0
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true",
                    help="write data/efv_bust_pool_ids.json and the receipt")
    ap.add_argument("--no-preview", action="store_true",
                    help="skip the in-process flag-on matrix count")
    args = ap.parse_args(argv)
    ids_doc, receipt = build(preview=not args.no_preview)
    print(json.dumps(summary(ids_doc, receipt), indent=1))
    if args.write:
        _write_json(IDS_OUT, ids_doc)
        _write_json(RECEIPT_OUT, receipt)
        print(f"wrote {IDS_OUT}\nwrote {RECEIPT_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
