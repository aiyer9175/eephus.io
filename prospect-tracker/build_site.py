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

# PROSPX sub-sections — deep links into the app (section = `tab` query param in
# the hash; `active` is the default so it has no param).
PROSPX_SUBNAV = [
    ("Prospects",     "/prospx/"),
    ("Farm Systems",  "/prospx/#tab=farm"),
    ("Leaderboards",  "/prospx/#tab=leaderboards"),
    ("Transactions",  "/prospx/#tab=traded"),
    ("Injured List",  "/prospx/#tab=injured"),
    ("Spotlights",    "/prospx/#tab=spotlights"),
    ("Debuted",       "/prospx/#tab=debuts"),
    ("MLB Draft",     "/prospx/#tab=draft"),
    ("International",  "/prospx/#tab=ifa"),
    ("Overseas",      "/prospx/#tab=overseas"),
    ("Scatterplots",  "/prospx/#tab=charts"),
    ("Glossary",      "/prospx/#tab=glossary"),
]

# Site-wide theme: read the shared key PROSPX uses (prospect-tracker.theme) and
# set <html data-theme> synchronously in <head> (no flash); toggle persists to
# the same key so light/dark stays in sync across the whole site incl. PROSPX.
THEME_INIT = (
    '<script>(function(){try{var t=localStorage.getItem("prospect-tracker.theme");'
    'if(!t)t=(window.matchMedia&&matchMedia("(prefers-color-scheme: dark)").matches)?"dark":"light";'
    'document.documentElement.setAttribute("data-theme",t);}catch(e){}})();'
    'function eephusToggleTheme(){try{var c=document.documentElement.getAttribute("data-theme")==="dark"?"light":"dark";'
    'document.documentElement.setAttribute("data-theme",c);localStorage.setItem("prospect-tracker.theme",c);}catch(e){}}</script>'
)
THEME_BTN = (
    '<button type="button" class="home-theme-toggle" data-theme-toggle onclick="eephusToggleTheme()" aria-label="Toggle dark mode">'
    '<span class="lbl-dark">☾ Dark</span><span class="lbl-light">☀ Light</span></button>'
)

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

def _byline(meta: dict, sep: str = " · ", link_handle: bool = True) -> str:
    # link_handle=False when the byline sits INSIDE a card <a> (nested <a> is
    # invalid HTML and the browser splits the card apart) — render @handle as text.
    author = html.escape(meta.get("author", "") or "")
    handle = (meta.get("handle") or "").lstrip("@")
    parts = [f'<span class="author">{author}</span>'] if author else []
    if handle:
        parts.append(
            f'<a href="https://x.com/{html.escape(handle)}">@{html.escape(handle)}</a>'
            if link_handle else f'<span class="handle">@{html.escape(handle)}</span>'
        )
    if meta.get("date_disp"):
        parts.append(html.escape(meta["date_disp"]))
    return sep.join(parts)

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
        f'{THEME_BTN}'
        "</header>"
    )

def page(title: str, active: str, body: str, description: str = "") -> str:
    desc = html.escape(description or "eephus.io — editorial baseball analytics portal")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
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
# --------------------------------------------------------------------------- #
# Live PROSPX data (build-time). Reads the same data/*.json PROSPX uses so the
# homepage modules + wire feed regenerate on each build (run after run_monthly).
# --------------------------------------------------------------------------- #
DATA_DIR = ROOT / "data"
ORG_NAMES = {
    "ARI": "Diamondbacks", "ATH": "Athletics", "ATL": "Braves", "BAL": "Orioles",
    "BOS": "Red Sox", "CHC": "Cubs", "CHW": "White Sox", "CIN": "Reds",
    "CLE": "Guardians", "COL": "Rockies", "DET": "Tigers", "HOU": "Astros",
    "KCR": "Royals", "LAA": "Angels", "LAD": "Dodgers", "MIA": "Marlins",
    "MIL": "Brewers", "MIN": "Twins", "NYM": "Mets", "NYY": "Yankees",
    "PHI": "Phillies", "PIT": "Pirates", "SDP": "Padres", "SEA": "Mariners",
    "SFG": "Giants", "STL": "Cardinals", "TBR": "Rays", "TEX": "Rangers",
    "TOR": "Blue Jays", "WSN": "Nationals",
}

def _fmt_iso_date(s: str | None) -> str:
    if not s:
        return "—"
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    except ValueError:
        return "—"

def load_site_data() -> dict | None:
    ts_path = DATA_DIR / "timeseries.json"
    if not ts_path.exists():
        return None
    ts = json.loads(ts_path.read_text(encoding="utf-8"))
    grads = []
    dpath = DATA_DIR / "debuts.json"
    if dpath.exists():
        d = json.loads(dpath.read_text(encoding="utf-8"))
        grads = d if isinstance(d, list) else (d.get("players") or d.get("debuts") or [])
    return {
        "as_of": _fmt_iso_date(ts.get("generated_at")),
        "players": ts.get("players") or [],
        "org_summary": ts.get("org_summary") or [],
        "graduates": grads,
    }

def _player_href(key: str) -> str:
    return f"/prospx/#player={key}" if key else "/prospx/"

# ORG abbreviation -> ESPN logo slug (mirrors ESPN_LOGO_SLUGS in prospx/index.html).
ESPN_SLUGS = {
    "ARI": "ari", "ATH": "ath", "ATL": "atl", "BAL": "bal", "BOS": "bos",
    "CHC": "chc", "CHW": "chw", "CIN": "cin", "CLE": "cle", "COL": "col",
    "DET": "det", "HOU": "hou", "KCR": "kc",  "LAA": "laa", "LAD": "lad",
    "MIA": "mia", "MIL": "mil", "MIN": "min", "NYM": "nym", "NYY": "nyy",
    "PHI": "phi", "PIT": "pit", "SDP": "sd",  "SEA": "sea", "SFG": "sf",
    "STL": "stl", "TBR": "tb",  "TEX": "tex", "TOR": "tor", "WSN": "wsh",
}

def _team_logo(org: str | None) -> str:
    """Clean ESPN CDN team logo (falls back to the ORG abbreviation chip)."""
    if not org:
        return ""
    o = html.escape(org)
    slug = ESPN_SLUGS.get(org, org.lower())
    return (f'<img class="row-logo" src="https://a.espncdn.com/i/teamlogos/mlb/500/{slug}.png" alt="{o}" loading="lazy" '
            f"onerror=\"this.outerHTML='<span class=&quot;row-logo&quot; style=&quot;font:700 9px var(--font-retro-mono);display:inline-flex;align-items:center;justify-content:center&quot;>{o}</span>'\">")

def _fv_label(p: dict) -> str:
    pts = p.get("points") or []
    if pts and pts[-1].get("consensus_fv_label") is not None:
        return str(pts[-1]["consensus_fv_label"])
    fv = p.get("fv_close")
    return str(round(fv)) if fv is not None else "—"

def _fv_pill(p: dict) -> str:
    fv = p.get("fv_close")
    cls = "fv-pill"
    if fv is not None and fv >= 61:
        cls += " holo"
    elif fv is not None and fv >= 60:
        cls += " gold"
    return f'<span class="{cls}">{html.escape(_fv_label(p))}</span>'

def _meta(*parts) -> str:
    return html.escape(" · ".join(str(x) for x in parts if x))

def _row_mover(p: dict) -> str:
    s = p.get("stock") or {}
    d = s.get("delta") or 0
    up = d > 0
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"), p.get("org"))}</span>'
            f'<span class="row-delta {"up" if up else "down"}">{"▲" if up else "▼"} {"+" if up else ""}{d:.0f}</span></a>')

def _row_top(p: dict, rank: int) -> str:
    return (f'<a class="row-link" href="{_player_href(p.get("player_key"))}">'
            f'<span class="row-rank">{rank}</span>{_team_logo(p.get("org"))}'
            f'<span class="row-name">{html.escape(p.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(p.get("position"))}</span>{_fv_pill(p)}</a>')

def _row_grad(g: dict) -> str:
    wag = ((g.get("debuted_value") or {}).get("wag") or {}).get("regressed_wag")
    if wag is not None:
        wtxt = f'<span class="row-delta {"up" if wag >= 0 else "down"}">{"+" if wag >= 0 else ""}{wag:.1f} WAG</span>'
    else:
        wtxt = '<span class="row-meta">debut</span>'
    return (f'<a class="row-link" href="{_player_href(g.get("player_key"))}">'
            f'{_team_logo(g.get("org"))}<span class="row-name">{html.escape(g.get("player_name") or "")}</span>'
            f'<span class="row-meta">{_meta(g.get("position"), g.get("org"))}</span>{wtxt}</a>')

def _row_farm(o: dict, rank: int) -> str:
    grade = (o.get("grades") or {}).get("overall") or "—"
    gcls = " gold" if str(grade).startswith("A") else ""
    name = ORG_NAMES.get(o.get("org"), o.get("org") or "—")
    return (f'<a class="row-link" href="/prospx/#farm-org={html.escape(o.get("org") or "")}">'
            f'<span class="row-rank">{rank}</span>{_team_logo(o.get("org"))}'
            f'<span class="row-name">{html.escape(name)}</span>'
            f'<span class="row-meta">{o.get("count", "")} prospects</span>'
            f'<span class="fv-pill{gcls}">{html.escape(str(grade))}</span></a>')

def _collect_events(players: list, graduates: list) -> list:
    ev = []
    def add(dt, typ, glyph, text, key):
        if dt:
            ev.append((str(dt)[:10], typ, glyph, text, key))
    for p in players:
        nm = p.get("player_name") or ""
        key = p.get("player_key")
        s = p.get("stock") or {}
        if s.get("delta") is not None and abs(s["delta"]) >= 3 and s.get("direction") not in ("flat", "debuted"):
            up = s["delta"] > 0
            add(s.get("to_date"), "up" if up else "down", "▲" if up else "▼",
                f'{nm} {"▲" if up else "▼"} {"+" if up else ""}{s["delta"]:.0f} FV', key)
        for lc in (p.get("level_changes") or []):
            if lc.get("kind") in ("promotion", "demotion"):
                promo = lc["kind"] == "promotion"
                add(lc.get("date"), "promo", "↑" if promo else "↓",
                    f'{nm} {"promoted" if promo else "demoted"} {lc.get("from_level", "?")}→{lc.get("to_level", "?")}', key)
        for tr in (p.get("trades") or []):
            add(tr.get("trade_date"), "trade", "⇄", f'{nm} traded {tr.get("from_org", "?")}→{tr.get("to_org", "?")}', key)
        il = p.get("il_status") or {}
        if il.get("is_on_il") and il.get("since"):
            add(il.get("since"), "il", "✚", f'{nm} to {il.get("type", "")} IL'.replace("  ", " "), key)
    for g in graduates:
        add(g.get("debut_date"), "debut", "★", f'{g.get("player_name", "")} debuted · {g.get("org", "")}', g.get("player_key"))
    ev.sort(key=lambda e: e[0], reverse=True)
    return ev

def _feed_html(events: list, n: int = 12) -> str:
    out = []
    for dt, typ, glyph, text, key in events[:n]:
        ts = f"{dt[5:7]}/{dt[8:10]}" if len(dt) >= 10 else dt
        out.append(f'<a class="feed-item" href="{_player_href(key)}"><span class="ts">{ts}</span>'
                   f'<span class="g {typ}">{glyph}</span>{html.escape(text)}</a>')
    return "".join(out)

def _ticker_html(events: list, n: int = 14) -> str:
    items = []
    for dt, typ, glyph, text, key in events[:n]:
        cls = typ if typ in ("up", "down") else "glyph"
        items.append(f'<span><span class="{cls}">{glyph}</span> {html.escape(text)}</span>')
    if not items:
        items = ['<span><span class="glyph">◆</span> PROSPX — live prospect wire</span>']
    return " ".join(items * 2)  # duplicated for seamless scroll

def _fv_sparkline(points: list, color: str) -> str:
    vals = [pt.get("consensus_fv_raw") for pt in (points or []) if pt.get("consensus_fv_raw") is not None]
    if len(vals) < 2:
        return ""
    w, h = 150, 34
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1
    step = w / (len(vals) - 1)
    pts = " ".join(f"{i*step:.1f},{h-2-((v-lo)/span)*(h-4):.1f}" for i, v in enumerate(vals))
    return (f'<svg viewBox="0 0 {w} {h}" style="width:100%;height:{h}px;display:block;">'
            f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="2" '
            'stroke-linejoin="round" stroke-linecap="round"/></svg>')

def _spotlight_html(players: list) -> str:
    # Biggest riser with FV history — rendered as a baseball card.
    cands = [p for p in players if (p.get("stock") or {}).get("delta") is not None]
    cands = [p for p in cands if (p["stock"].get("direction") not in ("flat", "debuted"))]
    if not cands:
        return ""
    p = max(cands, key=lambda x: x["stock"]["delta"])
    if p["stock"]["delta"] <= 0:
        return ""
    fv = p.get("fv_close")
    holo = " holo" if (fv is not None and fv >= 61) else ""
    mlbam = p.get("mlbam_id")
    photo = ""
    if mlbam:
        url = (f"https://img.mlbstatic.com/mlb-photos/image/upload/"
               f"d_people:generic:headshot:67:current.png/w_180,q_auto:best/v1/people/{mlbam}/headshot/67/current")
        photo = f'background-image:url(\'{url}\');'
    spark = _fv_sparkline(p.get("points"), "var(--accent-green)")
    d = p["stock"]["delta"]
    return (
        '<div class="sb-group"><div class="sb-group-label">Spotlight — Top Riser</div>'
        f'<a class="spotlight{holo}" href="{_player_href(p.get("player_key"))}" style="text-decoration:none;color:inherit;">'
        f'<div class="sp-photo" style="{photo}"></div>'
        '<div style="flex:1;min-width:0;display:flex;flex-direction:column;justify-content:center;gap:2px;">'
        f'<div class="sp-name">{html.escape(p.get("player_name") or "")}</div>'
        f'<div class="sp-meta">{_meta(p.get("position"), p.get("org"))}</div>'
        f'<div style="display:flex;align-items:center;gap:8px;margin-top:4px;">{_fv_pill(p)}'
        f'<span class="row-delta up" style="font-family:var(--font-retro-mono);font-size:12px;">▲ +{d:.0f} FV</span></div>'
        f'{spark}</div></a></div>'
    )

_GLOSSARY_TERMS = [
    ("DvM+", "development vs. mean"),
    ("Sur+", "FV-implied surplus value"),
    ("RPS+", "rate performance vs. same-age peers"),
    ("SC+", "Statcast composite"),
    ("WAG", "WAR above grade"),
    ("Tool+", "20–80 tool composite"),
]

def page_home(title: str, inner: str, description: str = "") -> str:
    desc = html.escape(description or "eephus.io — baseball prospect analytics")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
{THEME_INIT}
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{desc}">
<link rel="stylesheet" href="/assets/site.css">
</head>
<body class="eephus-page eephus-home">
{inner}
<footer class="eephus-footer">
  <span>eephus.io — editorial baseball analytics</span>
  <span>© {date.today().year} eephus.io</span>
</footer>
</body>
</html>
"""

def _home_module(kicker: str, see_all_href: str, see_all: str, body: str, full: bool = False) -> str:
    head = (f'<div class="kicker"><h2>{html.escape(kicker)}</h2>'
            f'<a class="see-all" href="{see_all_href}">{html.escape(see_all)} →</a></div>')
    return f'<section class="home-module{" full" if full else ""}">{head}{body}</section>'

def build_home(articles: list[dict], data: dict | None = None) -> str:
    """Homepage = sidebar + newspaper-style main, with live PROSPX modules + a
    prospect wire feed read from the build-time data layer."""
    data = data or {}
    players = data.get("players") or []
    org_summary = data.get("org_summary") or []
    graduates = data.get("graduates") or []
    as_of = data.get("as_of", "—")
    today = datetime.now().strftime("%A, %B %d, %Y").replace(" 0", " ")
    events = _collect_events(players, graduates)

    # ---- sidebar ----
    nav = []
    for key, label, href in NAV_ITEMS:
        cls = ' class="is-active"' if key == "home" else ""
        nav.append(f'<a href="{href}"{cls}>{html.escape(label)}</a>')
    sub = "".join(f'<a href="{href}"><span class="px-glyph">›</span>{html.escape(label)}</a>'
                  for label, href in PROSPX_SUBNAV)
    feed = _feed_html(events, 12) or '<div class="feed-item" style="color:#6f8a76;">No recent activity.</div>'
    spotlight = _spotlight_html(players)
    search = ('<input class="sb-search" type="search" placeholder="Search prospects…" aria-label="Search prospects" '
              "onkeydown=\"if(event.key==='Enter'&&this.value.trim()){location.href='/prospx/#q='+encodeURIComponent(this.value.trim());}\">")
    sidebar = (
        '<aside class="home-sidebar">'
        f'<div class="sb-brand"><a class="wm" href="/">eephus.io</a>{THEME_BTN}</div>'
        f'{search}'
        f'<div class="sb-group"><div class="sb-group-label">Sections</div><nav class="sb-nav">{"".join(nav)}</nav></div>'
        f'<div class="sb-group"><div class="sb-group-label">PROSPX</div><nav class="sb-subnav">{sub}</nav></div>'
        f'{spotlight}'
        f'<div class="sb-group"><div class="sb-feed"><div class="feed-head"><span class="blip"></span>Prospect Wire</div>{feed}</div></div>'
        '</aside>'
    )

    # ---- top wire ticker ----
    ticker = (f'<div class="home-ticker"><span class="ticker-tag"><span class="blip"></span>Wire</span>'
              f'<div class="ticker-track">{_ticker_html(events)}</div></div>')

    # ---- masthead ----
    masthead = (
        '<div class="masthead"><h1 class="nameplate">eephus<span class="dot">.io</span></h1>'
        '<div class="dateline"><span>Baseball Prospect Analytics</span>'
        f'<span>{html.escape(today)}</span><span>Data as of {html.escape(as_of)}</span></div></div>'
    )

    # ---- lead story (latest article) + secondary ----
    latest = articles[0] if articles else None
    if latest:
        lead = (
            '<article class="lead-story no-img">'
            '<div><div class="lead-kicker">Latest</div>'
            f'<h1>{html.escape(latest["title"])}</h1>'
            f'<div class="byline">{_byline(latest, link_handle=False)}</div>'
            f'<p class="excerpt">{html.escape(latest.get("summary", ""))}</p>'
            f'<a class="read" href="/articles/{latest["slug"]}/">Read the full story →</a></div>'
            '</article>'
        )
    else:
        lead = '<article class="lead-story no-img"><div><div class="lead-kicker">Latest</div><h1>No articles yet</h1></div></article>'
    sec = articles[1:4]
    secondary = ('<div class="secondary-stories">' + "".join(
        f'<a href="/articles/{a["slug"]}/"><div class="s-kicker">{html.escape(a.get("date_disp", ""))}</div>'
        f'<h3>{html.escape(a["title"])}</h3></a>' for a in sec) + '</div>') if sec else ""

    # ---- live PROSPX modules ----
    mv = [p for p in players if (p.get("stock") or {}).get("delta") is not None
          and (p["stock"].get("direction") not in ("flat", "debuted")) and abs(p["stock"]["delta"]) >= 1.5]
    risers = sorted((p for p in mv if p["stock"]["delta"] > 0), key=lambda p: -p["stock"]["delta"])[:5]
    fallers = sorted((p for p in mv if p["stock"]["delta"] < 0), key=lambda p: p["stock"]["delta"])[:4]
    movers_body = "".join(_row_mover(p) for p in risers + fallers)
    movers = _home_module("Top Movers", "/prospx/#tab=spotlights", "All movers", movers_body) if movers_body else ""

    topN = sorted(players, key=lambda p: (p.get("fv_close") if p.get("fv_close") is not None else -1), reverse=True)[:8]
    top_body = "".join(_row_top(p, p.get("overall_rank") or i) for i, p in enumerate(topN, 1))
    topp = _home_module("Top Prospects", "/prospx/", "Full board", top_body) if top_body else ""

    gr = sorted((g for g in graduates if g.get("debut_date")), key=lambda g: g["debut_date"], reverse=True)[:6]
    grad_body = "".join(_row_grad(g) for g in gr)
    grads = _home_module("Recent Graduates", "/prospx/#tab=debuts", "All graduates", grad_body) if grad_body else ""

    fm = sorted((o for o in org_summary if o.get("farm_rank")), key=lambda o: o["farm_rank"])[:4]
    farm_body = "".join(_row_farm(o, o.get("farm_rank") or i) for i, o in enumerate(fm, 1))
    farm = _home_module("Farm Spotlight", "/prospx/#tab=farm", "Farm systems", farm_body) if farm_body else ""

    term, defn = _GLOSSARY_TERMS[datetime.now().timetuple().tm_yday % len(_GLOSSARY_TERMS)]
    glossary = (f'<div class="glossary-teaser"><span>Today\'s term: <strong>{html.escape(term)}</strong> — {html.escape(defn)}</span>'
                f'<a href="/prospx/#tab=glossary">Glossary →</a></div>')

    main = (
        '<main class="home-main">'
        f'{masthead}{lead}{secondary}'
        f'<div class="module-cols">{movers}{topp}{grads}{farm}</div>'
        f'{glossary}'
        '</main>'
    )
    inner = f'{ticker}<div class="home-shell">{sidebar}{main}</div>'
    return page_home("eephus.io — baseball prospect analytics", inner,
                     "Live MiLB prospect movers, top prospects, graduates, and analysis.")

def build_articles_index(articles: list[dict]) -> str:
    cards = []
    for a in articles:
        excerpt = html.escape(a.get("summary", ""))
        cards.append(
            f'<a class="card article-card" href="/articles/{a["slug"]}/">'
            '<div class="eyebrow">Article</div>'
            f'<p class="meta">{_byline(a, link_handle=False)}</p>'
            f'<h3>{html.escape(a["title"])}</h3>'
            f"<p>{excerpt}</p>"
            '<span class="card-cta">Read →</span></a>'
        )
    grid = "".join(cards) or '<p>No articles yet.</p>'
    body = (
        '<div class="section-head"><h1>Articles</h1></div>'
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
        # Optional subtle note (only Noah gets "PROSPX Creator") — small mono pill.
        note_html = (
            f'<p class="team-note">{html.escape(m["note"])}</p>' if m.get("note") else ""
        )
        cards.append(
            f'<div class="card team-card"><p class="name">{html.escape(m["name"])}</p>{note_html}{handle_html}</div>'
        )
    body = (
        '<div class="section-head"><h1>Development Team</h1></div>'
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

    data = load_site_data()
    print("  data layer:", "loaded" if data else "MISSING (run run_monthly) — modules will be empty")

    _write("index.html", build_home(articles, data))
    _write("articles/index.html", build_articles_index(articles))
    for a in articles:
        _write(f"articles/{a['slug']}/index.html", build_article_page(a))
    _write("team/index.html", build_team())
    print(f"done — {len(articles)} article(s).")

if __name__ == "__main__":
    main()
