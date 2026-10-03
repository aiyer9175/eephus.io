# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Facts for the Masthead card backs (owner ask TEAM_2, 2026-10-02).

A card back line in data/team.json may carry {{key}} tokens. Each token is
read off the repository at build time: a count from git or the tree, a
verdict from the model registry, or an accuracy figure from the artifact
that measured it. Nothing that moves is typed into the roster file, so a
card back cannot drift from the record (the claims rule: every accuracy
claim derives from an artifact; test_team_card_backs.py holds the roster
file to it). A line whose token cannot be resolved (an artifact missing, a
shallow clone, git absent) is left off the card rather than printed with a
hole or a guess.

Typed facts that stay in the roster file are history that cannot move: a
ship date, or what one commit added on its day.
"""
from __future__ import annotations

import functools
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TEAM_JSON = DATA / "team.json"

TOKEN_RE = re.compile(r"\{\{([A-Za-z0-9_.@-]+)\}\}")
# The authorship header the owner and Will Cahoon put at the top of a file:
#   Copyright (C) 2026 <Name> (@<handle>) - All Rights Reserved
COPYRIGHT_RE = re.compile(r"Copyright \(C\) \d{4} [^(\n]+\((@[A-Za-z0-9_]+)\)")
MARKED_GLOBS = ("*.py", "*.js", "*.css")


class Missing(LookupError):
    """A token whose source is absent: the line it sits in is dropped."""


# ------------------------------------------------------------------ git

def _run(args: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(args, cwd=cwd, capture_output=True, timeout=60, check=True).stdout
    except Exception as exc:  # noqa: BLE001  (git absent, not a repo, timeout)
        raise Missing(" ".join(args[:3])) from exc
    return out.decode("utf-8", "replace")


@functools.lru_cache(maxsize=1)
def repo_root() -> Path | None:
    try:
        top = _run(["git", "rev-parse", "--show-toplevel"], ROOT).strip()
    except Missing:
        return None
    return Path(top) if top else None


@functools.lru_cache(maxsize=1)
def watermark_files() -> dict:
    """{'@handle': [repo paths]} for every tracked .py / .js / .css file in the
    whole repository (not only this module) whose first 300 bytes carry the
    authorship header. Empty when git is unavailable."""
    top = repo_root()
    if top is None:
        return {}
    try:
        out = _run(["git", "ls-files", "-z", "--", *MARKED_GLOBS], top)
    except Missing:
        return {}
    marks: dict = {}
    for rel in out.split("\0"):
        if not rel:
            continue
        try:
            with open(top / rel, "rb") as fh:
                head = fh.read(300).decode("utf-8", "replace")
        except OSError:
            continue
        m = COPYRIGHT_RE.search(head)
        if m:
            marks.setdefault(m.group(1), []).append(rel)
    return marks


def watermark_counts() -> dict:
    return {k: len(v) for k, v in watermark_files().items()}


@functools.lru_cache(maxsize=1)
def commit_log() -> tuple:
    """((author name, commit date), ...) for every non-merge commit reachable
    from HEAD. A shallow clone would undercount, so it reads as missing."""
    top = repo_root()
    if top is None:
        raise Missing("git")
    if _run(["git", "rev-parse", "--is-shallow-repository"], top).strip() != "false":
        raise Missing("shallow clone")
    rows = []
    for line in _run(["git", "log", "HEAD", "--no-merges", "--format=%an%x09%cs"], top).splitlines():
        name, _, day = line.partition("\t")
        if day:
            rows.append((name, day))
    return tuple(rows)


# ------------------------------------------------------------------ readers

@functools.lru_cache(maxsize=None)
def _json(name: str):
    p = DATA / name
    if not p.exists():
        raise Missing(name)
    return json.loads(p.read_text(encoding="utf-8"))


def _team() -> dict:
    return _json("team.json")


def _member(key: str) -> dict:
    for m in _team()["members"]:
        if m["key"] == key:
            return m
    raise Missing(key)


def _registry() -> list:
    return _json("model_registry.json")["models"]


def _n(x) -> str:
    return f"{int(x):,}"


def _get(d, *path):
    for k in path:
        if not isinstance(d, dict) or k not in d or d[k] is None:
            raise Missing(".".join(map(str, path)))
        d = d[k]
    return d


# ------------------------------------------------------------------ facts

def _member_commits(key: str) -> list:
    names = set(_member(key).get("git") or [])
    if not names:
        raise Missing(f"git names for {key}")
    days = sorted(day for name, day in commit_log() if name in names)
    if not days:
        raise Missing(f"no commits for {key}")
    return days


def _marks(key: str) -> list:
    mark = _member(key).get("watermark")
    files = watermark_files().get(mark or "")
    if not files:
        raise Missing(f"watermark for {key}")
    return files


def _marks_dirs(key: str) -> str:
    counts: dict = {}
    for rel in _marks(key):
        top = rel.split("/", 1)[0] if "/" in rel else "repository root"
        counts[top] = counts.get(top, 0) + 1
    order = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ", ".join(f"{d} {_n(c)}" for d, c in order)


def _registry_count(verdict: str | None) -> str:
    rows = _registry()
    return _n(len(rows) if verdict is None else sum(r.get("verdict") == verdict for r in rows))


def _verdict(model_id: str) -> str:
    for r in _registry():
        if r.get("model_id") == model_id:
            return str(r["verdict"])
    raise Missing(model_id)


def _plus(artifact: str, block: str, key: str, base: str, base_label: str, target: str) -> str:
    d = _json(artifact)
    rho = _get(d, block, key)
    ref = _get(d, block, base)
    pairs = _get(d, "n_forward_pairs")
    return (f"next-year {target} rho {rho:.3f} against {ref:.3f} for {base_label}, "
            f"{_n(pairs)} pairs")


def _bet_vintage() -> str:
    v = _get(_json("betting_model_eval.json"), "vintage")
    t = _get(v, "skill_vs_home_base", "t")
    return (f"on {_n(_get(v, 'n_graded'))} vintage-dated games from {_get(v, 'first_graded_date')} "
            f"to {_get(v, 'last_graded_date')}, Brier {_get(v, 'brier'):.4f} against "
            f"{_get(v, 'brier_home_base'):.4f} for the home-field constant (paired t {t:.2f})")


def _proj_gate1() -> str:
    w = _get(_json("fa_gate1_eval.json"), "pooled", "war")
    return (f"WAR MAE {_get(w, 'mae_model'):.3f} against {_get(w, 'mae_base'):.3f} for the 5/4/3 "
            f"carry-forward, {_n(_get(w, 'n'))} player-seasons")


def _fa_gate2() -> str:
    d = _json("fa_gate2_eval.json")
    g = _get(d, "pooled", "guarantee")
    return (f"guarantee MAE ${_get(g, 'mae_model'):.2f}M against ${_get(g, 'mae_base'):.2f}M for "
            f"comps, {_n(_get(g, 'n'))} contracts over {len(_get(d, 'test_winters'))} winters")


def _arb1() -> str:
    a = _get(_json("arbitration_eval.json"), "results", "arb1")
    return (f"MdAPE {_get(a, 'mdape_champion'):.3f} against {_get(a, 'mdape_bar'):.3f} for a "
            f"one-WAR bar, {_n(_get(a, 'n_paired'))} cases")


def _arb_swartz() -> str:
    s = _get(_json("arbitration_eval.json"), "a6_swartz")
    return (f"MdAPE {_get(s, 'swartz_mdape'):.3f} against {_get(s, 'ours_mdape'):.3f} for this "
            f"model on {_n(_get(s, 'n'))} identical settled cases")


def _defval() -> str:
    v = _get(_json("prospect_def_value_eval.json"), "validation_vs_fg")
    return (f"Spearman {_get(v, 'def_value_spearman'):.2f} against {_get(v, 'fg_tool_field_spearman'):.2f} "
            f"for the FanGraphs field grade at predicting realized MLB positional value, "
            f"n {_n(_get(v, 'n_graduated'))}")


def _ewar_span() -> str:
    s = _get(_json("ewar.json"), "seasons")
    if isinstance(s, list) and s:
        return f"{s[0]} to {s[-1]}"
    raise Missing("ewar seasons")


def _tests() -> tuple:
    files = sorted(ROOT.glob("test_*.py"))
    if not files:
        raise Missing("tests")
    fn = sum(len(re.findall(r"^\s*def test_", p.read_text(encoding="utf-8", errors="replace"), re.M))
             for p in files)
    return len(files), fn


def _icons() -> str:
    p = ROOT / "assets" / "eephus-icons.svg"
    if not p.exists():
        raise Missing("sprite")
    return _n(len(re.findall(r"<symbol ", p.read_text(encoding="utf-8"))))


def _gates() -> str:
    n = len({p for p in (ROOT / "docs").rglob("*.md") if "GATE" in p.name.upper()})
    if not n:
        raise Missing("gates")
    return _n(n)


def _ledger_clubs() -> str:
    n = len(list((DATA / "ledger_clubs").glob("*.json")))
    if not n:
        raise Missing("ledger_clubs")
    return _n(n)


def _efv_claim() -> str:
    text = _get(_json("xfv.json"), "meta", "served_model", "claim", "text")
    return str(text).strip()


_STATIC = {
    "registry.n": lambda: _registry_count(None),
    "registry.validated": lambda: _registry_count("validated"),
    "registry.provisional": lambda: _registry_count("provisional"),
    "registry.unvalidated": lambda: _registry_count("unvalidated"),
    "registry.deprecated": lambda: _registry_count("deprecated"),
    "registry.date": lambda: max(str(r.get("last_checked") or "") for r in _registry()),
    "gates.n": _gates,
    "tests.files": lambda: _n(_tests()[0]),
    "tests.functions": lambda: _n(_tests()[1]),
    "icons.n": _icons,
    "prospx.tracked": lambda: _n(_get(_json("timeseries.json"), "total_tracked")),
    "prospx.active": lambda: _n(_get(_json("timeseries.json"), "active_count")),
    "efv.claim": _efv_claim,
    "efv.ledger_rows": lambda: _n(len(_get(_json("efv_progress.json"), "rows"))),
    "ewar.n": lambda: _n(_get(_json("ewar.json"), "n_player_seasons")),
    "ewar.span": _ewar_span,
    "plus.hem": lambda: _plus("hem_plus_eval.json", "forward_spearman_vs_wOBA_next",
                              "hem_plus", "raw_woba", "raw wOBA", "wOBA"),
    "plus.sem": lambda: _plus("sem_plus_eval.json", "forward_spearman_vs_RA9_next",
                              "sem_plus", "raw_fip", "raw FIP", "RA9"),
    "plus.rem": lambda: _plus("rem_plus_eval.json", "forward_spearman_vs_RA9_next",
                              "rem_plus", "raw_fip", "raw FIP", "RA9"),
    "plus.dem": lambda: _plus("dem_plus_eval.json", "forward_spearman_vs_rate_next",
                              "dem_plus", "raw_rate", "the raw rate", "fielding rate"),
    "proj.gate1": _proj_gate1,
    "fa.gate2": _fa_gate2,
    "arb.arb1": _arb1,
    "arb.swartz": _arb_swartz,
    "bet.vintage": _bet_vintage,
    "defval.fg": _defval,
    "ledger.clubs": _ledger_clubs,
}

_PREFIXED = {
    "verdict.": _verdict,
    "git.commits.": lambda k: _n(len(_member_commits(k))),
    "git.first.": lambda k: _member_commits(k)[0],
    "git.last.": lambda k: _member_commits(k)[-1],
    "marks.dirs.": _marks_dirs,
    "marks.": lambda k: _n(len(_marks(k))),
}


def fact(key: str) -> str:
    """One token's value, or Missing."""
    if key in _STATIC:
        try:
            return str(_STATIC[key]())
        except Missing:
            raise
        except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
            raise Missing(key) from exc
    for prefix, fn in _PREFIXED.items():
        if key.startswith(prefix):
            try:
                return str(fn(key[len(prefix):]))
            except Missing:
                raise
            except (KeyError, TypeError, ValueError, IndexError, OSError) as exc:
                raise Missing(key) from exc
    raise Missing(f"unknown token {key}")


def fill(line: str) -> str | None:
    """The line with every token resolved, or None when any one cannot be."""
    try:
        return TOKEN_RE.sub(lambda m: fact(m.group(1)), line)
    except Missing:
        return None


def back_groups(member: dict) -> list:
    """[(head, [filled lines])] for one member's card back. A back item is a
    line (a string) or a group {"head", "lines"}; loose lines gather under
    'Record'. Lines that do not resolve are dropped, then empty groups."""
    groups: list = []
    loose: list = []

    def flush(head: str, lines) -> None:
        out = [f for f in (fill(ln) for ln in lines if isinstance(ln, str) and ln.strip()) if f]
        if out:
            groups.append((head, out))

    for item in member.get("back") or []:
        if isinstance(item, dict):
            flush("Record", loose)
            loose = []
            flush(str(item.get("head") or "Record"), item.get("lines") or [])
        else:
            loose.append(item)
    flush("Record", loose)
    return groups


def raw_lines(member: dict) -> list:
    """Every typed string on a member's back (group heads included), unfilled."""
    out = []
    for item in member.get("back") or []:
        if isinstance(item, dict):
            out.append(str(item.get("head") or ""))
            out.extend(x for x in item.get("lines") or [] if isinstance(x, str))
        elif isinstance(item, str):
            out.append(item)
    return out
