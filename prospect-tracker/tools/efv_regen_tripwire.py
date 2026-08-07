# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV regen tripwires: coverage, served weights, explainer churn.

WHAT THIS IS FOR. On 2026-08-04 the hitter training matrix gained 210 labeled
players with a real MiLB production block in a single regen, taking coverage
from 48.0 to 59.2 percent after three byte-stable vintages. The refit that
followed moved the ENTIRE production weight block: the level premium fell 32
percent, on-base 36 percent, OPS 12 percent, and age-for-level rose 46 percent.
Nothing gated it, because a refit is not a ship, and nothing connected the
coverage jump to the grade churn it caused. The owner noticed one prospect had
moved and asked why, and answering it took a full lab session reconstructing
affine maps out of committed explainer arrays. See
docs/ARIAS_ATTRIBUTION_2026-08-07.md.

This module records, once per regen, the three quantities that would have made
that answer immediate:

  T1  the training pool's MiLB feature coverage, per side, and its move
  T2  the SERVED ridge weights, per side, and the exact affine change each
      feature's contribution underwent against the previous vintage
  T3  how much of the live board's explainer output changed, beside the board
      basis fingerprint that is supposed to identify the board

WHAT THIS IS NOT. It is a tripwire, not a gate. It cannot block a run, cannot
change a grade, and is not admissible evidence for shipping or dropping
anything. It reports and it never refuses: every entry point swallows its own
exceptions and returns a row saying what it could not observe. A tripwire that
blocks the pipeline gets disabled the first time it is inconvenient and then
protects nothing.

WHY THE WEIGHTS ARE FAITHFUL. efv_score._fit_production calls
efv_model.fit_production_stack(rows, side, keys) on the on-disk training matrix
and serves the ridge it returns. This module calls efv_model.served_ridge_weights,
which is the same call. Verified 2026-08-07 by recomputing efv_score._factors
from this fit and comparing to the committed explainer arrays in data/xfv.json:
every ridge contribution reproduced to the 2dp the arrays carry, on 1,839 live
hitters and 2,226 live pitchers. The residual rows are display relabels
(_relabel_pace_factor) and non-ridge overlay chips, not weight disagreements.

ARTIFACTS. Two sidecars, both deliberately OUTSIDE the data/*_eval*.json glob
that test_model_registry.py polices, because neither is an eval and neither has
a registry row:

  data/xfv_regen_ledger.json   the readable ledger (one entry per vintage)
  data/xfv_regen_digest.json   per-player explainer hashes for the LAST vintage,
                               the state T3 needs because data/xfv.json is
                               overwritten in place

BOTH SHOULD STAY UNTRACKED, like data/build_info.json. deploy/nightly-build.sh
runs `git checkout -- .` before every pull, so a TRACKED ledger would be
restored to its last committed state at the start of each night and the box
would never accumulate history. The code is correct either way (each entry
carries the baseline it was compared against, and an unchanged observation is
not re-appended), but untracked is what makes the ledger a history rather than
a two-row window.

Run standalone: `python tools/efv_regen_tripwire.py` REPORTS and writes nothing.
Writing requires `--record`. That asymmetry is deliberate: efv_ungraded.py
writing on every invocation including --help has cost this program a session.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
# Same bootstrap the other tools/ labs use, so `python tools/efv_regen_tripwire.py`
# resolves efv_dataset / efv_model / efv_score. A no-op when run_monthly imports
# this module, where the package root is already the working directory.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA_DIR = ROOT / "data"
LEDGER_PATH = DATA_DIR / "xfv_regen_ledger.json"
DIGEST_PATH = DATA_DIR / "xfv_regen_digest.json"
BOARD_PATH = DATA_DIR / "xfv.json"

SCHEMA = "xfv-regen-tripwire-1"
# ~8.3KB per entry (the served weight vectors and the per-feature affine maps
# for both sides), so 30 vintages is about 250KB and roughly a month of nightly
# regens. Long enough to see a move and its context, short enough that the file
# stays readable by a person.
KEEP_ENTRIES = 30
SIDES = ("hit", "pit")
_SIDE_CODE = {"hit": "H", "pit": "P"}
_SIDE_WORD = {"hit": "hitter", "pit": "pitcher"}

# The ingest-health source name. It MUST match the entry added to
# run_monthly.SCHEDULED_EXPORTS or _ingest_kind files the row as 'unwatched'
# and write_ingest_health drops it out of red[] at drain time.
INGEST_SOURCE = "efv_regen_tripwire"


# ---------------------------------------------------------------------------
# thresholds, and how each one was chosen
# ---------------------------------------------------------------------------
#
# Every threshold below is the geometric midpoint of a GAP measured in the
# committed history, not a round number picked for looking like one. Each is
# also gap-invariant: any value inside the stated interval partitions the
# measured history identically, so the instrument does not turn on where in the
# gap the constant sits.

# T1. COVERAGE. Measured 2026-08-07 over all 35 committed vintages of
# data/xfv_dataset_report.json and data/xfv_pitcher_dataset_report.json
# (2026-06-22 to 2026-08-06), giving 68 consecutive-vintage deltas of
# milb_feature_coverage.level_rank as a fraction of rows_total. 27 are exactly
# zero. The 41 nonzero ones have a single clear gap:
#
#     ... 0.0015 0.0017 0.0029 0.0029 | 0.0087 0.0099 0.0110 0.0131 0.0156
#         0.0257 0.0313 0.0478 0.1121 0.1233 0.1243 0.1631 0.1634
#
# Below the gap is roster churn: a pool of ~2,000 rows gaining or losing a
# handful is 0.0005 to 0.003 by construction. Above it are the pipeline
# landings, including the 08-04 identity repair at +0.1121 hit / +0.0478 pit
# that caused the refit this module exists for. 13 of the 68 deltas are above.
_COVERAGE_GAP = (0.0029, 0.0087)
COVERAGE_TRIPWIRE = math.sqrt(_COVERAGE_GAP[0] * _COVERAGE_GAP[1])      # 0.00502

# T2. WEIGHT SCALE. The affine refit map is exact, not a smoothing convenience:
# holding a feature VALUE fixed, c = (w/sd)(x - mu) gives c_new = p*c_old + q
# with p = (w_new*sd_old)/(w_old*sd_new). So p - 1 IS "this feature's
# contribution was rescaled by this much", and p = 0.6433 is the sentence "the
# on-base weight was cut 36 percent".
#
# Measured 2026-08-07 by fitting that map on the committed explainer arrays in
# data/xfv.json across the 6 consecutive vintage pairs from 297d7eb (07-30) to
# 193c644 (08-06), both sides, RIDGE LABELS ONLY (per _ridge_label_set, so
# overlay chips that no weight produced are excluded), keeping fits with
# r2 > 0.90: 95 feature-vintage maps. Sorted |p - 1| has one gap in its tail:
#
#     ... 0.0434 0.0458 0.0600 0.0690 | 0.1066 0.1106 0.1142 0.1144 0.1206
#         0.1227 0.1512 0.1667 0.1667 0.1717 0.1940 0.3228 0.3567 0.4639 0.5717
#
# 15 of 95 are above, and they fall in exactly TWO of the six vintage pairs:
# 7626fd0 -> d50c1af (the 08-04 refit) and 297d7eb -> fe670dd. The second of
# those moved the pitcher age-for-level contribution by p = 1.5717, the largest
# weight move in the measured record, WITH NO COVERAGE MOVE AT ALL (0.4800 to
# 0.4800 hit, 0.4561 to 0.4561 pit). That is the case for keeping T1 and T2 as
# separate instruments: the coverage tripwire alone would have missed it.
_WEIGHT_SCALE_GAP = (0.0690, 0.1066)
WEIGHT_SCALE_TRIPWIRE = math.sqrt(_WEIGHT_SCALE_GAP[0] * _WEIGHT_SCALE_GAP[1])   # 0.0858

# T3. EXPLAINER CHURN. Same 6 vintage pairs, both sides, live board rows only
# (kind == "active"), measured through build_digest / churn themselves, so the
# threshold is calibrated on the figure the instrument actually emits. 12
# measurements of the share of players whose ridge factor LABEL SET changed:
#
#     0.000 0.002 0.027 0.038 0.044 0.050 0.095 0.108 0.112 | 0.253 0.493 0.597
#
# 3 of 12 above, and they land in the SAME two vintage pairs the weight
# tripwire flags. Two instruments built on different artifacts (one on the
# training matrix, one on the served board) agreeing on which 2 of 6 regens
# were refits is the closest thing to a control this lane has.
#
# The naive "share of explainer arrays that changed at all" figure is NOT used
# for the alarm. It runs 0.042 to 0.987 over the same 12 measurements and its
# median per-player magnitude move is 0.000: it is dominated by the 2dp
# rounding in the committed arrays, so it reports a redecoration as a
# revolution. It is still recorded, because it is what a reader diffing the
# artifact would see.
_CHURN_GAP = (0.112, 0.253)
EXPLAINER_SET_CHURN_TRIPWIRE = math.sqrt(_CHURN_GAP[0] * _CHURN_GAP[1])          # 0.1683


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _h8(obj) -> str:
    return hashlib.sha1(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8"),
    ).hexdigest()[:8]


def _parse_ratio(value) -> tuple[int, int] | None:
    """'1134/1917' -> (1134, 1917). The dataset report writes coverage as a
    display string, so this is the one place that shape is decoded."""
    if not isinstance(value, str) or "/" not in value:
        return None
    a, _, b = value.partition("/")
    try:
        num, den = int(a.strip()), int(b.strip())
    except ValueError:
        return None
    return (num, den) if den > 0 else None


def _pct(x: float) -> str:
    return f"{100.0 * x:.1f} points"


# ---------------------------------------------------------------------------
# T1 observation: training-pool coverage
# ---------------------------------------------------------------------------

def observe_coverage(side: str) -> dict:
    """milb_feature_coverage out of the side's dataset report.

    level_rank is the key read on both sides: it is the one MiLB feature that
    exists for hitters and pitchers, so the two sides' numbers mean the same
    thing. The other keys in that block are per-side (iso_rel / era_rel)."""
    from efv_dataset import report_path
    path = report_path(side)
    try:
        rep = _read_json(path)
    except (OSError, ValueError) as e:
        return {"observed": False, "why": f"cannot read {path.name}: {e}"}
    ratio = _parse_ratio((rep.get("milb_feature_coverage") or {}).get("level_rank"))
    if not ratio:
        return {"observed": False,
                "why": f"{path.name} has no readable milb_feature_coverage.level_rank"}
    covered, rows = ratio
    return {"observed": True, "covered": covered, "rows": rows,
            "frac": round(covered / rows, 6),
            "report_generated_at": rep.get("generated_at")}


# ---------------------------------------------------------------------------
# T2 observation: the served ridge weights
# ---------------------------------------------------------------------------

def observe_weights(side: str) -> dict:
    """The weights the board is served from, via efv_model.served_ridge_weights.

    Not a re-derivation of the model: the same function efv_score's shipped
    scorer fits through, on the same on-disk matrix, in the same run."""
    try:
        from efv_model import served_ridge_weights
        stack = served_ridge_weights(side)
    except Exception as e:                                       # noqa: BLE001
        return {"observed": False, "why": f"production stack unfittable: {e}"}
    if not stack:
        return {"observed": False, "why": "production stack returned nothing"}
    return {"observed": True, "n_train": stack["n"],
            "intercept": round(stack["intercept"], 6),
            "cal_a": round(stack["a"], 6), "cal_b": round(stack["b"], 6),
            "features": {k: {"w": round(w, 6), "mu": round(m, 6), "sd": round(s, 6)}
                         for k, w, m, s in zip(stack["keys"], stack["w"],
                                               stack["mu"], stack["sd"])}}


def affine_change(prev: dict, cur: dict) -> list[dict]:
    """Per feature, the exact affine map from the previous vintage's
    contribution to this one's, for a player whose feature VALUE did not move.

        c_new = p * c_old + q
        p = (w_new * sd_old) / (w_old * sd_new)
        q = (w_new / sd_new) * (mu_old - mu_new)

    p - 1 is the headline: 'this feature's contribution was rescaled by this
    much'. q is the board-wide shift the re-standardization applied on top,
    which moves everyone equally and therefore reorders nothing.

    A feature present on only one side of the pair is reported with p and q
    null and a `status` naming it, because an added or removed feature is a
    bigger event than any rescaling and must not read as a quiet zero."""
    pf, cf = prev.get("features") or {}, cur.get("features") or {}
    out = []
    for key in sorted(set(pf) | set(cf)):
        a, b = pf.get(key), cf.get(key)
        if a is None:
            out.append({"feature": key, "status": "added", "p": None, "q": None})
            continue
        if b is None:
            out.append({"feature": key, "status": "removed", "p": None, "q": None})
            continue
        if not a["w"] or not b["sd"] or not a["sd"]:
            out.append({"feature": key, "status": "degenerate", "p": None, "q": None})
            continue
        p = (b["w"] * a["sd"]) / (a["w"] * b["sd"])
        q = (b["w"] / b["sd"]) * (a["mu"] - b["mu"])
        out.append({"feature": key, "status": "held",
                    "p": round(p, 6), "q": round(q, 6),
                    "pct_change": round(100.0 * (p - 1.0), 2),
                    "w_prev": a["w"], "w_now": b["w"]})
    out.sort(key=lambda r: (r["p"] is not None, -abs((r["p"] or 1.0) - 1.0)))
    return out


# ---------------------------------------------------------------------------
# T3 observation: live-board explainer churn
# ---------------------------------------------------------------------------

def _ridge_label_set(side: str) -> set[str]:
    """The rendered explainer labels that are RIDGE contributions, for one side.

    Derived, not hard-coded: the declared feature keys for the side
    (efv_model._feature_spec) put through the same collinear grouping and the
    same label lookup efv_score._factors renders with
    (efv_factor_groups.display_label over efv_score._FACTOR_LABELS). Anything
    else on a card is an overlay chip that no weight produced.

    SIDE-AWARE ON PURPOSE. A first cut of this read _FACTOR_LABELS.values()
    flat and classified the pitchers' single largest ridge term, "Strikeout
    rate vs level", as an overlay, because that string is a pitcher-side
    override living in efv_factor_groups rather than in the label table. The
    pitcher churn figure came out 0.226 where it should have been 0.512. Going
    through display_label is what makes the classification match what the card
    actually renders.

    On failure the caller sees an empty set, records zero recognised labels,
    and the ridge figures degrade to the whole-array figure. Visible, not
    wrong."""
    try:
        import efv_factor_groups as _fg
        import efv_model as _xm
        import efv_score as _xs
        keys, _mono = _xm._feature_spec(side)
        label_of = (_xs._FACTOR_LABELS or {}).get
        return {_fg.display_label(_fg.group_id(k) or k, side,
                                 lambda kk: label_of(kk, kk))
                for k in keys}
    except Exception:                                            # noqa: BLE001
        return set()


# The n_milb_seasons chip is relabelled at DISPLAY time by
# efv_score._relabel_pace_factor for fast climbers, so its rendered label is
# not in _FACTOR_LABELS. It is still the same ridge term and must be counted as
# one, or every fast riser reads as a permanent label-set change.
_PACE_RELABEL_PREFIX = "Seasons used ("


def build_digest(board: dict | None = None) -> dict:
    """Per live-board player, three 8-hex digests of the committed explainer:

        full   the whole factors array as served, overlay chips included
        ridge  the ridge (label, dir, mag) triples only
        lset   the sorted ridge LABEL SET only

    Keyed player_key -> "fullridgelset" (24 hex). The digest exists because
    data/xfv.json is overwritten in place, so the previous vintage's arrays are
    gone by the time the next run wants to compare against them."""
    if board is None:
        board = _read_json(BOARD_PATH)
    ridge_labels = {s: _ridge_label_set(s) for s in SIDES}
    by_side: dict[str, dict[str, str]] = {s: {} for s in SIDES}
    seen: dict[str, set[str]] = {s: set() for s in SIDES}
    for pk, rec in (board.get("by_player") or {}).items():
        if rec.get("kind") != "active":
            continue
        factors = rec.get("factors") or []
        if not factors:
            continue
        side = next((s for s in SIDES if _SIDE_CODE[s] == rec.get("side")), None)
        if side is None:
            continue
        known = ridge_labels[side]
        full, ridge = [], []
        for f in factors:
            label = f.get("label")
            seen[side].add(label)
            triple = (label, f.get("dir"), f.get("mag"))
            full.append(triple)
            if label in known or (isinstance(label, str)
                                  and label.startswith(_PACE_RELABEL_PREFIX)):
                ridge.append(triple)
        lset = sorted({t[0] for t in ridge})
        by_side[side][pk] = _h8(full) + _h8(ridge) + _h8(lset)
    overlays = {s: sorted(lb for lb in seen[s]
                          if lb not in ridge_labels[s]
                          and not (isinstance(lb, str)
                                   and lb.startswith(_PACE_RELABEL_PREFIX)))
                for s in SIDES}
    return {"schema": SCHEMA,
            "board_generated_at": (board.get("meta") or {}).get("generated_at"),
            "written_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "n_ridge_labels_known": {s: len(ridge_labels[s]) for s in SIDES},
            "labels_classified_as_overlay": overlays,
            "by_side": by_side}


def churn(prev_side: dict | None, cur_side: dict) -> dict:
    """Churn figures for one side, over the players present in both digests."""
    if not prev_side:
        return {"observed": False, "why": "no previous digest for this side"}
    common = set(prev_side) & set(cur_side)
    n = len(common)
    if n < 50:
        return {"observed": False, "why": f"only {n} players in both digests"}
    ch_full = ch_ridge = ch_lset = 0
    for pk in common:
        a, b = prev_side[pk], cur_side[pk]
        if a[0:8] != b[0:8]:
            ch_full += 1
        if a[8:16] != b[8:16]:
            ch_ridge += 1
        if a[16:24] != b[16:24]:
            ch_lset += 1
    return {"observed": True, "n_compared": n,
            "n_only_now": len(set(cur_side) - set(prev_side)),
            "n_only_before": len(set(prev_side) - set(cur_side)),
            "share_changed_any": round(ch_full / n, 4),
            "share_changed_ridge": round(ch_ridge / n, 4),
            "share_label_set_changed": round(ch_lset / n, 4),
            "share_identical": round((n - ch_full) / n, 4)}


# ---------------------------------------------------------------------------
# the observation, and the comparison against the previous vintage
# ---------------------------------------------------------------------------

def _board_basis() -> str:
    """The board's own identity string, so the churn figure sits BESIDE the
    thing that is supposed to say when the board changed. Best effort: a
    coordination device must never be what takes a run down."""
    try:
        import storage as _st
        return _st.board_basis_fingerprint()
    except Exception:                                            # noqa: BLE001
        return "unavailable"


def observe() -> dict:
    """One full observation of the current on-disk artifacts. Writes nothing."""
    try:
        board = _read_json(BOARD_PATH)
    except (OSError, ValueError) as e:
        board = None
        board_why = f"cannot read xfv.json: {e}"
    else:
        board_why = ""
    obs = {
        "schema": SCHEMA,
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "board_generated_at": (board or {}).get("meta", {}).get("generated_at"),
        "board_basis": _board_basis(),
        "sides": {},
    }
    for side in SIDES:
        obs["sides"][side] = {"coverage": observe_coverage(side),
                              "weights": observe_weights(side)}
    obs["digest"] = build_digest(board) if board is not None else {"why": board_why}
    return obs


def _fingerprint(obs: dict) -> str:
    """Identifies a VINTAGE, so a rerun that regenerated nothing does not append
    a second entry claiming a zero-delta refit that never happened."""
    payload = {s: {"coverage": obs["sides"][s]["coverage"],
                   "weights": obs["sides"][s]["weights"]} for s in SIDES}
    payload["digest"] = {s: _h8(obs.get("digest", {}).get("by_side", {}).get(s, {}))
                         for s in SIDES}
    return _h8(payload)


def _last_observed(entries: list, side: str, kind: str) -> tuple[dict, str | None]:
    """The most recent entry whose (side, kind) block was actually OBSERVED,
    with the vintage it came from.

    Not simply entries[-1]. A run in which the instrument could not look (a
    missing dataset report, an unfittable stack) still files a row saying so,
    and comparing the NEXT run against that row would report a null delta and
    blind two nights for one outage. Walking back to the last real observation
    means an outage costs visibility for exactly the night it happened."""
    for e in reversed(entries or []):
        block = ((e.get("sides") or {}).get(side) or {}).get(kind) or {}
        if block.get("observed"):
            return block, e.get("board_generated_at")
    return {}, None


def compare(entries: list | None, obs: dict, prev_digest: dict | None) -> dict:
    """Build the ledger entry for `obs`, compared against the previous vintage.

    `entries` is the ledger's entry list, newest last, because each side and
    each instrument resolves its own baseline (see _last_observed).

    Returns the entry. Alerts ride on entry['alerts'] and are also returned by
    run() so the caller can log them. Nothing here can fail a run."""
    entries = list(entries or [])
    prev_entry = entries[-1] if entries else None
    entry = {
        "recorded_at": obs["recorded_at"],
        "board_generated_at": obs.get("board_generated_at"),
        "board_basis": obs.get("board_basis"),
        "fingerprint": _fingerprint(obs),
        "compared_against": (prev_entry or {}).get("fingerprint"),
        "compared_against_generated_at": (prev_entry or {}).get("board_generated_at"),
        "sides": {},
        "alerts": [],
    }
    for side in SIDES:
        word = _SIDE_WORD[side]
        cov, wts = obs["sides"][side]["coverage"], obs["sides"][side]["weights"]
        prev_cov, cov_from = _last_observed(entries, side, "coverage")
        prev_wts, wts_from = _last_observed(entries, side, "weights")
        row: dict = {"coverage": dict(cov), "weights": dict(wts),
                     "coverage_baseline_vintage": cov_from,
                     "weights_baseline_vintage": wts_from}

        # T1
        if cov.get("observed") and prev_cov.get("observed"):
            delta = round(cov["frac"] - prev_cov["frac"], 6)
            row["coverage"]["delta"] = delta
            row["coverage"]["prev_frac"] = prev_cov["frac"]
            row["coverage"]["prev_covered"] = prev_cov.get("covered")
            row["coverage"]["prev_rows"] = prev_cov.get("rows")
            if abs(delta) > COVERAGE_TRIPWIRE:
                direction = "UP" if delta > 0 else "DOWN"
                entry["alerts"].append({
                    "kind": "coverage", "side": side, "direction": direction,
                    "delta": delta, "threshold": round(COVERAGE_TRIPWIRE, 5),
                    "message": (
                        f"{word} MiLB feature coverage moved {direction} "
                        f"{_pct(abs(delta))}, {prev_cov['covered']}/{prev_cov['rows']} "
                        f"to {cov['covered']}/{cov['rows']}. Every mean, standard "
                        f"deviation and fitted weight on the MiLB block is a function "
                        f"of that pool, so expect a refit."),
                })
        elif not cov.get("observed"):
            row["coverage"]["delta"] = None

        # T2
        if wts.get("observed") and prev_wts.get("observed"):
            maps = affine_change(prev_wts, wts)
            row["weight_change"] = maps
            for m in maps:
                if m["status"] in ("added", "removed"):
                    entry["alerts"].append({
                        "kind": "weight_feature_set", "side": side,
                        "feature": m["feature"], "direction": m["status"].upper(),
                        "message": (f"{word} model feature {m['feature']!r} was "
                                    f"{m['status']} between vintages. A feature-set "
                                    f"change moves every row that carries it."),
                    })
                    continue
                if m["p"] is None:
                    continue
                if abs(m["p"] - 1.0) > WEIGHT_SCALE_TRIPWIRE:
                    direction = "UP" if m["p"] > 1.0 else "DOWN"
                    entry["alerts"].append({
                        "kind": "weight_scale", "side": side,
                        "feature": m["feature"], "direction": direction,
                        "p": m["p"], "pct_change": m["pct_change"],
                        "threshold": round(WEIGHT_SCALE_TRIPWIRE, 4),
                        "message": (
                            f"{word} feature {m['feature']!r} contribution rescaled "
                            f"{direction} {abs(m['pct_change']):.0f} percent "
                            f"(p={m['p']:.4f}). Costs most to the players most "
                            f"exposed to it."),
                    })
        obs_dig = (obs.get("digest") or {}).get("by_side", {}).get(side) or {}
        prev_dig = ((prev_digest or {}).get("by_side") or {}).get(side)
        ch = churn(prev_dig, obs_dig) if obs_dig else {
            "observed": False, "why": "no live explainer digest for this side"}
        row["explainer_churn"] = ch
        if ch.get("observed") and ch["share_label_set_changed"] > EXPLAINER_SET_CHURN_TRIPWIRE:
            entry["alerts"].append({
                "kind": "explainer_churn", "side": side,
                "share_label_set_changed": ch["share_label_set_changed"],
                "threshold": round(EXPLAINER_SET_CHURN_TRIPWIRE, 4),
                "message": (
                    f"{ch['share_label_set_changed'] * 100:.0f} percent of live {word} "
                    f"cards are showing a DIFFERENT set of reasons than last vintage "
                    f"({ch['n_compared']} compared, board basis "
                    f"{obs.get('board_basis')})."),
            })
        entry["sides"][side] = row

    entry["n_alerts"] = len(entry["alerts"])
    return entry


# ---------------------------------------------------------------------------
# ledger IO
# ---------------------------------------------------------------------------

_LEDGER_NOTE = (
    "Tripwire ledger for the eFV regen, one entry per VINTAGE. Reports, never "
    "gates: nothing here can block a run, move a grade or be cited as evidence "
    "for shipping or dropping a feature. Thresholds are geometric midpoints of "
    "measured gaps in the committed history, and each is gap-invariant. See "
    "tools/efv_regen_tripwire.py and docs/EFV_REGEN_TRIPWIRES_2026-08-07.md."
)


def load_ledger() -> dict:
    try:
        doc = _read_json(LEDGER_PATH)
    except (OSError, ValueError):
        doc = {}
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        doc = {"schema": SCHEMA, "note": _LEDGER_NOTE, "entries": []}
    doc.setdefault("entries", [])
    return doc


def load_digest() -> dict | None:
    try:
        doc = _read_json(DIGEST_PATH)
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and doc.get("schema") == SCHEMA else None


def _thresholds_block() -> dict:
    return {
        "coverage_frac": {
            "value": round(COVERAGE_TRIPWIRE, 5),
            "chosen": ("geometric midpoint of the gap [0.0029, 0.0087] in the 68 "
                       "consecutive-vintage coverage deltas across 35 committed "
                       "dataset reports; any value in that interval partitions the "
                       "measured history identically"),
        },
        "weight_scale_abs_p_minus_1": {
            "value": round(WEIGHT_SCALE_TRIPWIRE, 4),
            "chosen": ("geometric midpoint of the gap [0.0690, 0.1066] in 95 "
                       "ridge feature-vintage affine refit maps fitted on committed "
                       "explainer arrays over 6 vintage pairs; 15 fire, in 2 pairs"),
        },
        "explainer_label_set_churn": {
            "value": round(EXPLAINER_SET_CHURN_TRIPWIRE, 4),
            "chosen": ("geometric midpoint of the gap [0.112, 0.253] in 12 measured "
                       "side-vintage label-set churn shares; flags the same 2 of 6 "
                       "vintage pairs the weight tripwire does"),
        },
    }


def record(obs: dict | None = None, persist: bool = True) -> dict:
    """Compare the current artifacts against the previous vintage and append.

    Returns {"entry", "alerts", "appended", "wrote"}. Never raises."""
    obs = obs or observe()
    ledger = load_ledger()
    prev_entry = ledger["entries"][-1] if ledger["entries"] else None
    prev_digest = load_digest()
    entry = compare(ledger["entries"], obs, prev_digest)

    appended = True
    if prev_entry and prev_entry.get("fingerprint") == entry["fingerprint"]:
        # Same vintage seen again (a rerun that regenerated nothing). Stamp the
        # existing row rather than filing a fake zero-delta refit.
        prev_entry["last_seen_at"] = entry["recorded_at"]
        appended = False
    else:
        ledger["entries"].append(entry)
        ledger["entries"] = ledger["entries"][-KEEP_ENTRIES:]

    ledger["schema"] = SCHEMA
    ledger["note"] = _LEDGER_NOTE
    ledger["thresholds"] = _thresholds_block()
    ledger["generated_at"] = entry["recorded_at"]
    ledger["latest_alerts"] = entry["alerts"]

    wrote = False
    if persist:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            LEDGER_PATH.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
            dig = obs.get("digest") or {}
            if dig.get("by_side"):
                DIGEST_PATH.write_text(json.dumps(dig, separators=(",", ":")),
                                       encoding="utf-8")
            wrote = True
        except OSError as e:
            log.warning("efv regen tripwire: could not write ledger: %s", e)
    return {"entry": entry, "alerts": entry["alerts"],
            "appended": appended, "wrote": wrote}


# ---------------------------------------------------------------------------
# the pipeline entry point
# ---------------------------------------------------------------------------

def run(log_: logging.Logger | None = None, persist: bool = True) -> dict:
    """Called by run_monthly.rebuild_only right after the eFV regen.

    NEVER RAISES and never returns a falsy failure the caller has to guess at.
    `observed` is False only when the instrument could not look at all, which is
    the one condition worth a RED: a watch that has silently stopped watching is
    the failure class this whole lane exists for.

    Firing a tripwire leaves `observed` True on purpose. Measured base rate is
    roughly one regen in three, and a RED at that rate is a RED nobody reads."""
    lg = log_ or log
    try:
        obs = observe()
        res = record(obs, persist=persist)
    except Exception as e:                                       # noqa: BLE001
        lg.exception("efv regen tripwire crashed - continuing")
        return {"observed": False, "n_alerts": 0, "alerts": [],
                "message": f"tripwire crashed: {e}"}

    entry = res["entry"]
    blocked = [f"{s}:{k}" for s in SIDES for k in ("coverage", "weights")
               if not entry["sides"][s][k].get("observed")]
    observed = not blocked and bool(res["wrote"] or not persist)
    if not observed:
        why = (", ".join(blocked) if blocked
               else "ledger could not be written")
        lg.error("eFV regen tripwire: COULD NOT OBSERVE (%s). The next weight "
                 "move will be invisible until this is fixed.", why)
        return {"observed": False, "n_alerts": 0, "alerts": [],
                "message": f"could not observe: {why}"}

    for a in entry["alerts"]:
        lg.warning("eFV REGEN TRIPWIRE [%s/%s]: %s", a["kind"], a["side"],
                   a["message"])
    if not entry["alerts"]:
        lg.info("eFV regen tripwire: no coverage, weight or explainer move over "
                "threshold against vintage %s",
                entry.get("compared_against_generated_at") or "(none yet)")
    summary = _summary_line(entry, res["appended"])
    lg.info("eFV regen tripwire: %s", summary)
    return {"observed": True, "n_alerts": entry["n_alerts"],
            "alerts": entry["alerts"], "message": summary,
            "appended": res["appended"]}


def _summary_line(entry: dict, appended: bool) -> str:
    bits = []
    for side in SIDES:
        cov = entry["sides"][side].get("coverage") or {}
        ch = entry["sides"][side].get("explainer_churn") or {}
        d = cov.get("delta")
        bits.append(
            f"{side} cov {cov.get('frac')}"
            + (f" ({d:+.4f})" if isinstance(d, (int, float)) else "")
            + (f", set-churn {ch['share_label_set_changed']:.3f}"
               if ch.get("observed") else ""))
    return (f"{entry['n_alerts']} alert(s); "
            + "; ".join(bits)
            + ("" if appended else "; unchanged vintage, not re-filed"))


# ---------------------------------------------------------------------------
# CLI. Reports by default. --record is what writes.
# ---------------------------------------------------------------------------

def _print_report(entry: dict) -> None:
    print(f"board generated_at : {entry.get('board_generated_at')}")
    print(f"board basis        : {entry.get('board_basis')}")
    print(f"compared against   : {entry.get('compared_against_generated_at') or '(nothing yet)'}")
    for side in SIDES:
        row = entry["sides"][side]
        cov, wts = row["coverage"], row["weights"]
        print(f"\n--- {_SIDE_WORD[side]}")
        if cov.get("observed"):
            d = cov.get("delta")
            print(f"  coverage  {cov['covered']}/{cov['rows']} = {cov['frac']:.4f}"
                  + (f"   delta {d:+.4f}" if isinstance(d, (int, float)) else "   (no baseline)"))
        else:
            print(f"  coverage  NOT OBSERVED: {cov.get('why')}")
        if wts.get("observed"):
            print(f"  ridge     n_train={wts['n_train']} intercept={wts['intercept']} "
                  f"a={wts['cal_a']} b={wts['cal_b']}")
        else:
            print(f"  ridge     NOT OBSERVED: {wts.get('why')}")
        for m in (row.get("weight_change") or [])[:8]:
            if m["p"] is None:
                print(f"    {m['feature']:18s} {m['status']}")
            else:
                print(f"    {m['feature']:18s} p={m['p']:8.4f} q={m['q']:+.4f} "
                      f"({m['pct_change']:+.1f}%)")
        ch = row.get("explainer_churn") or {}
        if ch.get("observed"):
            print(f"  churn     n={ch['n_compared']} any={ch['share_changed_any']:.3f} "
                  f"ridge={ch['share_changed_ridge']:.3f} "
                  f"label-set={ch['share_label_set_changed']:.3f}")
        else:
            print(f"  churn     NOT OBSERVED: {ch.get('why')}")
    print()
    for a in entry["alerts"]:
        print(f"TRIPWIRE [{a['kind']}/{a['side']}] {a['message']}")
    if not entry["alerts"]:
        print("no tripwire over threshold")


def main(argv=None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    write = "--record" in argv
    obs = observe()
    ledger = load_ledger()
    entry = compare(ledger["entries"], obs, load_digest())
    _print_report(entry)
    if write:
        res = record(obs, persist=True)
        print(f"\nrecorded: appended={res['appended']} wrote={res['wrote']} "
              f"-> {LEDGER_PATH.name}, {DIGEST_PATH.name}")
    else:
        print("\n(report only. pass --record to write the ledger.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
