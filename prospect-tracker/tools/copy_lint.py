# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Copy voice linter (owner rule): flag em-dashes + LLM-ish phrasing in
user-facing copy. Companion to strip_emdashes.py, whose TARGETS list (the
canonical copy-surface set) this reuses.

Voice standard: terse, math-first, direct, human; no LLM cadence; no em-dashes.

Two severities so the gate stays meaningful without code false-positives:
  - em-dashes: hard fail anywhere (mirrors strip_emdashes --check).
  - LLM ban-list terms: hard fail in PURE-COPY files (glossary.json, README,
    content/*); advisory-only elsewhere (HTML/JS/PY also hold code, where words
    like "ensures"/"robust" are legitimate identifiers/comments).

Run: python tools/copy_lint.py [--check]
  --check: exit 1 on any hard finding (used by the copy-audit test).

Served mode (COPY_0, 2026-10-02; rules in docs/COPY_STYLE.md):
  python tools/copy_lint.py --served [--check] [--write-baseline] [--verbose]
  python tools/copy_lint.py --doc docs/COPY_STYLE.md
  --served lints sentences over what a reader sees (pages, inline and module
  scripts, the COPY_PRODUCERS by AST, glossary.json, the registry's reader
  fields) against rules L1 to L12 and the ratchet in tools/copy_baseline.json;
  tools/copy_registered.json lists exempt text. See the SERVED MODE block.
  Runtime on the worktree of 2026-10-02 (budget 20 s warm):
    --served --check cold (empty cache) 8.8 s, warm 3.4 to 4.0 s, measured
    2026-10-02 on the worktree while other lanes ran.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from strip_emdashes import EM, ROOT, _files, escaped_dash_count  # reuse the canonical surface list

# Whole-word / phrase patterns. Case-insensitive. Keep this list curated; the
# point is to catch LLM cadence, not to ban every long word.
# NOTE: the NOUN "leverage" is intentionally NOT banned - it's a core baseball
# term (Leverage Index; high-leverage role; the leverage of the moment). The
# owner's rule bans the marketing VERB, so only its verb forms are listed
# ("leverages", "leveraged", "leveraging"). "showcase" is banned in pure copy
# and advisory elsewhere, where "showcase circuit" is third-party scouting prose.
# Census X07-05 (2026-09-25) added the rest of the owner's list: essential,
# powerful, unlock, elevate, underscore, harness. "elevation" (a park's
# altitude) and "essentially" stay legal: the patterns are whole-word.
BAN = [
    r"\bseamless(ly)?\b", r"\brobust(ly|ness)?\b",
    r"\bdelve[ds]?\b", r"\bcomprehensive(ly)?\b", r"\bcrucial(ly)?\b",
    r"\butiliz\w*\b", r"\bmyriad\b", r"\bplethora\b", r"it'?s worth noting",
    r"in the realm of", r"a testament to", r"game-chang\w*", r"cutting-edge",
    r"\bdive into\b", r"(rich|vibrant) tapestry", r"\bmeticulous(ly)?\b",
    r"\bshowcases?\b",
    r"\bessential\b", r"\bpowerful(ly)?\b", r"\bunlock(s|ed|ing)?\b",
    r"\belevat(e|es|ed|ing)\b", r"\bunderscor(e|es|ed|ing)\b",
    r"\bharness(es|ed|ing)?\b", r"\bleverag(es|ed|ing)\b",
]
BAN_RE = re.compile("|".join(BAN), re.IGNORECASE)

# Perf (2026-07-17): the surfaces total ~95MB and running the 17-branch
# case-insensitive BAN_RE on every line took 30s+ per gate run. Every BAN
# alternative contains at least one of these literal lowercase needles, so
# a C-speed substring scan over a casefolded copy of the whole file finds
# every line that could possibly match; BAN_RE then runs on just those
# candidate lines (complete lines, so per-line match semantics and the
# report output are unchanged). Keep this tuple in sync with BAN: every
# alternative must contain at least one needle case-insensitively, or the
# prefilter could skip a real finding.
_NEEDLES = (
    "seamless", "robust", "delve", "comprehensive", "crucial", "utiliz",
    "myriad", "plethora", "worth noting", "in the realm of",
    "a testament to", "game-chang", "cutting-edge", "dive into",
    "tapestry", "meticulous", "showcase",
    "essential", "powerful", "unlock", "elevat", "underscor", "harness",
    "leverag",
)

# Files that are pure copy (no code), so a ban-list hit is real prose to fix.
# content/articles/* is owner editorial (long-form essays where normal English
# like "crucial" is the author's own voice), so it's ADVISORY, not hard-fail.
PURE_COPY = {
    "README.md", "data/glossary.json", "data/team.json",
    "assets/team/README.md",
}


def _is_pure(rel: str) -> bool:
    return rel in PURE_COPY


def _scan_lines(rel: str, text: str, em_hits: list[str], ban: list[str]) -> None:
    """The original exact per-line scan. Kept as the fallback for the rare
    file where casefolding changes the text length (a char like U+0130 with
    a multi-char casefold would shift the fast path's offsets)."""
    for i, line in enumerate(text.split("\n"), 1):
        if EM in line:
            em_hits.append(f"{rel}:{i}")
        for m in BAN_RE.finditer(line):
            ban.append(f"{rel}:{i}: {m.group(0)!r}")


def _scan(rel: str, text: str, em_hits: list[str], ban: list[str]) -> None:
    """Prefiltered scan. Output (records + order) is identical to
    _scan_lines: em-dash hits are one record per line in line order; BAN
    records run line-ascending then match-position-ascending, exactly like
    the old per-line finditer."""
    low = text.casefold()
    if len(low) != len(text):
        # Casefold moved offsets; take the exact per-line path instead.
        _scan_lines(rel, text, em_hits, ban)
        return
    has_em = EM in text
    cand: set[int] = set()
    for needle in _NEEDLES:
        j = low.find(needle)
        while j != -1:
            cand.add(j)
            j = low.find(needle, j + 1)
    if not has_em and not cand:
        return
    # Line-start offsets; a "\n"-split line number is bisect_right(starts, i).
    starts = [0]
    j = text.find("\n")
    while j != -1:
        starts.append(j + 1)
        j = text.find("\n", j + 1)
    n_lines = len(starts)
    if has_em:
        last_line = 0
        j = text.find(EM)
        while j != -1:
            ln = bisect_right(starts, j)
            if ln != last_line:  # one record per line, like `if EM in line`
                em_hits.append(f"{rel}:{ln}")
                last_line = ln
            j = text.find(EM, j + 1)
    if cand:
        # No BAN pattern (or needle) can span a newline, so running BAN_RE
        # over each complete candidate line reproduces per-line matching.
        for ln in sorted({bisect_right(starts, j) for j in cand}):
            lo = starts[ln - 1]
            hi = starts[ln] - 1 if ln < n_lines else len(text)
            for m in BAN_RE.finditer(text[lo:hi]):
                ban.append(f"{rel}:{ln}: {m.group(0)!r}")


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


# ---------------------------------------------------------------------------
# SERVED MODE (COPY_0, 2026-10-02): `--served [--check] [--write-baseline]`.
#
# The two gates above scan lines of the TARGETS files for dashes and the BAN
# words. Served mode lints SENTENCES over the set a reader sees, against the
# style guide in docs/COPY_STYLE.md (rules L1 to L12; L11, repetition, is a
# render test owned by COPY_3, not a static rule here):
#
#   1. pages: index.html, 404.html, */index.html, collegesavant/*.html, parsed
#      with bs4. Visible text (script, style, svg, template removed), the
#      title / aria-label / placeholder / alt / data-tip attributes, and the
#      share card (meta description, og:*, twitter:*). Data rows whose
#      template is linted where it is written (news feed items, On This Day
#      rows, homepage rail rows) are skipped: their instances change nightly.
#   2. scripts: inline <script> blocks (over 400 KB skipped as data blobs),
#      assets/*.js and collegesavant/*.js (over 400 KB skipped). String and
#      template literals pass through is_copy(), the prose filter ported from
#      the sitepass extractor; ${...} collapses to {x}.
#   3. Python producers (COPY_PRODUCERS) by AST: string constants and f-string
#      skeletons; docstrings, bare string statements and the arguments of
#      print / log / argparse / raise / assert are excluded.
#   4. data copy: data/glossary.json (definition, methodology, example,
#      caveat), data/model_registry.json (summary, predicts, baseline, metric
#      per row; `notes` is the lab log, class LAB_LOG, em-dash rule only).
#
# RATCHET (SP-D6): tools/copy_baseline.json records the findings of
# 2026-10-02 as sha1 of the normalised sentence per rule. `--served --check`
# fails on a finding not in the baseline and on a baseline entry that is no
# longer a finding, so the file only shrinks: a task that fixes a sentence
# removes its entry in the same commit (`--write-baseline` rewrites it; never
# run it to admit new copy). tools/copy_registered.json lists the exempt text
# (legal, credit, implied odds, registered claims, third party, lab log, FAQ,
# field names, owner quotes) with its class and pinning test.
#
# CACHE: extraction is keyed on each file's path, mtime and size plus the
# bytes of this script, under .cache/copy_lint/ (gitignored; the directory can
# be moved with the COPY_LINT_CACHE_DIR environment variable). Measured on
# 2026-10-02 over the worktree (prospx/index.html 3.4 MB is the heavy input):
# TIMING_COLD and TIMING_WARM below.

TIMING_COLD = "8.8 s (empty cache, 2026-10-02, worktree, other lanes running)"
TIMING_WARM = "3.4 to 4.0 s (cache hit on every file; budget 20 s)"

TOOLS = Path(__file__).resolve().parent
BASELINE_PATH = TOOLS / "copy_baseline.json"
REGISTERED_PATH = TOOLS / "copy_registered.json"


def _cache_dir() -> Path:
    env = os.environ.get("COPY_LINT_CACHE_DIR")
    return Path(env) if env else ROOT / ".cache" / "copy_lint"


# Producers that write reader copy outside the strip_emdashes TARGETS list
# when the served mode landed (each measured writing served copy on
# 2026-10-02; anchors in the sitepass LANE_COPY inventory). They are on
# TARGETS too, so the dash gate scans them.
EXTRA_PRODUCERS = (
    "data_catalog.py", "betting_shadow.py", "management.py",
    "win_expectancy.py", "pal_conversion.py", "build_glossary_data.py",
    "eta.py", "tools/arb_gate_a.py",
)


def copy_producers() -> list[str]:
    """COPY_PRODUCERS: the .py entries of strip_emdashes TARGETS plus the
    extra producers above, in that order, without repeats."""
    from strip_emdashes import TARGETS
    out = [t for t in TARGETS if t.endswith(".py")]
    for p in EXTRA_PRODUCERS:
        if p not in out:
            out.append(p)
    return out


COPY_PRODUCERS = copy_producers()

PAGE_GLOBS = ("index.html", "404.html", "*/index.html", "collegesavant/*.html")
JS_GLOBS = ("assets/*.js", "collegesavant/*.js")
JS_SKIP = ("assets/eephus-config.js", "assets/eephus-config.example.js",
           "assets/eephus-gl.js")
BLOB_BYTES = 400_000

# Data rows: the template is linted in the producer; each instance is data.
DATA_ROW_SELECTORS = (
    "a.feed-item", "a.otd-row", "a.xmod-row", "a.row-link", ".ticker-track",
    "span.signing", ".news-main", ".spot-body",
)

SURF_JS = {
    "projections": "projections", "mlbstats": "mlbstats", "fa": "fa",
    "fa_dpw": "fa", "trademachine": "trademachine", "ledger": "ledger",
    "franchise": "franchise", "management": "management",
    "arbitration": "arbitration", "hof": "hof", "betting": "betting",
    "diamond": "diamond", "diamond-config": "diamond",
    "eephus-diamond": "diamond", "fantasy": "fantasy",
    "fantasy-hub": "fantasy", "fantasy-card": "fantasy",
    "dynasty": "dynasty", "redraft": "redraft", "dfs": "dfs", "pal": "pal",
    "glossary": "glossary", "parks": "parks", "accountability": "models",
    "eephus-hub": "home",
}
PY_SURF = {
    "build_site.py": "build_site", "spotlights.py": "home",
    "ledger_export.py": "ledger", "franchise_export.py": "franchise",
    "fa_export.py": "fa", "mgmt_export.py": "management",
    "management.py": "management", "win_expectancy.py": "management",
    "hof_export.py": "hof", "arb_export.py": "arbitration",
    "tools/arb_gate_a.py": "arbitration", "betting_export.py": "betting",
    "betting_shadow.py": "betting", "war_board_export.py": "projections",
    "bullpen_export.py": "mlbstats", "pal_export.py": "pal",
    "pal_conversion.py": "pal", "source_backtest.py": "glossary",
    "build_glossary_data.py": "glossary", "proj_export.py": "projections",
    "draft_export.py": "prospx", "ifa_export.py": "prospx",
    "overseas_export.py": "prospx", "eta.py": "prospx",
    "data_catalog.py": "sources", "scores_core.py": "scores",
}

# ---- the prose filter (ported from SP/sitepass/copy_extract.py) ----------

STOP = set(
    "the a an of is are to in on for and with from no not this it its at by as "
    "or be was that than when each one per we our you your his her their has "
    "have had can will".split())
WORD = re.compile(r"[A-Za-z][A-Za-z'+%]*")
WORDS = re.compile(r"[A-Za-z][A-Za-z'+%-]*")
SQL = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|WITH|PRAGMA|ALTER|DROP)\b"
                 r"|\b(FROM|WHERE|JOIN|GROUP BY|ORDER BY)\b")


def is_copy(s: str) -> bool:
    """True when a string reads as prose: 4+ tokens, 55% or more word tokens,
    at least one function word, not a CSS rule, path or hyphenated class
    list, not SQL."""
    s = s.strip()
    if len(s) < 18 or ("{" in s and "}" in s and ":" in s and ";" in s):
        return False
    if (re.search(r"(^|\s)(\.|#)[a-z][\w-]*\s*[{,]", s)
            or s.startswith(("http", "/", "./", "data:"))):
        return False
    if SQL.search(s):
        return False
    toks = s.split()
    if len(toks) < 4:
        return False
    words = [t for t in toks if WORD.fullmatch(t.strip(".,;:()!?\"'"))]
    if len(words) < 4 or len(words) / len(toks) < 0.55:
        return False
    if not any(t.lower().strip(".,;:") in STOP for t in toks):
        return False
    hy = sum(1 for t in toks if re.fullmatch(r"[a-z]+(-[a-z0-9]+)+", t))
    if hy / len(toks) > 0.4:  # class lists
        return False
    return True


TAG = re.compile(r"<[^>]+>")
CODE_EL = re.compile(r"<code\b[^>]*>(.*?)</code>", re.S | re.I)
INTERP = re.compile(r"\$\{[^}]*\}")
ENT = (("&nbsp;", " "), ("&#160;", " "), ("&amp;", "&"), ("&lt;", "<"),
       ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&rarr;", "\u2192"),
       ("&hellip;", "..."), ("&middot;", "\u00b7"), ("&rsquo;", "'"),
       ("&lsquo;", "'"), ("&ldquo;", '"'), ("&rdquo;", '"'))
BS = chr(92)


# A block tag inside a string (a table cell, a list item, a heading) ends a
# sentence even without a full stop, so cells never run together.
BLOCK_TAG = re.compile(
    r"</?(p|li|td|th|tr|h[1-6]|div|dt|dd|summary|caption|figcaption|table|"
    r"ul|ol|dl|section|details|header|footer|blockquote|option)\b[^>]*>|<br\s*/?>",
    re.I)
PARA = "\u2029"


def clean(s: str) -> str:
    """Markup to plain sentence text: ${...} to {x}, <code> to a backtick
    span, block tags to a paragraph break, other tags dropped, the common
    entities decoded, escapes unwound."""
    s = INTERP.sub("{x}", s)
    s = CODE_EL.sub(lambda m: "`" + TAG.sub("", m.group(1)) + "`", s)
    s = BLOCK_TAG.sub(" " + PARA + " ", s)
    s = TAG.sub(" ", s)
    for a, b in ENT:
        s = s.replace(a, b)
    s = s.replace(BS + "n", " ").replace(BS + "t", " ")
    s = re.sub(re.escape(BS) + r"(['\"`])", r"\1", s)
    s = re.sub(r"[ \t\r\n\f\v]+", " ", s)
    return re.sub(r"\s*" + PARA + r"[\s" + PARA + r"]*", PARA, s).strip(" " + PARA)


def flat(s: str) -> str:
    """One line of text (attributes, share cards): paragraph breaks to spaces."""
    return s.replace(PARA, " ").strip()


SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\u2018\u201c])")


def sentences(s: str):
    """Split on block breaks, then on . ! ? followed by space and a capital,
    digit, quote or parenthesis; keep the pieces that read as prose."""
    for para in s.split(PARA):
        for x in SPLIT.split(para):
            x = x.strip()
            if is_copy(x) or (len(x.split()) >= 3 and x.endswith((".", "!", "?"))
                              and is_copy(x + " the x")):
                yield x


# ---- extraction ----------------------------------------------------------

ATTRS = ("title", "aria-label", "placeholder", "alt", "data-tip",
         "data-tooltip", "data-help")
SHARE = ("description", "og:description", "twitter:description", "og:title",
         "twitter:title")
ATTR_IN_STR = re.compile(
    r"\b(title|aria-label|data-tip|data-tooltip|placeholder|alt)\s*=\s*"
    r"(?:\\?\")([^\"\\]{20,})(?:\\?\")")
BLOCK = {"p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "dd",
         "dt", "figcaption", "summary", "caption", "label", "button", "div",
         "section", "article", "header", "footer", "nav", "main", "aside",
         "blockquote", "tr", "ul", "ol", "dl", "table", "details", "form",
         "option", "select", "body", "html", "legend", "fieldset", "pre"}


def _rec(out: list, surface: str, file: str, anchor: str, kind: str, text: str,
         faq: bool = False) -> None:
    for s in sentences(clean(text)):
        r = {"surface": surface, "file": file, "anchor": anchor, "kind": kind,
             "text": s}
        if faq:
            r["faq"] = True
        out.append(r)


def js_literals(src: str):
    """(offset, body) for every string and template literal in JS source.
    Comments and regex literals are skipped; ${...} inside a template
    collapses to {x} and the literals inside the expression are yielded on
    their own."""
    n = len(src)
    out: list = []
    REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
    KW = {"return", "typeof", "case", "in", "of", "delete", "void", "throw",
          "new", "else", "do", "yield", "await"}

    def scan(i: int, stop_brace: bool) -> int:
        prev, prev_word, depth = "", "", 0
        while i < n:
            c = src[i]
            if c in " \t\r\n":
                i += 1
                continue
            if c == "/" and i + 1 < n:
                d = src[i + 1]
                if d == "/":
                    j = src.find("\n", i)
                    i = n if j < 0 else j
                    continue
                if d == "*":
                    j = src.find("*/", i + 2)
                    i = n if j < 0 else j + 2
                    continue
                if prev == "" or prev in REGEX_PREV or prev_word in KW:
                    j, cls = i + 1, False
                    while j < n:
                        ch = src[j]
                        if ch == BS:
                            j += 2
                            continue
                        if ch == "[":
                            cls = True
                        elif ch == "]":
                            cls = False
                        elif ch == "/" and not cls:
                            break
                        elif ch == "\n":
                            break
                        j += 1
                    i, prev, prev_word = j + 1, "a", ""
                    continue
            if c in "\"'":
                j, buf = i + 1, []
                while j < n and src[j] != c and src[j] != "\n":
                    if src[j] == BS:
                        buf.append(src[j:j + 2])
                        j += 2
                        continue
                    buf.append(src[j])
                    j += 1
                out.append((i, "".join(buf)))
                i, prev, prev_word = j + 1, "a", ""
                continue
            if c == "`":
                j, buf = i + 1, []
                while j < n and src[j] != "`":
                    if src[j] == BS:
                        buf.append(src[j:j + 2])
                        j += 2
                        continue
                    if src[j] == "$" and j + 1 < n and src[j + 1] == "{":
                        buf.append("{x}")
                        j = scan(j + 2, True)
                        continue
                    buf.append(src[j])
                    j += 1
                out.append((i, "".join(buf)))
                i, prev, prev_word = j + 1, "a", ""
                continue
            if c.isalnum() or c in "_$":
                j = i
                while j < n and (src[j].isalnum() or src[j] in "_$"):
                    j += 1
                prev, prev_word = "a", src[i:j]
                i = j
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                if stop_brace and depth == 0:
                    return i + 1
                depth -= 1
            prev, prev_word = c, ""
            i += 1
        return n

    scan(0, False)
    return out


def _js_records(out: list, surface: str, rel: str, src: str, base_line: int = 0) -> None:
    starts = [0]
    j = src.find("\n")
    while j != -1:
        starts.append(j + 1)
        j = src.find("\n", j + 1)
    for off, body in js_literals(src):
        if len(body) < 18:
            continue
        line = bisect_right(starts, off) + base_line
        for m in ATTR_IN_STR.finditer(body):
            v = flat(clean(m.group(2)))
            if len(WORDS.findall(v)) > 12:
                out.append({"surface": surface, "file": rel, "anchor": f"L{line}",
                            "kind": "attr", "text": v})
        _rec(out, surface, rel, f"L{line}", "js", body)


def _is_blob(src: str, sample: bool = False) -> bool:
    """A data blob: over 400 KB (or a 400 KB sample of a bigger file) and
    nearly free of code. PROSPX's 2.8 MB inline app script is code
    (thousands of functions), so it is read."""
    return ((sample or len(src) > BLOB_BYTES)
            and (src.count("function") + src.count("=>")) * 50_000 < len(src))


def _head(p: Path) -> str:
    with p.open("rb") as fh:
        return fh.read(BLOB_BYTES).decode("utf-8", errors="replace")


def _page_surface(rel: str) -> str:
    if rel == "index.html":
        return "home"
    if rel == "404.html":
        return "404"
    return rel.split("/")[0]


def extract_page(rel: str, raw: str) -> list:
    from bs4 import BeautifulSoup, Comment
    out: list = []
    surf = _page_surface(rel)
    soup = BeautifulSoup(raw, "html.parser")
    for m in soup.find_all("meta"):
        name = m.get("name") or m.get("property") or ""
        if name in SHARE and (m.get("content") or "").strip():
            c = flat(clean(m.get("content")))
            out.append({"surface": surf, "file": rel, "anchor": f"meta[{name}]",
                        "kind": "share", "text": c})
            _rec(out, surf, rel, f"meta[{name}]", "meta", c)
    for sc in soup.find_all("script"):
        typ = (sc.get("type") or "").lower()
        txt = sc.string or ""
        if not sc.get("src") and "json" not in typ and not _is_blob(txt):
            _js_records(out, surf, rel, txt, (sc.sourceline or 1) - 1)
        sc.decompose()
    for st in soup.find_all(["style", "svg", "template", "noscript"]):
        st.decompose()
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
    for sel in DATA_ROW_SELECTORS:
        for el in soup.select(sel):
            el.decompose()
    for el in soup.find_all(True):
        for a in ATTRS:
            v = el.get(a)
            if v and isinstance(v, str):
                v = clean(v)
                if len(WORDS.findall(v)) > 12:
                    out.append({"surface": surf, "file": rel,
                                "anchor": f"{el.name}[{a}]", "kind": "attr",
                                "text": flat(v)})
                _rec(out, surf, rel, f"{el.name}[{a}]", "tip", v)
    # Visible text grouped by its nearest block ancestor, in document order.
    groups: dict = {}
    order: list = []
    for t in soup.find_all(string=True):
        if not t.strip():
            continue
        par = t.parent
        code = par is not None and par.name == "code"
        blk = par
        while blk is not None and blk.name not in BLOCK:
            blk = blk.parent
        if blk is None:
            continue
        k = id(blk)
        if k not in groups:
            groups[k] = (blk, [])
            order.append(k)
        groups[k][1].append("`" + str(t) + "`" if code else str(t))
    for k in order:
        blk, parts = groups[k]
        cls = " ".join(blk.get("class") or [])
        faq = "faq" in cls or any("faq" in " ".join(p.get("class") or [])
                                  for p in blk.parents if hasattr(p, "get"))
        anchor = blk.name + (f"#{blk['id']}" if blk.get("id") else "") + (
            "." + ".".join((blk.get("class") or [])[:2]) if blk.get("class") else "")
        text = " ".join(parts)
        for s in sentences(re.sub(r"\s+", " ", text).strip()):
            r = {"surface": surf, "file": rel, "anchor": anchor, "kind": "html",
                 "text": s}
            if faq:
                r["faq"] = True
            out.append(r)
    return out


def extract_js(rel: str, src: str) -> list:
    out: list = []
    stem = Path(rel).stem
    surf = "collegesavant" if rel.startswith("collegesavant/") else SURF_JS.get(stem, "shared")
    _js_records(out, surf, rel, src)
    return out


_SKIP_CALLS = {"print", "info", "warning", "warn", "error", "debug", "exception",
               "log", "critical", "add_argument", "ArgumentParser",
               "add_parser", "add_mutually_exclusive_group", "add_argument_group",
               "compile", "sub", "match", "search", "fullmatch", "findall",
               "finditer", "split", "execute", "executemany", "read_sql",
               "read_sql_query", "strftime", "strptime"}


def extract_py(rel: str, src: str) -> list:
    out: list = []
    surf = PY_SURF.get(rel, Path(rel).stem)
    tree = ast.parse(src)
    skip: set = set()

    def mark(node):
        for sub in ast.walk(node):
            skip.add(id(sub))

    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(
                    getattr(b[0], "value", None), ast.Constant):
                mark(b[0])
        elif isinstance(node, ast.Expr) and isinstance(node.value, (ast.Constant, ast.JoinedStr)):
            mark(node)
        elif isinstance(node, (ast.Raise, ast.Assert)):
            mark(node)
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else (
                fn.id if isinstance(fn, ast.Name) else "")
            if name in _SKIP_CALLS:
                mark(node)
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    parts.append(v.value)
                else:
                    parts.append("{x}")
                    mark(v)  # nested format specs are not copy
            for v in node.values:
                skip.add(id(v))
            node._copy_text = "".join(parts)  # type: ignore[attr-defined]
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if isinstance(node, ast.JoinedStr):
            _rec(out, surf, rel, f"L{node.lineno}", "py", node._copy_text)  # type: ignore[attr-defined]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if len(v) >= 18:
                for m in ATTR_IN_STR.finditer(v):
                    a = flat(clean(m.group(2)))
                    if len(WORDS.findall(a)) > 12:
                        out.append({"surface": surf, "file": rel,
                                    "anchor": f"L{node.lineno}", "kind": "attr",
                                    "text": a})
                _rec(out, surf, rel, f"L{node.lineno}", "py", v)
    return out


GLOSSARY_FIELDS = ("definition", "methodology", "example", "caveat")
REGISTRY_FIELDS = ("summary", "predicts", "baseline", "metric")


def extract_glossary(rel: str, src: str) -> list:
    out: list = []
    for e in json.loads(src).get("entries") or []:
        for k in GLOSSARY_FIELDS:
            if isinstance(e.get(k), str) and e[k]:
                _rec(out, "glossary", rel, f"{e.get('id')}.{k}", "glossary", e[k])
    return out


def extract_registry(rel: str, src: str) -> list:
    out: list = []
    for m in json.loads(src).get("models") or []:
        for k in REGISTRY_FIELDS:
            if isinstance(m.get(k), str) and m[k]:
                _rec(out, "registry", rel, f"{m.get('model_id')}.{k}", "registry", m[k])
    return out


def _registry_notes_set() -> set:
    """Normalised sentences of every row's `notes` (the lab log), so the same
    text reached through a page is skipped like the field itself."""
    p = ROOT / "data" / "model_registry.json"
    out: set = set()
    try:
        reg = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for m in reg.get("models") or []:
        notes = m.get("notes")
        for n in (notes if isinstance(notes, list) else [notes]):
            if isinstance(n, str):
                for s in sentences(clean(n)):
                    out.add(normalise(s))
    return out


def served_inputs() -> list:
    """(rel, kind) for every served copy source, sorted."""
    seen: dict = {}
    for pat in PAGE_GLOBS:
        for p in ROOT.glob(pat):
            if p.is_file():
                seen[_rel(p)] = "page"
    for pat in JS_GLOBS:
        for p in ROOT.glob(pat):
            rel = _rel(p)
            if p.is_file() and rel not in JS_SKIP and (
                    p.stat().st_size <= BLOB_BYTES
                    or not _is_blob(_head(p), sample=True)):
                seen[rel] = "js"
    for rel in COPY_PRODUCERS:
        if (ROOT / rel).is_file():
            seen[rel] = "py"
    seen["data/glossary.json"] = "glossary"
    seen["data/model_registry.json"] = "registry"
    return sorted(seen.items())


_EXTRACT = {"page": extract_page, "js": extract_js, "py": extract_py,
            "glossary": extract_glossary, "registry": extract_registry}


def _self_hash() -> str:
    return hashlib.sha1(Path(__file__).read_bytes()).hexdigest()[:16]


def extract_served(use_cache: bool = True) -> list:
    """Every served sentence record, through the mtime-keyed cache."""
    cdir = _cache_dir()
    ver = _self_hash()
    recs: list = []
    for rel, kind in served_inputs():
        p = ROOT / rel
        if not p.exists():
            continue
        st = p.stat()
        key = hashlib.sha1(rel.encode("utf-8")).hexdigest()
        cf = cdir / f"{key}.json"
        if use_cache:
            try:
                c = json.loads(cf.read_text(encoding="utf-8"))
                if (c.get("mtime") == st.st_mtime_ns and c.get("size") == st.st_size
                        and c.get("ver") == ver):
                    recs.extend(c["records"])
                    continue
            except (OSError, ValueError, KeyError):
                pass
        src = p.read_text(encoding="utf-8", errors="replace")
        got = _EXTRACT[kind](rel, src)
        recs.extend(got)
        if use_cache:
            try:
                cdir.mkdir(parents=True, exist_ok=True)
                cf.write_text(json.dumps({"rel": rel, "mtime": st.st_mtime_ns,
                                          "size": st.st_size, "ver": ver,
                                          "records": got}, ensure_ascii=False),
                              encoding="utf-8")
            except OSError:
                pass
    return recs


# ---- rules ----------------------------------------------------------------

def normalise(s: str) -> str:
    """The baseline key text: NFKC, lower case, digit runs to 0, whitespace
    collapsed. Numbers move with the data; the sentence does not."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"\d+", "0", s)
    return re.sub(r"\s+", " ", s).strip()


def sha(s: str) -> str:
    return hashlib.sha1(normalise(s).encode("utf-8")).hexdigest()


L5_WORDS = (
    "amazing compelling dynamic effortless elegant exciting flagship genuine "
    "genuinely honest honestly huge impressive incredible innovative insightful "
    "intuitive meaningful meticulous perfect powerful remarkable robust seamless "
    "sophisticated stunning transparent unique valuable vibrant holistic nuanced "
    "pivotal vital crucial essential comprehensive actually truly really very "
    "extremely simply clearly obviously highly").split()
L5_RE = re.compile(r"\b(" + "|".join(L5_WORDS) + r")\b", re.I)

HALLMARK = [
    r"\bensur(e|es|ed|ing)\b", r"\bstreamlin\w*", r"\bempower\w*",
    r"\binsights?\b", r"\bactionable\b", r"\bat a glance\b", r"\bin one place\b",
    r"\bone-stop\b", r"\bgo-to\b", r"\bdeep[- ]dive\b", r"\bunparalleled\b",
    r"\bworld-class\b", r"\bbest-in-class\b", r"\bstate-of-the-art\b",
    r"\beffortless(ly)?\b", r"\bintuitive(ly)?\b", r"\bholistic(ally)?\b",
    r"\bnuanced\b", r"\bpivotal\b", r"\bparamount\b", r"\bvital\b",
    r"\bindispensable\b", r"\btruly\b", r"\bincredibly\b", r"\bextremely\b",
    r"\babsolutely\b", r"\bliterally\b", r"\bremarkably\b", r"\bgenuinely\b",
    r"\bundeniably\b", r"\bneedless to say\b", r"\bin short\b",
    r"\bin summary\b", r"\bat the end of the day\b", r"\bsimply put\b",
    r"\bwhen it comes to\b", r"\ba wide range of\b", r"\ba variety of\b",
    r"\ba wealth of\b", r"\bplays a key role\b", r"\bserves as\b",
    r"\bstands as\b", r"\bever-evolving\b", r"\bfast-paced\b",
    r"\brest assured\b", r"\bfeel free\b", r"\bimagine\b",
    r"\bthink of it as\b", r"\bjourney\b", r"\blandscape\b", r"\becosystem\b",
    r"\brealm\b", r"\bcrafted\b", r"\bbespoke\b", r"\bboasts\b",
    r"\bfoster\b", r"\bbolster\b", r"\bembark\b", r"\bcoming soon\b",
    r"\bstay tuned\b", r"\bcheck back\b", r"\bhonest(ly)?\b", r"\bdishonest\b",
    r"\bflagship\b", r"\bgame-changer\b", r"\bhere's the thing\b",
    r"\bthe upshot\b", r"!$",
]
# BAN minus showcase (advisory in served mode: the amateur showcase circuit).
L6_RE = re.compile("|".join(HALLMARK + [b for b in BAN if "showcase" not in b]),
                   re.I)
L6_ADVISORY_RE = re.compile(
    r"\bcurated\b|\bleverage\b(?! index)|\bshowcases?\b|\breal\b|\bactually\b", re.I)

L7_RE = re.compile(r"\b(NOT|ONLY|NEVER|EVERY|SAME|WHOLE|ACTUALLY)\b")
L8_RE = re.compile(
    r"\b\w+\.py\b|\btest_\w+|\b_[a-z]\w*\(|\bdocs/[\w./-]+"
    r"|\bowner decision \d{4}-\d{2}-\d{2}"
    r"|\b(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{8,}\b")
L10_ASIDE = re.compile(r"\s-\s")
L10_ARROW = re.compile("\u2192|\\s->\\s")
L12_RE = re.compile(r"\bnewly launched\b|\bcoming soon\b|(?<!as )\bsoon\b(?! as)|\bwhile we build\b"
                    r"|\bcheck back\b|\brenamed from\b|\bnow inside\b", re.I)

RULES = ("L1", "L2", "L3", "L5", "L6", "L7", "L8", "L9", "L10", "L12")
SURFACE_RULES = ("L4", "L5_density", "coverage")
L1_HARD, L1_ADVISORY = 60, 40
L2_MAX = L3_MAX = 25
L4_MAX = 20.0
L5_DENSITY_MAX = 0.10


def _mask_code(s: str) -> str:
    """Backtick spans are field names (FIELD_NAME): masked for L6 to L8."""
    return re.sub(r"`[^`]*`", "`x`", s)


def _mostly_caps(s: str) -> bool:
    letters = [c for c in s if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) >= 0.6


def rule_hits(rec: dict) -> tuple[list, list]:
    """(hard rule ids, advisory notes) for one sentence record."""
    t = rec["text"]
    kind = rec.get("kind")
    n = len(WORDS.findall(t))
    hard, soft = [], []
    if kind == "attr":
        if n > L2_MAX:
            hard.append("L2")
        return hard, soft
    if kind == "share":
        if n > L3_MAX:
            hard.append("L3")
        return hard, soft
    if n > L1_HARD:
        hard.append("L1")
    elif n > L1_ADVISORY:
        soft.append("L1>40")
    m = _mask_code(t)
    if L5_RE.search(m):
        hard.append("L5")
    if L6_RE.search(m.strip()):
        hard.append("L6")
    for a in L6_ADVISORY_RE.findall(m):
        soft.append(f"L6~{a.lower()}")
    if not _mostly_caps(m) and L7_RE.search(m):
        hard.append("L7")
    if L8_RE.search(m):
        hard.append("L8")
    if t.rstrip().endswith("?") and not rec.get("faq"):
        hard.append("L9")
    if len(L10_ASIDE.findall(t)) >= 2 or len(L10_ARROW.findall(t)) >= 2:
        hard.append("L10")
    if L12_RE.search(m):
        hard.append("L12")
    return hard, soft


# ---- registered exemptions -------------------------------------------------

REGISTERED_CLASSES = ("LEGAL", "CREDIT", "IMPLIED_ODDS", "REGISTERED_CLAIM",
                      "THIRD_PARTY", "LAB_LOG", "FAQ", "FIELD_NAME",
                      "OWNER_QUOTE")


def load_registered(path: Path = REGISTERED_PATH) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return list(data.get("entries") or [])


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class Exemptions:
    def __init__(self, entries: list):
        self.texts: list = []
        self.regexes: list = []
        self.masks: list = []
        self.lab_fields: set = set()
        for e in entries:
            cls = e.get("class")
            if cls == "LAB_LOG" and e.get("field"):
                self.lab_fields.add((e.get("source"), e.get("field")))
                continue
            if cls == "FIELD_NAME" and e.get("text"):
                self.masks.append(e["text"])
                continue
            if e.get("regex"):
                self.regexes.append(re.compile(e["regex"]))
            elif e.get("text"):
                self.texts.append(_ws(e["text"]))

    def mask(self, s: str) -> str:
        for m in self.masks:
            s = s.replace(m, "`x`")
        return s

    def exempt(self, s: str) -> bool:
        """A sentence is exempt when it contains a registered text, sits
        inside one (a registered paragraph split into sentences) or matches
        a registered regex."""
        w = _ws(s)
        return (any(t in w or w in t for t in self.texts)
                or any(r.search(w) for r in self.regexes))


# ---- the run ----------------------------------------------------------------

def lint_records(recs: list, ex: "Exemptions | None" = None,
                 min_sentences: int = 20, min_words: int = 500) -> dict:
    """Findings by rule: {rule: {sha1: example record}}, plus surface rules
    {L4: {surface: mean}, L5_density: {surface: per100}} and advisories."""
    ex = ex or Exemptions([])
    lab = _registry_notes_set()
    by_rule: dict = {r: {} for r in RULES}
    advis: dict = {}
    surf_words: dict = {}
    surf_sents: dict = {}
    surf_l5: dict = {}
    seen: set = set()
    for r in recs:
        if ex.exempt(r["text"]):
            continue
        norm = normalise(r["text"])
        if r.get("kind") in ("html", "attr") and norm in lab:
            continue
        rr = dict(r, text=ex.mask(r["text"]))
        hard, soft = rule_hits(rr)
        key = (r["surface"], norm, r.get("kind") in ("attr", "share"))
        if key not in seen and r.get("kind") not in ("attr", "share"):
            seen.add(key)
            nw = len(WORDS.findall(r["text"]))
            surf_words[r["surface"]] = surf_words.get(r["surface"], 0) + nw
            surf_sents[r["surface"]] = surf_sents.get(r["surface"], 0) + 1
            surf_l5[r["surface"]] = surf_l5.get(r["surface"], 0) + len(
                L5_RE.findall(_mask_code(rr["text"])))
        h = sha(r["text"])
        for rule in hard:
            by_rule[rule].setdefault(h, r)
        for a in soft:
            advis.setdefault(a, {}).setdefault(h, r)
    l4 = {s: round(surf_words[s] / surf_sents[s], 2) for s in surf_sents
          if surf_sents[s] >= min_sentences and surf_words[s] / surf_sents[s] > L4_MAX}
    l5d = {s: round(100.0 * surf_l5[s] / surf_words[s], 3) for s in surf_words
           if surf_words[s] >= min_words and 100.0 * surf_l5[s] / surf_words[s] > L5_DENSITY_MAX}
    return {"rules": by_rule, "L4": l4, "L5_density": l5d, "advisory": advis,
            "surfaces": {s: {"sentences": surf_sents[s], "words": surf_words[s]}
                         for s in surf_sents}}


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def compare(result: dict, base: dict) -> tuple[dict, dict]:
    """(new findings, stale baseline entries), each {rule: [keys]}."""
    new, stale = {}, {}
    for rule in RULES:
        cur = set(result["rules"][rule])
        old = set(base.get(rule) or [])
        if cur - old:
            new[rule] = sorted(cur - old)
        if old - cur:
            stale[rule] = sorted(old - cur)
    for rule in SURFACE_RULES:
        cur = set(result[rule])
        old = set(base.get(rule) or [])
        if cur - old:
            new[rule] = sorted(cur - old)
        if old - cur:
            stale[rule] = sorted(old - cur)
    return new, stale


def baseline_from(result: dict) -> dict:
    out: dict = {"_about": (
        "Copy-lint ratchet (SP-D6). Each rule lists sha1 of the normalised "
        "sentence (NFKC, lower case, digit runs to 0) for every finding "
        "accepted on 2026-10-02; L4 and L5_density list surfaces; coverage "
        "lists shipped data files a page fetches whose 8+ word strings come "
        "from a writer outside COPY_PRODUCERS. "
        "`copy_lint.py --served --check` fails on a finding not listed here "
        "and on an entry that is no longer a finding, so the file only "
        "shrinks. Rewrite it with --write-baseline only in the commit that "
        "fixes copy.")}
    out["_counts"] = {r: len(result["rules"][r]) for r in RULES}
    out["_counts"].update({r: len(result[r]) for r in SURFACE_RULES})
    for rule in RULES:
        out[rule] = sorted(result["rules"][rule])
    for rule in SURFACE_RULES:
        out[rule] = sorted(result[rule])
    return out


def run_served(use_cache: bool = True) -> dict:
    recs = extract_served(use_cache=use_cache)
    result = lint_records(recs, Exemptions(load_registered()))
    result["coverage"] = coverage_report(use_cache=use_cache)
    return result


def _show(rec: dict) -> str:
    t = rec["text"]
    return f"{rec['file']} {rec['anchor']}: {t[:140]}"


def served_main(argv: list) -> int:
    t0 = time.time()
    try:  # findings carry arrows and accents; a cp1252 console must not crash
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    use_cache = "--no-cache" not in argv
    result = run_served(use_cache=use_cache)
    if "--write-baseline" in argv:
        base = baseline_from(result)
        BASELINE_PATH.write_bytes(
            (json.dumps(base, indent=1, ensure_ascii=False) + "\n")
            .replace("\n", "\r\n").encode("utf-8"))
        print("copy_lint --served: baseline written:", json.dumps(base["_counts"]))
        return 0
    base = load_baseline()
    new, stale = compare(result, base)
    counts = {r: len(result["rules"][r]) for r in RULES}
    counts.update({r: len(result[r]) for r in SURFACE_RULES})
    print("copy_lint --served findings:", json.dumps(counts))
    if "--verbose" in argv:
        for rule in RULES:
            for h, rec in sorted(result["rules"][rule].items(), key=lambda kv: kv[1]["file"]):
                print(f"  {rule} {_show(rec)}")
        for rule in SURFACE_RULES:
            for s, v in sorted(result[rule].items()):
                print(f"  {rule} {s}: {v}")
        print("advisory:", {k: len(v) for k, v in sorted(result["advisory"].items())})
    for rule, keys in new.items():
        print(f"NEW {rule} (fail):")
        for k in keys[:40]:
            rec = result["rules"][rule].get(k) if rule in RULES else None
            print("  " + (_show(rec) if rec else f"{k}: {result[rule][k]}"))
    for rule, keys in stale.items():
        print(f"STALE {rule} baseline entries (fixed or gone; remove them): {len(keys)}")
        for k in keys[:10]:
            print("  " + k)
    print(f"copy_lint --served: {time.time() - t0:.1f}s")
    if "--check" in argv:
        fail = bool(new or stale)
        print("copy_lint --served: FAIL" if fail else
              "copy_lint --served: clean against the baseline")
        return 1 if fail else 0
    return 0


# ---- producer coverage -----------------------------------------------------
#
# Every data/*.json that ships (not on deploy/data_exclude.txt), that a page
# script fetches and that carries a string of 8+ words is reader copy, so its
# writer belongs in COPY_PRODUCERS. The writer is found statically: a .py file
# (module root or tools/, tests and underscore labs excluded) that names the
# file and writes it on that line or through a constant assigned there. The
# files uncovered on 2026-10-02 are recorded under "coverage" in the baseline
# and ratchet like the rules: a NEW uncovered file fails (the next
# data_catalog.py), and an entry that becomes covered must leave the list.

JSON_NAME = re.compile(r"[\"'`/]([A-Za-z0-9_][A-Za-z0-9_.-]*\.json)[\"'`?]")
SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>(.*?)</script>", re.S | re.I)
WRITE_CALL = re.compile(
    r"\w*write\w*\(|\bjson\.dump\b|\bdump\w*\(|\.to_json\(|\.replace\("
    r"|open\([^)\n]*[\"'][wa]b?[\"']")
OUTISH = re.compile(r"(?i)\bout(put)?\b|_out\b|\bout_|dest\b|target\b|save")
PROSE_JSON = re.compile(rb"\"[A-Za-z(][^\"\\\n]*(?: [^\" \\\n]+){7}")


def _excluded_data() -> set:
    p = ROOT / "deploy" / "data_exclude.txt"
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")}


def fetched_data_files() -> list:
    """Shipped data/*.json names quoted in a served script."""
    names: set = set()
    for pat in JS_GLOBS:
        for p in ROOT.glob(pat):
            if p.is_file() and not _is_blob(_head(p), sample=p.stat().st_size > BLOB_BYTES):
                names.update(JSON_NAME.findall(p.read_text(encoding="utf-8", errors="replace")))
    for pat in PAGE_GLOBS:
        for p in ROOT.glob(pat):
            if p.is_file():
                for m in SCRIPT_BLOCK.finditer(p.read_text(encoding="utf-8", errors="replace")):
                    if not _is_blob(m.group(1)):
                        names.update(JSON_NAME.findall(m.group(1)))
    excl = _excluded_data()
    return sorted(n for n in names if n not in excl and (ROOT / "data" / n).is_file())


def _py_sources() -> dict:
    out = {}
    for p in list(ROOT.glob("*.py")) + list(ROOT.glob("tools/*.py")):
        if p.name.startswith(("test_", "conftest", "_")):
            continue
        out[_rel(p)] = p.read_text(encoding="utf-8", errors="replace")
    return out


def data_writers(name: str, sources: dict) -> list:
    """The .py files that write data/<name>, by the static rule above."""
    out = []
    for rel, src in sources.items():
        if name not in src:
            continue
        lines = src.split("\n")
        hit = False
        for i, ln in enumerate(lines):
            if name not in ln:
                continue
            win = "\n".join(lines[i:i + 3])
            if WRITE_CALL.search(win) or OUTISH.search(ln):
                hit = True
                break
            m = re.match(r"\s*([A-Za-z_]\w*)\s*(?::[^=]*)?=", ln)
            if m:
                word = re.compile(r"\b" + re.escape(m.group(1)) + r"\b")
                if any(word.search(o) and WRITE_CALL.search(o)
                       for j, o in enumerate(lines) if j != i and m.group(1) in o):
                    hit = True
                    break
        if hit:
            out.append(rel)
    return out


def _has_prose(p: Path, memo: dict) -> bool:
    st = p.stat()
    key = f"{st.st_mtime_ns}:{st.st_size}"
    got = memo.get(p.name)
    if got and got[0] == key:
        return got[1]
    yes = bool(PROSE_JSON.search(p.read_bytes()))
    memo[p.name] = [key, yes]
    return yes


def coverage_report(use_cache: bool = True) -> dict:
    """{name: writers} for every fetched, shipped data file with 8+ word
    strings whose writers miss COPY_PRODUCERS (writers [] = none found)."""
    cf = _cache_dir() / "coverage_prose.json"
    memo: dict = {}
    if use_cache:
        try:
            memo = json.loads(cf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            memo = {}
    sources = _py_sources()
    prod = set(COPY_PRODUCERS)
    out = {}
    for name in fetched_data_files():
        w = data_writers(name, sources)
        if prod.intersection(w):
            continue
        if _has_prose(ROOT / "data" / name, memo):
            out[name] = w
    if use_cache:
        try:
            cf.parent.mkdir(parents=True, exist_ok=True)
            cf.write_text(json.dumps(memo), encoding="utf-8")
        except OSError:
            pass
    return out


# ---- markdown docs (docs/COPY_STYLE.md must pass its own rules) ------------

def lint_doc(path: Path, ex: "Exemptions | None" = None) -> list:
    """Hard findings in a markdown doc. Quoted spans ('...', "...") and code
    spans are mentions, not use, and are masked first; table cells and list
    items are linted as sentences."""
    ex = ex or Exemptions(load_registered())
    out = []
    in_code = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip():
            continue
        s = re.sub(r"`[^`]*`", "`x`", line)
        s = re.sub(r"(?<!\w)'(?:[^'\n]|'(?=\w))+?'(?=[\s,.;:)|]|$)", "`x`", s)
        s = re.sub(r'"[^"\n]+"', "`x`", s)
        s = s.replace("\u2018", "'").replace("\u2019", "'")
        for cell in re.split(r"\s\|\s|^\||\|$", s):
            cell = re.sub(r"^[#>*\-\s\d.]+", "", cell).strip()
            if not cell or ex.exempt(cell):
                continue
            for sent in SPLIT.split(cell):
                hard, _ = rule_hits({"text": sent, "kind": "doc"})
                if EM in sent or "\u2013" in sent:
                    hard.append("dash")
                for h in hard:
                    out.append(f"{path.name}:{i}: {h}: {sent[:120]}")
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--served" in argv:
        return served_main(argv)
    if "--doc" in argv:
        docs = [Path(a).resolve() for a in argv if not a.startswith("--")]
        hits = [h for d in docs for h in lint_doc(d)]
        print(*hits, sep="\n") if hits else None
        print(f"copy_lint --doc: {len(hits)} finding(s)")
        return 1 if hits else 0
    check = "--check" in argv
    # Positional paths replace the TARGETS list (the gate's own tests use it).
    # An explicit file is judged as pure copy when its NAME is one of the
    # pure-copy names, so a fixture glossary.json fails like the real one.
    explicit = [Path(a).resolve() for a in argv if not a.startswith("--")]
    pure_names = {Path(r).name for r in PURE_COPY}
    em_hits: list[str] = []
    ban_hard: list[str] = []
    ban_soft: list[str] = []
    for p in (explicit or _files()):
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = _rel(p)
        pure = _is_pure(rel) or (bool(explicit) and p.name in pure_names)
        _scan(rel, text, em_hits, ban_hard if pure else ban_soft)
        if p.suffix == ".json" and escaped_dash_count(text):
            # ensure_ascii dumps store the dash as an escape; it still renders.
            em_hits.append(f"{rel}: {escaped_dash_count(text)} ASCII-escaped em/en-dash(es)")

    if em_hits:
        print("EM-DASHES (fail):", *em_hits[:60], sep="\n  ")
    if ban_hard:
        print("\nLLM TERMS in pure-copy (fail):", *ban_hard[:100], sep="\n  ")
    if ban_soft:
        print(f"\nLLM TERMS in code/copy files (advisory, review) - {len(ban_soft)} total:",
              *ban_soft[:60], sep="\n  ")

    fail = bool(em_hits or ban_hard)
    if check:
        print("\ncopy_lint: FAIL" if fail else
              "\ncopy_lint: clean (no em-dashes; no LLM terms in pure-copy)")
        return 1 if fail else 0
    print(f"\ncopy_lint: {len(em_hits)} em-dash, {len(ban_hard)} hard, "
          f"{len(ban_soft)} advisory")
    return 0


if __name__ == "__main__":
    sys.exit(main())
