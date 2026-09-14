# One-time Notion game-history import

This procedure imports the 2020 and 2021 ESPN matchup rows into PostgreSQL.
It does not import or activate PTGOTW behavior. `WasPTGOTW` and `Winner` are
retained only in the matchup's source metadata for audit purposes.

After a successful import, PostgreSQL is authoritative. There is no scheduled
or automatic Notion synchronization.

## Required environment variables

Set these values only in `.env`, which is ignored by Git:

```dotenv
NOTION_API_TOKEN=your-read-only-integration-token
NOTION_GAME_HISTORY_DATA_SOURCE_ID=
NOTION_GAME_HISTORY_DATABASE_ID=your-game-history-database-container-id
NOTION_API_VERSION=2026-03-11
NOTION_TIMEOUT_SECONDS=20
```

Set exactly one of the two ID variables:

- `NOTION_GAME_HISTORY_DATA_SOURCE_ID` is preferred when you copied the data
  source ID from Notion.
- `NOTION_GAME_HISTORY_DATABASE_ID` accepts the database/container ID formerly
  stored as `GAME_HISTORY_PAGE_ID`. BTB retrieves that container and resolves
  its single child data source. If it contains multiple data sources, set the
  explicit data-source ID instead.

The integration needs read-content access, and the Game History database must
be shared with it. BTB uses Notion's current
[`/v1/data_sources/{id}/query`](https://developers.notion.com/reference/query-a-data-source)
API and follows every pagination cursor.

Never copy the old repository's token into source code, terminal output,
screenshots, or support messages.

## Exact import procedure

1. Back up the BTB PostgreSQL database.
2. In **Admin → League history**, verify that 2020 and 2021 exist and both use
   the ESPN platform with no Sleeper league ID.
3. Create permanent Manager records for every person in those seasons. Former
   managers such as Tim and Pete do not need BTB login accounts.
4. Add a `Notion name` alias for every spelling found in `Team1Name` and
   `Team2Name`. Aliases are matched case-insensitively after whitespace is
   normalized.
5. Create a read-only Notion integration, share the Game History database with
   it, set the environment variables above, and restart the API.
6. Sign in to BTB as an administrator and open **Admin → League history →
   Imports**.
7. Select **Dry run** and review the validation report shown on the page.

8. Do not continue unless `status` is `succeeded`, every expected row appears
   under `rows_per_season`, and `unresolved_names`, `duplicate_rows`, and
   `invalid_records` are empty. Fix manager aliases or the Notion rows, restart
   only if environment settings changed, and repeat the dry run.
9. Select **Import 2020–2021**, review the confirmation, and run the import.

10. Verify that the result is `succeeded` and review the 2020 and 2021 matchup
    totals. Repeating the operation is safe: existing logical matchups are
    updated instead of duplicated, and every attempt is retained in
    `league_import_runs`.
11. Remove `NOTION_API_TOKEN` and both Notion ID values from `.env`, then
    restart the API. You may also revoke the temporary Notion integration.

The commit operation is atomic. Any unresolved name, malformed record,
duplicate logical matchup, missing ESPN season, or incorrectly configured
season produces `needs_attention` and commits no league-history rows. The
`ImportRun` audit record is still retained.
