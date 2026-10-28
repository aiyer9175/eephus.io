"""SITE_AUDIT_3C (2026-10-27): the pre-port audit's lens C fixes, pinned.

Each test names the finding it guards. They read the served sources as text,
so they run without a browser and without the data files.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PROSPX = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")


def _fn_body(src: str, head: str) -> str:
    """The text of one top-level function, from its header to the next
    column-zero closing brace."""
    i = src.index(head)
    j = src.index("\n}\n", i)
    return src[i:j]


def test_the_prospx_boot_probe_reads_one_chunk_and_cancels():
    """C1: loadData() probes timeseries.json with a Range header for its
    generated_at stamp and then fetches the ?v=-keyed payload. A host that
    answers the Range request with 200 (python http.server; nginx gzipping on
    the fly) streamed the whole 87 MB payload into probeResp.text() first, so
    the file crossed the wire twice per visit. The probe now reads the first
    chunk from the body stream and cancels the rest."""
    body = _fn_body(PROSPX, "async function loadData() {")
    probe = body.split("const probeResp = await fetch(DATA_URL", 1)[1]
    probe = probe.split("const url = cacheVersion", 1)[0]
    assert 'Range: "bytes=0-2048"' in probe
    assert "probeResp.body.getReader()" in probe
    assert "reader.cancel()" in probe
    assert 'head.match(/"generated_at"' in probe
    # the whole-body read survives only as the fallback for a body-less Response
    code = "\n".join(l for l in probe.splitlines() if not l.strip().startswith("//"))
    assert code.count("probeResp.text()") == 1
    assert re.search(r"\} else \{\s*head = await probeResp\.text\(\);", code)


def test_the_bare_timeseries_preload_stays_retired():
    """The v35 note above the stylesheet links explains why no bare-URL
    preload of the boot payload may come back: it is the same double
    download the probe fix closes."""
    head = PROSPX.split("</head>", 1)[0]
    head = re.sub(r"<!--.*?-->", "", head, flags=re.S)   # the note quotes the old tag
    tags = re.findall(r"<link\b[^>]*rel=\"preload\"[^>]*>", head)
    assert not any("timeseries.json" in t for t in tags), tags


def test_every_ledger_expand_column_header_has_a_name():
    """C3: the league board and four club tables end each header row with an
    empty <th> over the 'Show detail' button column; a screen reader read it
    as a blank column header. Every such cell now carries aria-label."""
    js = (ROOT / "assets" / "ledger.js").read_text(encoding="utf-8")
    cells = re.findall(r"<th[^>]*class=\"(?:lb|lc)-xp\"[^>]*>", js)
    assert len(cells) >= 5, cells
    for c in cells:
        assert 'aria-label="Row detail"' in c, c
