"""End-to-end browser verification of every surface this program changed.

Tests and isolated harnesses proved each change in place. This proves the SITE
still works: real Chromium, real fetches, console errors captured, and a content
assertion per route so a page that loads blank fails instead of passing.

Deliberately NOT pytest: conftest git-restores tracked files dirtied during a
run. It imports conftest.serve_site only, which is a plain static server.
"""
import sys
import pathlib

ROOT = pathlib.Path(r"c:/Users/noah/baseball-projects/BaseballR/prospect-tracker")
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402
import conftest  # noqa: E402

# (route, what must be on screen for the page to count as working)
ROUTES = [
    ("/",                              ".spotlight, .home-module"),
    ("/prospx/",                       ".player-row"),
    ("/prospx/#tab=farm",              ".farm-row, .farm-card, .rd-card"),
    ("/fantasy/",                      ".fantasy-mod, .rd-card, tbody tr"),
    ("/fantasy/#m=dynasty",            ".fantasy-mod"),
    ("/fantasy/#m=dfs",                ".fantasy-mod"),
    ("/redraft/",                      "a[href*='/fantasy/']"),
    ("/dynasty/",                      "a[href*='/fantasy/']"),
    ("/dfs/",                          "a[href*='/fantasy/']"),
    ("/models/",                       ".dm-table, table, .acct-row, tbody tr"),
    ("/projections/",                  ".proj-card, .mlb-card"),
    ("/projections/#view=teams",       "tbody tr, .mlb-card"),
    ("/fa/",                           ".fa-card, .mlb-card"),
    ("/betting/",                      ".bt-pick, .bt-panel"),
    ("/cards/",                        ".section-sub, .card, tbody tr"),
    ("/pal/",                          "tbody tr, .pal-tier"),
    ("/glossary/",                     ".gl-app, .g-term, tbody tr"),
    ("/glossary/#view=methodology",    ".meth-table, .meth-chart"),
    ("/glossary/#view=models",         "tbody tr, .gl-model-row"),
    ("/mlbstats/",                     "tbody tr, .mlb-card"),
    ("/diamond/",                      ".diamond-card, .card"),
    ("/parks/",                        "tbody tr, table"),
    ("/trademachine/",                 ".tm-row, .card, tbody tr"),
]

IGNORE = ("favicon", "ERR_CONNECTION", "net::ERR_ABORTED", "player_news.json")


def main() -> int:
    results, failures = [], []
    with conftest.serve_site() as base:
        with sync_playwright() as p:
            br = p.chromium.launch()
            for width, label in ((1440, "desktop"), (390, "phone")):
                pg = br.new_page(viewport={"width": width, "height": 900})
                errs: list[str] = []
                pg.on("console", lambda m: errs.append(m.text)
                      if m.type == "error" and not any(s in m.text for s in IGNORE) else None)
                pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
                for route, sel in ROUTES:
                    errs.clear()
                    try:
                        pg.goto(base + route, wait_until="networkidle", timeout=45000)
                        pg.wait_for_timeout(700)
                        found = pg.query_selector(sel) is not None
                        # a page must not scroll sideways
                        overflow = pg.evaluate(
                            "Math.max(0, document.documentElement.scrollWidth"
                            " - document.documentElement.clientWidth)")
                    except Exception as exc:  # noqa: BLE001
                        failures.append(f"{label} {route}: LOAD FAILED {exc}")
                        continue
                    bad = list(errs)
                    if not found:
                        failures.append(f"{label} {route}: no content matching {sel!r}")
                    if bad:
                        failures.append(f"{label} {route}: {len(bad)} console error(s): {bad[:2]}")
                    if overflow > 2:
                        failures.append(f"{label} {route}: page scrolls sideways by {overflow}px")
                    results.append((label, route, found, len(bad), overflow))
                pg.close()
            br.close()

    print(f"{'view':8s} {'route':34s} {'content':8s} {'errors':7s} {'hscroll'}")
    for label, route, found, nerr, ov in results:
        print(f"{label:8s} {route:34s} {'OK' if found else 'MISSING':8s} "
              f"{nerr:<7d} {ov}")
    print()
    if failures:
        print(f"=== {len(failures)} FAILURE(S) ===")
        for f in failures:
            print(" ", f)
        return 1
    print(f"ALL {len(results)} route-checks CLEAN "
          f"({len(ROUTES)} routes x 2 viewports)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
