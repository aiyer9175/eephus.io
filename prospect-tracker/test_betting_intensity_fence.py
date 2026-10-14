# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""THE WALL between the game-intensity chip and every betting price (plan Part 8,
item IX-S1; the betting section "Game intensity: stakes, matchup quality and the
postseason": the chip is a rendering beside a price, not a candidate, a column or a
look, and it reads into no probability, edge, expected value, Kelly figure, slot,
badge or record row). Modelled on test_betting_mgmt_fence.py, the 5l Dugout precedent.

  1. no pricer module (that file's PRICER_MODULES plus tools/betting_*.py) imports
     betting_intensity or names it or its payload key;
  2. betting_export reads the chip through one seam: one Import, the binding
     `intensity` Stored once in build behind SHOW_INTENSITY_CHIP and Loaded exactly
     twice (the payload key and the preview entry), never an argument of any Call,
     built from the PAYLOAD's list and date, and added after every other payload key
     but the Dugout block, which stays last; dfs_export calls the same function once,
     behind the same flag, on its draftable slate;
  3. no shadow, record, calibration or slot row carries a key that starts "ix_" or
     contains "intensity": the shadow, settlement and learning modules name none,
     and an executed build with the flag on carries none outside the block itself;
  4. the renderers never draw the chip on a started or settled game (the clock and
     status guards, by source; test_betting_intensity.py renders them);
  5. the flag is off, and with it off the payload and the preview carry no key.

The executed half builds the payload offline in the test_betting_mgmt_fence idiom:
bi.STATUS_PATH pointed at tmp, `_write` captured in memory, every other writer inside
build wrapped to write=False, so nothing under data/ or .cache/ moves. With the flag on,
build_block is replaced by a stub returning a fixture block, so no intensity value is
computed for a real game.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from test_betting_mgmt_fence import PRICER_MODULES, _imports

ROOT = Path(__file__).resolve().parent
PAYLOAD_KEY = "intensity"
#: The modules that write shadow, settlement and calibration rows.
ROW_MODULES = ("betting_shadow.py", "betting_settle.py", "betting_learning.py")


def _pricer_files() -> list[Path]:
    files = [ROOT / n for n in PRICER_MODULES if (ROOT / n).exists()]
    files += sorted((ROOT / "tools").glob("betting_*.py"))
    assert (ROOT / "betting_model.py") in files
    return files


def _string_constants(tree: ast.AST) -> list[str]:
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


# ---------------------------------------------------------------------------
# 1. no pricer module reaches the chip
# ---------------------------------------------------------------------------
def test_no_pricer_module_imports_the_chip_or_names_its_key():
    offenders = []
    for p in _pricer_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
        for name in _imports(tree):
            if name.startswith("betting_intensity"):
                offenders.append(f"{p.name} imports {name}")
        if "betting_intensity" in src:
            offenders.append(f"{p.name} names betting_intensity")
        if "SHOW_INTENSITY_CHIP" in src:
            offenders.append(f"{p.name} names SHOW_INTENSITY_CHIP")
        for s in _string_constants(tree):
            if s == PAYLOAD_KEY:
                offenders.append(f"{p.name} names the payload key {s!r}")
    assert not offenders, offenders


def test_the_chip_imports_no_pricer():
    tree = ast.parse((ROOT / "betting_intensity.py").read_text(encoding="utf-8"))
    names = _imports(tree)
    pricers = {Path(n).stem for n in PRICER_MODULES} | {"betting_export", "betting_dugout"}
    assert not [n for n in names if n.split(".")[0] in pricers], names
    assert "intensity_core" in names


# ---------------------------------------------------------------------------
# 2. one seam, by AST
# ---------------------------------------------------------------------------
EXPORT_SRC = (ROOT / "betting_export.py").read_text(encoding="utf-8")
EXPORT_TREE = ast.parse(EXPORT_SRC)


def _fn(tree, name) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _is_sub(node, owner: str, key: str) -> bool:
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == owner and isinstance(node.slice, ast.Constant)
            and node.slice.value == key)


def _guarded(fn: ast.AST, target: ast.AST) -> bool:
    """True when `target` sits inside an `if bix.SHOW_INTENSITY_CHIP:` body."""
    for node in ast.walk(fn):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Attribute)
                and node.test.attr == "SHOW_INTENSITY_CHIP"
                and isinstance(node.test.value, ast.Name) and node.test.value.id == "bix"
                and not node.orelse):
            for stmt in node.body:
                if any(sub is target for sub in ast.walk(stmt)):
                    return True
    return False


def test_betting_export_reads_the_chip_through_one_seam_only():
    imports = [n for n in ast.walk(EXPORT_TREE) if isinstance(n, ast.Import)
               and any(a.name == "betting_intensity" for a in n.names)]
    assert len(imports) == 1 and imports[0].names[0].asname == "bix"
    assert not any(isinstance(n, ast.ImportFrom)
                   and (n.module or "").startswith("betting_intensity")
                   for n in ast.walk(EXPORT_TREE))
    uses = [n for n in ast.walk(EXPORT_TREE) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name) and n.value.id == "bix"]
    assert sorted(u.attr for u in uses) == ["SHOW_INTENSITY_CHIP", "SHOW_INTENSITY_CHIP",
                                            "build_block"]

    fn = _fn(EXPORT_TREE, "build")
    stores = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "intensity"
              and isinstance(n.ctx, ast.Store)]
    loads = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "intensity"
             and isinstance(n.ctx, ast.Load)]
    assert len(stores) == 1 and len(loads) == 2

    assign = next(n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "intensity" for t in n.targets))
    call = assign.value
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
    assert call.func.attr == "build_block" and call.func.value.id == "bix"
    assert len(call.args) == 2 and not call.keywords
    assert _is_sub(call.args[0], "payload", "team_bets")
    assert _is_sub(call.args[1], "payload", "slate_date")
    assert _guarded(fn, assign)

    key_assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                   and _is_sub(n.targets[0], "payload", PAYLOAD_KEY)]
    prev_assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign) and len(n.targets) == 1
                    and _is_sub(n.targets[0], "preview", PAYLOAD_KEY)]
    assert len(key_assigns) == 1 and len(prev_assigns) == 1
    for a in key_assigns + prev_assigns:
        assert isinstance(a.value, ast.Name) and a.value.id == "intensity"
        assert _guarded(fn, a)

    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            for a in list(n.args) + [kw.value for kw in n.keywords]:
                for sub in ast.walk(a):
                    assert not (isinstance(sub, ast.Name) and sub.id == "intensity"), (
                        "`intensity` is passed to a call inside build; the block enters nothing")
    outside = [n for n in ast.walk(EXPORT_TREE) if isinstance(n, ast.Name)
               and n.id == "intensity"]
    assert len(outside) == 3
    # the payload key is named only at the two seam subscripts
    consts = [s for s in _string_constants(EXPORT_TREE) if "intensity" in s.lower()]
    assert consts == [PAYLOAD_KEY, PAYLOAD_KEY], consts


def test_the_chip_is_added_after_every_payload_key_but_the_dugout_block():
    fn = _fn(EXPORT_TREE, "build")
    ix_line = next(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and len(n.targets) == 1 and _is_sub(n.targets[0], "payload", PAYLOAD_KEY))
    dugout_line = next(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
                       and len(n.targets) == 1
                       and _is_sub(n.targets[0], "payload", "dugout_context"))
    others = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                        and t.value.id == "payload"
                        and not _is_sub(t, "payload", PAYLOAD_KEY)
                        and not _is_sub(t, "payload", "dugout_context")):
                    others.append(n.lineno)
    preview_line = next(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "preview"
                                for t in n.targets))
    assert others and max(others) < ix_line < dugout_line < preview_line


def test_dfs_export_calls_the_same_function_once_behind_the_flag():
    src = (ROOT / "dfs_export.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and n.func.attr == "build_block"]
    assert len(calls) == 1
    call = calls[0]
    assert call.func.value.id == "bix"
    assert [kw.arg for kw in call.keywords] == ["surface"]
    assert call.keywords[0].value.value == "dfs"
    assert isinstance(call.args[0], ast.Name) and call.args[0].id == "slate_games"
    fn = _fn(tree, "build_payload")
    assign = next(n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and len(n.targets) == 1 and _is_sub(n.targets[0], "payload", PAYLOAD_KEY))
    assert assign.value is call and _guarded(fn, assign)
    assert "SHOW_INTENSITY_CHIP" in src


# ---------------------------------------------------------------------------
# 3. no row carries an intensity key
# ---------------------------------------------------------------------------
def test_no_shadow_settlement_or_calibration_module_names_an_intensity_key():
    offenders = []
    for name in ROW_MODULES:
        p = ROOT / name
        if not p.exists():
            continue
        for s in _string_constants(ast.parse(p.read_text(encoding="utf-8"))):
            if s.startswith("ix_") or "intensity" in s.lower():
                offenders.append(f"{name}: {s!r}")
    assert not offenders, offenders


def _bad_keys(obj, path="") -> list[str]:
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            ks = str(k)
            here = f"{path}.{ks}" if path else ks
            if ks.startswith("ix_") or "intensity" in ks.lower():
                out.append(here)
            out.extend(_bad_keys(v, here))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_bad_keys(v, f"{path}[{i}]"))
    return out


FIXTURE_BLOCK = {"status": "built", "construction": "ix_v1", "games": {},
                 "summary": "Game intensity, not priced"}


def _build(monkeypatch_flag: bool):
    be = pytest.importorskip("betting_export")
    bi = pytest.importorskip("betting_ingest")
    import betting_intensity as bix
    mp = pytest.MonkeyPatch()
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="intensity_fence_"))
    mp.setattr(bi, "STATUS_PATH", tmp / "betting_status.json")
    written: dict = {}
    mp.setattr(be, "_write", lambda path, payload: written.__setitem__(Path(path).name, payload))

    def _dry(fn):
        def inner(*a, **kw):
            kw["write"] = False
            return fn(*a, **kw)
        return inner
    for name in ("market_gate_evaluate", "apply_slot_lock", "settle_record",
                 "maybe_publish_record"):
        mp.setattr(be, name, _dry(getattr(be, name)))
    for name in ("ensure_record_log", "render_record", "write_published_chain"):
        mp.setattr(be, name, lambda *a, **kw: None)
    calls = []
    if monkeypatch_flag:
        mp.setattr(bix, "SHOW_INTENSITY_CHIP", True)

        def stub(bets, slate_date, **kw):
            calls.append((bets, slate_date, kw))
            return dict(FIXTURE_BLOCK)
        mp.setattr(bix, "build_block", stub)
    try:
        payload = be.build(write=True)
    finally:
        mp.undo()
    return payload, written, calls


@pytest.fixture(scope="module")
def built_on():
    return _build(True)


@pytest.fixture(scope="module")
def built_off():
    return _build(False)


def test_with_the_flag_on_the_block_rides_beside_and_enters_no_row(built_on):
    payload, written, calls = built_on
    assert len(calls) == 1
    bets, slate_date, kw = calls[0]
    assert bets is payload["team_bets"] and slate_date == payload["slate_date"] and not kw
    assert payload[PAYLOAD_KEY] == FIXTURE_BLOCK
    keys = list(payload)
    assert keys[-1] == "dugout_context" and keys[-2] == PAYLOAD_KEY
    prev = written["betting_preview.json"]
    assert prev[PAYLOAD_KEY] is payload[PAYLOAD_KEY]
    for doc in (payload, prev):
        rest = {k: v for k, v in doc.items() if k != PAYLOAD_KEY}
        assert _bad_keys(rest) == [], _bad_keys(rest)
    for slot in ("pick_of_the_day", "longshot_of_the_day", "slot_lock", "pick_meta",
                 "record"):
        assert _bad_keys(payload.get(slot)) == []


# ---------------------------------------------------------------------------
# 4. the renderers' guards, by source
# ---------------------------------------------------------------------------
def _js_fn(src: str, name: str) -> str:
    m = re.search(r"function " + name + r"\(([^)]*)\) \{(.*?)\n  \}", src, re.S)
    assert m, name
    return m.group(2)


def test_the_betting_renderer_guards_on_the_clock_and_the_status():
    src = (ROOT / "assets" / "betting.js").read_text(encoding="utf-8")
    pre = _js_fn(src, "ixPregame")
    assert "gameStarted(b)" in pre and "IX_PREGAME[b.status]" in pre
    blk = _js_fn(src, "ixBlock")
    assert "ixPregame(b)" in blk and 'ctx.status !== "built"' in blk
    # drawn on the game card and the Model Watch card (by its game's row) only
    assert src.count("ixBlock(") == 3
    assert "ixBlock(b) + dugoutBlock(b.game_pk)" in src
    assert "ixBlock(pastGame) + dugoutBlock(p.game_pk)" in src
    # no price key is read inside the chip's renderer
    for k in ("model_prob", "edge", "odds", "kelly", "ev_per_unit", "moneyline"):
        assert k not in blk and k not in pre


def test_the_dfs_renderer_guards_on_the_clock_and_the_status():
    src = (ROOT / "assets" / "dfs.js").read_text(encoding="utf-8")
    card = _js_fn(src, "ixCard")
    assert "firstPitchMs(g)" in card and "IX_PREGAME[g.status]" in card
    assert 'ctx.status !== "built"' in card
    assert src.count("ixCard(") == 2


# ---------------------------------------------------------------------------
# 5. the flag is off, and off means no key
# ---------------------------------------------------------------------------
def test_the_flag_is_off_and_off_means_no_key(built_off):
    import betting_intensity as bix
    assert bix.SHOW_INTENSITY_CHIP is False
    payload, written, calls = built_off
    assert calls == []
    assert PAYLOAD_KEY not in payload
    assert PAYLOAD_KEY not in written["betting_preview.json"]
    assert list(payload)[-1] == "dugout_context"


def test_with_the_flag_off_the_dfs_payload_carries_no_key():
    from test_dfs_served_counts import _build as dfs_build
    p = dfs_build()
    assert p.get("n_games") == 1 and PAYLOAD_KEY not in p
