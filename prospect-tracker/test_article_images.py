# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Article image weight (bloat finding AS15, 2026-10-03).

Inline article images carry their intrinsic width and height (read from the
PNG header, so the page reserves the box and does not shift), plus
loading="lazy" and decoding="async"; the per-article share card is the
1200 x 630 OG size, not twice it. Checked on the renderer and on the
committed article pages.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PIL import Image

import build_site as B

ROOT = Path(__file__).parent
ARTICLE_PAGES = sorted((ROOT / "articles").glob("*/index.html"))
IMG = re.compile(r"<img\b[^>]*>", re.I)


def test_png_size_reads_the_header(tmp_path):
    p = tmp_path / "x.png"
    Image.new("RGB", (37, 11)).save(p)
    assert B._png_size(p) == (37, 11)
    (tmp_path / "y.png").write_bytes(b"not a png")
    assert B._png_size(tmp_path / "y.png") is None


def test_renderer_sizes_local_pngs_and_leaves_the_rest_alone():
    rel = "assets/articles/shortstops-galore-why-mlb-teams-love-ss/01-sandy-leon.png"
    w, h = Image.open(ROOT / rel).size
    html = B._size_article_images(B.render_markdown(
        f"![a](/{rel})\n\n![b](https://example.com/x.png)\n\n![c](/assets/missing.png)\n"))
    tags = IMG.findall(html)
    assert f'width="{w}" height="{h}" loading="lazy" decoding="async"' in tags[0]
    assert "width=" not in tags[1] and "width=" not in tags[2]
    assert B._size_article_images(tags[0]) == tags[0], "a sized tag must not be sized twice"


@pytest.mark.parametrize("page", ARTICLE_PAGES, ids=lambda p: p.parent.name)
def test_every_inline_article_image_is_sized_and_lazy(page):
    body = page.read_text(encoding="utf-8")
    body = body[body.index('<div class="article-body">'):]
    tags = IMG.findall(body[:body.index("</article>")])
    for tag in tags:
        src = re.search(r'src="(/assets/[^"]+\.png)"', tag)
        if not src:
            continue
        w, h = Image.open(ROOT / src.group(1).lstrip("/")).size
        assert f'width="{w}"' in tag and f'height="{h}"' in tag, tag
        assert 'loading="lazy"' in tag and 'decoding="async"' in tag, tag


@pytest.mark.parametrize("card", sorted((ROOT / "assets" / "articles").glob("*/share-card.png")),
                         ids=lambda p: p.parent.name)
def test_article_share_cards_are_og_size(card):
    assert Image.open(card).size == (1200, 630)
