# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Freeze the V 2026 rater scores (frame lv_2026) from the fWAR label epoch's step A
snapshot, after step Z (task SG_4B; docs/efv-v2/SURROGATE_2026_GATE.md Q5, s2.2, s4,
s8.13 and s11). Reads no outcome of any 2026 row and stores none.

WHY FROM THE SNAPSHOT. The gate's s2.2 names the scored object "V2 list-vintage fold
V = 2026, eWAR v2 label, RT 2025". The epoch's step C rebased the career_war table to
fWAR and step D+U flipped war_source.DEFAULT_PROVIDER, step RT moved
efv_dataset.RESOLVED_THROUGH to 2026, so the tree after step Z cannot fit that object.
SG_4 (the freeze before step C) did not run, so this tool reproduces the object from the
step A snapshot (../_pre_epoch_fwar_2026-10/, MANIFEST head 8a1c5b7f): the code at that
head (git archive), the snapshot's data files and its prospects.db (the career_war
basis before the rebase), and the efv2026 lane's pre-step-A universe bundle (debuts,
inactive, timeseries) for the inputs the snapshot lacks (orchestrator answer SG4B-Q1,
2026-10-14; the snapshot has no inactive.json, and a universe without the busts selects
on an outcome). Nothing is read from the post-Z tree except this tool and git.

HOW. The driver materializes a reproduction tree under --repro (code at the snapshot
head, the snapshot files sha-verified against its MANIFEST, the bundle sha-verified
against the pins below, a junction to the shared .cache), then runs this file again as
a worker inside that tree. The worker asserts RESOLVED_THROUGH == 2025 and
DEFAULT_PROVIDER == "ewar_v2" from the modules it imported, builds build_frame(side,
2026) on the bundle universe, fits the s2.2 fold object on labelled F-LV vintages
2011-2019 with every lv_2026 player left out (efv_v2_model.v2_lv_scores), scores the
zero-information twin (the non-consensus driver columns permuted within the vintage,
seed 20260931, scored by the same fitted object) and eFV v1 forward-chained on matrix
decision years before 2026 (efv_v2_model.lv_scores), and joins the ETA shadow rows of
data/eta_eval.json (fg_blend_gate_2026_09_25.live_shadow_2026, as committed at the
snapshot head) only where the shadow's listing_date is before the row's window end.
Every file the worker opened under the tree's data/, tools/ and .cache is hashed into
the freeze file.

RULES (SG_4's (1) to (4), carried by SG_4B):
  (1) a re-freeze is refused once data/efv_surrogate_frame_2026.json exists (the
      F-WATCH pattern, tools/xfv_promo_watch.py);
  (2) the file records the sha256 of every input, the git HEAD at the freeze, the
      snapshot head, RESOLVED_THROUGH and DEFAULT_PROVIDER as asserted;
  (3) test_efv_surrogate_frame_2026.py pins the timing (no input after a row's window
      end, the shadow join included), no 2026 season line in any feature, no label
      module in the frame builder, and no outcome column;
  (4) the row and person-id counts of s2.2 (590 / 617 rows; 522 / 570 person ids as
      re-baselined by the gate's dated amendment of 2026-10-14, SG4B-Q2 = A, from the
      453 / 454 taken at 64bf1bb3 before d24a87d1 and 6fd30aee) are re-taken before
      anything is written; on a mismatch of at most RECOUNT_MAX rows and ids per side
      that the identity split 1987b1b2 explains, the rows it touched are listed without
      a score and the matched rows are frozen; otherwise nothing is written and the
      run ends with 'BLOCKER: SG_4B recount'.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): nothing here groups, counts or averages
rows by consensus-FV level; consensus enters only as the V2 object's within-side
percentile. NO OUTCOME: no label, debut flag or 2026 season line is read for any
lv_2026 row, and the freeze file carries no such column (a window end cut at an April
debut is the frame's registered definition, s2.2, and the only date it carries).

Run once:  python tools/efv_surrogate_freeze_2026.py --snapshot <dir> --universe <dir>
                                                      --repro <scratch dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "efv_surrogate_frame_2026.json"
TOOL = "tools/efv_surrogate_freeze_2026.py"

FRAME = "lv_2026"
VINTAGE = 2026
FROZEN_BY = "SG_4B"
TASK = "SG_4B_FREEZE_LV2026_RATERS_POST_Z"
SIDES = ("hit", "pit")

#: The step A snapshot: its MANIFEST head, the commit that recorded step A, and its
#: path relative to the module root as the gate names it.
SNAPSHOT_HEAD = "8a1c5b7f68b96dd0942b9c3710ee2d605e7f5a07"
SNAPSHOT_REL = "../_pre_epoch_fwar_2026-10/"
STEP_A_COMMIT = "3ae607a2"
#: The step Z entry this freeze follows (FWAR part 9) and the commit carrying it.
FWAR_GATE = "docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md"
STEP_Z_HEADING = "### 2026-10-03: step Z, the fWAR label epoch's results"
STEP_Z_COMMIT = "73850ecccc0fcd223090668f0f4b134376ac0607"
#: What the snapshot head holds and the worker asserts from the imported modules.
EXPECTED_PROVIDER = "ewar_v2"
EXPECTED_RESOLVED_THROUGH = 2025
#: Snapshot files present but NOT used: the universe comes from the bundle whole, so
#: the frame's three files are internally consistent (SG4B-Q1).
SNAPSHOT_UNUSED = ("data/debuts.json", "data/timeseries.json")

#: The efv2026 lane's pre-step-A universe bundle (copied 2026-10-01 15:46, about 44
#: hours before step A; NOT the step A snapshot), pinned by sha256.
UNIVERSE_FILES = ("debuts.json", "inactive.json", "timeseries.json")
UNIVERSE_SHA256 = {
    "debuts.json": "4052a16d6e24589b5a85083b0778cdfd4277cd7c1062797584fc916aef434684",
    "inactive.json": "1ba3f7ddd91924250b02dc49b68d63249a1b8fc5646db3c20e12ec745a20919c",
    "timeseries.json": "e5449bbe551e9479fe5b1f907236ca126a8283715f16347af842630a5baa55fc",
}
UNIVERSE_NOTE = ("the efv2026 lane's universe bundle, copied 2026-10-01 15:46 local, "
                 "before epoch step A (2026-10-03 11:34) and after the identity split "
                 "1987b1b2 (2026-10-01 00:25); it is NOT the step A snapshot, whose "
                 "debuts.json and timeseries.json hash differently and which holds no "
                 "inactive.json; orchestrator answer SG4B-Q1 (2026-10-14)")

#: The scored object, named exactly as the gate's s2.2 names it.
V2_OBJECT_NAME = (
    "V2 list-vintage fold V = 2026, eWAR v2 label, RT 2025, DS-08 draft weights "
    "(data/efv_v2_assembly.json at git blob 91b04fa861ec64e9c1978d4fad727fbc00a45fd9, "
    "its content at 64bf1bb3, 26b446d9 and the step A head 3ae607a2), heads refit per "
    "EFV_V2_GATE.md s4.5 on labelled F-LV vintages 2011-2019 with the 6 lv_2026 players "
    "on 2017-2019 frames left out. This is NOT the served V2 (the vm fit) and NOT the "
    "registered candidate P5 (weights re-derived once on the frozen fWAR label); the "
    "fWAR re-derivation is not applied to it.")
ASSEMBLY_BLOB = "91b04fa861ec64e9c1978d4fad727fbc00a45fd9"
#: The zero-information twin's permutation seed (gate s4).
TWIN_SEED = 20260931
#: The ETA shadow block (gate s2.2; ETA s5) and its join rule.
ETA_BLOCK = ("fg_blend_gate_2026_09_25", "live_shadow_2026")
ETA_FIELDS = ("CH40", "A", "B", "fg_eta_year", "listing_date", "level", "on40")
ETA_NOTE = ("descriptive; not prospective with respect to the ETA look (recorded at "
            "be53132d, which scored the same forms against 2026 debut events of V 2024 "
            "rows); joined only where the shadow row's listing_date is before the frame "
            "row's window end, None otherwise")

#: Rule (4): the s2.2 counts and the bound. The rows are the universe snapshot's
#: (2026-09-30 12:45); the person ids are the step A head's, by the gate's dated
#: amendment of 2026-10-14 (SG4B-Q2 = A): the 453 / 454 printed at the draft were
#: taken at 64bf1bb3 before d24a87d1 (the 2019 to 2025 draft classes in the index)
#: and 6fd30aee (the side and recency tiebreaks), both registered before step A.
S22_COUNTS = {"hit": {"rows": 590, "person_ids": 522},
              "pit": {"rows": 617, "person_ids": 570}}
S22_COUNTS_AT_DRAFT = {"hit": {"rows": 590, "person_ids": 453},
                       "pit": {"rows": 617, "person_ids": 454}}
S22_AMENDMENT = ("SURROGATE_2026_GATE.md s11.1, dated 2026-10-14 (SG4B-Q2 = A): the "
                 "person-id counts re-baselined from 453 / 454 (64bf1bb3) to 522 / 570 "
                 "(the step A head 8a1c5b7f); every row frozen with the step A head "
                 "resolver")
RECOUNT_MAX = 10
#: The identity split (commit 1987b1b2): the incumbent keys, the keys the rows were
#: split onto, and the five MLBAM ids, read from the commit's diff of scrapers.py.
SPLIT_COMMIT = "1987b1b2"
SPLIT_KEYS = frozenset({
    "jose_rodriguez", "michael_massey", "carlos_rodriguez",
    "jose_rodriguez_679563", "jose_rodriguez_800412", "jose_rodriguez_836624",
    "michael_massey__sa3037259", "carlos_d_rodriguez"})
SPLIT_IDS = frozenset({679563, 800412, 836624, 695602, 677578})

#: Source modules whose blob ids at the snapshot head are recorded.
CODE_PINS = ("efv_vintage_frame.py", "efv_v2_model.py", "efv_dataset.py", "efv_labels.py",
             "efv_model.py", "efv_identity.py", "efv_drivers.py", "war_source.py",
             "milb_history.py", "source_backtest.py", "storage.py", "level_norms.py",
             "tools/efv_v2_assemble.py", "data/efv_v2_assembly.json",
             "data/efv_identity_balance.json", "data/eta_eval.json",
             "tools/_arch_bio_panel.json")

GRADE_KEYS = (("prospx_consensus", "prospx_consensus"), ("mlb_pipeline", "mlb_pipeline"),
              ("fangraphs", "fangraphs"))
V2_ROW_FIELDS = ("u_c", "e_skill", "e_time", "order_idx", "efv_grade")


class FreezeRefused(RuntimeError):
    """The freeze file exists: a re-freeze is refused (rule 1)."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_hashed(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        for chunk in iter(lambda: fi.read(1 << 22), b""):
            h.update(chunk)
            fo.write(chunk)
    return h.hexdigest()


def _jsonable(obj):
    """Plain JSON: numpy scalars to floats, tuples to lists, inf to 'inf'."""
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, float):
        if math.isinf(obj):
            return "inf" if obj > 0 else "-inf"
        if math.isnan(obj):
            return None
        return obj
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    if hasattr(obj, "item"):
        return _jsonable(obj.item())
    if hasattr(obj, "tolist"):
        return _jsonable(obj.tolist())
    return str(obj)


def canonical_sha256(obj) -> str:
    return hashlib.sha256(json.dumps(_jsonable(obj), sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _git(*args: str, cwd: Path = ROOT) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def refuse_if_frozen(path: Path = OUT) -> None:
    """Rule (1): the freeze happens once."""
    if Path(path).exists():
        raise FreezeRefused(f"{path} exists: the lv_2026 freeze is taken once and never "
                            f"re-taken (SG_4 rule 1); delete nothing, re-freeze nothing")


def step_z_entry(gate_path: Path = ROOT / FWAR_GATE) -> dict:
    """The step Z entry of FWAR part 9, or a RuntimeError when it is absent."""
    lines = gate_path.read_text(encoding="utf-8").splitlines()
    for i, ln in enumerate(lines, 1):
        if ln.strip() == STEP_Z_HEADING:
            return {"doc": FWAR_GATE, "heading": STEP_Z_HEADING, "line": i,
                    "commit": STEP_Z_COMMIT}
    raise RuntimeError(f"{FWAR_GATE} carries no step Z entry: SG_4B waits for it")


# ---------------------------------------------------------------------------
# the reproduction tree
# ---------------------------------------------------------------------------

def prepare_repro(repro: Path, snapshot: Path, universe: Path, *, force: bool = False
                  ) -> dict:
    """Materialize the snapshot-head tree, the snapshot's files, the bundle and the
    cache junction under `repro`; returns the receipt (memoized in REPRO_RECEIPT.json)."""
    repro = Path(repro)
    receipt_path = repro / "REPRO_RECEIPT.json"
    if receipt_path.exists() and not force:
        return json.loads(receipt_path.read_text(encoding="utf-8"))
    if repro.exists():
        shutil.rmtree(repro)
    repro.mkdir(parents=True)
    pt = repro / "prospect-tracker"
    t0 = time.time()
    tar = repro / "tree.tar"
    with open(tar, "wb") as fh:
        # the pathspec is relative to -C, so archive from the git root
        subprocess.run(["git", "-C", str(ROOT.parent), "archive", "--format=tar",
                        SNAPSHOT_HEAD, "prospect-tracker"], stdout=fh, check=True,
                       timeout=600)
    with tarfile.open(tar) as t:
        t.extractall(repro, filter="data")
    tar.unlink()
    if not (pt / "efv_vintage_frame.py").exists():
        raise RuntimeError(f"git archive {SNAPSHOT_HEAD} did not yield prospect-tracker/")
    man = json.loads((snapshot / "MANIFEST.json").read_text(encoding="utf-8"))
    if man.get("head") != SNAPSHOT_HEAD:
        raise RuntimeError(f"snapshot MANIFEST head {man.get('head')} is not "
                           f"{SNAPSHOT_HEAD}")
    inputs: dict = {}
    for rel, info in man["files"].items():
        # the snapshot stores data/ files flat at its root; model/ keeps its path
        src = snapshot / (rel[len("data/"):] if rel.startswith("data/") else rel)
        if not src.exists():
            raise RuntimeError(f"STOP: the step A snapshot lacks {rel}")
        if rel in SNAPSHOT_UNUSED:
            sha = sha256_file(src)
            used = False
        else:
            sha = _copy_hashed(src, pt / rel)
            used = True
        if sha != info["sha256"]:
            raise RuntimeError(f"STOP: snapshot {rel} hashes {sha}, MANIFEST says "
                               f"{info['sha256']}")
        inputs[rel] = {"sha256": sha, "bytes": int(info.get("bytes") or 0),
                       "mtime": info.get("mtime"), "materialized": used}
    bundle: dict = {}
    for fn in UNIVERSE_FILES:
        src = universe / fn
        if not src.exists():
            raise RuntimeError(f"STOP: the universe bundle lacks {fn}")
        sha = _copy_hashed(src, pt / "data" / fn)
        if sha != UNIVERSE_SHA256[fn]:
            raise RuntimeError(f"STOP: bundle {fn} hashes {sha}, pinned "
                               f"{UNIVERSE_SHA256[fn]}")
        bundle[fn] = {"sha256": sha, "bytes": src.stat().st_size,
                      "mtime": datetime.fromtimestamp(src.stat().st_mtime).isoformat(
                          timespec="seconds")}
    cache_real = (ROOT / ".cache").resolve()
    link = pt / ".cache"
    if os.name == "nt":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(cache_real)],
                       check=True, capture_output=True)
    else:
        os.symlink(cache_real, link, target_is_directory=True)
    receipt = {"repro": str(repro), "tree": str(pt), "head": SNAPSHOT_HEAD,
               "snapshot": str(snapshot), "manifest_started": man.get("started"),
               "snapshot_inputs": inputs, "universe_dir": str(universe),
               "universe": bundle, "cache": str(cache_real),
               "prepared_in_s": round(time.time() - t0, 1)}
    receipt_path.write_text(json.dumps(receipt, indent=1) + "\n", encoding="utf-8",
                            newline="\n")
    return receipt


# ---------------------------------------------------------------------------
# the worker: runs INSIDE the reproduction tree on the snapshot head's modules
# ---------------------------------------------------------------------------

def _install_read_log(pt: Path) -> set[str]:
    opened: set[str] = set()
    keep = (str(pt / "data"), str(pt / "tools"), str(pt / ".cache"), str(pt / "prospects.db"))

    def hook(event, args):
        if event == "open":
            path, mode, flags = args[0], args[1], args[2]
            if not isinstance(path, str):
                return
            if mode is None:
                if flags & (os.O_WRONLY | os.O_RDWR):
                    return
            elif any(c in str(mode) for c in "wax+"):
                return
            if path.startswith(keep):
                opened.add(path)
        elif event == "sqlite3.connect":
            db = args[0]
            if isinstance(db, str) and db.startswith(keep):
                opened.add(db)
    sys.addaudithook(hook)
    return opened


def _person_id(row: dict):
    v = row.get("mlbam_id")
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _split_touched(row: dict) -> bool:
    ids = {_person_id(row)}
    try:
        ids.add(int(row.get("record_mlbam_id")))
    except (TypeError, ValueError):
        pass
    return row.get("player_key") in SPLIT_KEYS or bool(ids & SPLIT_IDS)


def _rows_at_or_after_v(mat: list[dict], frame_keys: set) -> dict:
    """The matrix rows lv_scores leaves out of v1's training by its own rule
    (decision_year < V): named, so the receipt shows no feature of theirs is read. A
    frame row with the same player key (a V 2026 list player whose matrix row is dated
    after the window) is scored from its own in-window drivers, never from that row."""
    late = [r for r in mat if int(r["decision_year"]) >= VINTAGE]
    return {"n": len(late),
            "decision_years": sorted({int(r["decision_year"]) for r in late}),
            "player_keys": sorted(r["player_key"] for r in late),
            "in_frame": sorted(r["player_key"] for r in late
                               if r["player_key"] in frame_keys),
            "note": ("left out of v1's training by efv_v2_model.lv_scores "
                     "(decision_year < V); no feature read; a frame row of the same "
                     "key is scored from its own in-window drivers")}


def _head_receipt(head: dict | None) -> dict | None:
    if head is None:
        return None
    adm = head.get("admission") or {}
    return {"keys": list(head.get("keys") or []), "alpha": _jsonable(head.get("alpha")),
            "n_train": head.get("n_train"), "trained_on": head.get("trained_on"),
            "b_uc": head.get("b_uc"), "beta": list(head.get("beta") or []),
            "candidates": list(head.get("candidates") or []),
            "admitted": sorted(k for k, v in adm.items()
                               if isinstance(v, dict) and v.get("admitted")),
            "admission": _jsonable(adm)}


def worker(repro: Path, out: Path) -> None:
    pt = (Path(repro) / "prospect-tracker").resolve()
    here = Path(__file__).resolve().parent
    sys.path[:] = [p for p in sys.path
                   if Path(p or ".").resolve() not in (here, ROOT, ROOT / "tools")]
    sys.path.insert(0, str(pt / "tools"))
    sys.path.insert(0, str(pt))
    os.chdir(pt)
    opened = _install_read_log(pt)
    import numpy as np
    import efv_dataset as D
    import efv_drivers as DRV
    import efv_labels as L
    import efv_model as V1
    import efv_v2_model as H
    import efv_vintage_frame as F
    import source_backtest as SB
    import storage
    import war_source
    import efv_v2_assemble as ASM
    for m in (D, DRV, L, V1, H, F, SB, storage, war_source, ASM):
        if not Path(m.__file__).resolve().is_relative_to(pt):
            raise RuntimeError(f"{m.__name__} imported from {m.__file__}, not the "
                               f"reproduction tree")
    asserted = {"resolved_through": int(D.RESOLVED_THROUGH),
                "default_provider": str(war_source.DEFAULT_PROVIDER),
                "reserved_lv": sorted(F.RESERVED_LV),
                "r_vm_first_debut_year": int(F.R_VM_FIRST_DEBUT_YEAR),
                "reserved_vm_pins": F.reserved_vm_pins(),
                "dev_vintages": list(F.DEV_VINTAGES),
                "debut_years_last": int(max(D.DEBUT_YEARS)),
                "current_season": int(D.CURRENT_SEASON),
                "milb_floor_lv": int(F.MILB_FLOOR_LV),
                "milb_floor_withheld": sorted(F.MILB_FLOOR_LV_WITHHELD),
                "consensus_key": SB.CONSENSUS_KEY,
                "rule_last_year": int(H.RULE_LAST_YEAR),
                "modules": {m.__name__: str(Path(m.__file__).relative_to(pt))
                            for m in (D, DRV, L, V1, H, F, SB, storage, war_source, ASM)}}
    if asserted["resolved_through"] != EXPECTED_RESOLVED_THROUGH:
        raise RuntimeError(f"STOP: RESOLVED_THROUGH is {asserted['resolved_through']}, "
                           f"the snapshot head must hold {EXPECTED_RESOLVED_THROUGH}")
    if asserted["default_provider"] != EXPECTED_PROVIDER:
        raise RuntimeError(f"STOP: DEFAULT_PROVIDER is {asserted['default_provider']!r}, "
                           f"the snapshot head must hold {EXPECTED_PROVIDER!r}")
    if asserted["reserved_vm_pins"] or set(F.DEV_VINTAGES) & F.RESERVED_LV \
            or VINTAGE in F.RESERVED_LV:
        raise RuntimeError("STOP: a reserved frame would be read")
    for fn in UNIVERSE_FILES:
        sha = sha256_file(pt / "data" / fn)
        if sha != UNIVERSE_SHA256[fn]:
            raise RuntimeError(f"STOP: {fn} in the reproduction tree is not the bundle")
    t0 = time.time()
    universe = F.load_universe()
    # the career_war basis the labels read (counts by the stored `source` per row)
    table = storage.load_career_war()
    by_source: dict = {}
    for agg in table.values():
        s = str((agg or {}).get("source"))
        by_source[s] = by_source.get(s, 0) + 1
    label = {"provider": L.provider(), "resolved_through": L.resolved_through(),
             "career_war_table": {"rows": len(table), "by_source": by_source,
                                  "read_through": "storage.load_career_war on the "
                                                  "snapshot's prospects.db"},
             "used_for": ("W3 and R3 labels of the F-LV training vintages 2011-2019 "
                          "and the v1 matrices' labels; no label of any 2026 row")}
    # training frames (dev vintages, sidecars, labels) exactly as the assembly builds them
    frames = ASM.build_frames()
    train_receipt: dict = {}
    for side in SIDES:
        rec = {}
        for V, (rows, labs) in sorted(frames[side].items()):
            st: dict = {}
            for lab in labs:
                st[str(lab.get("status"))] = st.get(str(lab.get("status")), 0) + 1
            rec[str(V)] = {"frame_rows": len(rows),
                           "labelled_w3_r3": sum(1 for lab in labs
                                                 if lab.get("w3") is not None
                                                 and lab.get("r3") is not None),
                           "status": st}
        train_receipt[side] = rec
    # the lv_2026 frame on the bundle universe, with the V2 sidecars
    tx = DRV.load_league_transactions(VINTAGE - 1)
    panel = DRV.load_bio_panel()
    weights = H.load_weights()
    assembly_sha = sha256_file(pt / "data" / "efv_v2_assembly.json")
    eta_doc = json.loads((pt / "data" / "eta_eval.json").read_text(encoding="utf-8"))
    shadow = eta_doc[ETA_BLOCK[0]][ETA_BLOCK[1]]
    shadow_rows = {r["player_key"]: r for r in shadow["rows"]}
    sides_out: dict = {}
    for side in SIDES:
        F.guard_score_request(VINTAGE, purpose="SG_4B freeze")
        rows = F.build_frame(side, VINTAGE, universe=universe)
        DRV.protection_for_frame(rows, index=tx)
        DRV.bmi_for_rows(rows, panel=panel)
        DRV.pl_revision_for_rows(rows)
        keys = {r["player_key"] for r in rows}
        train = H.lv_training_rows(side, frames[side])
        excluded = [r for r in train if r["player_key"] in keys]
        sc2 = H.v2_lv_scores(side, VINTAGE, rows, train, weights=weights)
        model = sc2["model"]
        v2 = {p["player_key"]: p for p in sc2["rows"]}
        test = H.lv_v2_rows(side, VINTAGE, rows)
        rng = np.random.default_rng(TWIN_SEED)
        perm = rng.permutation(len(test))
        twin_rows = [dict(test[i], feats=test[j]["feats"], extra=test[j]["extra"],
                          v2=test[j]["v2"]) for i, j in enumerate(perm)]
        twin = {p["player_key"]: p for p in H.predict_v2(model, twin_rows)}
        mat = H.training_rows(side)
        sc1 = H.lv_scores(side, VINTAGE, rows, data=mat)
        out_rows = []
        eta_joined = eta_absent = eta_late = 0
        for r in rows:
            k = r["player_key"]
            lo, hi = r["window"]
            g = r.get("grades") or {}
            sh = shadow_rows.get(k)
            eta = None
            if sh is None:
                eta_absent += 1
            elif str(sh.get("listing_date"))[:10] < hi:
                eta = {f: sh.get(f) for f in ETA_FIELDS}
                eta_joined += 1
            else:
                eta_late += 1
            p2 = v2.get(k)
            pt2 = twin.get(k)
            out_rows.append({
                "player_key": k,
                "person_id": _person_id(r),
                "id_how": r.get("id_how"),
                "id_candidates": r.get("id_candidates"),
                "record_mlbam_id": r.get("record_mlbam_id"),
                "side": side, "vintage": int(r["vintage"]),
                "window": [lo, hi],
                "asof_date": r.get("asof_date"),
                "source_dates": list(r.get("source_dates") or []),
                "real_sources": list(r.get("real_sources") or []),
                "position": r.get("position"),
                "birth_date": r.get("birth_date"),
                "milb_last_season": r.get("milb_last_season"),
                "milb_floor": r.get("milb_floor"),
                "milb_block": bool(r.get("milb")),
                "protection": {"cutoff": r.get("protection_cutoff"),
                               "observed": r.get("protection_observed"),
                               "on_40man_at_v": r.get("on_40man_at_v"),
                               "nov_add_v_minus_1": r.get("nov_add_v_minus_1")},
                "bmi_at_read": r.get("bmi_at_read"),
                "bmi_asof_date": r.get("bmi_asof_date"),
                "pl_rev_at_read": r.get("pl_rev_at_read"),
                "grades": {name: g.get(src) for src, name in GRADE_KEYS},
                "efv_v1": sc1["v1"].get(k) if sc1.get("status") == "ok" else None,
                "v2": ({f: p2[f] for f in V2_ROW_FIELDS} if p2 else None),
                "twin": ({f: pt2[f] for f in V2_ROW_FIELDS} if pt2 else None),
                "eta": eta,
                "recount_split": _split_touched(r),
            })
        sides_out[side] = {
            "rows": out_rows,
            "counts": {"rows": len(rows),
                       "person_ids": sum(1 for r in rows if _person_id(r) is not None),
                       "with_consensus": sum(1 for r in rows
                                             if (r.get("grades") or {}).get(
                                                 SB.CONSENSUS_KEY) is not None),
                       "v2_scored": len(v2), "twin_scored": len(twin),
                       "v1_scored": len(sc1.get("v1") or {}),
                       "eta_joined": eta_joined, "eta_absent": eta_absent,
                       "eta_listing_at_or_after_window_end": eta_late},
            "v2_model": _jsonable(model),
            "v2_fold_receipt": {
                "n_train": sc2["n_train"], "n_scored": sc2["n_scored"],
                "train_years": model.get("train_years"),
                "n_train_excluded_in_frame_rows": len(excluded),
                "n_train_excluded_in_frame_players": len({r["player_key"]
                                                          for r in excluded}),
                "excluded_vintages": sorted({int(r["decision_year"]) for r in excluded}),
                "w_skill": model.get("w_skill"), "w_time": model.get("w_time"),
                "consensus_only": model.get("consensus_only"),
                "consensus_only_reason": model.get("consensus_only_reason"),
                "skill_head": _head_receipt(model.get("skill")),
                "timing_head": _head_receipt(model.get("timing")),
                "war_map": _jsonable(model.get("war_map")),
                "absence_admitted": bool(H.absence_admitted(side))},
            "v1_receipt": {"status": sc1.get("status"), "n_train": sc1.get("n_train"),
                           "n_train_excluded_in_frame": sc1.get(
                               "n_train_excluded_in_frame"),
                           "matrix_rows": len(mat),
                           "decision_years": sorted({int(r["decision_year"])
                                                     for r in mat}),
                           "train_decision_years": sorted({
                               int(r["decision_year"]) for r in mat
                               if int(r["decision_year"]) < VINTAGE}),
                           "rows_at_or_after_v": _rows_at_or_after_v(mat, keys),
                           "blend_lambda": V1.blend_lambda(side)},
        }
    files = {}
    for p in sorted(opened):
        q = Path(p)
        if not q.is_file():
            continue
        rel = str(q.relative_to(pt)) if q.is_relative_to(pt) else p
        if q.name == "prospects.db":
            files[rel] = {"bytes": q.stat().st_size, "sha256": "see snapshot.inputs"}
        else:
            files[rel] = {"bytes": q.stat().st_size, "sha256": sha256_file(q)}
    res = {"asserted": asserted, "label": label, "training_frames": train_receipt,
           "weights": weights, "assembly_sha256": assembly_sha,
           "eta_block": {"keys": list(ETA_BLOCK), "frozen": shadow.get("frozen"),
                         "score_not_before": shadow.get("score_not_before"),
                         "rows": len(shadow["rows"]),
                         "rows_listed_before_window_close": sum(
                             1 for r in shadow["rows"]
                             if str(r.get("listing_date"))[:10] < f"{VINTAGE}-05-01")},
           "sides": sides_out, "files_read": files,
           "elapsed_s": round(time.time() - t0, 1)}
    Path(out).write_text(json.dumps(_jsonable(res), indent=1) + "\n", encoding="utf-8",
                         newline="\n")


# ---------------------------------------------------------------------------
# the driver
# ---------------------------------------------------------------------------

def recount(retaken: dict, sides: dict) -> tuple[dict | None, dict]:
    """Rule (4). Returns (recount block or None when every count equals s2.2, the
    matched rows per side). Raises RuntimeError ending 'BLOCKER: SG_4B recount'."""
    equal = all(retaken[s][k] == S22_COUNTS[s][k] for s in SIDES
                for k in ("rows", "person_ids"))
    if equal:
        return None, {s: sides[s]["rows"] for s in SIDES}
    block: dict = {"snapshot_counts": S22_COUNTS, "retaken": retaken, "difference": {},
                   "split_commit": SPLIT_COMMIT, "split_keys": sorted(SPLIT_KEYS),
                   "split_ids": sorted(SPLIT_IDS), "marked": {}, "excluded_rows": {},
                   "bound": RECOUNT_MAX}
    matched: dict = {}
    for s in SIDES:
        d_rows = retaken[s]["rows"] - S22_COUNTS[s]["rows"]
        d_ids = retaken[s]["person_ids"] - S22_COUNTS[s]["person_ids"]
        marked = [r for r in sides[s]["rows"] if r["recount_split"]]
        block["difference"][s] = {"rows": d_rows, "person_ids": d_ids}
        block["marked"][s] = len(marked)
        block["excluded_rows"][s] = [{"player_key": r["player_key"],
                                      "record_mlbam_id": r["record_mlbam_id"],
                                      "person_id": r["person_id"]} for r in marked]
        ok = (abs(d_rows) <= RECOUNT_MAX and abs(d_ids) <= RECOUNT_MAX
              and abs(d_rows) <= len(marked) and abs(d_ids) <= len(marked))
        if not ok:
            raise RuntimeError(
                f"the re-taken lv_2026 counts differ from s2.2 beyond what the identity "
                f"split explains on side {s}: rows {S22_COUNTS[s]['rows']} -> "
                f"{retaken[s]['rows']} ({d_rows:+d}), person ids "
                f"{S22_COUNTS[s]['person_ids']} -> {retaken[s]['person_ids']} "
                f"({d_ids:+d}), rows marked recount_split {len(marked)}; nothing "
                f"written. BLOCKER: SG_4B recount")
        matched[s] = [r for r in sides[s]["rows"] if not r["recount_split"]]
    return block, matched


def assemble(worker_out: dict, receipt: dict, *, repro: Path) -> dict:
    retaken = {s: {"rows": worker_out["sides"][s]["counts"]["rows"],
                   "person_ids": worker_out["sides"][s]["counts"]["person_ids"]}
               for s in SIDES}
    rc, matched = recount(retaken, worker_out["sides"])
    rows_out = {}
    for s in SIDES:
        rows_out[s] = []
        for r in matched[s]:
            rr = dict(r)
            if rc is None:
                rr.pop("recount_split", None)
            rows_out[s].append(rr)
    head = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    code = {p: _git("rev-parse", f"{SNAPSHOT_HEAD}:prospect-tracker/{p}") for p in CODE_PINS}
    if code["data/efv_v2_assembly.json"] != ASSEMBLY_BLOB:
        raise RuntimeError(f"STOP: data/efv_v2_assembly.json at {SNAPSHOT_HEAD} is blob "
                           f"{code['data/efv_v2_assembly.json']}, s2.2 names "
                           f"{ASSEMBLY_BLOB}")
    v2_models = {s: worker_out["sides"][s]["v2_model"] for s in SIDES}
    doc = {
        "schema": 1,
        "frame": FRAME,
        "vintage": VINTAGE,
        "frozen_by": FROZEN_BY,
        "task": TASK,
        "frozen_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "gate": {"doc": "docs/efv-v2/SURROGATE_2026_GATE.md",
                 "items": ["Q5", "s2.2", "s4", "s8.13", "s11"],
                 "owner_answers": {"efv2026 OQ1": "A", "efv2026 OQ2": "A",
                                   "SG4B-Q1": "the efv2026 lane universe bundle",
                                   "SG4B-Q2": "A"}},
        "head_at_freeze": head,
        "branch_at_freeze": branch,
        "step_z_entry": step_z_entry(),
        "snapshot": {"path": SNAPSHOT_REL, "absolute": receipt["snapshot"],
                     "manifest_head": SNAPSHOT_HEAD, "step_a_commit": STEP_A_COMMIT,
                     "started": receipt.get("manifest_started"),
                     "inputs": receipt["snapshot_inputs"],
                     "unused": list(SNAPSHOT_UNUSED),
                     "note": ("every file the snapshot MANIFEST lists, sha-verified; the "
                              "two marked materialized False are present but not read, "
                              "because the universe comes from the bundle whole")},
        "universe": {"source": "efv2026 lane bundle (surr_work/universe)",
                     "dir": receipt["universe_dir"], "files": receipt["universe"],
                     "is_step_a_snapshot": False, "note": UNIVERSE_NOTE},
        "code": {"commit": SNAPSHOT_HEAD, "blobs": code,
                 "tool": TOOL, "tool_sha256": sha256_file(Path(__file__)),
                 "reproduction_tree": str(repro)},
        "asserted": worker_out["asserted"],
        "label": worker_out["label"],
        "training_frames": worker_out["training_frames"],
        "v2_object": {"name": V2_OBJECT_NAME,
                      "assembly_blob": ASSEMBLY_BLOB,
                      "assembly_sha256_working_tree": worker_out["assembly_sha256"],
                      "weights": worker_out["weights"],
                      "sha256": canonical_sha256(v2_models),
                      "sha256_by_side": {s: canonical_sha256(v2_models[s]) for s in SIDES},
                      "fold_receipt": {s: worker_out["sides"][s]["v2_fold_receipt"]
                                       for s in SIDES},
                      "model": v2_models,
                      "row_fields": list(V2_ROW_FIELDS),
                      "note": ("fitted by efv_v2_model.v2_lv_scores at the snapshot "
                               "head on efv_v2_model.lv_training_rows over the labelled "
                               "F-LV vintages 2011-2019, every lv_2026 player left out "
                               "of training; e_skill and e_time are the per-row head "
                               "indices (s4, s7)")},
        "efv_v1": {"name": "eFV v1 forward-chained at decision years up to 2025",
                   "receipt": {s: worker_out["sides"][s]["v1_receipt"] for s in SIDES},
                   "note": ("efv_v2_model.lv_scores at the snapshot head: v1's own fold "
                            "scorer on the matrix rows with decision year before 2026, "
                            "every lv_2026 player left out")},
        "twin": {"seed": TWIN_SEED,
                 "method": ("the non-consensus driver columns (feats, extra, v2) of the "
                            "scored lv_2026 rows permuted within the vintage, one "
                            "permutation per side from numpy default_rng(seed), and "
                            "scored by the same fitted fold object; the consensus "
                            "percentile u_c stays on its own row"),
                 "row_fields": list(V2_ROW_FIELDS)},
        "eta_shadow": dict(worker_out["eta_block"], fields=list(ETA_FIELDS), note=ETA_NOTE,
                           joined={s: worker_out["sides"][s]["counts"]["eta_joined"]
                                   for s in SIDES},
                           absent={s: worker_out["sides"][s]["counts"]["eta_absent"]
                                   for s in SIDES},
                           listing_at_or_after_window_end={
                               s: worker_out["sides"][s]["counts"][
                                   "eta_listing_at_or_after_window_end"] for s in SIDES}),
        "grades": {"keys": [n for _s, n in GRADE_KEYS],
                   "note": "the in-window grades as efv_vintage_frame.frame_row reads them"},
        "counts": {"s2_2": S22_COUNTS, "s2_2_at_draft": S22_COUNTS_AT_DRAFT,
                   "s2_2_amendment": S22_AMENDMENT, "retaken": retaken,
                   "detail": {s: worker_out["sides"][s]["counts"] for s in SIDES},
                   "matched": {s: {"rows": len(rows_out[s]),
                                   "person_ids": sum(1 for r in rows_out[s]
                                                     if r["person_id"] is not None)}
                               for s in SIDES}},
        "recount": rc,
        "rules": {"re_freeze": "refused once this file exists (SG_4 rule 1)",
                  "outcome_columns": "none: no label, debut flag, WAR or 2026 season line",
                  "window": ("[V-01-01, min(V-05-01, an April debut)) as "
                             "efv_vintage_frame.window_bounds defines it (s2.2); the "
                             "only date a row carries beyond its read dates")},
        "inputs_read": worker_out["files_read"],
        "elapsed_s": worker_out["elapsed_s"],
        "rows": rows_out,
    }
    doc["rows_sha256"] = canonical_sha256(doc["rows"])
    return doc


def write_freeze(doc: dict, path: Path = OUT) -> None:
    refuse_if_frozen(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(_jsonable(doc), indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--snapshot", type=Path, default=ROOT.parent / "_pre_epoch_fwar_2026-10",
                    help="the step A snapshot directory (MANIFEST.json beside its files)")
    ap.add_argument("--universe", type=Path, required=False,
                    help="the efv2026 lane universe bundle directory (SG4B-Q1)")
    ap.add_argument("--repro", type=Path, required=False,
                    help="scratch directory for the reproduction tree")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--out", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--force-prepare", action="store_true",
                    help="rebuild the reproduction tree even when its receipt exists")
    a = ap.parse_args(argv)
    if a.worker:
        worker(a.repro, a.out)
        return 0
    refuse_if_frozen(OUT)
    if a.universe is None or a.repro is None:
        ap.error("--universe and --repro are required")
    if not (Path(a.snapshot) / "MANIFEST.json").exists():
        raise RuntimeError(f"STOP: the step A snapshot {a.snapshot} is missing")
    step_z_entry()
    receipt = prepare_repro(a.repro, Path(a.snapshot), Path(a.universe),
                            force=a.force_prepare)
    worker_out_path = Path(a.repro) / "worker_out.json"
    cmd = [sys.executable, str(Path(__file__).resolve()), "--worker", "--repro",
           str(a.repro), "--out", str(worker_out_path)]
    r = subprocess.run(cmd, cwd=receipt["tree"])
    if r.returncode != 0:
        raise RuntimeError(f"the worker failed with rc {r.returncode}; nothing written")
    worker_out = json.loads(worker_out_path.read_text(encoding="utf-8"))
    doc = assemble(worker_out, receipt, repro=Path(a.repro))
    write_freeze(doc, OUT)
    print(f"wrote {OUT} sha256 {sha256_file(OUT)}")
    for s in SIDES:
        c = doc["counts"]
        print(f"  {s}: rows {c['retaken'][s]['rows']} (s2.2 {S22_COUNTS[s]['rows']}), "
              f"person ids {c['retaken'][s]['person_ids']} (s2.2 "
              f"{S22_COUNTS[s]['person_ids']}), matched {c['matched'][s]['rows']}, "
              f"eta joined {doc['eta_shadow']['joined'][s]}")
    print(f"  v2 object sha256 {doc['v2_object']['sha256']}; recount "
          f"{'none' if doc['recount'] is None else 'recorded'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
