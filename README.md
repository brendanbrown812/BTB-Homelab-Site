# BTB League Website

BTB is a private, homelab-friendly website for one fantasy football league. The first finished feature is weekly winner predictions; the core account, season, navigation, database, and Sleeper integration layers are reusable by future league features.

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
- PostgreSQL persistence, Alembic migrations, and Docker Compose

## Architecture

```text
app/, components/                 BTB web interface and routes
backend/app/auth/                 shared authentication
backend/app/core/                 configuration and security
backend/app/database/             shared PostgreSQL session/base
backend/app/models/               BTB-wide User and Season models
backend/app/services/sleeper/     reusable Sleeper adapter
backend/app/features/predictions/ prediction API, models and scoring
backend/alembic/                  database migrations
```

Sleeper is the source of truth for fantasy matchups and scores. PostgreSQL is the source of truth for accounts, picks, results, and retained prediction history. Sleeper payloads are normalized by the shared service before prediction code sees them.

## Run with Docker

1. Copy `.env.example` to `.env`.
2. Set `SLEEPER_LEAGUE_ID` to the numeric league ID from your Sleeper league URL.
3. Replace `POSTGRES_PASSWORD`, `SECRET_KEY`, and `BOOTSTRAP_ADMIN_PASSWORD` with long random values.
4. Run `docker compose up --build`.
5. Open `http://localhost:3000` and sign in using `BOOTSTRAP_ADMIN_USERNAME` (defaults to `admin`) and `BOOTSTRAP_ADMIN_PASSWORD`.
6. In **Admin → BTB accounts**, create your permanent admin account, copy its generated password, and sign in with it.
7. Clear `BOOTSTRAP_ADMIN_PASSWORD` in `.env` and restart the API. This disables the environment bootstrap account.

The API applies migrations at startup. PostgreSQL data lives in the `btb_postgres` volume.

## Local development

On Windows, double-click `run-local.bat`. The first run creates or updates `.env` and opens it for you. Add your Sleeper league ID, replace the example secret, and set a temporary bootstrap admin password. Save, then run the launcher again. It will:

- create a private Python environment;
- install missing backend and frontend packages;
- use a local SQLite database, so PostgreSQL and Docker are not required;
- start the API and frontend in separate command windows; and
- open the site at `http://localhost:5173`.

Sign in with username `admin` and the `BOOTSTRAP_ADMIN_PASSWORD` value. Create your permanent account in **Admin → BTB accounts**, copy its generated password, then clear the bootstrap password and restart BTB.

To stop the local site, close the **BTB Backend** and **BTB Frontend** command windows.

Every local session is also written to `logs/backend.log` and
`logs/frontend.log`. These files are excluded from Git and retain the console
output needed to diagnose a failure later.

All prediction screens use the authenticated BTB API. The API refreshes the active week's teams, owners, records, matchups, and scores from Sleeper; no sample league records are shown when Sleeper is unavailable or unconfigured.

## Security

- There is no public registration endpoint.
- Generated passwords are returned only in the account-creation response and are never stored as plaintext.
- Passwords are hashed with Argon2, and signed-in users can change their own password by confirming the current one.
- New sign-ins remain valid for 30 days by default; `ACCESS_TOKEN_MINUTES` can override that duration.
- The environment bootstrap account is marked separately and is disabled when `BOOTSTRAP_ADMIN_PASSWORD` is cleared.
- Change every example secret before exposing the service.
- Put the deployment behind HTTPS and a trusted reverse proxy.
