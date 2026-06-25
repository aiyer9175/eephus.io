# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Apply the project's proprietary copyright watermark to every authored
source file (idempotent).

The watermark text mirrors the canonical closed-source header form
documented in the SE answer the project owner shared:

    Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
    Unauthorized copying of this file, via any medium is strictly prohibited
    Proprietary and confidential
    Written by Noah J. Dengler (@ARKNDJL), 2026

The block is inserted at the top of each file, using the appropriate
comment syntax per language. README.md gets a visible footer rather
than a hidden HTML comment (readers should see the copyright when they
land on the repo). Auto-generated artifacts (.cache/, data/*.json,
data/value_framework.js, etc.) and third-party content (vendor/) are
skipped — the watermark belongs only on code you authored.

Re-running this script is safe: each file is scanned for an existing
"Copyright (C) ... Noah J. Dengler" line and skipped if found. To bump
the year or change the wording, edit COPYRIGHT_HOLDER / COPYRIGHT_YEAR
below and re-run — the script will detect any header that DIDN'T match
the current canonical text and rewrite it.

Usage:
    python tools/apply_watermark.py [--dry-run] [--rewrite]

    --dry-run   Report which files would change without writing.
    --rewrite   Replace any existing project-owned watermark with the
                current canonical wording (default: skip files that
                already carry any watermark line, even if stale).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Canonical watermark text. Edit here to re-anchor the project (year, name,
# wording) and re-run with --rewrite to roll the change through every file.
# ---------------------------------------------------------------------------
COPYRIGHT_HOLDER = "Noah J. Dengler (@ARKNDJL)"
COPYRIGHT_YEAR   = 2026

WATERMARK_LINES = [
    f"Copyright (C) {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER} - All Rights Reserved",
    "Unauthorized copying of this file, via any medium is strictly prohibited",
    "Proprietary and confidential",
    f"Written by {COPYRIGHT_HOLDER}, {COPYRIGHT_YEAR}",
]

# Detection sentinel — if this string appears in the file (in any comment
# form) we treat the file as already watermarked. Generic enough to catch
# variants from --rewrite cycles or hand-edits.
DETECTION_RE = re.compile(
    r"Copyright\s*\(C\)\s*\d{4}\s*Noah J\.\s*Dengler",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# File-type configuration
# ---------------------------------------------------------------------------
class FileSpec:
    """One file-format spec: the comment delimiters used to wrap the
    watermark, plus the position where the watermark should land."""
    def __init__(self, *, prefix: str = "# ", open_token: str | None = None,
                 close_token: str | None = None, footer: bool = False,
                 visible_md: bool = False) -> None:
        # prefix:        per-line prefix (e.g. "# " for Python, "  " inside HTML).
        # open_token:    line emitted ABOVE the block (e.g. "<!--").
        # close_token:   line emitted BELOW the block (e.g. "-->").
        # footer:        append the watermark at the END of the file, not the top.
        # visible_md:    render as a visible Markdown footer (no comment syntax).
        self.prefix      = prefix
        self.open_token  = open_token
        self.close_token = close_token
        self.footer      = footer
        self.visible_md  = visible_md


SPEC_BY_EXT: dict[str, FileSpec] = {
    ".py":           FileSpec(prefix="# "),
    ".txt":          FileSpec(prefix="# "),
    ".html":         FileSpec(prefix="  ", open_token="<!--", close_token="-->"),
    ".md":           FileSpec(footer=True, visible_md=True),
}


def render_watermark(spec: FileSpec) -> str:
    """Build the watermark block as a single string with trailing newline."""
    if spec.visible_md:
        # Visible Markdown footer (rendered as text on the README page).
        body = (
            "---\n\n"
            "## Copyright & License\n\n"
            + "\n".join(WATERMARK_LINES) + "\n\n"
            "See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md) for full terms.\n"
        )
        return body
    lines: list[str] = []
    if spec.open_token is not None:
        lines.append(spec.open_token)
    for w in WATERMARK_LINES:
        lines.append(f"{spec.prefix}{w}")
    if spec.close_token is not None:
        lines.append(spec.close_token)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# File targeting
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent

# Paths to ALWAYS skip (auto-generated, third-party, binary, or data).
SKIP_DIRS = {
    ".cache", "__pycache__", "vendor", "logs",
    "data",                 # data/*.json and data/*.js are auto-generated
    "data/fangraphs_imports",  # user-imported CSVs (data, not code)
    "test_fixtures",        # third-party scraped HTML (NCAA stat pages, etc.)
                            # captured as parser test inputs — not authored code,
                            # so a "Written by …" header would be a false claim.
}
SKIP_EXTS = {
    ".pyc", ".pyo", ".json", ".csv", ".db", ".sqlite",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".lock", ".log",
}
SKIP_FILES = {
    ".gitignore", ".gitattributes",
    "qa_out.txt",        # pytest output capture, regenerated on every run
}


def _should_skip(path: Path) -> bool:
    """Return True if `path` should NOT be watermarked."""
    rel = path.relative_to(_ROOT)
    if path.name in SKIP_FILES:
        return True
    if path.suffix.lower() in SKIP_EXTS:
        return True
    for part in rel.parts:
        if part in SKIP_DIRS:
            return True
    if path.suffix.lower() not in SPEC_BY_EXT:
        return True
    return False


def _enumerate_targets() -> list[Path]:
    """Walk _ROOT and produce the list of files in scope for watermarking."""
    out: list[Path] = []
    for p in _ROOT.rglob("*"):
        if not p.is_file():
            continue
        try:
            if _should_skip(p):
                continue
        except ValueError:
            continue
        out.append(p)
    # Stable order so dry-run output is diff-friendly.
    return sorted(out)


# ---------------------------------------------------------------------------
# Insertion logic per file type
# ---------------------------------------------------------------------------
_PY_PREFIX_KEEP_RE = re.compile(
    r"^(?:#!.*\n)?(?:#\s*-\*-.*coding.*-\*-.*\n)?"
)
_HTML_DOCTYPE_RE = re.compile(r"^<!DOCTYPE[^>]*>\s*\n?", re.IGNORECASE)


def insert_watermark(text: str, path: Path, spec: FileSpec) -> str:
    """Return `text` with the watermark inserted at the correct position.
    Pure function — does not write to disk."""
    block = render_watermark(spec)
    if spec.footer:
        # Trim trailing whitespace, then append.
        body = text.rstrip() + "\n\n" + block
        return body
    # Header insertion. For Python: respect shebang + encoding declaration.
    if path.suffix.lower() == ".py":
        m = _PY_PREFIX_KEEP_RE.match(text)
        head = text[: m.end()] if m else ""
        rest = text[m.end() :] if m else text
        # If the file begins with a docstring/code immediately, insert the
        # block followed by a blank line so the docstring isn't glued to
        # the comment.
        sep = "\n" if rest and not rest.startswith("\n") else ""
        return head + block + sep + rest
    if path.suffix.lower() == ".html":
        m = _HTML_DOCTYPE_RE.match(text)
        if m:
            return text[: m.end()] + block + text[m.end():]
        return block + text
    # Generic: prepend.
    return block + text


def remove_existing_watermark(text: str, path: Path) -> str:
    """Strip any previously-applied watermark block so --rewrite can put
    the current canonical text in its place. Conservative: only removes
    a CONTIGUOUS comment block that contains the detection sentinel."""
    if not DETECTION_RE.search(text):
        return text
    lines = text.splitlines(keepends=True)
    # Find the line containing the sentinel.
    target = None
    for i, ln in enumerate(lines):
        if DETECTION_RE.search(ln):
            target = i
            break
    if target is None:
        return text
    # Walk outward to find the contiguous comment-ish block.
    suffix = path.suffix.lower()
    def _is_comment_line(ln: str) -> bool:
        s = ln.strip()
        if not s:
            return False
        if suffix == ".py" or suffix == ".txt":
            return s.startswith("#")
        if suffix == ".html":
            return s.startswith("<!--") or s.endswith("-->") or s.startswith(("  ", "\t"))
        if suffix == ".md":
            return True   # md visible-footer covers itself separately
        return False
    start, end = target, target + 1
    while start > 0 and _is_comment_line(lines[start - 1]):
        start -= 1
    while end < len(lines) and _is_comment_line(lines[end]):
        end += 1
    # For HTML, also consume the opener/closer tokens immediately around.
    if suffix == ".html":
        if start > 0 and lines[start - 1].strip().startswith("<!--"):
            start -= 1
        if end < len(lines) and lines[end].strip() == "-->":
            end += 1
    # Drop one trailing blank line if present (was the separator we inserted).
    if end < len(lines) and lines[end].strip() == "":
        end += 1
    return "".join(lines[:start] + lines[end:])


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would change; don't write.")
    ap.add_argument("--rewrite", action="store_true",
                    help="Replace existing watermarks with current canonical text.")
    args = ap.parse_args()

    targets = _enumerate_targets()
    n_added = 0
    n_rewritten = 0
    n_skipped = 0
    for path in targets:
        spec = SPEC_BY_EXT[path.suffix.lower()]
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            print(f"  skip (binary?): {path.relative_to(_ROOT)}")
            n_skipped += 1
            continue
        has_existing = bool(DETECTION_RE.search(text))
        if has_existing and not args.rewrite:
            n_skipped += 1
            continue
        new_text = text
        if has_existing and args.rewrite:
            new_text = remove_existing_watermark(new_text, path)
        new_text = insert_watermark(new_text, path, spec)
        if new_text == text:
            n_skipped += 1
            continue
        rel = path.relative_to(_ROOT)
        if args.dry_run:
            label = "rewrite" if has_existing else "add"
            print(f"  {label}: {rel}")
        else:
            path.write_text(new_text, encoding="utf-8")
            label = "rewritten" if has_existing else "added"
            print(f"  {label}: {rel}")
        if has_existing:
            n_rewritten += 1
        else:
            n_added += 1

    print()
    if args.dry_run:
        print(f"Dry run: would add to {n_added}, rewrite {n_rewritten}, "
              f"skip {n_skipped} files (total scanned: {len(targets)})")
    else:
        print(f"Done: added {n_added}, rewrote {n_rewritten}, "
              f"skipped {n_skipped} (total scanned: {len(targets)})")
    sys.exit(0)


if __name__ == "__main__":
    main()
