# PR 6: port-stage1-pages

**Branch:** `port-stage1-pages` (stacked on PR 5). **Commit:** 03b5013. **Target:** `main` after PR 5. The large one: 190 files, 81,172 insertions, 11,283 deletions; 214 files and 84,925,966 bytes under the page paths after the change (CollegeSavant's embedded data modules are 69 MB of it).

## What

- Every page directory and root file named in `deploy/publish_paths.txt` replaced by the producer's copy at its commit 1a1bd74d (the bundle the pin references was built from it): 34 directories, 5 root files, 214 files. 128 text files rewritten from CRLF to LF to match every other blob here; binaries byte for byte. Each directory replaced whole, so a retired file does not linger.
- `frontend/teams/` deleted: the producer retired it on 2026-10-07 and the new `404.html` forwards `/teams/` to `/projections/#view=teams` through its redirect map; `robots.txt` no longer disallows it.
- The tracked set under the page paths equals the bundle manifest's 214 non-data rows exactly (checked by script). The bundle's copies additionally carry the producer's two publish-time comment strips (`prospx/index.html` 3,476,595 bytes here, 2,716,765 in the bundle); the producer's equivalence check reads CRLF as LF.

## The rebuild's frontend fixes, each considered against the static pages

| Fix | Decision | Why |
|---|---|---|
| Deep-link section highlight (a2e7597c) | **Applied**, in the producer's prospx first (its commit 1a1bd74d adds the same `SECTION_FOR_VIEW` table and else-branch, with its own comment), so this copy and the bundle agree byte for byte | Checked in headless Chromium against the producer's tree: `#farm-org=BAL` lights the farm section and round-trips to `farm-org=BAL&tab=farm`; an explicit tab still wins; zero page errors. |
| Lazy sparklines and infinite-scroll hydration (3b741c8f) | Not applicable | Both halves hang off htmx (`renderActives`' `htmx.ajax` promise, the `htmx:afterSwap` listener, the `.board-more` sentinel). The static board builds its rows inside `render()`'s synchronous body, where `observeLazyCharts` already runs after them, the case the commit itself names as unaffected. |
| Headshot crop and density (1dcac941, 29769051) | Not applicable | Both fix the Go templates' class-less `<img>` in the board, injured and transactions Fragments. The static rows carry the `.headshot` class and the CSS those fixes restored the rows to. |
| Org from the MLB register (2688d59c) | Not applicable to a page | A Build step (`materialize.go`); the producer resolves orgs in its own pipeline. |
| Home farm ranking (82876482) | Already true in the producer's generator | Its home module ranks on `org_summary`'s `farm_rank` and reads the same letter the PROSPX farm board shows (`build_site.py` `_row_farm`), one derivation for both surfaces, which is what that commit made `cmd/buildsite` do. With `index.html` bundle-owned, `cmd/buildsite` no longer writes the home page. |
| The headshot proxy (`/images/headshots/{mlbamID}`) | Kept available, not wired | The pages keep their `img.mlbstatic.com` URLs (face crops at the size each surface asks for) so they stay byte-identical to the producer's build. The owner's decision (PORT-R2) names the proxy as a permitted difference; switching a surface to it is a producer-side change plus one line in the equivalence check's explained list. The nginx `/images/` location stays. |

## The forums and account layer

`forums/index.html`, `eephus-account.js`, `eephus-account.css` and the blank `eephus-config.js` stub come back with the set (you removed them in d14a7f28). They are inert without a Supabase configuration, which this box does not have, and shipping them inert keeps the published site identical to the producer's. PORT-R2 names this layer as the other permitted difference: dropping it instead is one explained-list line on the producer's side and a deletion here. Your call; the owner has the same question on his side.

## How verified

```
go test -count=1 ./internal/site/
ok      git.btq.ee/eephus/eephus-backend/internal/site  3.103s
--- PASS: TestExcludedDataIsNotFetchedByAnyPage (2.26s)     scans the new pages against the 44-name list
--- PASS: TestExcludedDataIsNotARegistryArtifact
--- PASS: TestSitemapSurfacesAreShipped                     every advertised surface resolves against the new list
--- PASS: TestRobotsDoesNotBlockTheSitemap
--- PASS: TestCommittedPinOwnsTheStageOnePages
--- SKIP: the five generated-vs-committed page comparisons (bundle-owned)
```

GOOS=linux `go build ./...` and `go vet ./...` exit 0 (`verify/port-stage1-pages.txt`).

## Asks

- Review size: the diff is large because the pages are the producer's 2,434 commits since 71ea151. Reading it as "the published site's source now lives here" is the point; the per-page review is the producer's history.
- Push size: Cloudflare's 100 MB request cap applies to the push. The chain's objects compress well (the git bundle beside this file is the measure); if a single push is refused, push PR 1 to PR 5 first and PR 6 alone.
