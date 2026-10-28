# PR 8: port-stage3-shadow-gates

**Branch:** `port-stage3-shadow-gates` (stacked on PR 7). **Commit:** e14d10d. **Target:** `main` after PR 7.

## What

- `deploy/shadow_gates.tsv`, registered 2026-10-27: 20 rows over 10 modules your Go models produce and the bundle also carries (consensus FV; eFV grade and six-year WAR; surplus; the hitter, starter and bullpen boards' plus stats and WAR; the projections' WAR and NPV; the trade machine's values; PAL fit; fantasy points; Swing+; aStuff+). Each row names the JSON route, the bundle file it replaced, the row container and key, the field, the rule and the floor. `round:N` and `ceil:N` compare values as the producer's pages print them (Math.round half up; Math.ceil for FV grades), `exact` the JSON values where no display rule is cited yet, `abs:X` an absolute difference. Every floor is 1.
- `internal/shadow` and `cmd/shadoweq`: ask a shadow server (`cmd/server` without `-bundle-dir`, on a loopback address) for each route, or read a saved dump with `-challenger-dir`; compare with the bundle's file; print and write a report: per module PASS, FAIL or NOT RUN, row coverage both ways, per field the rows compared and agreeing, the largest difference and five disagreeing rows by key.
- Refusals: an answer with `X-Eephus-Source: bundle` (that server is serving the producer's file, and the comparison would pass by construction); a report path inside the bundle (it would become an unlisted file the next verify rejects) or under the webroot.
- README section "The shadow challengers (port Stage 3)".

## Why

Owner decision PORT-R4: your Go models keep running and serve nothing; each takes its module over only after a pre-registered equivalence gate passes and the schema-level as-of accessor (PR 9) is in the store. This is the gate's registration and its measuring tool. The table changes only by PR and before a run reads it; every report records its sha256.

## How verified

```
go test -count=1 -v ./internal/shadow/
--- PASS: TestRulesAgreeAsThePagePrints
--- PASS: TestTheCommittedTableParsesAndIsConsistent
--- PASS: TestTableRefusals
--- PASS: TestRunPassesTheSameRecoversAPlantDigitAndFailsANullChallenger
--- PASS: TestHTTPSourceRefusesTheBundleAndReadsTheShadowServer
--- PASS: TestRowsReportsDuplicateAndKeylessRows
ok      git.btq.ee/eephus/eephus-backend/internal/shadow
```

The run test is the planted-recovery and null-comparator check: the champion against itself passes; a change no page prints (47.4 to 46.6) passes; a change of a printed digit (47.4 to 47.6) fails and names the row; a null for a number, a different row set and a swapped two-way row fail; an empty challenger fails; a missing file is NOT RUN.

On the rehearsal bundle (`verify/stage3_shadow_rehearsal.txt`): the bundle against itself, 10 PASS, 0 FAIL, 0 NOT RUN (9,515 eFV rows, 6,316 trade values, every row agreeing). With this repository's committed `frontend/data` as a stand-in challenger (no Build Target on the preparing PC): 0 PASS, 8 FAIL, 2 NOT RUN, for example eFV grade 1,632 of 8,999 matched rows printing the same and 516 bundle rows absent. That stand-in is the July data, not your Build's answers: it rehearses the tool and says nothing about any model.

GOOS=linux `go build ./...` and `go vet ./...` exit 0 (`verify/port-stage3-shadow-gates.txt`).

## Asks

1. Run it once against your Build: `bin/server -addr 127.0.0.1:8081 -data-dir var &` then `bin/shadoweq -bundle /opt/eephus/artifacts/current/site -challenger http://127.0.0.1:8081 -out /var/lib/eephus/shadow/<date>.json`, and send the owner the report. Nothing is served or changed by it.
2. If a field's display rule in the table is wrong for how your templates print it, say so by PR before the first run; after a run has read the table, a changed rule is a new registration.
