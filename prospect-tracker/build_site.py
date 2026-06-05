# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""
build_site.py — static-site generator for the editorial pages of eephus.io.

Reads `content/` and writes the static pages that share the PROSPX theme
(`assets/site.css`) + the site-wide nav:

    /              -> index.html              (Home: brand hero + module cards)
    /articles/     -> articles/index.html     (grid of article cards, newest first)
    /articles/<s>/ -> articles/<slug>/index.html  (one page per content/articles/<slug>.md)
    /team/         -> team/index.html          (from content/team.json)

PROSPX lives at /prospx/index.html and is NOT touched by this script (its nav +
asset paths were wired once, by hand). `run_monthly.py` (the data pipeline that
writes data/*.json) is also independent of this build.

Add an article = drop a markdown file in content/articles/ with frontmatter
(title/author/handle/date/summary) and rerun `python build_site.py`. Embed a
YouTube clip on its own line with `@youtube: <url-or-id>`.

Usage:  python build_site.py
"""
from __future__ import annotations

import html
import json
import re
from datetime import date, datetime
from pathlib import Path

import markdown as md

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"

NAV_ITEMS = [
    ("home",     "Home",             "/"),
    ("articles", "Articles",         "/articles/"),
    ("prospx",   "PROSPX",           "/prospx/"),
    ("team",     "Development Team",  "/team/"),
]

# --------------------------------------------------------------------------- #
# Markdown + YouTube
# --------------------------------------------------------------------------- #
_YT_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})"
)

def _youtube_id(raw: str) -> str | None:
    raw = raw.strip()
    m = _YT_RE.search(raw)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", raw):   # bare id
        return raw
    return None

def _youtube_embed(video_id: str) -> str:
    src = f"https://www.youtube.com/embed/{video_id}"
    return (
        '<div class="video-embed">'
        f'<iframe src="{src}" title="YouTube video" loading="lazy" '
        'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
        'picture-in-picture" allowfullscreen></iframe></div>'
    )

def render_markdown(text: str) -> str:
    """Render article markdown to HTML, with a clean `@youtube: <url>` directive.
    The directive is swapped for a placeholder before conversion, then back to a
    responsive iframe afterward, so the markdown engine never mangles the embed."""
    placeholders: dict[str, str] = {}
    out_lines = []
    for line in text.splitlines():
        m = re.match(r"^\s*@youtube:\s*(\S+)\s*$", line)
        if m:
            vid = _youtube_id(m.group(1))
            if vid:
                token = f"@@YT_{len(placeholders)}@@"
                placeholders[token] = _youtube_embed(vid)
                out_lines.append("")
                out_lines.append(token)
                out_lines.append("")
                continue
        out_lines.append(line)
    body = md.markdown(
        "\n".join(out_lines),
        extensions=["extra", "sane_lists", "smarty"],
        output_format="html5",
    )
    for token, embed in placeholders.items():
        body = body.replace(f"<p>{token}</p>", embed).replace(token, embed)
    return body

# --------------------------------------------------------------------------- #
# Frontmatter
# --------------------------------------------------------------------------- #
def parse_article(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            fm = raw[3:end].strip("\n")
            body = raw[end + 4:].lstrip("\n")
            for ln in fm.splitlines():
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    meta[k.strip()] = v.strip()
    meta.setdefault("title", path.stem.replace("-", " ").title())
    meta["slug"] = path.stem
    meta["body_html"] = render_markdown(body)
    meta["date_sort"] = meta.get("date", "")
    meta["date_disp"] = _fmt_date(meta.get("date", ""))
    return meta

def _fmt_date(s: str) -> str:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%B %-d, %Y")
    except (ValueError, AttributeError):
        try:  # Windows strftime has no %-d
            return datetime.strptime(s.strip(), "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return s

def _byline(meta: dict, sep: str = " · ") -> str:
    author = html.escape(meta.get("author", "") or "")
    handle = (meta.get("handle") or "").lstrip("@")
    parts = [f'<span class="author">{author}</span>'] if author else []
    if handle:
        parts.append(f'<a href="https://x.com/{html.escape(handle)}">@{html.escape(handle)}</a>')
    out = sep.join(parts)
    if meta.get("date_disp"):
        out += f'<span class="dot-sep">·</span>{html.escape(meta["date_disp"])}'
    return out

# --------------------------------------------------------------------------- #
# Page shell
# --------------------------------------------------------------------------- #
def _nav(active: str) -> str:
    items = []
    for key, label, href in NAV_ITEMS:
        cls = ' class="is-active"' if key == active else ""
        items.append(f'<a href="{href}"{cls}>{html.escape(label)}</a>')
    return (
        '<header class="eephus-nav">'
        '<a class="eephus-wordmark" href="/">eephus.io</a>'
        f'<nav class="eephus-links">{"".join(items)}</nav>'
        "</header>"
    )

def page(title: str, active: str, body: str, description: str = "") -> str:
    desc = html.escape(description or "eephus.io — editorial baseball analytics portal")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body class="eephus-page">
{_nav(active)}
<main class="eephus-wrap">
{body}
</main>
<footer class="eephus-footer">
  <span>eephus.io — editorial baseball analytics</span>
  <span>© {date.today().year} eephus.io</span>
</footer>
</body>
</html>
"""

# --------------------------------------------------------------------------- #
# Page builders
# --------------------------------------------------------------------------- #
def build_home() -> str:
    cards = [
        ("Read", "Articles", "Analysis &amp; long-form on prospects, development, and the game.", "Browse articles →", "/articles/"),
        ("Tool", "PROSPX", "Consensus FV-based MiLB prospect tracker with surplus-value analytics.", "Open PROSPX →", "/prospx/"),
        ("About", "Development Team", "The people building eephus.io.", "Meet the team →", "/team/"),
    ]
    mod = "".join(
        f'<a class="card module-card" href="{href}">'
        f'<div class="eyebrow">{eye}</div><h2>{html.escape(name)}</h2>'
        f'<p>{desc}</p><span class="card-cta">{cta}</span></a>'
        for eye, name, desc, cta, href in cards
    )
    body = (
        '<section class="hero">'
        '<h1>eephus<span class="dot">.io</span></h1>'
        '<div class="hero-rule"></div>'
        "<p>An editorial baseball-analytics portal — long-form articles, the PROSPX "
        "prospect tracker, and the people behind it.</p>"
        "</section>"
        f'<div class="module-grid">{mod}</div>'
    )
    return page("eephus.io — editorial baseball analytics", "home", body,
                "Editorial baseball analytics portal: articles, the PROSPX prospect tracker, and the team.")

def build_articles_index(articles: list[dict]) -> str:
    cards = []
    for a in articles:
        excerpt = html.escape(a.get("summary", ""))
        cards.append(
            f'<a class="card article-card" href="/articles/{a["slug"]}/">'
            '<div class="eyebrow">Article</div>'
            f'<p class="meta">{_byline(a)}</p>'
            f'<h3>{html.escape(a["title"])}</h3>'
            f"<p>{excerpt}</p>"
            '<span class="card-cta">Read →</span></a>'
        )
    grid = "".join(cards) or '<p>No articles yet.</p>'
    body = (
        '<div class="section-head"><h1>Articles</h1>'
        '<span class="section-sub">analysis &amp; long-form from the eephus desk</span></div>'
        f'<div class="article-grid">{grid}</div>'
    )
    return page("Articles — eephus.io", "articles", body, "Long-form baseball analysis from eephus.io.")

def build_article_page(a: dict) -> str:
    body = (
        '<a class="back-link" href="/articles/">← All articles</a>'
        '<article class="article">'
        '<header class="article-header">'
        f'<h1>{html.escape(a["title"])}</h1>'
        f'<div class="byline">{_byline(a)}</div>'
        "</header>"
        + (f'<p class="article-summary">{html.escape(a["summary"])}</p>' if a.get("summary") else "")
        + f'<div class="article-body">{a["body_html"]}</div>'
        "</article>"
    )
    return page(f'{a["title"]} — eephus.io', "articles", body, a.get("summary", ""))

def build_team() -> str:
    team = json.loads((CONTENT / "team.json").read_text(encoding="utf-8"))
    cards = []
    for m in team:
        handle = (m.get("handle") or "").lstrip("@")
        handle_html = (
            f'<p class="handle"><a href="https://x.com/{html.escape(handle)}">@{html.escape(handle)}</a></p>'
            if handle else ""
        )
        cards.append(
            f'<div class="card team-card"><p class="name">{html.escape(m["name"])}</p>{handle_html}</div>'
        )
    body = (
        '<div class="section-head"><h1>Development Team</h1>'
        '<span class="section-sub">the people building eephus.io</span></div>'
        f'<div class="team-grid">{"".join(cards)}</div>'
    )
    return page("Development Team — eephus.io", "team", body, "The team behind eephus.io.")

# --------------------------------------------------------------------------- #
def _write(rel: str, content: str) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {rel}")

def main() -> None:
    print("build_site.py — generating editorial pages")
    art_dir = CONTENT / "articles"
    articles = [parse_article(p) for p in sorted(art_dir.glob("*.md"))] if art_dir.exists() else []
    articles.sort(key=lambda a: a.get("date_sort", ""), reverse=True)  # newest first

    _write("index.html", build_home())
    _write("articles/index.html", build_articles_index(articles))
    for a in articles:
        _write(f"articles/{a['slug']}/index.html", build_article_page(a))
    _write("team/index.html", build_team())
    print(f"done — {len(articles)} article(s).")

if __name__ == "__main__":
    main()
