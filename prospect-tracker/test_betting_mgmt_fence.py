# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""THE WALL between In-Game Management and every betting price (D4, 2026-09-23).

Layer 1 (the Dugout context block) reads the management board through ONE seam in
betting_export.build and is passed to nothing. Layer 2 (the 5l club-policy columns)
is registration only until 2027. This file pins the wall from the pricer side:

  1. no pricer module imports a management module or names the board, the ledger
     directory or the block;
  2. betting_export reads the board through betting_dugout only: one Import, the
     binding `dugout` Stored once in build and Loaded exactly twice (the payload key
     and the preview entry), never an argument of any Call, and built from the
     PAYLOAD's list and date (review defect M2: a carried night replaces both);
  3. the block is the last key added to the payload before the preview is sliced;
  4. the preview carries the block whole, and a redacted slot carries no game_pk (the
     redaction guard, review defect L8);
  5. no dark or served team column starts with "mg_" at HEAD (registration only; this
     assertion is REPLACED by the schema-7 pin when the builder legitimately lands).

The executed half builds the payload once, offline, the test_betting_publish_hygiene
idiom: bi.STATUS_PATH pointed at tmp, `_write` captured in memory, and every other
writer inside build wrapped to write=False, so nothing under data/ or .cache/ moves.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent

PRICER_MODULES = ("betting_model.py", "leaderboard_vintages.py", "betting_ingest.py",
                  "betting_shadow.py", "betting_settle.py", "betting_learning.py",
                  "betting_credits.py", "betting_usage.py", "betting_weather.py",
                  "betting_props_dark.py")
BANNED_IMPORT_PREFIXES = ("mgmt_", "management", "betting_dugout")
BANNED_STRINGS = ("management_board", "mgmt_decisions", "dugout_context")


def _pricer_files() -> list[Path]:
    files = [ROOT / n for n in PRICER_MODULES if (ROOT / n).exists()]
    files += sorted((ROOT / "tools").glob("betting_*.py"))
    assert (ROOT / "betting_model.py") in files
    return files


def _imports(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            out.append(node.module or "")
    return out


# ---------------------------------------------------------------------------
# 1. no pricer module reaches management
# ---------------------------------------------------------------------------
def test_no_betting_pricer_module_imports_a_management_module():
    offenders = []
    for p in _pricer_files():
        src = p.read_text(encoding="utf-8", errors="replace")
        for name in _imports(ast.parse(src)):
            if any(name.startswith(b) for b in BANNED_IMPORT_PREFIXES):
                offenders.append(f"{p.name} imports {name}")
        for s in BANNED_STRINGS:
            if s in src:
                offenders.append(f"{p.name} names {s}")
    assert not offenders, offenders


# ---------------------------------------------------------------------------
# 2. one seam, by AST
# ---------------------------------------------------------------------------
EXPORT_SRC = (ROOT / "betting_export.py").read_text(encoding="utf-8")
EXPORT_TREE = ast.parse(EXPORT_SRC)


def _build_fn() -> ast.FunctionDef:
    for node in EXPORT_TREE.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build":
            return node
    raise AssertionError("betting_export.build not found")


def _is_payload_sub(node, key: str) -> bool:
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == "payload" and isinstance(node.slice, ast.Constant)
            and node.slice.value == key)


def test_betting_export_reads_the_board_through_one_seam_only():
    imports = [n for n in ast.walk(EXPORT_TREE) if isinstance(n, ast.Import)
               and any(a.name == "betting_dugout" for a in n.names)]
    assert len(imports) == 1, "exactly one `import betting_dugout as bd`"
    assert imports[0].names[0].asname == "bd"
    assert "management_board" not in EXPORT_SRC
    assert not any(isinstance(n, ast.ImportFrom) and (n.module or "").startswith("betting_dugout")
                   for n in ast.walk(EXPORT_TREE))

    fn = _build_fn()
    stores = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "dugout"
              and isinstance(n.ctx, ast.Store)]
    loads = [n for n in ast.walk(fn) if isinstance(n, ast.Name) and n.id == "dugout"
             and isinstance(n.ctx, ast.Load)]
    assert len(stores) == 1, "the name `dugout` is bound exactly once inside build"
    assert len(loads) == 2, "the name `dugout` is read exactly twice inside build"

    # the one Store: dugout = bd.build_block(payload["team_bets"], payload["slate_date"])
    assign = next(n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "dugout" for t in n.targets))
    call = assign.value
    assert isinstance(call, ast.Call)
    assert isinstance(call.func, ast.Attribute) and call.func.attr == "build_block"
    assert isinstance(call.func.value, ast.Name) and call.func.value.id == "bd"
    assert len(call.args) == 2 and not call.keywords
    assert _is_payload_sub(call.args[0], "team_bets"), (
        "the first argument must be payload['team_bets'], never the local `bets` (M2)")
    assert _is_payload_sub(call.args[1], "slate_date"), (
        "the second argument must be payload['slate_date'] (M2)")

    # Load 1: payload["dugout_context"] = dugout
    key_assigns = [n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                   and len(n.targets) == 1 and _is_payload_sub(n.targets[0], "dugout_context")]
    assert len(key_assigns) == 1
    assert isinstance(key_assigns[0].value, ast.Name) and key_assigns[0].value.id == "dugout"

    # Load 2: the preview dict literal entry "dugout_context": dugout
    dict_entries = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if isinstance(k, ast.Constant) and k.value == "dugout_context":
                    dict_entries.append(v)
    assert len(dict_entries) == 1
    assert isinstance(dict_entries[0], ast.Name) and dict_entries[0].id == "dugout"

    # never an argument of any Call
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            for a in list(n.args) + [kw.value for kw in n.keywords]:
                for sub in ast.walk(a):
                    assert not (isinstance(sub, ast.Name) and sub.id == "dugout"), (
                        "`dugout` is passed to a call inside build; the block enters nothing")
    # and nowhere else in the module
    outside = [n for n in ast.walk(EXPORT_TREE) if isinstance(n, ast.Name) and n.id == "dugout"]
    assert len(outside) == 3


def test_the_block_is_the_last_key_added_before_the_preview():
    fn = _build_fn()
    key_line = next(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
                    and len(n.targets) == 1 and _is_payload_sub(n.targets[0], "dugout_context"))
    other_lines = []
    for n in ast.walk(fn):
        if isinstance(n, (ast.Assign, ast.AugAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                        and t.value.id == "payload" and not _is_payload_sub(t, "dugout_context")):
                    other_lines.append(n.lineno)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "append":
            src_line = EXPORT_SRC.splitlines()[n.lineno - 1]
            if "blockers" in src_line or "pick_blockers" in src_line:
                other_lines.append(n.lineno)
    preview_line = next(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "preview" for t in n.targets))
    assert other_lines and key_line > max(other_lines), (key_line, max(other_lines))
    assert key_line < preview_line


# ---------------------------------------------------------------------------
# 4. the preview carries the block whole (executed, offline)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def built():
    """build(write=True) with `_write` captured and every other writer forced to
    write=False, so the preview dict is observable and nothing on disk moves."""
    be = pytest.importorskip("betting_export")
    bi = pytest.importorskip("betting_ingest")
    mp = pytest.MonkeyPatch()
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="dugout_fence_"))
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
    try:
        payload = be.build(write=True)
        yield payload, written
    finally:
        mp.undo()


def test_the_preview_carries_the_block_whole(built):
    payload, written = built
    assert "betting.json" in written and "betting_preview.json" in written
    assert "dugout_context" in payload
    assert written["betting_preview.json"]["dugout_context"] == payload["dugout_context"]
    assert written["betting_preview.json"]["dugout_context"] is payload["dugout_context"]
    assert list(payload).index("dugout_context") == len(payload) - 1, (
        "dugout_context is the last key on the payload")
    # the redaction guard (L8): a redacted slot entry carries no game_pk
    for slot in ("pick_of_the_day", "longshot_of_the_day"):
        p = written["betting_preview.json"].get(slot)
        if isinstance(p, dict) and p.get("redacted"):
            assert "game_pk" not in p, "a redacted slot must not carry game_pk"


def test_the_block_on_the_payload_is_the_sidecars_for_the_payloads_list(built):
    """The seam's first argument is the payload's list: rebuilding the block from
    payload['team_bets'] and payload['slate_date'] reproduces it exactly."""
    bd = pytest.importorskip("betting_dugout")
    payload, _ = built
    blk = payload["dugout_context"]
    again = bd.build_block(payload["team_bets"], payload["slate_date"])
    assert blk == again
    assert set(blk["games"]) == {str(b["game_pk"]) for b in payload["team_bets"]}
    assert blk["season"] == int(payload["slate_date"][:4])
    assert bd.forbidden_keys(blk) == []


# ---------------------------------------------------------------------------
# 5. registration only: no dugout column at HEAD
# ---------------------------------------------------------------------------
def test_betting_model_and_leaderboard_vintages_have_no_dugout_column():
    bm = pytest.importorskip("betting_model")
    lv = pytest.importorskip("leaderboard_vintages")
    cols = list(getattr(lv, "TEAM_COLUMNS", ())) + list(getattr(bm, "DARK_TEAM_COLUMNS", ()))
    for name, val in vars(bm).items():
        if name.startswith("DARK") and name.endswith("_TEAM_COLUMNS") and isinstance(val, tuple):
            cols += list(val)
    assert not any(str(c).startswith("mg_") for c in cols), (
        "a 5l column exists at HEAD; replace this assertion with the schema-7 pin in "
        "test_leaderboard_vintages.py in the same commit as the builder")
    assert getattr(bm, "SERVE_MGMT_POLICY", False) is False
