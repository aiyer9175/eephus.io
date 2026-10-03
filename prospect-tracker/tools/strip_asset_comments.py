# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Publish-time comment strip for the SHIPPED copies of the site's CSS and JS.

The sibling of tools/strip_prospx_comments.py (bloat finding AS14,
2026-10-02: about a quarter of the shipped asset bytes were comments, site.css
alone 40 percent). deploy/nightly-build.sh runs it against the WEBROOT after
the rsync and before the precompress, so the .gz twin is built from the
stripped copy and the repo sources keep every comment (tests and docs read
them). The ?v= stamps hash the SOURCE file, so they do not move.

Targets, relative to the root given on the command line (TARGETS below):
assets/*.css, assets/*.js, collegesavant/app.js, collegesavant/pitcher_app.js.

Per file, fail-open (a failure keeps that file as shipped, never blocks the
nightly, never touches any other file):
  JS   strip with strip_prospx_comments.strip_js (the same tokenizer the PROSPX
       strip has run since 2026-07-23: strings, template literals with nested
       ${...}, regex literals and // inside URLs in strings are never touched;
       only own-line // comments and /* */ comments go; Copyright and /*!
       notices stay), re-scan the output for a clean lexer state, then compile
       the output with a JavaScript engine (node --check: node on PATH, the
       EEPHUS_NODE override, or VS Code's Electron in node mode; else V8
       through py_mini_racer). No engine available keeps every JS file whole.
  CSS  strip /* */ comments with a tokenizer that walks strings and unquoted
       url(...) bodies, then validate with an independent regex scan: braces
       balance and the rule count (opening braces outside strings and
       comments) is the same before and after.
Every write is atomic (temp file + replace).

Usage:
    python tools/strip_asset_comments.py <webroot> --in-place
    python tools/strip_asset_comments.py <root> --out-dir <dir>
    python tools/strip_asset_comments.py <root> --check        (dry run)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from strip_prospx_comments import strip_js  # noqa: E402

TARGETS = (
    "assets/*.css",
    "assets/*.js",
    "collegesavant/app.js",
    "collegesavant/pitcher_app.js",
)

_KEEP_COMMENT = re.compile(r"^/\*!|copyright|\(c\)", re.I)


def target_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for pat in TARGETS:
        out.extend(sorted(p for p in root.glob(pat) if p.is_file()))
    return out


# --------------------------------------------------------------------------- #
# CSS
# --------------------------------------------------------------------------- #
def _css_line_blank_before(out: list[str]) -> bool:
    for ch in reversed(out):
        if ch == "\n":
            return True
        if not ch.isspace():
            return False
    return True


def _css_drop_line_prefix(out: list[str]) -> None:
    while out and out[-1] != "\n" and out[-1].isspace():
        out.pop()


def _css_prev_char(out: list[str]) -> str:
    return out[-1] if out else ""


def strip_css(src: str, counters: dict) -> str:
    """Strip /* */ comments from a stylesheet. Strings and unquoted url()
    bodies pass through verbatim. An own-line comment takes its line with it;
    a mid-line comment is dropped where a neighbour is whitespace or one of
    { } ; , and otherwise shrinks to an empty /**/ so two tokens can never
    merge (a CSS comment separates tokens without being whitespace)."""
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'":
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == c or src[j] == "\n":
                    j += 1
                    break
                j += 1
            out.append(src[i:j])
            i = j
        elif c in "uU" and src[i:i + 4].lower() == "url(" and \
                not (i > 0 and (src[i - 1].isalnum() or src[i - 1] in "-_\\")):
            k = i + 4
            while k < n and src[k] in " \t\r\n":
                k += 1
            if k < n and src[k] in "\"'":
                out.append(src[i:k])        # quoted: the string branch takes it
                i = k
            else:
                j = src.find(")", k)
                j = (j + 1) if j >= 0 else n
                out.append(src[i:j])        # unquoted url body, verbatim
                i = j
        elif c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            if j < 0:
                raise ValueError("unterminated /* comment")
            j += 2
            comment = src[i:j]
            if _KEEP_COMMENT.search(comment):
                out.append(comment)
                i = j
                continue
            counters["css_block"] = counters.get("css_block", 0) + 1
            k = src.find("\n", j)
            k = k if k >= 0 else n
            if _css_line_blank_before(out) and src[j:k].strip() == "":
                _css_drop_line_prefix(out)
                i = k + 1 if k < n else n
                continue
            prev = _css_prev_char(out)
            nxt = src[j] if j < n else ""
            safe = "{};,"
            if (not prev or prev.isspace() or not nxt or nxt.isspace()
                    or prev in safe or nxt in safe):
                pass
            else:
                out.append("/**/")
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)


_CSS_SCAN = re.compile(
    r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|/\*[\s\S]*?\*/|[{}]')


def css_shape(text: str) -> tuple[int, bool]:
    """(rule count, braces balanced) from an independent regex scan: strings
    and comments are skipped, every other { opens a rule or block."""
    depth, rules, ok = 0, 0, True
    for m in _CSS_SCAN.finditer(text):
        tok = m.group(0)
        if tok == "{":
            depth += 1
            rules += 1
        elif tok == "}":
            depth -= 1
            if depth < 0:
                ok = False
    return rules, ok and depth == 0


def validate_css(original: str, stripped: str) -> str | None:
    r0, ok0 = css_shape(original)
    r1, ok1 = css_shape(stripped)
    if not ok1:
        return "braces unbalanced after the strip"
    if r0 != r1:
        return f"rule count {r0} before, {r1} after"
    return None


# --------------------------------------------------------------------------- #
# JS syntax check
# --------------------------------------------------------------------------- #
def _node_command() -> list[str] | None:
    override = os.environ.get("EEPHUS_NODE")
    if override and Path(override).exists():
        return [override]
    found = shutil.which("node")
    if found:
        return [found]
    local = os.environ.get("LOCALAPPDATA")
    if local:
        code = Path(local) / "Programs" / "Microsoft VS Code" / "Code.exe"
        if code.exists():
            return [str(code)]
    return None


def js_checker():
    """A callable text -> error message or None, and a label naming the
    engine; (None, 'none') when no JavaScript engine is available."""
    cmd = _node_command()
    if cmd:
        env = dict(os.environ, ELECTRON_RUN_AS_NODE="1")

        def check_node(text: str) -> str | None:
            fd, tmp = tempfile.mkstemp(suffix=".js")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(text.encode("utf-8"))
                r = subprocess.run(cmd + ["--check", tmp], capture_output=True,
                                   text=True, env=env, timeout=120)
                if r.returncode != 0:
                    return (r.stderr or r.stdout or "node --check failed").strip()[-400:]
                return None
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
        return check_node, "node --check"
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from py_mini_racer import MiniRacer
        ctx = MiniRacer()

        def check_v8(text: str) -> str | None:
            res = ctx.eval("(function(s){try{new Function(s);return ''}"
                           "catch(e){return String(e)}})(" + json.dumps(text) + ")")
            return res or None
        return check_v8, "py_mini_racer"
    except Exception:
        return None, "none"


# --------------------------------------------------------------------------- #
# Per file
# --------------------------------------------------------------------------- #
def strip_text(name: str, text: str, checker) -> tuple[str | None, str]:
    """(stripped text or None to keep the file whole, status note)."""
    counters = {"js_line": 0, "js_block": 0, "html": 0, "css_block": 0}
    try:
        if name.endswith(".css"):
            out = strip_css(text, counters)
            err = validate_css(text, out)
            if err:
                return None, f"kept: CSS check failed ({err})"
        else:
            out = strip_js(text, counters)
            strip_js(out, dict(counters))        # clean lexer state on a re-scan
            if checker is None:
                return None, "kept: no JavaScript engine to check the output"
            err = checker(out)
            if err:
                return None, f"kept: syntax check failed ({err.splitlines()[-1]})"
    except Exception as exc:                     # fail-open, per file
        return None, f"kept: {type(exc).__name__}: {exc}"
    if not out.strip():
        return None, "kept: empty output"
    if len(out) >= len(text):
        return None, "unchanged: no strippable comments"
    return out, "stripped"


def _atomic_write(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def run(root: Path, out_dir: Path | None = None, write: bool = True) -> list[dict]:
    checker, engine = js_checker()
    rows = []
    for path in target_files(root):
        rel = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            rows.append({"file": rel, "before": len(raw), "after": len(raw),
                         "status": "kept: not UTF-8"})
            continue
        out, status = strip_text(rel, text, checker)
        after = len(out.encode("utf-8")) if out is not None else len(raw)
        if out is not None and write:
            try:
                _atomic_write((out_dir / rel) if out_dir else path, out)
            except OSError as exc:
                status, after = f"kept: write failed ({exc})", len(raw)
        rows.append({"file": rel, "before": len(raw), "after": after, "status": status,
                     "engine": engine if rel.endswith(".js") else "css scan"})
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", help="the webroot (or any tree laid out like the app root)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--in-place", action="store_true", help="rewrite the files under root")
    g.add_argument("--out-dir", help="write stripped copies under this directory instead")
    g.add_argument("--check", action="store_true", help="dry run: report, write nothing")
    ap.add_argument("--json", action="store_true", help="print one JSON row per file")
    args = ap.parse_args(argv)

    root = Path(args.root)
    rows = run(root, Path(args.out_dir) if args.out_dir else None, write=not args.check)
    before = sum(r["before"] for r in rows)
    after = sum(r["after"] for r in rows)
    for r in rows:
        if args.json:
            print(json.dumps(r))
        elif not r["status"].startswith("stripped"):
            print(f"  {r['file']}: {r['status']}")
    kept = sum(1 for r in rows if r["status"].startswith("kept"))
    print(f"asset comment strip: {len(rows)} files, {before:,} -> {after:,} bytes "
          f"({before - after:,} saved), {kept} kept whole")
    return 0


if __name__ == "__main__":
    sys.exit(main())
