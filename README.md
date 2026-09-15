# BTB League Website

BTB is a private, homelab-friendly website for one fantasy football league. It combines weekly prediction games with a separate, authenticated league-history archive backed by PostgreSQL.

## Included

- Admin-created BTB accounts with `user` and `admin` roles
- Commissioner-generated account passwords, self-service password changes, and Argon2 hashing
- BTB-wide `Season` model and reusable Sleeper service
- Six-matchup prediction cards with editable picks until lock
- Full Sleeper starters and benches with player and team images, names, positions, teams, injuries, and weekly points
- Private picks before lock, shared picks afterward
- Automatic win/loss/push scoring; blank picks score as losses
- Weekly records, standings, history, and champions
- Admin refresh, finalize, and recalculate endpoints
- Database-backed recurring tasks with execution history and safe retry leases
- Automatic prediction-week refresh and finalization every Tuesday at 7:00 AM Central
- PostgreSQL persistence, Alembic migrations, and Docker Compose
- Permanent manager profiles that survive team-name changes and do not require BTB login accounts
- ESPN-era matchup history for 2020–2021 through a one-time Notion import
- Idempotent Sleeper history imports for teams, matchups, placements, trades, waivers, free agents, picks, and FAAB
- Public league overview, teams, seasons, records, trades, and waiver-wire pages for authenticated members
- Commissioner-managed placements, punishments, custom facts, identity aliases, and manual weekly-highlight corrections

## Architecture

```text
app/, components/                 BTB web interface and routes
backend/app/auth/                 shared authentication
backend/app/core/                 configuration and security
backend/app/database/             shared PostgreSQL session/base
backend/app/models/               BTB-wide User and Season models
backend/app/services/sleeper/     reusable Sleeper adapter
backend/app/services/notion/      read-only one-time Notion adapter
backend/app/features/predictions/ prediction API, models and scoring
backend/app/features/league_history/ league archive, imports and statistics
backend/app/tasks/                recurring-task registry, runner, and worker
backend/alembic/                  database migrations
```

Sleeper is the live source for current fantasy data and the import source for Sleeper-era seasons. Notion is used only once for the 2020–2021 ESPN Game History archive. PostgreSQL is authoritative for league-history pages after import, as well as accounts, predictions, corrections, and commissioner-entered history. League-history routes do not read prediction, PTGOTW, or poll tables.

## Run with Docker

1. Copy `.env.example` to `.env`.
2. Set `SLEEPER_LEAGUE_ID` to the numeric league ID from your Sleeper league URL.
3. Replace `POSTGRES_PASSWORD`, `SECRET_KEY`, and `BOOTSTRAP_ADMIN_PASSWORD` with long random values.
4. Run `docker compose up --build`.
5. Open `http://localhost:3000` and sign in using `BOOTSTRAP_ADMIN_USERNAME` (defaults to `admin`) and `BOOTSTRAP_ADMIN_PASSWORD`.
6. In **Admin → BTB accounts**, create your permanent admin account, copy its generated password, and sign in with it.
7. Clear `BOOTSTRAP_ADMIN_PASSWORD` in `.env` and restart the API. This disables the environment bootstrap account.

The API applies migrations at startup. PostgreSQL data lives in the `btb_postgres` volume. After the API is healthy, the dedicated `scheduler` service starts and registers recurring tasks. Prediction weeks are refreshed and finalized every Tuesday at 7:00 AM in `America/Chicago`, including daylight-saving-time changes. Failed runs are recorded and retried after `TASK_RETRY_MINUTES`; the existing commissioner buttons remain available as manual fallbacks.

## Local development

On Windows, double-click `run-local.bat`. The first run creates or updates `.env` and opens it for you. Add your Sleeper league ID, replace the example secret, and set a temporary bootstrap admin password. Save, then run the launcher again. It will:

- create a private Python environment;
- install missing backend and frontend packages;
- use a local SQLite database, so PostgreSQL and Docker are not required;
- start the API, frontend, and recurring-task scheduler in separate command windows; and
- open the site at `http://localhost:5173`.

Sign in with username `admin` and the `BOOTSTRAP_ADMIN_PASSWORD` value. Create your permanent account in **Admin → BTB accounts**, copy its generated password, then clear the bootstrap password and restart BTB.

To stop the local site, close the **BTB Backend**, **BTB Scheduler**, and **BTB Frontend** command windows.

Every local session is also written to `logs/backend.log`, `logs/scheduler.log`, and
`logs/frontend.log`. These files are excluded from Git and retain the console
output needed to diagnose a failure later.

All prediction screens use the authenticated BTB API. The API refreshes the active week's teams, owners, records, matchups, and scores from Sleeper; no sample league records are shown when Sleeper is unavailable or unconfigured.

The historical 2020–2021 ESPN matchup archive can be imported once from
Notion. See [the Notion game-history import runbook](docs/notion-game-history-import.md).

## League history setup

1. Apply the migrations by starting the API.
2. In **Admin → League history**, create one permanent Manager per person, including former members without BTB accounts.
3. Link current managers to BTB users where appropriate. Add all historical Notion-name aliases and stable Sleeper user-ID aliases before importing.
4. Create 2020 and 2021 as ESPN seasons with no Sleeper league ID. Follow the one-time Notion runbook, review the dry run, and commit only after every name resolves.
5. Create each season from 2022 onward as Sleeper and enter that season's league ID in the admin screen. Dry-run and then import each season. Refreshing an imported Sleeper season is idempotent; commissioner placement overrides, manual highlights, and custom facts remain intact.
6. Keep exactly one season active. When a league is renewed, create the new season and enter its new Sleeper league ID rather than replacing an older ID.

The commissioner must still enter information that neither source contains reliably: manager biographies and BTB user links, historical aliases, ESPN final placements, placement corrections, punishment titles and assignees, custom season facts, and weekly awards unavailable from stored Sleeper player details. Lineup-efficiency awards currently require manual entry because the retained data does not contain enough roster-slot eligibility information to calculate an optimal lineup safely.

## Security

- There is no public registration endpoint.
- Generated passwords are returned only in the account-creation response and are never stored as plaintext.
- Passwords are hashed with Argon2, and signed-in users can change their own password by confirming the current one.
- New sign-ins remain valid for 30 days by default; `ACCESS_TOKEN_MINUTES` can override that duration.
- The environment bootstrap account is marked separately and is disabled when `BOOTSTRAP_ADMIN_PASSWORD` is cleared.
- Change every example secret before exposing the service.
- Put the deployment behind HTTPS and a trusted reverse proxy.
