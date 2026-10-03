# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The publish-time asset comment strip (tools/strip_asset_comments.py, bloat
finding AS14, 2026-10-03).

The nightly rewrites the WEBROOT copies of assets/*.css, assets/*.js and the
two CollegeSavant app scripts. These tests run the same per-file path over
every shipped source, in memory (nothing in the tree is written), and hold:
  - every file strips, passes the tool's own validation (a JS engine compile,
    or the CSS brace and rule-count scan) and comes out smaller;
  - an INDEPENDENT tokenizer sees the same token stream before and after
    (esprima for JS, tinycss2 for CSS): only comments and whitespace went;
  - the tokenizer edge cases (strings, template literals, regex literals,
    URLs with //, CSS strings and unquoted url()) survive byte for byte;
  - a file that fails validation is kept whole while its neighbours strip;
  - the nightly runs the step after the rsync and before the precompress,
    fail-open.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "tools"))
import strip_asset_comments as S  # noqa: E402

FILES = S.target_files(ROOT)
CHECKER, ENGINE = S.js_checker()


def test_the_target_set_is_the_shipped_asset_set():
    rels = {p.relative_to(ROOT).as_posix() for p in FILES}
    assert "assets/site.css" in rels and "assets/mlbstats.js" in rels
    assert {"collegesavant/app.js", "collegesavant/pitcher_app.js"} <= rels
    assert len(rels) >= 40, sorted(rels)


def _css_tokens(text):
    tinycss2 = pytest.importorskip("tinycss2")
    out = []

    def walk(nodes):
        for n in nodes:
            if n.type in ("whitespace", "comment"):
                continue
            if n.type == "function":
                out.append(("function", n.lower_name))
                walk(n.arguments)
                out.append(("end",))
            elif n.type in ("() block", "[] block", "{} block"):
                out.append((n.type,))
                walk(n.content)
                out.append(("end",))
            else:
                out.append((n.type, n.serialize()))
    walk(tinycss2.parse_component_value_list(text, skip_comments=True))
    return out


def _js_tokens(text):
    esprima = pytest.importorskip("esprima")
    return [(t.type, t.value) for t in esprima.tokenize(text)]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_shipped_asset_strips_validates_and_shrinks(path):
    rel = path.relative_to(ROOT).as_posix()
    if rel.endswith(".js") and CHECKER is None:
        pytest.skip("no JavaScript engine on this machine (node or py_mini_racer)")
    text = path.read_bytes().decode("utf-8")
    out, status = S.strip_text(rel, text, CHECKER)
    assert status == "stripped" and out is not None, f"{rel}: {status}"
    assert len(out) < len(text), rel
    if rel.endswith(".css"):
        assert S.validate_css(text, out) is None
        assert _css_tokens(out) == _css_tokens(text), f"{rel}: CSS token stream moved"
    else:
        assert CHECKER(out) is None
        assert _js_tokens(out) == _js_tokens(text), f"{rel}: JS token stream moved"
    # Idempotent: a second pass over the shipped copy finds nothing more to take.
    again, _ = S.strip_text(rel, out, CHECKER)
    assert again is None or again == out


def test_css_edge_cases_keep_strings_urls_and_token_boundaries():
    src = (
        "/* header */\r\n"
        ".a::before { content: \"/* not a comment */\"; }\r\n"
        ".b { background: url(//cdn.example/x/*y*/z.png); }\r\n"
        ".c { background: url( 'q/*r*/s.png' ); }\r\n"
        "  /* own line,\r\n     two lines */\r\n"
        ".d/**/.e { color: red; /* trailing */ }\r\n"
        "a/* glue */b { margin: 0 }\r\n"
        "/*! keep me */\r\n"
        "/* Copyright 2026 */\r\n"
    )
    out = S.strip_css(src, {})
    assert '"/* not a comment */"' in out
    assert "url(//cdn.example/x/*y*/z.png)" in out
    assert "url( 'q/*r*/s.png' )" in out
    assert "own line" not in out and "header" not in out and "trailing" not in out
    assert "a/**/b" in out, "two idents must not merge into one"
    assert ".d/**/.e" in out, "kept as an empty comment: '1/**/.5' must not become '1.5'"
    assert _css_tokens(out) == _css_tokens(src)
    assert "/*! keep me */" in out and "/* Copyright 2026 */" in out
    assert S.validate_css(src, out) is None


def test_js_edge_cases_keep_strings_templates_regexes_and_urls():
    src = (
        "// own line\n"
        "const u = \"https://example.com/a//b\";\n"
        "const t = `x ${ {a: 1}.a } /* in template */ ${'//'}`;\n"
        "const r = /\\/\\/*[/*]/g; // trailing kept\n"
        "/* block */\n"
        "const q = 'it\\'s /* not */'.length; /* mid */ const z = 2;\n"
    )
    out = S.strip_js(src, {"js_line": 0, "js_block": 0, "html": 0})
    assert "own line" not in out and "block" not in out and "mid" not in out
    for keep in ('"https://example.com/a//b"', "/* in template */",
                 "/\\/\\/*[/*]/g", "// trailing kept", "'it\\'s /* not */'"):
        assert keep in out, keep


def test_a_file_that_fails_validation_ships_whole_while_neighbours_strip(tmp_path):
    (tmp_path / "assets").mkdir()
    good = "/* c */\nfunction f() { return 1; }\n"
    bad = "/* c */\nfunction f( { return 1; }\n"
    css_bad = "/* c */\n.a { color: red;\n"
    (tmp_path / "assets" / "good.js").write_text(good, encoding="utf-8")
    (tmp_path / "assets" / "bad.js").write_text(bad, encoding="utf-8")
    (tmp_path / "assets" / "a.css").write_text("/* c */\n.a { color: red; }\n", encoding="utf-8")
    (tmp_path / "assets" / "b.css").write_text(css_bad, encoding="utf-8")
    rows = {r["file"]: r for r in S.run(tmp_path)}
    assert (tmp_path / "assets" / "bad.js").read_text(encoding="utf-8") == bad
    assert rows["assets/bad.js"]["status"].startswith("kept")
    assert (tmp_path / "assets" / "b.css").read_text(encoding="utf-8") == css_bad
    assert rows["assets/b.css"]["status"].startswith("kept")
    assert rows["assets/a.css"]["status"] == "stripped"
    if CHECKER is not None:
        assert rows["assets/good.js"]["status"] == "stripped"
        assert "/* c */" not in (tmp_path / "assets" / "good.js").read_text(encoding="utf-8")


def test_nightly_runs_the_strip_after_rsync_before_precompress_fail_open():
    sh = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    rsync = sh.index("rsync -a --delete")
    step = sh.index("tools/strip_asset_comments.py")
    gz = sh.index("gzip -9 -k -f")
    assert rsync < step < gz
    line = sh[step:sh.index("\n", sh.index("\n", step) + 1)]
    assert '"$WEBROOT" --in-place' in line and "|| echo" in line, line
