# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""eFV v4: Driver System V2 plus the new-source columns of the eFV v4 research lanes,
selected by the rule of docs/efv-v2/EFV_V4_BACKTEST.md (EFV4_SELECT_SHIP; owner EW2-8 to
EW2-12, 2026-10-08).

DARK. EFV_V4_ON is False: nothing served reads this module's fit while it is off
(efv_v2_serve.production_models checks the flag and fits V2 as before). The flag flips
only through the ship rule of the backtest document (EW2-10: v4 beats served V2 on
lv_dev, vm_dev, R-LV and R-VM, point estimates pooled over sides).

THE CONFIGURATION SPACE. A v4 configuration is V2 (efv_v2_model.fit_v2 at the P5 weights
the owner kept, EW2-9) with v4 COLUMNS ADDED to a head: each is offered to the skill or
timing head of its side beside the side's own candidates, under the unchanged DS-06
admission rule inside every fold. Nothing is re-weighted, removed or re-anchored: the v3
menu was read once on the reserved frames and is spent. fit_v4 is efv_v3.fit_v3 at a
configuration whose only entries are additions, with the v4 columns registered in
efv_v3.W2_COLUMNS for the life of the call (registered()); at base_config() it is fit_v2
bit for bit (test_efv_v4.py).

THE MENU (menu_columns): every arm of the seven v4 families whose registered development
read (data/_labs/efv_w2/efv_w2_<family>.json) admitted it in at least one fold of lv_dev
or vm_dev, at the head that read declared (the report fields at the head the
report_absent probe resolved), in family order then registered order. A column refused
in every development fold is V2 itself and is not offered; a withheld report field is
not offered; the park correction is a flagged replacement, not a column.

The committed configuration lives in data/efv_v4_spec.json (SPEC_PATH), written by
tools/efv_v4_backtest.py --select and read by load_spec / spec_config.

RESERVED FRAMES. Nothing here reads a frame or a label. fit_v4 runs
efv_v2_candidates.guard_training_rows (through fit_v3) first: a reserved list vintage or a
2025+ year in the training rows raises unless the committed gate's sha is handed in.

GATE COMPLIANCE (docs/PROSPECT_ANCHOR_GATE.md): consensus enters as a within-group
percentile and as the value multiset the grade is drawn from. Nothing here groups,
counts or averages rows by consensus-FV level; test_efv_v4.py scans this source.
"""
from __future__ import annotations

import copy
import json
import re
from contextlib import contextmanager
from pathlib import Path

import efv_v2_model as H
import efv_v3 as V3
import efv_vintage_frame as F

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
LAB_DIR = DATA_DIR / "_labs" / "efv_w2"

#: THE SWITCH. False: nothing served reads a v4 fit. Flips through the ship rule only.
EFV_V4_ON = False
MODEL_ID = "efv_v4"
#: The committed configuration (tools/efv_v4_backtest.py --select writes it once).
SPEC_PATH = DATA_DIR / "efv_v4_spec.json"
#: The selection rule, the step log and the spent-frame read.
BACKTEST_DOC = "docs/efv-v2/EFV_V4_BACKTEST.md"
HEADS: tuple[str, ...] = V3.HEADS

#: The seven v4 families in menu order: the module that builds the column, the
#: registered development artifact whose admission receipts make the menu, and the
#: arm field that names the builder's argument.
FAMILIES: tuple[dict, ...] = (
    {"family": "il", "module": "efv_w2_il_backfill", "artifact": "efv_w2_il_backfill.json",
     "arg": "stat"},
    {"family": "nri", "module": "efv_w2_nri", "artifact": "efv_w2_nri.json", "arg": "stat"},
    {"family": "pbp", "module": "efv_w2_pbp", "artifact": "efv_w2_pbp.json", "arg": "stat"},
    {"family": "pbp_bb", "module": "efv_w2_pbp_bb", "artifact": "efv_w2_pbp_bb.json",
     "arg": "stat"},
    {"family": "popmle", "module": "efv_w2_popmle", "artifact": "efv_w2_popmle.json",
     "arg": None},
    {"family": "raters", "module": "efv_w2_raters", "artifact": "efv_w2_raters.json",
     "arg": None},
    {"family": "report", "module": "efv_w2_report_llm", "artifact": "efv_w2_report_llm.json",
     "arg": "field_column"},
)
_FOLDS_RE = re.compile(r"^\s*(\d+)\s*(?:/|of)\s*(\d+)\s*$")
_MENU: dict | None = None


# ---------------------------------------------------------------------------
# the menu, derived from the registered development artifacts
# ---------------------------------------------------------------------------

def _folds(s) -> tuple[int, int] | None:
    m = _FOLDS_RE.match(str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def _artifact(fam: dict) -> dict:
    return json.loads((LAB_DIR / fam["artifact"]).read_text(encoding="utf-8"))


def _declared(fam: dict, doc: dict) -> list[dict]:
    """[{name, side, head, arg, withheld}] in the family's registered order."""
    if fam["family"] == "report":
        return [{"name": a["name"], "side": a["side"], "head": a["head"],
                 "arg": a["field_column"], "withheld": a.get("withheld")}
                for a in doc["arms_declared"]]
    arms = __import__(fam["module"]).ARMS
    out = []
    for a in arms:
        if fam["family"] == "raters":
            if len(a["sides"]) != 1:
                continue
            out.append({"name": a["name"], "side": a["sides"][0], "head": a["head"],
                        "arg": a["name"], "withheld": None})
        else:
            out.append({"name": a["name"], "side": a["side"], "head": a["head"],
                        "arg": a[fam["arg"]] if fam["arg"] else a["name"], "withheld": None})
    return out


def _admission(fam: dict, doc: dict) -> dict:
    """{arm name: {"lv_dev": (a, b) | None, "vm_dev": (a, b) | None}}."""
    rows = doc["dev"]["summary"] if fam["family"] == "raters" else doc["summary"]
    out = {}
    for e in rows:
        out[e.get("arm")] = {fid: _folds((e.get(fid) or {}).get("admitted_folds"))
                             for fid in ("lv_dev", "vm_dev")}
    return out


def menu_columns(*, refresh: bool = False) -> dict[str, dict]:
    """{name: {side, head, module, arg, family, key, admitted}} for every v4 column on
    the menu (admitted in at least one development fold on either frame), in family
    order then registered order. Memoized per process."""
    global _MENU
    if _MENU is not None and not refresh:
        return _MENU
    out: dict = {}
    for fam in FAMILIES:
        doc = _artifact(fam)
        adm = _admission(fam, doc)
        for a in _declared(fam, doc):
            if a.get("withheld"):
                continue
            rec = adm.get(a["name"])
            if rec is None:
                continue
            n = sum((rec[fid] or (0, 0))[0] for fid in ("lv_dev", "vm_dev"))
            if n <= 0:
                continue
            if a["name"] in out or a["name"] in V3.W2_COLUMNS:
                raise RuntimeError(f"{a['name']} is already a column")
            out[a["name"]] = {"side": a["side"], "head": a["head"], "module": fam["module"],
                              "arg": a["arg"], "family": fam["family"],
                              "key": f"{H.V2_SCREEN_PREFIX}{a['name']}",
                              "admitted": {fid: (None if rec[fid] is None
                                                else f"{rec[fid][0]}/{rec[fid][1]}")
                                           for fid in ("lv_dev", "vm_dev")}}
    _MENU = out
    return out


@contextmanager
def registered(names=None):
    """The v4 menu columns (or `names`) as efv_v3.W2_COLUMNS entries for the life of the
    block, so efv_v3's fit, candidate lists and attach path read them; removed
    afterwards, so the v3 menu is never widened. Re-entrant: a name already registered
    by an outer block is left alone."""
    menu = menu_columns()
    want = list(menu) if names is None else list(names)
    added = []
    try:
        for n in want:
            if n in V3.W2_COLUMNS:
                continue
            spec = menu.get(n)
            if spec is None:
                raise KeyError(f"{n} is not a v4 menu column")
            V3.W2_COLUMNS[n] = {k: spec[k] for k in ("side", "head", "module", "arg", "key")}
            added.append(n)
        yield V3.W2_COLUMNS
    finally:
        for n in added:
            V3.W2_COLUMNS.pop(n, None)


# ---------------------------------------------------------------------------
# configurations
# ---------------------------------------------------------------------------

def base_config() -> dict:
    """V2 exactly: no anchor, every factor 1.0, nothing removed, nothing added."""
    return V3.base_config()


def validate_config(cfg: dict) -> dict:
    """The configuration, checked: no anchor, factors 1.0, nothing removed, every added
    column a v4 menu column on its own side and head."""
    if cfg.get("anchor") is not None:
        raise ValueError("a v4 configuration takes no anchor")
    menu = menu_columns()
    for s in F.SIDES:
        for h in HEADS:
            if float(cfg["scale"][s][h]) != 1.0:
                raise ValueError(f"a v4 configuration keeps the P5 weight of {s} {h}")
            if cfg["remove"][s][h]:
                raise ValueError(f"a v4 configuration removes no driver ({s} {h})")
            for a in cfg["add"][s][h]:
                spec = menu.get(a)
                if spec is None or spec["side"] != s or spec["head"] != h:
                    raise ValueError(f"{a} is not a v4 {s} {h} column")
    with registered(added(cfg)):
        V3.validate_config(cfg)
    return cfg


def added(cfg: dict) -> list[str]:
    return [a for s in F.SIDES for h in HEADS for a in cfg["add"][s][h]]


def is_base(cfg: dict) -> bool:
    return V3.is_base(cfg)


def describe(cfg: dict) -> str:
    parts = [f"{s} {h} plus {a}" for s in F.SIDES for h in HEADS for a in cfg["add"][s][h]]
    return "; ".join(parts) if parts else "V2 as assembled (no step)"


def with_column(cfg: dict, name: str) -> dict:
    spec = menu_columns()[name]
    new = copy.deepcopy(cfg)
    new["add"][spec["side"]][spec["head"]].append(name)
    return validate_config(new)


# ---------------------------------------------------------------------------
# the fit (efv_v3's machinery at an add-only configuration)
# ---------------------------------------------------------------------------

def fit_v4(train: list[dict], side: str, *, frame: str, weights: dict[str, dict],
           cfg: dict, absent_ok: bool | None = None, gate_sha: str | None = None) -> dict:
    """v4 on one fold's training rows (each carrying `v2`, `fv`, `target`, `reached`,
    `decision_year`; every added column already on the v2 view under its key). At
    base_config() this is fit_v2's model, bit for bit."""
    validate_config(cfg)
    with registered(added(cfg)):
        m = V3.fit_v3(train, side, frame=frame, weights=weights, cfg=cfg,
                      absent_ok=absent_ok, gate_sha=gate_sha)
    m["model_id"] = MODEL_ID
    return m


def predict_v4(model: dict, rows: list[dict]) -> list[dict]:
    """predict_v2's output under the configuration (the added columns are read from
    the rows' v2 view by key; no registration is needed to score)."""
    return V3.predict_v3(model, rows)


# ---------------------------------------------------------------------------
# the committed spec and the dark production fit
# ---------------------------------------------------------------------------

def load_spec(path: Path | None = None) -> dict:
    p = SPEC_PATH if path is None else Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def spec_config(spec: dict | None = None) -> dict:
    """The committed configuration, validated."""
    doc = load_spec() if spec is None else spec
    return validate_config(copy.deepcopy(doc["config"]))


def production_models(*, weights: dict | None = None) -> dict[str, dict]:
    """The dark production fit: v4 at the committed configuration on the v1 matrices,
    decision years before the R-VM cohort. Read only while EFV_V4_ON is True. The live
    path has no v4 column builder: the ship step wires one when the rule passes; until
    then a configuration with an added column raises rather than serving a half-built
    fit, and the base configuration is V2 itself."""
    cfg = spec_config()
    if added(cfg):
        raise NotImplementedError("the live path has no v4 column builder yet (the ship "
                                  "step of EFV4_SELECT_SHIP wires it)")
    w = H.load_weights() if weights is None else weights
    out = {}
    for side in F.SIDES:
        train = [r for r in H.matrix_training_rows(side)
                 if int(r["decision_year"]) < F.train_end_year()]
        m = fit_v4(train, side, frame="vm", weights=w, cfg=cfg)
        m["war_map_6yr"] = H.fit_war_map(train)
        m["train_years"] = sorted({int(r["decision_year"]) for r in train})
        out[side] = m
    return out
