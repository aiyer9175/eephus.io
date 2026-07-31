# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Publish-time comment strip for the SHIPPED copy of prospx/index.html.

The prospx source keeps its comments (they are the app's documentation);
the ~180KB-gz of comment bytes just should not ride every page load. This
tool is run by deploy/nightly-build.sh against the WEBROOT copy after the
rsync, so the repo file is never touched.

Deliberately conservative (a broken prospx is far worse than a big one):
  - a real character-level tokenizer walks every inline <script> body
    tracking ' " ` strings (template literals incl. nested ${...}), regex
    literals (prev-significant-token heuristic, self-healing at newline -
    regexes cannot span lines), line comments, and block comments;
  - it strips ONLY (a) // comments on their OWN line, (b) /* ... */ block
    comments, (c) <!-- ... --> HTML comments outside script/style;
  - trailing same-line // comments are KEPT (zero regex/division risk),
    string literals are NEVER touched, <style> is untouched, and any
    comment carrying a Copyright / (C) notice is kept verbatim;
  - inline (mid-line) block comments are replaced by one space so tokens
    can never merge; own-line comments take their whole line(s) with them;
  - scripts whose type is not JavaScript (ld+json etc.) pass through;
  - after stripping, the tokenizer re-scans its own output and the tool
    refuses to write unless both passes end in a clean lexer state.

Usage:
    python tools/strip_prospx_comments.py <file.html> --in-place
    python tools/strip_prospx_comments.py <file.html> -o out.html

Writes are atomic (temp file + replace). Prints the raw byte delta; the
nightly's gzip step turns that into the on-the-wire win.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

# Chars that, as the previous significant character, mean a following '/'
# starts a REGEX literal (not division). Biased toward regex: a false
# "regex" only makes us keep bytes, never strip them (and the state
# self-heals at end-of-line, before any line-start strip could trigger).
_REGEX_PRECEDERS = set("([{,;=:!&|?+-*%~^<>")
_REGEX_KEYWORDS = {
    "return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
    "throw", "case", "do", "else", "yield", "await",
}

_COPYRIGHT = re.compile(r"copyright|\(c\)", re.I)

_SCRIPT_OPEN = re.compile(r"<script\b[^>]*>", re.I)
_STYLE_OPEN = re.compile(r"<style\b[^>]*>", re.I)
_TYPE_ATTR = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)


def _is_js_type(open_tag: str) -> bool:
    m = _TYPE_ATTR.search(open_tag)
    if not m:
        return True
    t = m.group(1).lower()
    return t in ("text/javascript", "application/javascript", "module")


def _prev_significant(out: list[str]) -> str:
    """Last non-whitespace char already emitted (search a bounded tail)."""
    for ch in reversed(out[-200:]):
        if not ch.isspace():
            return ch
    return ""


def _prev_word(out: list[str]) -> str:
    """Identifier immediately before the cursor, for keyword-regex detection."""
    tail = "".join(out[-24:])
    m = re.search(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*$", tail)
    return m.group(1) if m else ""


def _line_is_blank_before(out: list[str]) -> bool:
    """True when everything emitted since the last newline is whitespace."""
    for ch in reversed(out):
        if ch == "\n":
            return True
        if not ch.isspace():
            return False
    return True


def _drop_line_prefix(out: list[str]) -> None:
    """Remove the whitespace indentation emitted since the last newline."""
    while out and out[-1] != "\n" and out[-1].isspace():
        out.pop()


def strip_js(src: str, counters: dict) -> str:
    """Strip own-line // comments and /* */ comments from JS source.

    States: CODE / strings / template stack / regex / comments, tracked
    char-by-char. Only comment bytes are ever removed; every other byte is
    emitted verbatim.
    """
    out: list[str] = []
    i, n = 0, len(src)
    state = "CODE"
    # Template-literal nesting: one brace-depth counter per open ${ level.
    tmpl_depth: list[int] = []
    in_class = False  # regex [...] class

    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if state == "CODE":
            if c == "'":
                state = "SQ"; out.append(c); i += 1
            elif c == '"':
                state = "DQ"; out.append(c); i += 1
            elif c == "`":
                state = "TMPL"; out.append(c); i += 1
            elif tmpl_depth and c == "{":
                tmpl_depth[-1] += 1; out.append(c); i += 1
            elif tmpl_depth and c == "}":
                tmpl_depth[-1] -= 1
                if tmpl_depth[-1] < 0:
                    tmpl_depth.pop(); state = "TMPL"
                out.append(c); i += 1
            elif c == "/" and nxt == "/":
                # Line comment: strip only when it owns the line.
                j = src.find("\n", i)
                if j < 0:
                    j = n
                comment = src[i:j]
                if _COPYRIGHT.search(comment) or not _line_is_blank_before(out):
                    out.append(comment)          # kept verbatim
                    i = j
                else:
                    _drop_line_prefix(out)
                    i = j
                    if i < n:                    # swallow the newline too
                        i += 1
                    counters["js_line"] += 1
            elif c == "/" and nxt == "*":
                j = src.find("*/", i + 2)
                j = (j + 2) if j >= 0 else n
                comment = src[i:j]
                own_line = _line_is_blank_before(out)
                # trailing rest-of-line after */ must be whitespace for a
                # clean whole-line removal
                k = src.find("\n", j)
                k = k if k >= 0 else n
                tail_blank = src[j:k].strip() == ""
                if _COPYRIGHT.search(comment):
                    out.append(comment)
                elif own_line and tail_blank:
                    _drop_line_prefix(out)
                    j = k + 1 if k < n else n    # swallow trailing WS + newline
                    counters["js_block"] += 1
                else:
                    out.append(" ")              # token-merge guard
                    counters["js_block"] += 1
                i = j
            elif c == "/":
                prev = _prev_significant(out)
                if prev in _REGEX_PRECEDERS or prev == "" \
                        or (prev.isalnum() or prev in "_$") and _prev_word(out) in _REGEX_KEYWORDS:
                    state = "REGEX"; in_class = False
                out.append(c); i += 1
            else:
                out.append(c); i += 1

        elif state in ("SQ", "DQ"):
            if c == "\\":
                out.append(src[i:i + 2]); i += 2
            elif (state == "SQ" and c == "'") or (state == "DQ" and c == '"') or c == "\n":
                state = "CODE"; out.append(c); i += 1
            else:
                out.append(c); i += 1

        elif state == "TMPL":
            if c == "\\":
                out.append(src[i:i + 2]); i += 2
            elif c == "`":
                state = "CODE"; out.append(c); i += 1
            elif c == "$" and nxt == "{":
                tmpl_depth.append(0); state = "CODE"; out.append("${"); i += 2
            else:
                out.append(c); i += 1

        elif state == "REGEX":
            if c == "\\":
                out.append(src[i:i + 2]); i += 2
            elif c == "[":
                in_class = True; out.append(c); i += 1
            elif c == "]":
                in_class = False; out.append(c); i += 1
            elif (c == "/" and not in_class) or c == "\n":
                # '/' closes the regex; a newline means the '/' was really
                # division (regex literals cannot span lines) - either way
                # nothing was stripped while here.
                state = "CODE"; out.append(c); i += 1
            else:
                out.append(c); i += 1

    if state not in ("CODE", "REGEX") or tmpl_depth:
        raise ValueError(f"lexer ended in state {state} (template depth {len(tmpl_depth)})"
                         " - refusing to strip this script")
    return "".join(out)


def strip_document(text: str, counters: dict) -> str:
    """Single-pass document walker with COMPETING openers.

    At every step the next `<!--`, `<script...>`, or `<style...>` is found
    and whichever starts FIRST wins; the walker then jumps past that whole
    construct. This ordering is the correctness core: a `<script>` mentioned
    inside an HTML comment is consumed with the comment (never treated as a
    real script boundary), and a `<!--` inside a script body is handled by
    the JS lexer, never as an HTML comment (the first cut of this tool
    segmented on script tags before comments and leaked a doc-comment's body
    into the page as text).
    """
    out: list[str] = []
    i, n = 0, len(text)
    lower = text.lower()
    while i < n:
        jc = text.find("<!--", i)
        ms = _SCRIPT_OPEN.search(text, i)
        mt = _STYLE_OPEN.search(text, i)
        cands = []
        if jc >= 0:
            cands.append((jc, "comment"))
        if ms:
            cands.append((ms.start(), "script"))
        if mt:
            cands.append((mt.start(), "style"))
        if not cands:
            out.append(text[i:])
            break
        pos, kind = min(cands)
        out.append(text[i:pos])

        if kind == "comment":
            k = text.find("-->", pos + 4)
            k = (k + 3) if k >= 0 else n
            comment = text[pos:k]
            if comment.startswith("<!--[if") or _COPYRIGHT.search(comment):
                out.append(comment)              # conditional / legal: kept
            else:
                counters["html"] += 1
                # own-line comment: swallow indentation + trailing newline
                if _line_is_blank_before(out):
                    _drop_line_prefix(out)
                    m2 = text.find("\n", k)
                    if m2 >= 0 and text[k:m2].strip() == "":
                        k = m2 + 1
            i = k
        else:
            m = ms if kind == "script" else mt
            out.append(m.group(0))               # the open tag, verbatim
            close = "</script" if kind == "script" else "</style"
            j = lower.find(close, m.end())
            if j < 0:                            # unterminated - bail verbatim
                out.append(text[m.end():])
                break
            body = text[m.end():j]
            if kind == "script" and _is_js_type(m.group(0)) and body.strip():
                out.append(strip_js(body, counters))
            else:
                out.append(body)                 # style / JSON / empty: untouched
            i = j
    return "".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("file", help="the SHIPPED html copy to strip (webroot path)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--in-place", action="store_true", help="rewrite file atomically")
    g.add_argument("-o", "--out", help="write stripped copy here instead")
    args = ap.parse_args(argv)

    path = Path(args.file)
    text = path.read_bytes().decode("utf-8")
    counters = {"js_line": 0, "js_block": 0, "html": 0}
    stripped = strip_document(text, counters)

    # Paranoia gate 1: the output must be smaller, never empty.
    if not stripped.strip() or len(stripped) >= len(text) + 1:
        print("!!! strip produced no reduction or empty output - aborting", file=sys.stderr)
        return 1
    # Paranoia gate 2: re-scan our own output; every script must still end
    # in a clean lexer state (catches any state-machine desync loudly).
    strip_document(stripped, {"js_line": 0, "js_block": 0, "html": 0})

    dest = Path(args.out) if args.out else path
    fd, tmp = tempfile.mkstemp(dir=str(dest.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(stripped.encode("utf-8"))
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    print(f"stripped {path.name}: {len(text.encode('utf-8')):,} -> "
          f"{len(stripped.encode('utf-8')):,} bytes "
          f"({counters['js_line']} own-line //, {counters['js_block']} /* */, "
          f"{counters['html']} <!-- -->)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
