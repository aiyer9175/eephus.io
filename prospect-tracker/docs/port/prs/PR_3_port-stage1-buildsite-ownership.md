# PR 3: port-stage1-buildsite-ownership

**Branch:** `port-stage1-buildsite-ownership` (stacked on PR 2). **Commit:** 3eac0ba. **Target:** `main` after PR 2.

## What

- `internal/site/ownership.go`: `LoadOwnership(root)` reads the pin's `owned` list into an `Ownership` (`"prospx/"` owns a directory, `"index.html"` a file); `Owns(rel)`; a root with no pin owns nothing; a pin that will not parse or names a path outside the root is an error.
- `internal/site/build.go`: `site.Run` consults it before every page. An owned page is neither written nor rendered (the home page's render keeps the wire ledger as a side effect). `Result.Skipped` counts them; `cmd/buildsite` logs the count. `rewriteAssetVersions` leaves an owned hand-authored page as the bundle shipped it (`RewriteAssetVersions(root)` keeps its signature).
- Tests: `ownership_test.go` (parser, `Owns`, a `Run` against a temporary root with a pin, a `Run` without one, and the committed pin owning every shell and Stage 1 page while not claiming the data layer). The existing comparisons of a generated page with its committed copy (`TestShellsMatchThePublishedPages`, the footer read off `fantasy/`, the team page, the article rendering, the hand-maintained nav copies) skip a page the bundle owns, naming the pin in the skip reason; removing a page's entry in Stage 2 turns its comparison back on with no test change.

## Why

With the bundle published through `publish.sh`, `cmd/buildsite` and the bundle were two writers of the same files: `buildsite` runs at every publish and rewrote the shells, home, news, articles, `team/`, `teams/`, `robots.txt` and `sitemap.xml` to this tree's markup and this Build's numbers, and re-stamped the hand-authored pages' `?v=` queries; the bundle's copies then took the webroot back at the rsync. The pin makes ownership explicit and gives Stage 2 its mechanism: a page comes back to this generator by deleting one line.

## How verified

```
gofmt -l ./internal/site ./cmd/buildsite      (clean)
go test ./internal/site/ ./cmd/buildsite/
ok      git.btq.ee/eephus/eephus-backend/internal/site  1.891s
ok      git.btq.ee/eephus/eephus-backend/cmd/buildsite  1.603s
```

With `-v`: `TestRunSkipsBundleOwnedPages`, `TestRunWithoutAPinWritesEverything`, `TestOwnership*` and `TestCommittedPinOwnsTheStageOnePages` PASS; `TestArticleRenderingMatchesTheReference`, `TestShellsMatchThePublishedPages`, `TestFooterMatchesTheNewestPublishedPage`, `TestTeamPageMatchesThePublishedPage` and `TestStaticNavCopiesMirrorTheCanonicalNav` SKIP as bundle-owned. GOOS=linux `go build ./...` and `go vet ./...` exit 0 (`verify/port-stage1-buildsite-ownership.txt`).

## A note on what the skips mean

At Stage 1 the bundle owns every page, so the five comparisons are vacuous until Stage 2. That is the honest state: the generator's output for those pages is not published. The ownership test asserts the opposite direction (owned pages are not written) so the mechanism itself is under test.
