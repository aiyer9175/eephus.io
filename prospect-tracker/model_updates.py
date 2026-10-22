# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Model Updates: the dated record of every model update (LIBRARY_11).

Owner ask 2026-10-02: a standalone "Model Updates" page with a timetable of
each model update, when it happened, the change in what the model is scored
on, and the resulting edge against the benchmark it is trying to beat, in the
form "Result (<stat>): +0.017 lead". This module writes the data behind that
page, data/model_updates.json (schema 1). The plan is LIBRARY_PLAN.md section
4 and lane LANE_UPDATES.md sections 2 to 6.

HONEST BY CONSTRUCTION:

1. THIS LAYER COMPUTES NO STATISTIC. Every number in an event is copied from a
   named key of a named artifact: a registry card's eval artifact read through
   the card spec in data/model_registry.json (model_registry.derive_card), or
   a row of data/efv_progress.json copied by run_id. The only arithmetic here
   is orientation: the gap between two copied numbers, signed so positive
   means the model is better, and the before-to-after change of a copied
   number when the rows are the same. A content hash and a timestamp are the
   rest.
2. ONE EDGE RULE. edge() is the only place a verdict word is printed (lead,
   tie, trails); its order is section 3.1 of the lane: an interval first, then
   a one-sided paired t, then the artifact's own flag or its floor, and
   without any of them only "ahead" or "behind" plus "no interval on record".
3. APPEND-ONLY. An event is never rewritten. The registry is diffed against
   the last state the ledger holds per model; eFV rows are copied once per
   run_id; note rows once per content. A rerun on unchanged inputs appends
   nothing. Events sit in append order and each run's batch is ordered by
   date, so the file only ever grows at its end (the page sorts).
4. DURABLE. The deploy box runs `git checkout -- .` before every nightly, so
   every event is also appended to .cache/model_updates/ledger.jsonl
   (untracked) and merged back on each run, as efv_progress does.
5. NEVER READ. Only the eFV progress frames named in EFV_FRAMES are opened;
   every other frame of that ledger is skipped by name. Nothing is cut by a
   consensus-FV cell, and no registry prose number is quoted (the Scored on
   text is the card's own `stat`).

The history before the first nightly run is the BACKFILL (python
model_updates.py --backfill, once, never on the nightly path): every
first-parent version of data/model_registry.json is read with git, and at each
version where a card changed the row's eval artifact AS COMMITTED IN THAT
COMMIT is re-read with today's card spec. A version whose artifact was never
committed (data/source_backtest.json is gitignored) or whose key paths do not
resolve lands as layer 'typed': the registry card as committed, flagged as not
re-derivable, never in the default view and never with an edge.

Field note: what the plan calls an event's "tier" is the key `layer` here,
because test_efv_progress._no_fv_cell rejects any key containing "tier" and
that rule applies to this file's keys too. For the same reason `models` is a
list, not a dict keyed by model_id (xfv_bucket_age_head would trip it).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import model_registry as R

log = logging.getLogger("model_updates")

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUT_PATH = DATA_DIR / "model_updates.json"
LEDGER_PATH = ROOT / ".cache" / "model_updates" / "ledger.jsonl"
TYPED_PATH = DATA_DIR / "model_updates_typed.json"
#: Read only. Held as a name, not a path constant: a module constant that
#: resolves to a watched artifact reads, to the test isolation sweep, like a
#: default write target.
PROGRESS_NAME = "efv_progress.json"
REGISTRY_REL = "data/model_registry.json"
PROGRESS_REL = "data/efv_progress.json"
TYPED_REL = "data/model_updates_typed.json"

SCHEMA = 1
EDGE_RULE_VERSION = 1
T_ONE_SIDED_95 = R.T_ONE_SIDED_95
#: The owner's form, in one place so it can be flipped in one line (plan C7).
RESULT_FORM = "Result ({stat}): {body}"
NO_SCORE_TEXT = "no score on record for this change"
TYPED_EDGE_TEXT = "registry card as committed; artifact not re-derivable, no edge printed"
RULE = ("append-only; an event is added when a model's registry state, its card "
        "legs, an eFV progress ledger row or a dated note changes; every number is "
        "copied from the artifact key named in the event; the edge is printed by "
        "edge() v1; events sit in append order, each run's batch ordered by date")

# ---------------------------------------------------------------------------
# families (route table first, the glossary _modelFamily heuristic as fallback)

FAMILIES = ("PROSPX and eFV", "Sources and Consensus", "MLB Projections",
            "Free Agency", "Arbitration", "MLB Stats", "Betting", "eWAR",
            "Alchemy Lab", "Draft", "Trade Machine", "Fantasy", "Hall of Fame",
            "CollegeSavant", "Management", "Franchise", "Scores / Standings", "Other",
            "Development")
DEVELOPMENT = "Development"
#: Rows the glossary files under "Internal / model-dev": tested first, so a
#: development artifact that mentions a product page stays out of it.
DEV_MARKERS = ("model-dev", "rendered nowhere", "loss ledger", "not wired", "n/a",
               "internal")
#: Tested only on a row no route claims (PORT_RED_TESTS_TRIAGE, 2026-10-22): a
#: surface that says the row serves nothing is a development row, not "Other".
#: Tested after the routes so a product row that mentions its dark twin stays
#: with its module.
UNSERVED_MARKERS = ("none served", "no surface", "not served", "no served page",
                    "no page reads it", "no page prints it", "nothing served",
                    "diagnostic only", "in the local cache", "dark twin", "ingest only")
#: (where to look, needles, family), tested in order on the lowercased text.
#: "start" is the start of the model_id, "id" anywhere in it, "any" anywhere in
#: the surface text plus the model_id.
ROUTES = (
    ("start", ("ewar", "fwar", "sdr_"), "eWAR"),
    ("id", ("_ewar_",), "eWAR"),
    ("id", ("efv", "xfv"), "PROSPX and eFV"),
    ("any", ("/betting/", "betting_"), "Betting"),
    ("any", ("/arbitration/", "arb_", "arbitration"), "Arbitration"),
    ("any", ("/pal/", "alchemy lab", "pal_", "_pal"), "Alchemy Lab"),
    ("any", ("/hof/", "hof_", "hall of fame", "/awards/", "awards_"), "Hall of Fame"),
    ("any", ("/scores/", "scores_"), "Scores / Standings"),
    ("any", ("/fantasy/", "fantasy_", "dfs_"), "Fantasy"),
    ("any", ("/trademachine/", "trade machine", "trademachine"), "Trade Machine"),
    ("any", ("collegesavant", "college_"), "CollegeSavant"),
    ("any", ("/management/", "mgmt_", "mwar_", "win_expectancy"), "Management"),
    ("any", ("/franchise/", "franchise_"), "Franchise"),
    ("any", ("/sources/", "source comparison", "source-comparison", "source_backtest",
             "source-accuracy", "source_", "claim_", "ba_", "grade_normalization",
             "the displayed consensus"), "Sources and Consensus"),
    ("any", ("/mlbstats/", "mlbstats", "bullpen", "starter"), "MLB Stats"),
    ("any", ("/fa/", "free agency", "fa_dpw", "dpw_", "$/war"), "Free Agency"),
    ("any", ("/projections/", "projections"), "MLB Projections"),
    ("any", ("draft",), "Draft"),
    ("any", ("prospx", "efv", "xfv", "fv_to_war", "farm", "overseas", "org_"),
     "PROSPX and eFV"),
)


def family(m: dict) -> str:
    """The module a registry row belongs to, from its surface route."""
    mid = (m.get("model_id") or "").lower()
    text = ((m.get("surface") or "") + " " + mid).lower()
    if any(k in text for k in DEV_MARKERS):
        return DEVELOPMENT
    for where, needles, fam in ROUTES:
        if where == "start":
            hit = any(mid.startswith(n) for n in needles)
        else:
            hay = mid if where == "id" else text
            hit = any(n in hay for n in needles)
        if hit:
            return fam
    if any(k in text for k in UNSERVED_MARKERS):
        return DEVELOPMENT
    return "Other"


#: Tokens kept upper case when a model_id is turned into a label (the glossary
#: list plus the lane's additions).
LABEL_ACR = {"REM", "RIV", "SEM", "FV", "WAR", "WAG", "PAL", "FA", "DPW", "QO", "SC",
             "RPS", "KRP", "DS", "MLB", "ETA", "IFA", "NPB", "KBO", "CPBL", "AAA",
             "AA", "ERA", "OPS", "AUC", "HEM", "DEM", "HOF"}
LABEL_MIXED = {"efv": "eFV", "xfv": "eFV", "gmli": "gmLI", "xhem": "xHEM",
               "fwdhem": "fwdHEM", "ewar": "eWAR"}
LABEL_STOP = {"to", "vs", "of", "and", "the", "per", "by", "a"}


def label(mid: str) -> str:
    out = []
    for i, tok in enumerate((mid or "").split("_")):
        low = tok.lower()
        if low in LABEL_MIXED:
            out.append(LABEL_MIXED[low])
        elif tok.upper() in LABEL_ACR:
            out.append(tok.upper())
        elif tok == "plus":
            out.append("+")
        elif i and low in LABEL_STOP:
            out.append(low)
        else:
            out.append(tok[:1].upper() + tok[1:])
    return " ".join(out).replace(" +", "+")


# ---------------------------------------------------------------------------
# the eFV progress ledger: frames, aliases and trigger words

#: Frames copied, by name. vm was the headline until the 2026-09-25 handover
#: and is copied only through that day; every other frame is never opened.
EFV_FRAMES = {"vm": "headline", "vm2": "headline", "vm_dev": "development",
              "lv_dev": "development", "vm_oos_dev": "development"}
VM_HEADLINE_THROUGH = "2026-09-25"
EFV_FRAME_LABELS = {"vm": "vintage-matched (vm1)",
                    "vm2": "vintage-matched, timing-pinned (vm2)",
                    "vm_dev": "vintage-matched development",
                    "lv_dev": "list vintage development",
                    "vm_oos_dev": "v1 out-of-sample development"}
#: ledger model id -> (model_id on the page, label, registry rows it stands for)
ALIASES = {
    "efv_v1": ("efv_v1", "eFV v1", ["xfv_hitter", "xfv_pitcher"]),
    "efv_v2": ("efv_v2", "eFV V2", ["efv_v2"]),
    "efv_v2_h0": ("efv_v2_h0", "eFV V2 H0", ["efv_v2_h0"]),
    "efv_v1_overlays": ("efv_v1_overlays", "eFV v2 (development)", []),
    "efv_v2_pbust": ("efv_v2_pbust", "eFV v2 (development)", []),
    "efv_v2_ds_assembled": ("efv_v2_ds_assembled", "eFV v2 (development)", []),
}
#: ledger trigger -> (kind, reader words). The raw trigger name never reaches
#: a reader field.
TRIGGERS = {
    "efv_change": ("model_change", "model change"),
    "harness_correction": ("scoring_correction", "scoring correction"),
    "data_correction": ("data_correction", "data correction"),
    "frame_change": ("frame_change", "frame change"),
    "backfill": ("backfill", "backfill"),
    "nightly": ("rescored", "rescored"),
    "look": ("rescored", "rescored at a registered look"),
}
#: (delta key, rater key, reader name of the benchmark, role)
EFV_LEGS = (("vs_prospx_consensus", "prospx_consensus", None, "headline"),
            ("vs_mlb_pipeline", "mlb_pipeline", "MLB Pipeline", "secondary"),
            ("vs_fangraphs", "fangraphs", "FanGraphs", "secondary"))
EFV_DIGITS = 4

LAYERS = ("headline", "secondary", "development", "typed", "registration", "note")
DEFAULT_LAYERS = ("headline", "secondary", "note")
KINDS = ("registered", "verdict", "artifact_change", "first_scored", "rescored",
         "model_change", "scoring_correction", "data_correction", "frame_change",
         "backfill", "removed", "note")
#: Fields re-stamped from the current tables on every run; left out of the
#: content hash so a route-table change never forks an event's identity.
PRESENTATION = ("label", "family", "served", "default_view")

# ---------------------------------------------------------------------------
# helpers (no statistics)


def _now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(raw: bytes | None) -> str | None:
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def _sha256(path: Path) -> str | None:
    try:
        return _sha256_bytes(Path(path).read_bytes())
    except OSError:
        return None


def _load_json(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _rnd(v, digits):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and digits is not None:
        return round(v, digits)
    return v


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


NO_BENCH = re.compile(r"^\s*(n/a|none|descriptive by design|no champion|nothing)"
                      r"|league mean = 100", re.I)


def has_benchmark(m: dict) -> bool:
    return not NO_BENCH.search(m.get("baseline") or "")


# ---------------------------------------------------------------------------
# the edge rule


def edge(stat: str | None, adv=None, *, ci=None, resolvable=None, t=None,
         mde95=None, digits=3, benchmark=True, has_eval=True, wired=True,
         contest=True) -> dict:
    """{"state", "text"} for one leg (LANE_UPDATES.md 3.1). `adv` is oriented
    so positive means the model is better; `ci` is the 95% interval on that
    same gap; `resolvable` is the artifact's own flag."""
    if not benchmark:
        return {"state": "no_benchmark", "text": "no benchmark registered"}
    if not has_eval:
        return {"state": "no_eval", "text": "no eval artifact on record"}
    if not wired:
        return {"state": "unwired", "text": "benchmark named; headline not wired yet"}

    def out(state, body):
        return {"state": state, "text": RESULT_FORM.format(stat=stat, body=body)}

    if not contest:
        return out("no_contest", "no head-to-head on record")
    if adv is None:
        return out("unscored", "no number on record")
    d = 3 if digits is None else digits
    sgn, mag = f"{adv:+.{d}f}", f"{abs(adv):.{d}f}"
    if ci is not None:
        lo, hi = ci
        if lo > 0 and resolvable is not False:
            return out("lead", f"{sgn} lead")
        if hi < 0:
            return out("trails", f"trails by {mag}")
        if lo > 0:
            return out("tie", f"tie ({sgn}, inside the floor)")
        return out("tie", f"tie ({sgn})")
    if t is not None:
        if t >= T_ONE_SIDED_95:
            return out("lead", f"{sgn} lead")
        if t <= -T_ONE_SIDED_95:
            return out("trails", f"trails by {mag}")
        return out("tie", f"tie ({sgn})")
    if resolvable is not None:
        if resolvable and adv > 0:
            return out("lead", f"{sgn} lead")
        if resolvable and adv < 0:
            return out("trails", f"trails by {mag}")
        return out("tie", f"tie ({sgn})")
    if mde95 is not None:
        if adv > mde95:
            return out("lead", f"{sgn} lead")
        if adv < -mde95:
            return out("trails", f"trails by {mag}")
        return out("tie", f"tie ({sgn})")
    if adv >= 0:
        return out("unresolved", f"{mag} ahead, no interval on record")
    return out("unresolved", f"{mag} behind, no interval on record")


# ---------------------------------------------------------------------------
# card legs (read through the registry card spec; no per-model paths here)


def _own_flag(doc, path):
    """The artifact's own resolvable flag as the card spec names it."""
    try:
        if isinstance(path, dict) and set(path) == {"above_zero"}:
            bound = R._dig_path(doc, path["above_zero"])
            return bound > 0 if _num(bound) else None
        if isinstance(path, str):
            v = R._dig_path(doc, path)
            return v if isinstance(v, bool) else None
    except (KeyError, TypeError):
        return None
    return None


def _orient(champion, baseline, better, digits):
    """The gap between two copied numbers, signed so positive means the model
    is better, at the card's digits (6 when the card names none)."""
    if not (_num(champion) and _num(baseline)):
        return None
    gap = champion - baseline if better != "lower" else baseline - champion
    return round(gap, digits if digits is not None else 6)


def _raw(doc, path):
    try:
        v = R._dig_path(doc, path)
    except (KeyError, TypeError):
        return None
    return v if _num(v) else None


def card_legs(m: dict, doc) -> list[dict | None]:
    """One entry per card leg: the leg read from `doc` with the card spec of
    `m`, or None where that leg's key paths do not resolve in `doc`."""
    card = m.get("card") or {}
    spec = card.get("derived_from") or {}
    heads = card.get("headline") or []
    specs = spec.get("headline") or []
    digits = spec.get("digits")
    contest = card.get("contest", True)
    card_n = None
    if spec.get("n"):
        try:
            v = R._dig_path(doc, spec["n"])
            card_n = v if _num(v) else None
        except (KeyError, TypeError):
            card_n = None
    base_spec = {k: v for k, v in spec.items() if k not in ("headline", "n")}
    base_card = {k: v for k, v in card.items() if k not in ("headline", "derived_from")}
    out = []
    for i, (h, hs) in enumerate(zip(heads, specs)):
        one = {"eval_artifact": m.get("eval_artifact"),
               "card": {**base_card, "headline": [h],
                        "derived_from": {**base_spec, "headline": [hs]}}}
        try:
            got = R.derive_card(one, doc)["headline"][0]
        except (KeyError, ValueError, TypeError, AttributeError, IndexError):
            out.append(None)
            continue
        better = h.get("better")
        stat = h.get("stat") or h.get("label")
        n = got.get("n") if "n" in hs else card_n
        gap = got.get("gap_ci")
        ci = [gap["lo"], gap["hi"]] if isinstance(gap, dict) else None
        flag = _own_flag(doc, hs.get("resolvable")) if "resolvable" in hs else None
        # The gap is taken on the artifact's own numbers, before the card's
        # rounding, so the printed edge is the artifact's gap at the card's digits.
        adv = _orient(_raw(doc, hs.get("champion")), _raw(doc, hs.get("baseline")),
                      better, digits)
        e = edge(stat, adv, ci=ci, resolvable=flag, t=got.get("t"),
                 mde95=got.get("mde95"), digits=digits, contest=contest)
        keys = {"model": hs.get("champion"), "benchmark": hs.get("baseline")}
        if "n" in hs or spec.get("n"):
            keys["n"] = hs.get("n") or spec.get("n")
        if isinstance(hs.get("gap_ci"), dict):
            keys["ci95"] = [hs["gap_ci"]["lo"], hs["gap_ci"]["hi"]]
            if hs["gap_ci"].get("orientation"):
                keys["ci95_orientation"] = hs["gap_ci"]["orientation"]
        for f in ("t", "mde95"):
            if f in hs:
                keys[f] = hs[f]
        if "resolvable" in hs:
            keys["resolvable"] = hs["resolvable"]
        out.append({"stat": stat, "better": better,
                    "role": "headline" if i == 0 else "secondary",
                    "model": got.get("champion"),
                    "benchmark_label": h.get("baseline_label"),
                    "benchmark": got.get("baseline"), "n": n, "delta": adv,
                    "ci95": ci, "mde95": got.get("mde95"), "t": got.get("t"),
                    "resolvable": flag, "digits": digits,
                    "edge_state": e["state"], "edge_text": e["text"], "keys": keys})
    return out


def committed_legs(card: dict | None) -> list[dict]:
    """The legs of a registry card as committed (typed values; no edge)."""
    if not card or not isinstance(card.get("headline"), list):
        return []
    out = []
    for i, h in enumerate(card["headline"]):
        if not isinstance(h, dict):
            continue
        gap = h.get("gap_ci")
        out.append({"stat": h.get("stat") or h.get("label"), "better": h.get("better"),
                    "role": "headline" if i == 0 else "secondary",
                    "model": h.get("champion"), "benchmark_label": h.get("baseline_label"),
                    "benchmark": h.get("baseline"), "n": h.get("n", card.get("n")),
                    "ci95": [gap.get("lo"), gap.get("hi")] if isinstance(gap, dict) else None,
                    "mde95": h.get("mde95"), "t": h.get("t"),
                    "digits": (card.get("derived_from") or {}).get("digits"),
                    "edge_state": "typed", "edge_text": TYPED_EDGE_TEXT,
                    "keys": {"model": f"models[model_id].card.headline.{i}.champion",
                             "benchmark": f"models[model_id].card.headline.{i}.baseline"}})
    return out


def _compact(legs) -> list | None:
    """The card part of a model's state: what a rescore is detected on."""
    if legs is None:
        return None
    return [None if lg is None else
            {k: lg.get(k) for k in ("stat", "benchmark_label", "model", "benchmark",
                                    "n", "ci95", "t", "mde95")}
            for lg in legs]


#: The numbers a rescore is detected on; a label-only edit of a card is not one.
_SIG_FIELDS = ("model", "benchmark", "n", "ci95", "t", "mde95")


def _numbers(card) -> list | None:
    if card is None:
        return None
    return [None if lg is None else [lg.get(k) for k in _SIG_FIELDS] for lg in card]


def _same_leg(p: dict | None, lg: dict) -> bool:
    """Whether a previous leg at the same position is the same comparison: the
    same stat or the same benchmark (card labels were reworded over time)."""
    if not p:
        return False
    return (p.get("stat") == lg.get("stat")
            or (p.get("benchmark_label") is not None
                and p.get("benchmark_label") == lg.get("benchmark_label")))


def _with_change(legs, prev_card, digits_default=4):
    """Attach before / after per leg: before is the previous state's value of
    the same leg (same stat and benchmark); `improvement` only on the same
    rows."""
    out = []
    for i, lg in enumerate(legs):
        if lg is None:
            continue
        lg = dict(lg)
        p = prev_card[i] if prev_card and i < len(prev_card) else None
        same_leg = _same_leg(p, lg)
        before = p.get("model") if same_leg else None
        n_before = p.get("n") if same_leg else None
        same_rows = bool(same_leg and lg.get("n") is not None and n_before == lg.get("n"))
        imp = None
        if same_rows and _num(before) and _num(lg.get("model")):
            d = lg.get("digits")
            imp = _orient(lg["model"], before, lg.get("better"),
                          d if d is not None else digits_default)
        lg.update(before=before, n_before=n_before, same_rows=same_rows, improvement=imp)
        out.append(lg)
    return out


def _statistic(legs, frame=None):
    if not legs:
        return None
    h = legs[0]
    return {"stat": h.get("stat"), "better": h.get("better"), "before": h.get("before"),
            "after": h.get("model"), "improvement": h.get("improvement"),
            "n_before": h.get("n_before"), "n": h.get("n"),
            "same_rows": bool(h.get("same_rows")), "frame": frame}


def _edge_of(legs):
    if not legs:
        return {"state": "none", "text": NO_SCORE_TEXT}
    h = legs[0]
    return {"state": h.get("edge_state"), "text": h.get("edge_text"),
            "delta": h.get("delta"), "ci95": h.get("ci95"), "mde95": h.get("mde95"),
            "t": h.get("t"), "resolvable": h.get("resolvable")}


# ---------------------------------------------------------------------------
# events: identity, state, merge


def content_hash(ev: dict) -> str:
    body = {k: v for k, v in ev.items()
            if k not in ("event_id", "content_hash") + PRESENTATION}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _finish(ev: dict) -> dict:
    ev["content_hash"] = content_hash(ev)
    ev["event_id"] = f"{ev['date']}|{ev.get('model_id') or ev.get('family')}|{ev['kind']}|{ev['content_hash'][:8]}"
    return ev


def sort_day(d: str) -> str:
    """The first day of a written date: 2026-06 -> 2026-06-01,
    2026-07-29/30 -> 2026-07-29."""
    d = (d or "").split("/")[0]
    return d + "-01" if len(d) == 7 else d


def fold_state(events: list[dict]) -> dict:
    """{model_id: last registry state} from the events that carry one."""
    st = {}
    for ev in events:
        s = ev.get("state")
        if s is not None and ev.get("model_id"):
            st[ev["model_id"]] = s
    return st


def merge_events(served: list[dict], durable: list[dict]) -> list[dict]:
    """The served events, then every durable event the served file lost, in
    ledger order. The served order is kept as the prefix."""
    have = {e.get("event_id") for e in served}
    out = list(served)
    for e in durable:
        if e.get("event_id") not in have:
            out.append(e)
            have.add(e.get("event_id"))
    return out


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
            log.warning("model_updates: unreadable ledger line skipped")
    return rows


def _append_ledger(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# git (the backfill reads committed blobs; it never checks anything out)


class _Git:
    """A `git cat-file --batch` reader over the module's repository."""

    def __init__(self, root: Path = ROOT):
        self.root = Path(root)
        self.prefix = self._run("rev-parse", "--show-prefix").decode().strip()
        self.proc = subprocess.Popen(["git", "-C", str(self.root), "cat-file", "--batch"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def _run(self, *args) -> bytes:
        return subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                              check=True).stdout

    def show(self, commit: str, rel: str) -> bytes | None:
        self.proc.stdin.write(f"{commit}:{self.prefix}{rel}\n".encode())
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode().strip()
        if header.endswith("missing") or len(header.split()) != 3:
            return None
        size = int(header.split()[2])
        raw = self.proc.stdout.read(size)
        self.proc.stdout.read(1)
        return raw

    def versions(self, rel: str) -> list[tuple[str, str, str]]:
        out = self._run("log", "--first-parent", "--reverse", "--format=%H|%h|%ad",
                        "--date=short", "--", rel).decode("utf-8", "replace")
        return [tuple(ln.split("|", 2)) for ln in out.splitlines() if ln.strip()]

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:                                       # noqa: BLE001
            self.proc.kill()


def git_show(commit: str, rel: str, root: Path = ROOT) -> bytes | None:
    """One committed blob, or None (used by the tests' reconciliation)."""
    try:
        return subprocess.run(["git", "-C", str(root), "show", f"{commit}:./{rel}"],
                              capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _head_short() -> str | None:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                              capture_output=True, check=True).stdout.decode().strip()
    except (OSError, subprocess.CalledProcessError):
        return None


# ---------------------------------------------------------------------------
# registry events


def _committed_card_sig(m: dict):
    card = m.get("card")
    if not card or not isinstance(card.get("headline"), list):
        return None
    heads = [{k: v for k, v in h.items()} for h in card["headline"] if isinstance(h, dict)]
    return json.dumps({"n": card.get("n"), "h": heads}, sort_keys=True, default=str)


def _registry_event(kind, mid, day, commit, state, *, change, verdict=None,
                    artifact=None, source_path=REGISTRY_REL):
    layer = "headline" if kind == "verdict" else "registration"
    ev = {"date": day, "sort_date": day, "model_id": mid, "kind": kind, "layer": layer,
          "change": change, "verdict": verdict, "statistic": None, "benchmark": None,
          "edge": {"state": "none", "text": NO_SCORE_TEXT}, "legs": [],
          "source": {"path": source_path, "commit": commit}, "state": state}
    if artifact is not None:
        ev["artifact"] = artifact
    return ev


def _card_event(mid, day, commit, prev_state, legs, *, art, raw_sha, typed=False,
                reason=None, read_from=None):
    prev_card = (prev_state or {}).get("card")
    legs = _with_change(legs, prev_card)
    first = not prev_card
    kind = "first_scored" if first else "rescored"
    if typed:
        change = ("registry card changed; the artifact is not re-derivable at this commit"
                  + (f" ({reason})" if reason else ""))
    else:
        change = "first scored" if first else "rescored"
    h = legs[0] if legs else {}
    ev = {"date": day, "sort_date": day, "model_id": mid, "kind": kind,
          "layer": "typed" if typed else "headline", "change": change, "verdict": None,
          "statistic": _statistic(legs), "benchmark": (
              {"label": h.get("benchmark_label"), "value": h.get("benchmark")} if legs else None),
          "edge": ({"state": "typed", "text": TYPED_EDGE_TEXT} if typed else _edge_of(legs)),
          "legs": legs,
          "source": {"path": REGISTRY_REL if typed else art, "commit": commit,
                     "sha256": raw_sha, "rederivable": not typed}}
    if typed:
        ev["source"]["artifact"] = art
        ev["source"]["reason"] = reason
    if read_from:
        ev["source"]["read_from"] = read_from
    return ev


def _state_of(m: dict, card) -> dict:
    return {"verdict": m.get("verdict"), "eval_artifact": m.get("eval_artifact"),
            "card": card, "removed": False}


def registry_diff(reg: dict, state: dict, *, day: str, commit: str | None,
                  cards_today: dict, read_artifact, read_from=None,
                  card_change_only_when=None) -> tuple[list[dict], dict]:
    """Events for every difference between `reg` and the folded `state`.

    `read_artifact(rel)` returns (bytes or None) for an eval artifact at this
    version. `card_change_only_when(mid, m)` (backfill) decides whether the
    card is re-read at this version; None (nightly) re-reads every card and
    lets the signature decide."""
    events = []
    state = dict(state)
    cur = {m["model_id"]: m for m in reg.get("models") or []
           if isinstance(m, dict) and m.get("model_id")}
    for mid, m in cur.items():
        prev = state.get(mid)
        if prev is None or prev.get("removed"):
            st = _state_of(m, None)
            ev = _registry_event("registered", mid, day, commit, dict(st),
                                 change=f"registered as {m.get('verdict')}",
                                 verdict={"before": None, "after": m.get("verdict")})
            events.append(ev)
            state[mid] = st
            prev = st
            reread = mid in cards_today and (
                card_change_only_when is None or bool(m.get("card")))
        else:
            if m.get("verdict") != prev.get("verdict"):
                st = dict(prev, verdict=m.get("verdict"))
                events.append(_registry_event(
                    "verdict", mid, day, commit, st,
                    change=f"verdict {prev.get('verdict')} to {m.get('verdict')}",
                    verdict={"before": prev.get("verdict"), "after": m.get("verdict")}))
                state[mid] = prev = st
            if m.get("eval_artifact") != prev.get("eval_artifact"):
                st = dict(prev, eval_artifact=m.get("eval_artifact"))
                events.append(_registry_event(
                    "artifact_change", mid, day, commit, st, change="eval artifact changed",
                    artifact={"before": prev.get("eval_artifact"),
                              "after": m.get("eval_artifact")}))
                state[mid] = prev = st
            reread = mid in cards_today and (
                card_change_only_when is None or card_change_only_when(mid, m))
        if not reread:
            continue
        spec_row = cards_today[mid]
        art = m.get("eval_artifact") or spec_row.get("eval_artifact")
        raw = read_artifact(art) if art else None
        doc = None
        if raw is not None:
            try:
                doc = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                doc = None
        legs = card_legs({**spec_row, "eval_artifact": art}, doc) if doc is not None else []
        if any(lg is not None for lg in legs):
            card = _compact(legs)
            if _numbers(card) == _numbers(prev.get("card")):
                continue
            ev = _card_event(mid, day, commit, prev, legs, art=art,
                             raw_sha=_sha256_bytes(raw), read_from=read_from)
        else:
            if card_change_only_when is None:
                continue          # nightly: a card that does not derive is not an event
            typed = committed_legs(m.get("card"))
            if not typed:
                continue
            card = _compact(typed)
            if _numbers(card) == _numbers(prev.get("card")):
                continue
            reason = ("artifact never committed at this commit" if raw is None
                      else "today's key paths do not resolve in this version")
            ev = _card_event(mid, day, commit, prev, typed, art=art, raw_sha=None,
                             typed=True, reason=reason)
        st = dict(prev, card=card)
        ev["state"] = st
        events.append(ev)
        state[mid] = st
    for mid, prev in list(state.items()):
        if mid not in cur and not prev.get("removed"):
            st = dict(prev, removed=True)
            events.append(_registry_event("removed", mid, day, commit, st,
                                          change="removed from the registry"))
            state[mid] = st
    return events, state


# ---------------------------------------------------------------------------
# eFV events (copied from data/efv_progress.json by run_id)


def _efv_flag(leg: dict, dkey: str, key: str):
    if dkey != "vs_prospx_consensus":
        h = leg.get("holm")
        return h.get("reject_holm") if isinstance(h, dict) else None
    return leg.get("resolvable") if key == "spearman" else leg.get("clears_e_cond_floor")


def efv_row_legs(r: dict) -> list[dict]:
    """The legs of one ledger row, every number copied from the row."""
    raters, deltas = r.get("raters") or {}, r.get("deltas") or {}
    efv = raters.get("efv") or {}
    stat_base = "Spearman, within side and vintage" if r.get("statistic") else "Spearman"
    out = []
    for dkey, rkey, name, role in EFV_LEGS:
        block = deltas.get(dkey) or {}
        for key, stat in (("spearman", stat_base), ("auc", "AUC")):
            d = block.get(key)
            if not isinstance(d, dict) or d.get("delta") is None:
                continue
            st = stat if name is None else f"{stat} vs {name}"
            flag = _efv_flag(d, dkey, key)
            ci = d.get("ci95")
            e = edge(st, d.get("delta"), ci=ci, resolvable=flag, mde95=d.get("mde95"),
                     digits=EFV_DIGITS)
            flag_key = (f"deltas.{dkey}.{key}.holm.reject_holm" if dkey != "vs_prospx_consensus"
                        else f"deltas.{dkey}.{key}." + ("resolvable" if key == "spearman"
                                                        else "clears_e_cond_floor"))
            out.append({"stat": st, "better": "higher", "role": role,
                        "model": efv.get(key),
                        "benchmark_label": name or "PROSPX consensus",
                        "benchmark": (raters.get(rkey) or {}).get(key),
                        "n": efv.get("n", r.get("n")), "delta": d.get("delta"),
                        "ci95": ci, "mde95": d.get("mde95"), "t": None,
                        "resolvable": flag, "digits": EFV_DIGITS,
                        "edge_state": e["state"], "edge_text": e["text"],
                        "keys": {"model": f"raters.efv.{key}",
                                 "benchmark": f"raters.{rkey}.{key}",
                                 "n": "raters.efv.n", "delta": f"deltas.{dkey}.{key}.delta",
                                 "ci95": f"deltas.{dkey}.{key}.ci95",
                                 "mde95": f"deltas.{dkey}.{key}.mde95",
                                 "resolvable": flag_key}})
    return out


def _efv_lineage(frame: str, ledger_id: str, stat: str | None):
    if EFV_FRAMES.get(frame) == "headline":
        return f"h|{frame}"
    return f"d|{frame}|{ledger_id}|{stat}"


def efv_events(progress: dict | None, done_run_ids: set, lineage: dict) -> tuple[list, dict]:
    """Events for every copyable ledger row not yet copied. `lineage` maps a
    lineage key to the last copied headline leg ({model, n, stat})."""
    events, skipped = [], {"no_alias": [], "other_frames": 0, "vm_after_handover": 0}
    lineage = dict(lineage)
    for r in (progress or {}).get("rows") or []:
        frame = r.get("frame")
        if frame not in EFV_FRAMES:
            skipped["other_frames"] += 1
            continue
        if frame == "vm" and (r.get("date") or "") > VM_HEADLINE_THROUGH:
            skipped["vm_after_handover"] += 1
            continue
        if r.get("run_id") in done_run_ids:
            continue
        lid = r.get("model_id")
        if lid not in ALIASES:
            skipped["no_alias"].append({"run_id": r.get("run_id"), "ledger_model_id": lid})
            continue
        mid, _lab, regs = ALIASES[lid]
        legs = efv_row_legs(r)
        layer = EFV_FRAMES[frame]
        kind, word = TRIGGERS.get(r.get("trigger"), ("rescored", "rescored"))
        lkey = _efv_lineage(frame, lid, legs[0]["stat"] if legs else None)
        prev = lineage.get(lkey)
        if legs:
            h = legs[0]
            same = bool(prev and prev.get("stat") == h["stat"]
                        and prev.get("n") is not None and prev.get("n") == h["n"])
            prev_card = [{"stat": h["stat"], "benchmark_label": h["benchmark_label"],
                          "model": prev.get("model"), "n": prev.get("n")}] if prev else None
            legs = [dict(lg) for lg in legs]
            legs[:1] = _with_change(legs[:1], prev_card, EFV_DIGITS)
            legs[0]["same_rows"] = same
            if not same:
                legs[0]["improvement"] = None
            lineage[lkey] = {"model": h.get("model"), "n": h.get("n"), "stat": h["stat"]}
        mv = r.get("model_version") or {}
        ev = {"date": r.get("date"), "sort_date": r.get("date"), "model_id": mid,
              "registry_ids": regs, "kind": kind, "layer": layer,
              "change": f"{word} on the {EFV_FRAME_LABELS[frame]} frame",
              "verdict": None, "statistic": _statistic(legs, frame),
              "benchmark": ({"label": legs[0]["benchmark_label"], "value": legs[0]["benchmark"]}
                            if legs else None),
              "edge": _edge_of(legs), "legs": legs,
              "source": {"path": PROGRESS_REL, "run_id": r.get("run_id"),
                         "ledger_model_id": lid, "model_commit": mv.get("commit"),
                         "row_content_hash": r.get("content_hash")}}
        events.append(ev)
    return events, {"lineage": lineage, "skipped": skipped}


def efv_lineage_from(events: list[dict]) -> dict:
    lin = {}
    for ev in events:
        src = ev.get("source") or {}
        if src.get("path") != PROGRESS_REL or not ev.get("legs"):
            continue
        st = ev.get("statistic") or {}
        lkey = _efv_lineage(st.get("frame"), src.get("ledger_model_id"), st.get("stat"))
        lin[lkey] = {"model": st.get("after"), "n": st.get("n"), "stat": st.get("stat")}
    return lin


# ---------------------------------------------------------------------------
# the note layer (data/model_updates_typed.json)

NOTE_ORIGINS = ("methodology changelog", "model upgrades panel", "xfv entry v1 history",
                "other")
NOTE_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2}(/\d{2})?)?$")
NOTE_VERDICT_RE = re.compile(r"\b(lead|leads|leading|trail|trails|trailing|beat|beats|"
                             r"win|wins|better)\b", re.I)
NOTE_DASH_RE = re.compile("[‒–—―−]|--| - ")
_DATE_TOKEN = re.compile(r"\b\d{4}-\d{2}(?:-\d{2}(?:/\d{2})?)?\b")
_FIGURE = re.compile(r"(?<![A-Za-z0-9.\-])[-+]?\d+(?:[.,]\d+)*%?")
_YEAR = re.compile(r"^(19|20)\d{2}$")


def note_figures(text: str) -> list[str]:
    """Numbers in a note other than years, dates in the accepted forms and
    labels glued to letters (v38, DS-01, H0)."""
    t = _DATE_TOKEN.sub(" ", text or "")
    return [f for f in _FIGURE.findall(t) if not _YEAR.match(f)]


def _ban_re():
    try:
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        from copy_lint import BAN_RE
        return BAN_RE
    except Exception:                                           # noqa: BLE001
        return re.compile(r"\b(harness|leverag(es|ed|ing)|seamless|robust|delve)\b", re.I)


def validate_notes(doc, registry_ids) -> list[str]:
    """Problems with data/model_updates_typed.json; [] when it is clean."""
    if doc is None:
        return []
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA \
            or not isinstance(doc.get("notes"), list):
        return ["model_updates_typed.json must be {schema: 1, notes: [...]}"]
    ban = _ban_re()
    ok_ids = set(registry_ids) | set(ALIASES)
    probs = []
    for i, n in enumerate(doc["notes"]):
        where = f"notes[{i}]"
        if not isinstance(n, dict):
            probs.append(f"{where}: not an object")
            continue
        extra = set(n) - {"date", "model_id", "family", "text", "origin", "source"}
        if extra:
            probs.append(f"{where}: unknown fields {sorted(extra)}")
        d = n.get("date")
        if not (isinstance(d, str) and NOTE_DATE_RE.match(d)):
            probs.append(f"{where}: date {d!r} is not YYYY-MM-DD, YYYY-MM or YYYY-MM-DD/DD")
        mid = n.get("model_id")
        if mid is None:
            if n.get("family") not in FAMILIES:
                probs.append(f"{where}: a note with no model_id needs a family from the route table")
        elif mid not in ok_ids:
            probs.append(f"{where}: model_id {mid!r} is neither a registry row nor a ledger alias")
        text = n.get("text")
        if not (isinstance(text, str) and text.strip()):
            probs.append(f"{where}: text is empty")
            text = ""
        if NOTE_DASH_RE.search(text):
            probs.append(f"{where}: text carries a dash")
        if ban.search(text):
            probs.append(f"{where}: text carries a banned word")
        if NOTE_VERDICT_RE.search(text):
            probs.append(f"{where}: text carries a verdict word (only edge() prints one)")
        if n.get("origin") not in NOTE_ORIGINS:
            probs.append(f"{where}: origin {n.get('origin')!r} is not one of {NOTE_ORIGINS}")
        src = n.get("source")
        if not (isinstance(src, dict) and (src.get("commit") or src.get("path"))):
            probs.append(f"{where}: source must name an artifact path and key, or a commit")
            src = {}
        if note_figures(text) and not (src.get("path") and src.get("key")):
            probs.append(f"{where}: a figure in the text needs the artifact key it came from")
    return probs


def note_events(doc, done_ids: set, registry_ids) -> tuple[list[dict], list[str]]:
    probs = validate_notes(doc, registry_ids)
    bad = {int(p.split("]")[0].split("[")[1]) for p in probs if p.startswith("notes[")}
    events = []
    for i, n in enumerate((doc or {}).get("notes") or []):
        if i in bad or not isinstance(n, dict):
            continue
        mid = n.get("model_id")
        regs = list(ALIASES[mid][2]) if mid in ALIASES else ([mid] if mid else [])
        ev = {"date": n["date"], "sort_date": sort_day(n["date"]), "model_id": mid,
              "registry_ids": regs, "kind": "note", "layer": "note", "change": n["text"],
              "origin": n["origin"], "verdict": None, "statistic": None, "benchmark": None,
              "edge": {"state": "note", "text": NO_SCORE_TEXT}, "legs": [],
              "source": dict(n["source"], path=n["source"].get("path"), typed_input=TYPED_REL)}
        if mid is None:
            ev["note_family"] = n["family"]
        _finish(ev)
        if ev["event_id"] not in done_ids:
            events.append(ev)
    return events, probs


def empty_typed_doc() -> dict:
    return {
        "schema": SCHEMA,
        "rule": ("hand-kept dated notes for the Model Updates timetable; each becomes "
                 "one event of layer note; validated by model_updates.validate_notes"),
        "fields": {
            "date": "YYYY-MM-DD, YYYY-MM or a day range YYYY-MM-DD/DD, printed as written",
            "model_id": "a registry model_id, a ledger alias (efv_v1), or null",
            "family": "required when model_id is null: a family of the route table",
            "text": ("a dated fact: no dash, no banned word, no verdict word; any number "
                     "other than a year, a date or a version label needs source.key"),
            "origin": list(NOTE_ORIGINS),
            "source": "{path, key} of the artifact a figure came from, or {commit}",
        },
        "notes": [],
    }


# ---------------------------------------------------------------------------
# the models block (today)


def efv_today(progress: dict | None) -> tuple[list[dict], dict | None]:
    rows = [r for r in (progress or {}).get("rows") or [] if r.get("frame") == "vm2"]
    if not rows:
        return [], None
    r = rows[-1]
    return efv_row_legs(r), r


def models_block(reg: dict, progress: dict | None, events: list[dict],
                 sources: list) -> list[dict]:
    fresh = {}
    try:
        fresh = R.freshness(reg)
    except Exception:                                           # noqa: BLE001
        log.exception("model_updates: freshness failed")
    by_model: dict[str, list[dict]] = {}
    for ev in events:
        ids = set(ev.get("registry_ids") or []) | ({ev["model_id"]} if ev.get("model_id") else set())
        for mid in ids:
            by_model.setdefault(mid, []).append(ev)
    seen_art = {s["path"] for s in sources}
    out = []
    for m in reg.get("models") or []:
        mid = m["model_id"]
        fam = family(m)
        bench = has_benchmark(m)
        legs, src, err = [], None, None
        if mid == "efv_v2":
            legs, row = efv_today(progress)
            src = "efv_progress" if legs else None
            for lg in legs:
                lg["source"] = {"path": PROGRESS_REL, "run_id": (row or {}).get("run_id")}
        elif (m.get("card") or {}).get("derived_from"):
            p = ROOT / m["eval_artifact"]
            doc = _load_json(p)
            got = card_legs(m, doc) if doc is not None else []
            if got and all(lg is not None for lg in got):
                legs, src = got, "card"
                for lg in legs:
                    lg["source"] = {"path": m["eval_artifact"], "sha256": _sha256(p)}
                if m["eval_artifact"] not in seen_art:
                    sources.append({"path": m["eval_artifact"], "sha256": _sha256(p),
                                    "generated_at": (doc or {}).get("generated_at")})
                    seen_art.add(m["eval_artifact"])
            else:
                err = "card does not derive from its artifact"
        if legs:
            state = next((lg["edge_state"] for lg in legs if lg["role"] == "headline"),
                         legs[0]["edge_state"])
            ed = {"state": state, "text": legs[0]["edge_text"]}
        elif err:
            state, ed = "card_error", {"state": "card_error", "text": err}
        else:
            ed = edge(None, benchmark=bench, has_eval=bool(m.get("eval_artifact")),
                      wired=False)
            state = ed["state"]
        evs = by_model.get(mid, [])
        dated = [e for e in evs if e.get("kind") != "registered"]
        reg_ev = next((e for e in evs if e.get("kind") == "registered"), None)
        f = fresh.get(mid) or {}
        out.append({
            "model_id": mid, "label": label(mid), "family": fam,
            "served": fam != DEVELOPMENT, "verdict": m.get("verdict"),
            "provisional_kind": m.get("provisional_kind"), "benchmark": bench,
            "benchmark_label": legs[0]["benchmark_label"] if legs else None,
            "eval_artifact": m.get("eval_artifact"), "headline_source": src,
            "state": state, "edge": ed, "today": legs,
            "registered": reg_ev["date"] if reg_ev else None,
            "last_update": max((e["sort_date"] for e in dated), default=None),
            "events": len(evs),
            "freshness": {"artifact_age_days": f.get("artifact_age_days"),
                          "age_is_evidence": f.get("age_is_evidence"),
                          "stale": f.get("stale")},
        })
    return out


# ---------------------------------------------------------------------------
# the document


def _restamp(events: list[dict], fam_of: dict) -> list[dict]:
    out = []
    for ev in events:
        ev = dict(ev)
        mid = ev.get("model_id")
        if ev.get("kind") == "note" and mid is None:
            fam = ev.get("note_family") or "Other"
        elif mid in fam_of:
            fam = fam_of[mid]
        elif mid in ALIASES or (ev.get("source") or {}).get("path") == PROGRESS_REL:
            fam = "PROSPX and eFV"
        else:
            fam = family({"model_id": mid})    # a row no longer in the registry
        ev["family"] = fam
        ev["label"] = ALIASES[mid][1] if mid in ALIASES else (label(mid) if mid else None)
        ev["served"] = fam != DEVELOPMENT
        ev["default_view"] = ev.get("layer") == "note" or (
            ev.get("layer") in DEFAULT_LAYERS and ev["served"])
        out.append(ev)
    return out


def counts(events: list[dict], models: list[dict], reg: dict) -> dict:
    return {
        "events": len(events),
        "default_view": sum(1 for e in events if e.get("default_view")),
        "by_kind": dict(sorted(Counter(e["kind"] for e in events).items())),
        "by_layer": dict(sorted(Counter(e["layer"] for e in events).items())),
        "verdict_changes": sum(1 for e in events if e["kind"] == "verdict"),
        "registry_models": len(reg.get("models") or []),
        "served_models": sum(1 for m in models if m["served"]),
        "scored_models": sum(1 for m in models if m["today"]),
        "scored_legs": sum(len(m["today"]) for m in models),
        "model_states": dict(sorted(Counter(m["state"] for m in models).items())),
        "registry_verdicts": dict(sorted(Counter(m.get("verdict") for m in
                                                 reg.get("models") or []).items())),
        "by_family": dict(sorted(Counter(m["family"] for m in models).items())),
    }


def build_doc(events, reg, progress, *, now_iso, sources, backfill, efv_copy,
              note_problems) -> dict:
    fam_of = {m["model_id"]: family(m) for m in reg.get("models") or []}
    events = _restamp(events, fam_of)
    models = models_block(reg, progress, events, sources)
    return {
        "schema": SCHEMA,
        "generated_at": now_iso,
        "rule": RULE,
        "edge_rule_version": EDGE_RULE_VERSION,
        "result_form": RESULT_FORM,
        "regen_cmd": ("python model_updates.py (nightly: run_monthly after the eFV "
                      "progress ledger and after the registry refresh); history once: "
                      "python model_updates.py --backfill"),
        "sources": sources,
        "families": list(FAMILIES),
        "layers": list(LAYERS),
        "default_layers": list(DEFAULT_LAYERS),
        "kinds": list(KINDS),
        "aliases": {k: {"model_id": v[0], "label": v[1], "registry_ids": v[2]}
                    for k, v in ALIASES.items()},
        "never_read": {"frames_copied": list(EFV_FRAMES),
                       "vm_copied_through": VM_HEADLINE_THROUGH,
                       "note": ("eFV progress frames are selected by name and no other "
                                "frame is opened; nothing is cut by consensus-FV cell; no "
                                "registry prose number is quoted")},
        "efv_copy": efv_copy,
        "note_problems": note_problems,
        "counts": counts(events, models, reg),
        "models": models,
        "events": events,
        "backfill": backfill,
    }


def _write(doc: dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        from storage import _atomic_replace
    except Exception:                                           # noqa: BLE001
        _atomic_replace = None
    if _atomic_replace is not None:
        _atomic_replace(tmp, path)
    else:
        tmp.replace(path)


def _base_sources(reg_path: Path, progress_path: Path, typed_path: Path, progress) -> list:
    return [{"path": REGISTRY_REL, "sha256": _sha256(reg_path)},
            {"path": PROGRESS_REL, "sha256": _sha256(progress_path),
             "generated_at": (progress or {}).get("generated_at")},
            {"path": TYPED_REL, "sha256": _sha256(typed_path)}]


def _cards_today(reg: dict) -> dict:
    return {m["model_id"]: m for m in reg.get("models") or []
            if (m.get("card") or {}).get("derived_from")}


def _run(*, out_path, ledger_path, registry_path, progress_path, typed_path, today,
         now_iso, dry_run, history: list[dict] | None, backfill_receipt: dict | None,
         prev_doc: dict | None, durable: list[dict]) -> dict:
    """The shared tail of update() and backfill(): diff, copy, write."""
    reg = _load_json(registry_path) or {"models": []}
    progress = _load_json(progress_path)
    typed = _load_json(typed_path)
    existing = list(history or [])
    state = fold_state(existing)
    head = _head_short()
    ids = {e.get("event_id") for e in existing}

    def wt_read(rel):
        try:
            return (ROOT / rel).read_bytes()
        except OSError:
            return None

    new, state = registry_diff(reg, state, day=today, commit=head,
                               cards_today=_cards_today(reg), read_artifact=wt_read,
                               read_from="working tree")
    done_runs = {(e.get("source") or {}).get("run_id") for e in existing}
    efv_new, efv_info = efv_events(progress, done_runs, efv_lineage_from(existing))
    new += efv_new
    notes, probs = note_events(typed, ids, {m["model_id"] for m in reg.get("models") or []})
    new_sorted = sorted([_finish(e) if "content_hash" not in e else e for e in new],
                        key=lambda e: e["sort_date"])
    new_sorted += [e for e in notes]
    new_sorted = sorted(new_sorted, key=lambda e: e["sort_date"])
    fresh_new = [e for e in new_sorted if e["event_id"] not in ids]
    events = existing + fresh_new
    copied = sum(1 for e in events if (e.get("source") or {}).get("path") == PROGRESS_REL)
    efv_copy = {"rows_copied": copied, "skipped_other_frames": efv_info["skipped"]["other_frames"],
                "skipped_vm_after_handover": efv_info["skipped"]["vm_after_handover"],
                "not_copied_no_alias": efv_info["skipped"]["no_alias"]}
    sources = _base_sources(registry_path, progress_path, typed_path, progress)
    receipt = backfill_receipt or (prev_doc or {}).get("backfill")
    doc = build_doc(events, reg, progress, now_iso=now_iso, sources=sources,
                    backfill=receipt, efv_copy=efv_copy, note_problems=probs)
    if not dry_run:
        _write(doc, out_path)
        in_ledger = {e.get("event_id") for e in durable}
        _append_ledger(ledger_path, [e for e in events if e.get("event_id") not in in_ledger])
    last = max((e["sort_date"] for e in events), default=None)
    return {"status": "ok", "appended": [e["event_id"] for e in fresh_new],
            "n_events": len(events), "last_date": last, "note_problems": probs,
            "out": str(out_path), "ledger": str(ledger_path), "doc": doc}


def _resolve(out_path, ledger_path, registry_path, progress_path, typed_path,
             data_dir=None):
    """Paths, read from the module constants at call time (the test mirror
    redirects OUT_PATH and LEDGER_PATH). A data_dir other than the real one
    keeps every read and write inside it, the efv_progress convention."""
    if data_dir is not None and Path(data_dir).resolve() != DATA_DIR.resolve():
        d = Path(data_dir)
        out_path = out_path or d / OUT_PATH.name
        ledger_path = ledger_path or d / ".model_updates_ledger.jsonl"
        registry_path = registry_path or d / R.REGISTRY_PATH.name
        progress_path = progress_path or d / PROGRESS_NAME
        typed_path = typed_path or d / TYPED_PATH.name
    return (Path(out_path or OUT_PATH), Path(ledger_path or LEDGER_PATH),
            Path(registry_path or R.REGISTRY_PATH), Path(progress_path or DATA_DIR / PROGRESS_NAME),
            Path(typed_path or TYPED_PATH))


def update(*, data_dir=None, out_path=None, ledger_path=None, registry_path=None,
           progress_path=None, typed_path=None, now: datetime | None = None,
           dry_run: bool = False) -> dict:
    """The nightly path: merge the durable copy, diff, copy, append."""
    out, led, regp, progp, typp = _resolve(out_path, ledger_path, registry_path,
                                           progress_path, typed_path, data_dir)
    now_dt = now or datetime.now(timezone.utc)
    prev = _load_json(out) or {}
    durable = _read_ledger(led)
    history = merge_events(list(prev.get("events") or []), durable)
    if not history:
        return {"status": "no history on record; run python model_updates.py --backfill once",
                "appended": [], "n_events": 0}
    return _run(out_path=out, ledger_path=led, registry_path=regp, progress_path=progp,
                typed_path=typp, today=now_dt.astimezone().date().isoformat(),
                now_iso=_now_iso(now_dt), dry_run=dry_run, history=history,
                backfill_receipt=None, prev_doc=prev, durable=durable)


def backfill(*, data_dir=None, out_path=None, ledger_path=None, registry_path=None,
             progress_path=None, typed_path=None, now: datetime | None = None,
             dry_run: bool = False, git_root: Path = ROOT) -> dict:
    """Once: rebuild the history from the registry's first-parent git log,
    then run the nightly tail on the working tree."""
    out, led, regp, progp, typp = _resolve(out_path, ledger_path, registry_path,
                                           progress_path, typed_path, data_dir)
    prev = _load_json(out) or {}
    durable = _read_ledger(led)
    if merge_events(list(prev.get("events") or []), durable):
        return {"status": "backfill already on record; the history is append-only",
                "appended": [], "n_events": len(prev.get("events") or [])}
    now_dt = now or datetime.now(timezone.utc)
    reg_today = _load_json(regp) or {"models": []}
    cards_today = _cards_today(reg_today)
    g = _Git(git_root)
    events, state = [], {}
    versions = g.versions(REGISTRY_REL)
    read, unparseable, artifact_reads = 0, 0, 0
    prev_sig: dict[str, str | None] = {}
    try:
        for full, short, day in versions:
            raw = g.show(full, REGISTRY_REL)
            try:
                reg = json.loads(raw.decode("utf-8")) if raw is not None else None
            except (ValueError, UnicodeDecodeError):
                reg = None
            if not isinstance(reg, dict):
                unparseable += 1
                continue
            read += 1
            sigs = {m["model_id"]: _committed_card_sig(m) for m in reg.get("models") or []
                    if isinstance(m, dict) and m.get("model_id")}

            def changed(mid, m, _sigs=sigs):
                return _sigs.get(mid) is not None and _sigs.get(mid) != prev_sig.get(mid)

            def at_commit(rel, _full=full):
                nonlocal artifact_reads
                artifact_reads += 1
                return g.show(_full, rel)

            evs, state = registry_diff(reg, state, day=day, commit=short,
                                       cards_today=cards_today, read_artifact=at_commit,
                                       card_change_only_when=changed)
            events += evs
            prev_sig = sigs
    finally:
        g.close()
    events = [_finish(e) for e in events]
    receipt = {"from": "git log --first-parent -- data/model_registry.json",
               "versions_read": read, "commits": len(versions), "unparseable": unparseable,
               "artifact_reads": artifact_reads, "rows_emitted": None,
               "typed_rows": sum(1 for e in events if e["layer"] == "typed"),
               "ran_at": _now_iso(now_dt), "head": _head_short()}
    res = _run(out_path=out, ledger_path=led, registry_path=regp, progress_path=progp,
               typed_path=typp, today=now_dt.astimezone().date().isoformat(),
               now_iso=_now_iso(now_dt), dry_run=True, history=events,
               backfill_receipt=receipt, prev_doc=prev, durable=durable)
    receipt["rows_emitted"] = res["n_events"]
    res["doc"]["backfill"] = receipt
    # The backfill is the first batch, so it is ordered by date as a whole
    # (stable: within a day the registry's commit order, then the ledger's).
    # Every later run appends its own batch, ordered by date, after it.
    res["doc"]["events"] = sorted(res["doc"]["events"], key=lambda e: e["sort_date"])
    res["appended"] = [e["event_id"] for e in res["doc"]["events"]]
    if not dry_run:
        _write(res["doc"], out)
        in_ledger = {e.get("event_id") for e in durable}
        _append_ledger(led, [e for e in res["doc"]["events"]
                             if e.get("event_id") not in in_ledger])
    return res


def summary_line(res: dict) -> str:
    """One line for a heartbeat and the ingest-health row."""
    if res.get("status") != "ok":
        return str(res.get("status"))[:120]
    return (f"{res.get('n_events')} events, {len(res.get('appended') or [])} new, "
            f"last event {res.get('last_date')}")


def load(path: Path | None = None) -> dict | None:
    return _load_json(path or OUT_PATH)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dry = "--dry-run" in sys.argv
    if "--backfill" in sys.argv:
        r = backfill(dry_run=dry)
    else:
        r = update(dry_run=dry)
    print(summary_line(r))
    if r.get("doc"):
        c = r["doc"]["counts"]
        print(json.dumps({k: c[k] for k in ("events", "default_view", "by_kind", "by_layer",
                                              "verdict_changes", "scored_models",
                                              "scored_legs", "model_states")}, indent=1))
        if r["doc"].get("backfill"):
            print(json.dumps(r["doc"]["backfill"]))
    if r.get("note_problems"):
        print("NOTE PROBLEMS:", r["note_problems"])
