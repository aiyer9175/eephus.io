# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eFV progress ledger (EV-00, docs/efv-v2/PROGRAM.md s5).

data/efv_progress.json is the dated record the glossary Source Comparison view
charts: one row per (frame, measured state) of eFV against PROSPX consensus,
MLB Pipeline and FanGraphs. The owner asked on 2026-09-24 to be able to watch
the eFV redo make progress, or fail to, on that page; this is the record.

HONEST BY CONSTRUCTION (PROGRAM.md s5.1):

1. THIS LAYER COMPUTES NO STATISTIC. Every number in a row is copied from a
   named key of a named artifact (data/source_backtest.json,
   data/xfv_scoreboard_eval.json, and for development reads the artifacts in
   DEV_ARTIFACTS: data/efv_v2_dev_eval.json and its `ds16` block,
   data/efv_overlay_oos_eval.json and data/efv_v2_pbust_eval.json, and the MC-5
   pricing read data/efv_v2_pricing_calibration_eval.json), and the row
   stores each artifact's path,
   generated_at and sha256. The only things computed here are a content hash
   and a timestamp.
2. CIs come from the producer (source_backtest._paired_delta_ci), never from
   here.
3. APPEND-ONLY. update() builds a candidate row for every frame the artifacts
   carry, compares its content hash with that frame's last row, appends on a
   change and otherwise only moves that row's last_verified_at. A nightly run
   with no change adds no row.
4. Tilted frames are rows with role "tilted". They are never the headline and
   the page never charts them. A frame that lost the headline (vm1, role
   "superseded" since 2026-09-25, owner answer FP3-1) keeps its rows as
   history in the table and is not charted either.

WHY THERE IS A SECOND, UNTRACKED COPY. The deploy box runs `git checkout -- .`
before every nightly pull (deploy/nightly-build.sh), which is how the public
betting record was once reverted every night. A ledger row appended on the box
would be lost the same way, so every row is also appended to
.cache/efv_progress/ledger.jsonl (untracked, survives the checkout) and update()
merges rows from there back in before it compares. The served file is the
union; nothing is ever dropped from either copy.

Strata: rows carry n by side (hit, pit) and nothing finer. No key or stratum
is named after a consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md).

The scoreboard matrix (EFV3_D3, SP/efv3/LANE_D.md s3.7). The headline row and the
DS-16 development row carry an optional `matrix` pointer into
data/efv_matrix_eval.json (tools/efv_matrix.py): the artifact's path, file sha256
and generated_at, the frame block's id, Family S's k and the producer's reading
counts, every one copied. A look row copies the same shape from
data/efv_v2_gate.json `strata` once the look runner has written it (EFV3_D6).
The pointer joins the content hash only when present, so a row is appended when
the matrix state changes and every earlier row keeps its hash. No stratum cell
enters a row: the counts are the producer's and the ledger adds nothing to them.
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("efv_progress")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "efv_progress.json"
LEDGER_PATH = ROOT / ".cache" / "efv_progress" / "ledger.jsonl"
SB_NAME = "source_backtest.json"
SC_NAME = "xfv_scoreboard_eval.json"
#: EV-09: the development read of eFV v2 champion H0 (tools/efv_v2_dev_read.py).
DEV_NAME = "efv_v2_dev_eval.json"
#: dev-artifact frame id -> ledger frame id (both development).
DEV_FRAMES = ("vm_dev", "lv_dev")
#: ledger rater name -> rater name in the dev artifact. `efv` is the candidate.
DEV_RATERS = (("efv", "efv_v2_h0"), ("efv_v1", "efv_v1"),
              ("prospx_consensus", "prospx_consensus"),
              ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
#: ledger delta name -> comparison name in the dev artifact.
DEV_DELTAS = (("vs_prospx_consensus", "h0_vs_prospx_consensus"),
              ("vs_efv_v1", "h0_vs_efv_v1"),
              ("vs_mlb_pipeline", "h0_vs_mlb_pipeline"),
              ("vs_fangraphs", "h0_vs_fangraphs"),
              ("efv_v1_vs_prospx_consensus", "efv_v1_vs_prospx_consensus"))
#: DS-11: the out-of-sample read of eFV v1's served overlays
#: (tools/efv_overlay_oos_read.py). Its frame and rater names are already the ledger's.
OVERLAY_NAME = "efv_overlay_oos_eval.json"
#: DS-17: the P(bust) chip's calibration read (tools/efv_pbust_read.py). Its raters carry
#: an AUC for reaching the majors and no Spearman, so its rows sit in the table and never
#: on the chart (the chart plots the Spearman delta).
PBUST_NAME = "efv_v2_pbust_eval.json"
_SAME_RATERS = (("efv", "efv"), ("efv_v1", "efv_v1"),
                ("prospx_consensus", "prospx_consensus"),
                ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
_SAME_DELTAS = (("vs_prospx_consensus", "vs_prospx_consensus"),
                ("vs_efv_v1", "vs_efv_v1"),
                ("efv_v1_vs_prospx_consensus", "efv_v1_vs_prospx_consensus"))
#: DS-16: the one pre-declared development read of the assembled Driver System V2
#: (tools/efv_v2_dev_read.py --ds16), kept under the key `ds16` of the H0 artifact. Its
#: rows carry the registered PRIMARY statistic (within (side, vintage) Spearman,
#: docs/efv-v2/EFV_V2_GATE.md s3) in `spearman`, name it in `statistic`, and carry the
#: pooled secondary beside it in `secondary`.
DS16_SUBKEY = "ds16"
V2_RATERS = (("efv", "efv_v2"), ("efv_v1", "efv_v1"),
             ("prospx_consensus", "prospx_consensus"),
             ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
V2_DELTAS = (("vs_prospx_consensus", "v2_vs_prospx_consensus"),
             ("vs_efv_v1", "v2_vs_efv_v1"),
             ("vs_mlb_pipeline", "v2_vs_mlb_pipeline"),
             ("vs_fangraphs", "v2_vs_fangraphs"),
             ("efv_v1_vs_prospx_consensus", "efv_v1_vs_prospx_consensus"))
#: The screening lab (tools/efv_screen_lab.py, EFV3 lane B s5): one development row per
#: measured arm, model_id "efv_v2_screen:wave<n>:<candidate>:<side>", resolvable null.
#: The artifact carries `arms[]`, each with a `frame` block in the DS-16 shape and a
#: `screening` block the row copies; screen_arm_docs splits it into one document per
#: arm. An arm whose screening.exploratory is true never lands a row (the exploratory
#: run writes outside data/, and a copy that strays in is still refused here).
SCREEN_NAME = "xfv_screen_wave1.json"
SCREEN_MODEL_PREFIX = "efv_v2_screen:"
SCREEN_RATERS = (("efv", "efv_v2_candidate"), ("efv_v2_base", "efv_v2_base"),
                 ("prospx_consensus", "prospx_consensus"),
                 ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
SCREEN_DELTAS = (("vs_efv_v2_base", "candidate_vs_efv_v2_base"),
                 ("vs_prospx_consensus", "candidate_vs_prospx_consensus"),
                 ("efv_v2_base_vs_prospx_consensus", "efv_v2_base_vs_prospx_consensus"))
#: The admission numbers a screening arm's delta leg carries beside delta, ci95 and mde95
#: (tools/efv_screen_lab.py: lb95 = delta - mde95, the head's floor on that side, the
#: one-sided permutation p and its Holm-adjusted p). Copied on a screening row only, when
#: the leg carries them, so no other development row's content or hash moves (EFV3_B8).
SCREEN_LEG_FIELDS = ("lb95", "floor", "p_perm", "holm_p")
#: Every development artifact the ledger copies from: (file, its frames, rater map,
#: delta map, sub-document key or None). Each frame must be registered in FRAMES with
#: role "development".
DEV_ARTIFACTS = ((DEV_NAME, DEV_FRAMES, DEV_RATERS, DEV_DELTAS, None),
                 (OVERLAY_NAME, ("vm_oos_dev",), _SAME_RATERS, _SAME_DELTAS, None),
                 (PBUST_NAME, ("vm_oos_dev", "lv_dev"), _SAME_RATERS, _SAME_DELTAS, None),
                 (DEV_NAME, DEV_FRAMES, V2_RATERS, V2_DELTAS, DS16_SUBKEY),
                 (SCREEN_NAME, ("lv_dev",), SCREEN_RATERS, SCREEN_DELTAS, None))
#: EFV3_D3: the scoreboard matrix (tools/efv_matrix.py), FRAME x CELL x COMPARATOR x
#: STATISTIC. The headline row points at its vm2 block; the DS-16 development row
#: (the one read the matrix's lv_dev block repeats, tools/efv_v2_dev_read.v2_lv_dev)
#: points at its lv_dev block; no other development row carries a pointer, because
#: the block is a read of a different scored object than that row's. A reserved
#: block (lv_res, vm_pros) is pointed at by a look row only, copied from the look
#: record in data/efv_v2_gate.json.
MATRIX_NAME = "efv_matrix_eval.json"
GATE_NAME = "efv_v2_gate.json"
#: The keys of a `matrix` pointer, in this order; nothing else enters one.
MATRIX_FIELDS = ("artifact", "sha256", "generated_at", "frame_block", "k_family_s",
                 "summary")
#: EFV3_C05: the MC-5 pricing read (tools/efv_v2_pricing_calibration.py), one development
#: row per frame, model_id efv_v2_pricing_pos_age, metric "mae". A pricing item, not a rank
#: item: the row carries no rater and no delta (its order is V2's own, bit for bit), and
#: its MAE numbers ride in `pricing`, copied from the artifact's frame block.
PRICING_NAME = "efv_v2_pricing_calibration_eval.json"
PRICING_FRAMES = ("lv_dev", "vm_dev")
#: The keys of a `pricing` field, copied in this order from the frame block.
PRICING_FIELDS = ("mae_base", "mae_position_age", "delta", "ci95", "sd",
                  "mean_resid_base", "mean_resid_new")

SCHEMA = 1
MODEL_ID = "efv_v1"
TRIGGERS = ("nightly", "efv_change", "look", "backfill", "harness_correction",
            "data_correction", "frame_change")
#: Triggers whose rows record a CORRECTION, never a change to the model's
#: specification: a fix to how eFV is scored (harness_correction, DS-01, bug B1
#: in docs/efv-v2/DRIVER_SYSTEM_V2.md) or to the rows it is trained and scored
#: on (data_correction, DS-12 and DS-13). The page marks them apart from model
#: progress.
CORRECTION_TRIGGERS = ("harness_correction", "data_correction")
#: Triggers whose rows record a change of the HEADLINE FRAME (owner answer FP3-1,
#: 2026-09-25: vm2 replaced vm1). The same model measured on the frame that now
#: carries the headline; never model progress, and the page marks it apart.
FRAME_CHANGE_TRIGGERS = ("frame_change",)
REGEN_CMD = ("python -c \"import efv_progress as P; P.update(trigger='efv_change')\" "
             "(nightly: run_monthly after the 9g scoreboard refresh and after "
             "run_source_backtest; by hand: tools/efv_scoreboard.py)")

#: The frame registry (PROGRAM.md s5.1). `role` decides where a row may appear:
#: headline and development rows are charted, reserved rows are charted as
#: looks, tilted rows are never charted and never the headline, secondary rows
#: sit in the table only.
FRAMES = {
    # vm1, the headline until 2026-09-25. Superseded by vm2 (owner answer FP3-1):
    # its rows stay in the ledger as history, sit in the table and are never
    # charted, because on some of them eFV's consensus input was read after the
    # raters' preseason window.
    "vm": {"basis_key": "pooled_efv_common_vintage_matched", "role": "superseded",
           "tilted": False,
           "label": "Vintage-matched (vm1)",
           "note": ("superseded 2026-09-25 by the timing-pinned frame: eFV's "
                    "consensus input was read at its matrix date, after the "
                    "raters' preseason window on some rows")},
    # EV-01 (PROGRAM.md s3.4): the same frame with eFV's consensus input pinned
    # to the raters' preseason read. The headline since 2026-09-25 (FP3-1).
    "vm2": {"basis_key": "pooled_efv_common_vintage_matched_vm2",
            "role": "headline", "tilted": False,
            "label": "Vintage-matched, timing-pinned",
            "note": ("timing-pinned: eFV's consensus input is the raters' own "
                     "preseason read; the headline since 2026-09-25")},
    # EV-09 (PROGRAM.md s3.4): development reads of a v2 candidate. Both frames are
    # spent; their rows are charted hollow and adjudicate nothing.
    "vm_dev": {"role": "development", "tilted": False,
               "label": "Vintage-matched, development",
               "note": "development frame, spent, not a claim"},
    "lv_dev": {"role": "development", "tilted": False,
               "label": "List vintage, development",
               "note": "development frame, spent, not a claim"},
    # DS-11 / DS-17: eFV v1's own forward-chained training pool (debuted rows and
    # resolved busts, each decision year scored by a fit on earlier years). Spent;
    # table only, never charted, because it is not the vintage-matched comparison.
    "vm_oos_dev": {"role": "development", "tilted": False,
                   "label": "v1 out-of-sample pool, development",
                   "note": "development frame, spent, not a claim"},
    "lv_res": {"role": "reserved", "tilted": False,
               "label": "List vintage, reserved"},
    "vm_pros": {"role": "reserved", "tilted": False,
                "label": "Vintage-matched, prospective"},
    "predebut": {"basis_key": "pooled_efv_common_predebut", "role": "tilted",
                 "tilted": True, "tilt_toward": "efv",
                 "label": "Pre-debut reads"},
    "all_vintages": {"basis_key": "pooled_efv_common", "role": "tilted",
                     "tilted": True, "tilt_toward": "consensus",
                     "label": "All base years"},
    "disagreement": {"role": "secondary", "tilted": False,
                     "label": "Biggest disagreements",
                     "note": "latest pre-debut consensus read"},
    # SG_5 (efv2026 plan item N7; the 2026 surrogate gate draft, s6.2 and s6.3):
    # the frozen 2026 preseason list's frames. Registered before any read so a row
    # can only ever land as tilted or secondary: none is charted (CHART_FRAMES) and
    # none carries a basis_key, so none can become the headline. No row exists yet.
    # Under efv2026 OQ2 = A no one-season surrogate read ever runs, so
    # lv_2026_surrogate stays a registered frame with no row.
    "lv_2026_surrogate": {"role": "tilted", "tilted": True,
                          "tilt_toward": ("efv on arrival via the timing head; "
                                          "stat readers on production"),
                          "label": "List vintage 2026, one-season surrogate",
                          "note": ("surrogate outcome, tilted by construction, a V2 "
                                   "lead expected by construction, never a claim")},
    "lv_2026_r3": {"role": "tilted", "tilted": True, "tilt_toward": "efv",
                   "label": "List vintage 2026, R3 at RT 2029",
                   "note": "the timing head's own target; tilted, descriptive"},
    "lv_2026_w3": {"role": "secondary", "tilted": False,
                   "label": "List vintage 2026, W3 at RT 2031",
                   "note": ("the frozen frame's registered long-run primary; never "
                            "the headline")},
}

#: Registered role changes, applied to every stored row of the frame on each
#: commit so the served file, the durable copy and the page agree on what a row
#: is. Only the role moves: the measured content, and so the content hash, is
#: untouched. frame id -> (role before, role after, when and why).
ROLE_CHANGES = {
    "vm": ("headline", "superseded",
           "2026-09-25, owner answer FP3-1: the timing-pinned frame vm2 replaced "
           "vm1 as the headline"),
    "vm2": ("headline_candidate", "headline",
            "2026-09-25, owner answer FP3-1: promoted from headline candidate"),
}

#: head_to_head_verdict.basis -> ledger frame id.
BASIS_TO_FRAME = {v["basis_key"]: k for k, v in FRAMES.items() if v.get("basis_key")}
#: ledger frame id -> key under accuracy.head_to_head_by_frame and
#: claim_instruments.head_to_head_floors.
BY_FRAME_KEY = {"vm": "vintage_matched", "vm2": "vintage_matched_vm2",
                "predebut": "predebut", "all_vintages": "all_vintages"}
#: The frame version each vintage-matched frame's rows carry: vm1 the frame
#: superseded on 2026-09-25, vm2 the EV-01 timing-pinned headline. Read from the
#: artifact when the artifact says.
DEFAULT_FRAME_VERSION = {"vm": "vm1", "vm2": "vm2"}
#: Frames a chart series may contain. Tilted, secondary and superseded frames
#: never (vm1 left the chart when vm2 took the headline; its rows stay in the
#: table).
CHART_FRAMES = ("vm2", "vm_dev", "lv_dev", "lv_res", "vm_pros")
#: The only strata a row may carry (n_by_side keys).
STRATA = ("hit", "pit")
#: ledger rater name -> rater key in source_backtest.
RATERS = (("efv", "xfv"), ("prospx_consensus", "prospx_consensus"),
          ("mlb_pipeline", "mlb_pipeline"), ("fangraphs", "fangraphs"))
SOURCES_VS = ("prospx_consensus", "mlb_pipeline", "fangraphs")

#: Fields that make up a row's content hash. Commit, date, trigger, sources
#: and last_verified_at are left out on purpose: a new commit or a rerun that
#: measures the same thing is the same state, not progress.
_HASH_FIELDS = ("frame", "frame_version", "window", "n", "n_by_side", "raters",
                "deltas", "resolvable", "verdict", "share")
#: Hashed only when a row carries them (DS-16 development rows; `screening` on the
#: screening lab's rows; `matrix` on the rows that point at the scoreboard matrix,
#: so a changed matrix state appends a row and every earlier row keeps its hash;
#: `metric` and `pricing` on the MC-5 pricing rows, EFV3_C05).
_OPTIONAL_HASH_FIELDS = ("statistic", "secondary", "screening", "matrix", "metric",
                         "pricing")


# ---------------------------------------------------------------------------
# helpers (no statistics)

def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def _rel(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).name


def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def content_hash(row: dict) -> str:
    """sha256 over the measured content of a row (model identity included)."""
    mv = row.get("model_version") or {}
    body = {k: row.get(k) for k in _HASH_FIELDS}
    body["model"] = {"id": row.get("model_id"),
                     "fingerprint": mv.get("fingerprint"),
                     "label": mv.get("label"),
                     "resolved_through": mv.get("resolved_through")}
    # DS-16 rows name their statistic and carry a secondary; the fields enter the hash
    # only when present, so every earlier row keeps its hash.
    for k in _OPTIONAL_HASH_FIELDS:
        if row.get(k) is not None:
            body[k] = row.get(k)
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _label_from_fingerprint(fp: str | None) -> str | None:
    """The eWAR label identity, read out of the board fingerprint string."""
    for part in (fp or "").split("|"):
        if part.startswith("label="):
            return part[len("label="):]
    return None


def _git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short=8", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, check=False, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def current_model_version(commit: str | None = None) -> dict:
    """fingerprint, commit, label and resolved_through of the model in the tree."""
    try:
        import storage
        fp = storage.board_basis_fingerprint()
    except Exception:                                         # noqa: BLE001
        log.warning("board_basis_fingerprint unavailable", exc_info=True)
        fp = None
    try:
        import efv_dataset
        rt = int(efv_dataset.RESOLVED_THROUGH)
    except Exception:                                         # noqa: BLE001
        rt = None
    return {"fingerprint": fp, "commit": commit if commit is not None else _git_commit(),
            "label": _label_from_fingerprint(fp), "resolved_through": rt}


def _rater_block(block: dict | None) -> dict:
    out = {}
    for name, key in RATERS:
        r = (block or {}).get(key) or {}
        if r.get("spearman") is None and r.get("auc") is None:
            continue
        out[name] = {"spearman": r.get("spearman"), "auc": r.get("auc"), "n": r.get("n")}
    return out


def _by_side(floors: dict | None) -> dict | None:
    sides = (floors or {}).get("floor_E_cond_by_side") or {}
    out = {s: (sides.get(s) or {}).get("n") for s in STRATA if (sides.get(s) or {}).get("n")}
    return out or None


def _window(sb: dict) -> list | None:
    ys = ((sb or {}).get("window") or {}).get("years") or []
    return [min(ys), max(ys)] if ys else None


def _finish(row: dict) -> dict:
    row["content_hash"] = content_hash(row)
    return row


def _matrix_pointer(block: dict | None, frame_id: str, *, artifact: str,
                    generated_at: str | None, sha256: str | None) -> dict | None:
    """One `matrix` pointer from a scored frame block (the shape tools/efv_matrix
    .score_frame writes, under `frames` of the matrix artifact or under `strata` of
    the look record). None when the block is absent, reserved and unread, or carries
    no reading counts. Copies only: the counts are the producer's."""
    if not isinstance(block, dict) or block.get("reserved"):
        return None
    summ = block.get("summary") or {}
    counts = summ.get("counts")
    if not isinstance(counts, dict):
        return None
    return {"artifact": artifact, "sha256": sha256, "generated_at": generated_at,
            "frame_block": frame_id, "k_family_s": summ.get("k_family_s"),
            "summary": dict(counts)}


def matrix_pointer(mx: dict | None, frame_id: str, *, path: Path | None = None,
                   sha256: str | None = None) -> dict | None:
    """The `matrix` field of a row on `frame_id`, copied from the matrix artifact's
    frame block of the same id (data/efv_matrix_eval.json). `sha256` is the
    artifact file's, as the row's `sources` carry it."""
    blk = ((mx or {}).get("frames") or {}).get(frame_id)
    return _matrix_pointer(blk, frame_id, artifact=_rel(path) if path else f"data/{MATRIX_NAME}",
                           generated_at=(mx or {}).get("generated_at"), sha256=sha256)


def look_matrix_pointer(gate: dict | None, frame_id: str, *, path: Path | None = None,
                        sha256: str | None = None) -> dict | None:
    """The `matrix` field of a look row on a reserved frame, copied from the look
    record's `strata` block (data/efv_v2_gate.json, written once by the look runner,
    EFV3_D6). None until the look has written it."""
    blk = ((gate or {}).get("strata") or {}).get(frame_id)
    return _matrix_pointer(blk, frame_id, artifact=_rel(path) if path else f"data/{GATE_NAME}",
                           generated_at=(gate or {}).get("generated_at"), sha256=sha256)


# ---------------------------------------------------------------------------
# row builders

def build_rows(sb: dict, sc: dict | None, model_version: dict, *,
               sources: list[dict], date: str, trigger: str,
               now_iso: str, matrix: dict | None = None,
               matrix_sha256: str | None = None) -> list[dict]:
    """Candidate rows for every frame the artifacts carry. Copies only. `matrix` is
    the scoreboard matrix artifact when it exists; the headline row then carries a
    pointer at its frame block (EFV3_D3), and no tilted or secondary row does."""
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}, not {trigger!r}")
    acc = (sb or {}).get("accuracy") or {}
    gen = (sb or {}).get("generated_at") or ""
    floors = ((acc.get("claim_instruments") or {}).get("head_to_head_floors") or {})
    by_frame = acc.get("head_to_head_by_frame") or {}
    hv = acc.get("head_to_head_verdict") or {}
    vs = ((acc.get("head_to_head_vs_sources") or {}).get("sources") or {})
    head = BASIS_TO_FRAME.get(hv.get("basis"))
    # DS-02: the model the artifact scored (efv_v1 until eFV V2 serves; an artifact
    # written before the key existed scored v1).
    model_id = (acc.get("efv_scored_object") or {}).get("model_id") or MODEL_ID
    rows = []

    def _base(frame, n, n_by_side, note=""):
        meta = FRAMES[frame]
        return {"run_id": None, "date": date, "trigger": trigger,
                "model_id": model_id, "model_version": dict(model_version),
                "frame": frame,
                "frame_version": DEFAULT_FRAME_VERSION.get(frame),
                "role": meta["role"], "tilted": bool(meta["tilted"]),
                "window": _window(sb), "n": n, "n_by_side": n_by_side,
                "raters": {}, "deltas": {}, "resolvable": None, "verdict": None,
                "share": None, "sources": [dict(s) for s in sources],
                "note": note, "last_verified_at": now_iso}

    def _verdict_row(frame, hv, vs, n_by_side, hv_key, vs_key, note=""):
        row = _base(frame, hv.get("n"), n_by_side, note=note)
        if hv.get("frame_version"):
            row["frame_version"] = hv["frame_version"]
        row["raters"] = _rater_block(acc.get(hv.get("basis")))
        cons = {"delta": hv.get("delta"), "ci95": hv.get("ci95"),
                "mde95": hv.get("mde95"),
                "mde95_estimator": hv.get("mde95_estimator") or "E_refit",
                "ci95_estimator": hv.get("ci95_estimator"),
                "resolvable": hv.get("resolvable"),
                "key": hv_key}
        # A floor carried from another frame is copied with its label (FP3-1).
        if hv.get("mde95_status"):
            cons["mde95_status"] = hv["mde95_status"]
            cons["mde95_carried_from"] = hv.get("mde95_carried_from")
        deltas = {}
        for src in SOURCES_VS:
            cell = vs.get(src) or {}
            legs = {}
            for metric in ("spearman", "auc"):
                leg = cell.get(metric)
                if not leg:
                    continue
                legs[metric] = {
                    "delta": leg.get("delta"), "ci95": leg.get("ci95"),
                    "mde95": leg.get("mde95"),
                    "mde95_estimator": leg.get("mde95_estimator"),
                    "ci95_estimator": "E_cond, player-clustered",
                    "clears_e_cond_floor": leg.get("clears_e_cond_floor"),
                    "key": f"{vs_key}.sources.{src}.{metric}"}
                # FP3-3: the Holm-corrected reading, copied (never computed here).
                if leg.get("holm") is not None:
                    legs[metric]["holm"] = dict(leg["holm"])
                    legs[metric]["holm_verdict"] = leg.get("verdict")
            if src == "prospx_consensus":
                sp = cell.get("spearman") or {}
                if sp.get("holm") is not None:
                    cons = dict(cons, holm=dict(sp["holm"]),
                                holm_verdict=sp.get("verdict"))
                legs["spearman"] = cons
            if legs:
                deltas[f"vs_{src}"] = legs
        if "vs_prospx_consensus" not in deltas:
            deltas["vs_prospx_consensus"] = {"spearman": cons}
        row["deltas"] = deltas
        row["resolvable"] = hv.get("resolvable")
        row["verdict"] = hv.get("verdict")
        return row

    # The headline frame: the verdict itself, plus the per-source block. Since
    # FP3-1 that is vm2, found through head_to_head_verdict.basis like any other.
    if head:
        nbs = ({s: hv["n_by_side"][s] for s in STRATA
                if (hv.get("n_by_side") or {}).get(s)}
               or _by_side(floors.get(BY_FRAME_KEY.get(head, ""))))
        row = _verdict_row(
            head, hv, vs, nbs, "accuracy.head_to_head_verdict",
            "accuracy.head_to_head_vs_sources", note=FRAMES[head].get("note", ""))
        ptr = matrix_pointer(matrix, head, sha256=matrix_sha256)
        if ptr is not None:
            row["matrix"] = ptr
        rows.append(row)

    # Tilted frames: the by-frame cells, with the claim-instrument interval.
    for frame in ("predebut", "all_vintages"):
        if frame == head:
            continue
        cell = by_frame.get(BY_FRAME_KEY[frame]) or {}
        if cell.get("delta") is None:
            continue
        fl = floors.get(BY_FRAME_KEY[frame]) or {}
        row = _base(frame, cell.get("n"), _by_side(fl), note=cell.get("basis_note") or "")
        row["raters"] = _rater_block(acc.get(cell.get("basis")))
        row["deltas"] = {"vs_prospx_consensus": {"spearman": {
            "delta": cell.get("delta"),
            "ci95": (fl.get("floor_E_cond_in_run") or {}).get("ci95"),
            "ci95_estimator": "E_cond, player-clustered",
            "mde95": cell.get("mde95"), "mde95_estimator": "E_refit",
            "resolvable": cell.get("resolvable"),
            "key": f"accuracy.head_to_head_by_frame.{BY_FRAME_KEY[frame]}"}}}
        row["resolvable"] = cell.get("resolvable")
        row["verdict"] = cell.get("verdict")
        rows.append(row)

    # Secondary: the disagreement receipts on the scoreboard.
    rec = (sc or {}).get("disagreement_receipts") or {}
    if rec.get("efv_right_share") is not None:
        row = _base("disagreement", rec.get("n_disagreements"), None,
                    note=FRAMES["disagreement"]["note"])
        row["share"] = {"efv_right_share": rec.get("efv_right_share"),
                        "ci95": rec.get("efv_right_share_ci95"),
                        "null": rec.get("null"),
                        "key": "disagreement_receipts"}
        row["resolvable"] = rec.get("efv_right_share_resolvable")
        row["verdict"] = rec.get("efv_right_share_verdict")
        rows.append(row)

    for row in rows:
        _finish(row)
        row["run_id"] = f"{gen}|{row['frame']}|{row['content_hash'][:8]}"
    return rows


def build_dev_rows(dev: dict | None, *, sources: list[dict], date: str, trigger: str,
                   now_iso: str, frames=DEV_FRAMES, raters=DEV_RATERS,
                   deltas=DEV_DELTAS, statistic_fields: bool = False,
                   matrix: dict | None = None,
                   matrix_sha256: str | None = None) -> list[dict]:
    """Development rows (EV-09) copied from data/efv_v2_dev_eval.json, one per frame
    it carries. role "development", resolvable None: a development read adjudicates
    nothing. Copies only. `frames`, `raters` and `deltas` name another development
    artifact's frames and keys (DEV_ARTIFACTS); a frame's own note, when it carries
    one, replaces the registry note. `statistic_fields` (the DS-16 block only) also
    copies the frame's `statistic` and pooled `secondary`; it is off for every other
    artifact so their existing rows keep their content hash. `matrix` (passed for
    the DS-16 block only, EFV3_D3) adds the pointer at the scoreboard matrix's block
    of the same frame when the artifact scores that frame."""
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}, not {trigger!r}")
    if not dev or dev.get("role") != "development":
        return []
    dev_frames = dev.get("frames") or {}
    lab = dev.get("label") or {}
    mv = {"fingerprint": None, "commit": (dev.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    gen = dev.get("generated_at") or ""
    rows = []
    rater_map, delta_map = raters, deltas
    screen = isinstance(dev.get("screening"), dict)
    for fid in frames:
        f = dev_frames.get(fid) or {}
        if not f.get("n") or not f.get("raters"):
            continue
        meta = FRAMES[fid]
        if meta["role"] != "development":
            raise ValueError(f"{fid} is not a development frame")
        raters = {}
        for name, key in rater_map:
            r = (f.get("raters") or {}).get(key) or {}
            if r.get("spearman") is None and r.get("auc") is None:
                continue
            raters[name] = {"spearman": r.get("spearman"), "auc": r.get("auc"),
                            "n": r.get("n")}
        deltas = {}
        for name, comp in delta_map:
            legs = {}
            for metric in ("spearman", "auc"):
                leg = ((f.get("deltas") or {}).get(comp) or {}).get(metric)
                if not leg:
                    continue
                legs[metric] = {"delta": leg.get("delta"), "ci95": leg.get("ci95"),
                                "mde95": leg.get("mde95"),
                                "mde95_estimator": leg.get("estimator"),
                                "ci95_estimator": leg.get("ci95_estimator"),
                                "resolvable": None, "reading": leg.get("reading"),
                                "key": f"frames.{fid}.deltas.{comp}.{metric}"}
                if screen:
                    legs[metric].update({k: leg[k] for k in SCREEN_LEG_FIELDS if k in leg})
            if legs:
                deltas[name] = legs
        nbs = {s: (f.get("n_by_side") or {})[s] for s in STRATA
               if (f.get("n_by_side") or {}).get(s)} or None
        row = {"run_id": None, "date": date, "trigger": trigger,
               "model_id": dev.get("model_id"), "model_version": dict(mv),
               "frame": fid, "frame_version": f.get("frame_version"),
               "role": meta["role"], "tilted": bool(meta["tilted"]),
               "window": f.get("window"), "n": f.get("n"), "n_by_side": nbs,
               "raters": raters, "deltas": deltas, "resolvable": None,
               "verdict": f.get("verdict"), "share": None,
               "sources": [dict(s) for s in sources],
               "note": f.get("note") or meta.get("note") or "",
               "last_verified_at": now_iso}
        if isinstance(dev.get("screening"), dict):
            row["screening"] = dict(dev["screening"])
        if statistic_fields and f.get("statistic"):
            row["statistic"] = f["statistic"]
        if statistic_fields and isinstance(f.get("secondary"), dict):
            sec = f["secondary"]
            leg = (sec.get("deltas") or {})
            row["secondary"] = {
                "statistic": sec.get("statistic"),
                "raters": {name: (sec.get("raters") or {}).get(key)
                           for name, key in rater_map
                           if (sec.get("raters") or {}).get(key) is not None},
                "deltas": {name: leg[comp] for name, comp in delta_map if comp in leg}}
        ptr = matrix_pointer(matrix, fid, sha256=matrix_sha256)
        if ptr is not None:
            row["matrix"] = ptr
        _finish(row)
        row["run_id"] = f"{gen}|{fid}|{row['content_hash'][:8]}"
        rows.append(row)
    return rows


def screen_arm_docs(doc: dict | None) -> list[dict]:
    """One development document per MEASURED, non-exploratory arm of a screening lab
    artifact (its `arms[]`), in the shape build_dev_rows reads: role development, the
    arm's model_id, the artifact's label and code, the arm's `frame` block under
    lv_dev and its `screening` block. Copies only."""
    if not doc or not isinstance(doc.get("arms"), list):
        return []
    out = []
    for arm in doc["arms"]:
        if not isinstance(arm, dict) or not arm.get("measured"):
            continue
        scr = arm.get("screening") or {}
        if scr.get("exploratory") or doc.get("exploratory"):
            continue
        frame = arm.get("frame")
        if not isinstance(frame, dict) or not str(arm.get("model_id") or "").startswith(
                SCREEN_MODEL_PREFIX):
            continue
        out.append({"role": "development", "model_id": arm["model_id"],
                    "generated_at": doc.get("generated_at"),
                    "label": doc.get("label") or {}, "code": doc.get("code") or {},
                    "screening": dict(scr), "frames": {"lv_dev": frame}})
    return out


def build_pricing_rows(doc: dict | None, *, sources: list[dict], date: str, trigger: str,
                       now_iso: str) -> list[dict]:
    """EFV3_C05: one development row per frame of the MC-5 pricing artifact, model_id
    and note from the artifact, metric "mae", raters and deltas empty (no rank claim:
    the order is V2's own), the MAE numbers copied into `pricing` with the artifact key
    each came from. An exploratory artifact, or one that is not a development read,
    lands no row. Copies only."""
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger must be one of {TRIGGERS}, not {trigger!r}")
    if not doc or doc.get("role") != "development" or doc.get("exploratory"):
        return []
    lab = doc.get("label") or {}
    mv = {"fingerprint": None, "commit": (doc.get("code") or {}).get("commit"),
          "label": lab.get("id"), "resolved_through": lab.get("resolved_through"),
          "provider": lab.get("provider")}
    gen = doc.get("generated_at") or ""
    rows = []
    for fid in PRICING_FRAMES:
        f = (doc.get("frames") or {}).get(fid) or {}
        if not f.get("n"):
            continue
        meta = FRAMES[fid]
        if meta["role"] != "development":
            raise ValueError(f"{fid} is not a development frame")
        pricing = {k: f.get(k) for k in PRICING_FIELDS}
        pricing["key"] = f"frames.{fid}"
        nbs = {s: (f.get("n_by_side") or {})[s] for s in STRATA
               if (f.get("n_by_side") or {}).get(s)} or None
        row = {"run_id": None, "date": date, "trigger": trigger,
               "model_id": doc.get("model_id"), "model_version": dict(mv),
               "frame": fid, "frame_version": f.get("frame_version"),
               "role": meta["role"], "tilted": bool(meta["tilted"]),
               "window": f.get("window"), "n": f.get("n"), "n_by_side": nbs,
               "raters": {}, "deltas": {}, "resolvable": None,
               "verdict": f.get("verdict"), "share": None,
               "sources": [dict(s) for s in sources],
               "note": doc.get("note") or "", "last_verified_at": now_iso,
               "metric": doc.get("metric"), "pricing": pricing}
        _finish(row)
        row["run_id"] = f"{gen}|{fid}|{row['content_hash'][:8]}"
        rows.append(row)
    return rows


def _pricing_candidates(data_dir: Path, *, date: str, trigger: str,
                        now_iso: str) -> list[dict]:
    path = data_dir / PRICING_NAME
    doc = _load_json(path)
    if not doc:
        return []
    return build_pricing_rows(doc, sources=[{"path": _rel(path),
                                             "generated_at": doc.get("generated_at"),
                                             "sha256": _sha256(path)}],
                              date=date, trigger=trigger, now_iso=now_iso)


# ---------------------------------------------------------------------------
# the ledger

def _read_ledger(path: Path) -> list[dict]:
    rows = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return rows
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            rows.append(json.loads(ln))
        except ValueError:
            log.warning("efv_progress: unreadable ledger line skipped")
    return rows


def _append_ledger(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


def merge_rows(served: list[dict], durable: list[dict]) -> list[dict]:
    """The served rows, then every durable row the served file lost, in date
    order among themselves. Served order is kept as the prefix."""
    have = {r.get("run_id") for r in served}
    lost = [r for r in durable if r.get("run_id") not in have]
    if not lost:
        return list(served)
    out = list(served)
    for r in lost:
        out.append(r)
        have.add(r.get("run_id"))
    # A stable sort by date keeps the served prefix intact whenever the lost
    # rows are newer, which is the only way they arise (the checkout restores
    # an OLDER committed file).
    return sorted(out, key=lambda r: r.get("date") or "")


def restamp_roles(rows: list[dict]) -> list[dict]:
    """Apply ROLE_CHANGES to stored rows: the row's role follows the registry,
    the role it was written with is kept in `role_was`, and `role_changed` says
    when and why. Idempotent; the content hash does not include the role."""
    out = []
    for r in rows:
        ch = ROLE_CHANGES.get(r.get("frame"))
        if ch and r.get("role") == ch[0]:
            r = dict(r, role=ch[1], role_was=ch[0], role_changed=ch[2])
        out.append(r)
    return out


def apply(rows: list[dict], candidates: list[dict], now_iso: str) -> tuple[list[dict], list[dict]]:
    """Append each candidate whose content differs from its frame's last row;
    otherwise move that row's last_verified_at. Returns (rows, appended)."""
    rows = [dict(r) for r in rows]
    appended = []
    for cand in candidates:
        # A frame's history is per model: a v2 development row never displaces a
        # v1 row of the same frame, or the reverse.
        last = None
        for r in reversed(rows):
            if (r.get("frame") == cand.get("frame")
                    and (r.get("model_id") or MODEL_ID) == (cand.get("model_id") or MODEL_ID)):
                last = r
                break
        same_id = next((r for r in rows if r.get("run_id") == cand.get("run_id")), None)
        if same_id is not None:
            same_id["last_verified_at"] = now_iso
            continue
        if last is not None and last.get("content_hash") == cand.get("content_hash"):
            last["last_verified_at"] = now_iso
            continue
        rows.append(cand)
        appended.append(cand)
    return rows, appended


def _doc(rows: list[dict], sb: dict | None, now_iso: str, prev: dict | None) -> dict:
    acc = (sb or {}).get("accuracy") or {}
    hv = acc.get("head_to_head_verdict") or {}
    frames = json.loads(json.dumps(FRAMES))
    by_frame = acc.get("head_to_head_by_frame") or {}
    for fid in ("predebut", "all_vintages"):
        note = (by_frame.get(BY_FRAME_KEY[fid]) or {}).get("basis_note")
        if note:
            frames[fid]["note"] = note
    head = BASIS_TO_FRAME.get(hv.get("basis")) or ((prev or {}).get("headline_frame")) or "vm"
    doc = {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "headline_frame": head,
        "frames": frames,
        "chart": {"series_frames": list(CHART_FRAMES),
                  "excluded_roles": ["tilted", "secondary", "superseded"],
                  "y": "eFV minus PROSPX consensus, Spearman rho",
                  "band": "plus and minus the row's mde95 around zero"},
        "strata": list(STRATA),
        "correction_triggers": list(CORRECTION_TRIGGERS),
        "frame_change_triggers": list(FRAME_CHANGE_TRIGGERS),
        "regen_cmd": REGEN_CMD,
        "rule": ("append-only; a row is added when a frame's measured content "
                 "changes and otherwise only its last_verified_at moves; every "
                 "number is copied from the artifact key named in the row"),
        "rows": rows,
    }
    if prev and prev.get("backfill"):
        doc["backfill"] = prev["backfill"]
    return doc


def _write(doc: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        from storage import _atomic_replace
    except Exception:                                         # noqa: BLE001
        _atomic_replace = None
    if _atomic_replace is not None:
        _atomic_replace(tmp, path)
    else:
        tmp.replace(path)


def _paths(data_dir, out_path, ledger_path):
    data_dir = Path(data_dir) if data_dir is not None else DATA_DIR
    real = data_dir.resolve() == DATA_DIR.resolve()
    out = Path(out_path) if out_path else (OUT_PATH if real else data_dir / "efv_progress.json")
    led = Path(ledger_path) if ledger_path else (
        LEDGER_PATH if real else data_dir / ".efv_progress_ledger.jsonl")
    return data_dir, out, led


def load(path: Path | None = None) -> dict | None:
    return _load_json(path or OUT_PATH)


def commit_rows(new_rows: list[dict], *, data_dir=None, out_path=None,
                ledger_path=None, sb: dict | None = None, now_iso: str | None = None,
                backfill_receipt: dict | None = None) -> dict:
    """Merge, apply and write. Shared by update() and the backfill tool."""
    data_dir, out, led = _paths(data_dir, out_path, ledger_path)
    now_iso = now_iso or _now_iso()
    prev = _load_json(out) or {}
    durable = _read_ledger(led)
    rows = restamp_roles(merge_rows(list(prev.get("rows") or []), durable))
    rows, appended = apply(rows, new_rows, now_iso)
    if backfill_receipt is not None:
        prev = dict(prev)
        prev["backfill"] = backfill_receipt
    doc = _doc(rows, sb, now_iso, prev)
    _write(doc, out)
    in_ledger = {r.get("run_id") for r in durable}
    _append_ledger(led, [r for r in rows if r.get("run_id") not in in_ledger])
    return {"appended": [r["run_id"] for r in appended], "n_rows": len(rows),
            "out": str(out), "ledger": str(led)}


def update(data_dir=None, trigger: str = "nightly", *, out_path=None,
           ledger_path=None, now: datetime | None = None,
           model_version: dict | None = None, note: str | None = None) -> dict:
    """Read the artifacts, build candidate rows, append what changed.

    `note` is prefixed to every candidate row's note; a harness correction
    names the fix there. It is not part of the content hash."""
    data_dir, out, led = _paths(data_dir, out_path, ledger_path)
    sb_path, sc_path = data_dir / SB_NAME, data_dir / SC_NAME
    sb = _load_json(sb_path)
    if not sb or not (sb.get("accuracy") or {}).get("head_to_head_verdict"):
        return {"appended": [], "status": "no head_to_head_verdict in source_backtest.json"}
    sc = _load_json(sc_path)
    now_dt = now or datetime.now(timezone.utc)
    now_iso = _now_iso(now_dt)
    sources = [{"path": _rel(sb_path), "generated_at": sb.get("generated_at"),
                "sha256": _sha256(sb_path)}]
    if sc:
        sources.append({"path": _rel(sc_path), "generated_at": sc.get("generated_at"),
                        "sha256": _sha256(sc_path)})
    mv = model_version if model_version is not None else current_model_version()
    # EFV3_D3: the scoreboard matrix, when the producer has written it. Its file
    # sha and generated_at ride on the pointer, so the pointer (and the row's hash)
    # moves only when the producer rewrote the artifact (compare-before-write).
    mx_path = data_dir / MATRIX_NAME
    mx = _load_json(mx_path)
    mx_sha = _sha256(mx_path) if mx else None
    cands = build_rows(sb, sc, mv, sources=sources, date=now_dt.date().isoformat(),
                       trigger=trigger, now_iso=now_iso, matrix=mx, matrix_sha256=mx_sha)
    for name, fids, rmap, dmap, sub in DEV_ARTIFACTS:
        dev_path = data_dir / name
        dev = _load_json(dev_path)
        if dev and sub:
            dev = dev.get(sub) if isinstance(dev.get(sub), dict) else None
        if not dev:
            continue
        screening = name == SCREEN_NAME
        for d in (screen_arm_docs(dev) if screening else [dev]):
            cands += build_dev_rows(
                d, sources=[{"path": _rel(dev_path),
                             "generated_at": dev.get("generated_at"),
                             "sha256": _sha256(dev_path)}],
                date=now_dt.date().isoformat(), trigger=trigger, now_iso=now_iso,
                frames=fids, raters=rmap, deltas=dmap,
                statistic_fields=bool(sub) or screening,
                matrix=mx if sub == DS16_SUBKEY else None, matrix_sha256=mx_sha)
    cands += _pricing_candidates(data_dir, date=now_dt.date().isoformat(),
                                 trigger=trigger, now_iso=now_iso)
    if note:
        for c in cands:
            c["note"] = f"{note} {c.get('note') or ''}".strip()
    res = commit_rows(cands, data_dir=data_dir, out_path=out, ledger_path=led,
                      sb=sb, now_iso=now_iso)
    res["status"] = "ok"
    return res


def update_pricing(data_dir=None, trigger: str = "efv_change", *, out_path=None,
                   ledger_path=None, now: datetime | None = None) -> dict:
    """The MC-5 pricing rows alone (EFV3_C05, tools/efv_v2_pricing_calibration.py): build
    them from the pricing artifact and append what changed, leaving every other frame's
    candidates to update(). The nightly update() builds the same rows."""
    data_dir, out, led = _paths(data_dir, out_path, ledger_path)
    now_dt = now or datetime.now(timezone.utc)
    now_iso = _now_iso(now_dt)
    cands = _pricing_candidates(data_dir, date=now_dt.date().isoformat(),
                                trigger=trigger, now_iso=now_iso)
    if not cands:
        return {"appended": [], "status": f"no development rows in {PRICING_NAME}"}
    res = commit_rows(cands, data_dir=data_dir, out_path=out, ledger_path=led,
                      sb=_load_json(data_dir / SB_NAME), now_iso=now_iso)
    res["status"] = "ok"
    return res


def summary_line(res: dict) -> str:
    """One line for a heartbeat."""
    if res.get("status") != "ok":
        return str(res.get("status"))[:120]
    return f"{len(res.get('appended') or [])} row(s) appended, {res.get('n_rows')} total"


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    trig = sys.argv[1] if len(sys.argv) > 1 else "efv_change"
    print(summary_line(update(trigger=trig)))
