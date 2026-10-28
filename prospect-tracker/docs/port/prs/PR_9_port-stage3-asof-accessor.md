# PR 9: port-stage3-asof-accessor

**Branch:** `port-stage3-asof-accessor` (stacked on PR 8). **Commit:** 64b78aa. **Target:** `main` after PR 8.

## What

- `internal/asof`: `asof.Open(ctx, db, cutoff, asof.Tables)` returns a Reader on one connection that sees the Build Target as known strictly before the cutoff day. For every table it creates a `TEMP VIEW` with the table's own name; SQLite resolves an unqualified name in the temp schema first, so a model's unchanged query reads only rows known before the cutoff. The connection is set `query_only`, and the Reader refuses a statement that names a schema (`main.`, `temp.`), attaches or sets a pragma. The views live on that connection only.
- `internal/asof/tables.go` classifies all 57 tables of `internal/store`'s schema: 11 Observed (a knowledge date), 21 Seasonal (seasons before the cutoff's year), 2 Reference (with reasons), 23 Unversioned (an empty view whose only column is `asof_refused`, so naming a real column fails). The Unversioned set includes every model output and the identity registers that carry a debut (`resolved_ids.mlb_debut_date`, `chadwick_people.mlb_first`).
- `asof.Readiness(asof.Tables, inputs...)` names the inputs of a model that cannot be read as of a date.
- `docs/AS_OF_ACCESSOR.md`: the problem, the mechanism, the classes, the migration that makes an Unversioned table readable (`known_at`, history kept, a live-Build view), and the takeover entry condition.

## Why

Leakage control here is each model's own code (`efvdata.AsOfPoint`, `efvproxy`, the label and norms); no table carries a knowledge time, and a query that forgets its filter fails nothing. PORT-R4 makes a schema-level accessor an entry condition for any takeover. `TestEveryStoreTableIsClassified` builds an empty Build Target with the store's own schema and fails when a table has no class, a registered column is absent, or the registry names a table the store no longer has: a `CREATE TABLE` added without a decision about its knowledge time fails `go test`, which `publish.sh` runs before every publish.

## How verified

```
go test -count=1 -v ./internal/asof/
    asof_test.go:63: 57 tables: 11 observed, 21 seasonal, 2 reference, 23 unversioned
--- PASS: TestEveryStoreTableIsClassified
--- PASS: TestOpenOnTheRealSchema
--- PASS: TestAnAsOfConnectionSeesOnlyWhatWasKnown
--- PASS: TestOpenRefusesASchemaItCannotVouchFor
--- PASS: TestReadinessNamesTheInputsThatCannotBeReadAsOfADate
ok      git.btq.ee/eephus/eephus-backend/internal/asof
```

The fixture shows the point published on the cutoff day excluded, a late timestamp the day before included, an undated row never shown, the season in progress hidden, an Unversioned table empty with its debut column unreadable, a join through two views, six bypass statements and an insert refused, and another pool connection still reading every row. GOOS=linux `go build ./...` and `go vet ./...` exit 0 (`verify/port-stage3-asof-accessor.txt`).

## Asks

1. Review the classification in `tables.go`; a table you know to carry a better knowledge column than the one named, or to be safe to read as Reference, is a one-line change with its reason.
2. Nothing reads through the accessor yet. A model that wants to take a module over moves its inputs onto it first (the design's takeover condition 3); the migration of an Unversioned table it reads comes with that PR.
