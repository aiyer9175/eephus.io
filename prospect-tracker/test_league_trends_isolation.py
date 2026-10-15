# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""League Trends stays apart from the betting side (plan section 7, Part 8
8.A; task TR_3_EXPORT_PIPELINE_DARK).

Both directions, by AST and by string:
  1. no betting module, no betting tool and leaderboard_vintages imports a
     League Trends module or names a League Trends file;
  2. no League Trends module imports a betting module, names a betting,
     vintage, lineup, odds, weather or game-feed cache or
     data/betting_model_context.json, or calls the corpus map builder (club
     identity comes from trend_frames' own half-inning vote);
  3. no League Trends module names a string section 5m or section 5l of
     docs/diamond-betting.md bans;
  4. no League Trends module writes under the Swing+ cache or edits P8.2's
     mlbstats_games, and the two writers that sit next to a protected cache
     refuse it as an out directory;
  5. the payload carries no per-hand key.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent

#: League Trends' own modules (plan 5.1).
TREND_FILES = ("league_trends_export.py", "trend_frames.py", "trend_detect.py",
               "savant_days.py", "tools/league_trends_calibrate.py",
               "tools/build_pitch_physics.py")
TREND_MODULES = frozenset(Path(f).stem for f in TREND_FILES)
#: Names a betting-side file must never carry.
TREND_STRINGS = ("league_trends", "trend_frames", "trend_detect", "savant_days", "pbp_physics")
#: The caches and the file plan section 7 bars League Trends from.
BANNED_PATHS = (".cache/betting", "cache\" / \"betting", "leaderboard_vintages",
                "lineup_captures", ".cache/odds", "weather_forecasts", "game_feeds",
                "betting_model_context")
BANNED_SEGMENTS = frozenset({"betting", "leaderboard_vintages", "lineup_captures", "odds",
                             "weather_forecasts", "game_feeds"})
#: Section 5m's and section 5l's banned strings.
BANNED_STRINGS = ("sp_n365", "sp_budget", "sp_ppo", "sp_xouts", "bat_ppa_l30",
                  "mg_pen_", "mg_hook_")
WRITE_CALLS = frozenset({"to_csv", "to_parquet", "write_text", "write_bytes", "replace",
                         "rename", "mkdir", "unlink", "rmtree", "_write_parquet",
                         "_write_csv_atomic", "_write_bytes_atomic", "write_artifact",
                         "write_manifest", "_write"})
SWING_CACHE_NAMES = ("swing_pitches", "SWING_CACHE", "SWING_DIRS", "swing_dir", "sdir")


def _betting_side() -> list:
    files = sorted(ROOT.glob("betting*.py")) + sorted((ROOT / "tools").glob("betting*.py"))
    files.append(ROOT / "leaderboard_vintages.py")
    return [f for f in files if f.exists() and not f.name.startswith("test_")]


def _trend_side() -> list:
    out = [ROOT / f for f in TREND_FILES]
    js = ROOT / "assets" / "mlbstats-league-trends.js"
    if js.exists():
        out.append(js)
    return out


def _imports(tree) -> set:
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            out.add(mod)
            out |= {f"{mod}.{a.name}" if mod else a.name for a in n.names}
            out |= {a.name for a in n.names}
    return out


def _tree(p: Path):
    return ast.parse(p.read_text(encoding="utf-8"))


def test_the_trend_modules_exist():
    for f in TREND_FILES:
        assert (ROOT / f).exists(), f


def test_no_betting_module_reads_or_imports_league_trends():
    files = _betting_side()
    assert len(files) >= 10, "the betting census found too few modules"
    for f in files:
        src = f.read_text(encoding="utf-8")
        mods = {m.split(".")[-1] for m in _imports(ast.parse(src))}
        assert not mods & TREND_MODULES, (f.name, sorted(mods & TREND_MODULES))
        for s in TREND_STRINGS:
            assert s not in src, (f.name, s)


def test_no_trend_module_imports_a_betting_module():
    for f in TREND_FILES:
        mods = _imports(_tree(ROOT / f))
        bad = sorted(m for m in mods if re.match(r"(tools\.)?(betting|leaderboard_vintages|dfs|"
                                                 r"diamond|odds)", m))
        assert not bad, (f, bad)


def test_no_trend_module_names_a_banned_cache():
    for p in _trend_side():
        src = p.read_text(encoding="utf-8")
        for s in BANNED_PATHS:
            assert s not in src, (p.name, s)
        if p.suffix != ".py":
            continue
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                segs = set(re.split(r"[\\/]", n.value.strip()))
                assert not segs & BANNED_SEGMENTS, (p.name, n.value[:60])


def test_club_identity_never_comes_from_the_corpus_map_builder():
    for f in TREND_FILES:
        for n in ast.walk(_tree(ROOT / f)):
            name = (n.id if isinstance(n, ast.Name) else
                    n.attr if isinstance(n, ast.Attribute) else
                    n.name if isinstance(n, ast.alias) else None)
            assert name != "build_map", f
    src = (ROOT / "league_trends_export.py").read_text(encoding="utf-8")
    assert "import trend_frames as TF" in src and "TF.pitch_game_frame(" in src
    assert not {m for m in _imports(ast.parse(src)) if m.startswith("mgmt_teams")}


def test_no_banned_string():
    for p in _trend_side():
        src = p.read_text(encoding="utf-8")
        for s in BANNED_STRINGS:
            assert s not in src, (p.name, s)
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = rm.index("def _league_trends_nightly(")
    helper = rm[i:rm.index(chr(10) + "def ", i + 10)]
    for s in BANNED_STRINGS:
        assert s not in helper, s


def test_no_trend_module_writes_the_swing_cache_or_edits_mlbstats_games():
    for f in TREND_FILES:
        tree = _tree(ROOT / f)
        aliases = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                   for a in n.names if a.name == "mlbstats_games"}
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                fn = n.func.attr if isinstance(n.func, ast.Attribute) else \
                    n.func.id if isinstance(n.func, ast.Name) else None
                if fn in WRITE_CALLS or (fn == "open" and any(
                        isinstance(a, ast.Constant) and isinstance(a.value, str)
                        and re.search(r"[wa+]", a.value) for a in n.args[1:2])):
                    text = ast.unparse(n)
                    for s in SWING_CACHE_NAMES:
                        assert s not in text, (f, text[:80])
            if isinstance(n, (ast.Assign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for t in targets:
                    if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name):
                        assert t.value.id not in aliases, (f, ast.unparse(t))
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                assert "mlbstats_games.py" not in n.value, f


def test_the_writers_beside_a_protected_cache_refuse_it(tmp_path):
    import savant_days
    from tools import build_pitch_physics as B
    with pytest.raises(SystemExit):
        savant_days._guard_out(Path(savant_days.SWING_CACHE))
    with pytest.raises(SystemExit):
        savant_days._guard_out(Path(savant_days.SWING_CACHE) / "x")
    with pytest.raises(SystemExit):
        B._guard_out(B.CORPUS_DIR)
    savant_days._guard_out(tmp_path)
    B._guard_out(tmp_path)


def test_no_per_hand_key_in_the_payload():
    import league_trends_export as X
    p = X.out_dir() / X.OUT_NAME
    if not p.exists():
        pytest.skip(f"no League Trends payload on this machine ({p})")
    keys: set = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                keys.add(str(k))
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(json.loads(p.read_text(encoding="utf-8")))
    hand = re.compile(r"(^|_)(vs_?[lr]|lhp|rhp|lhh|rhh|hand|platoon|bat_side|pitch_hand)($|_)",
                      re.I)
    assert not sorted(k for k in keys if hand.search(k))
