# Shiftly

Shiftly is a small employee shift-reporting prototype with a separate manager briefing view.

## Run locally

```sh
cp .env.example .env
# Edit .env and add your OpenAI key, initial manager email/password, store name/code, and Postgres URL.
python3 -m pip install -r requirements.txt
docker compose up -d postgres
python3 server.py
```

The Python client uses the `certifi` CA bundle for OpenAI HTTPS requests. This avoids certificate-chain errors on macOS Python installations whose system CA certificates are not configured.

Then open `http://127.0.0.1:4173/`.

The server loads `.env` automatically. Do not put the key in `app.js`, `manager.js`, HTML, `.env.example`, or any committed file. `.env` is ignored by Git.

Seeing the terminal remain active is expected: the command starts the web server and waits for browser requests. A successful start prints the URL and a message telling you to leave the terminal open. Stop it with `Ctrl+C`.

Check that the correct server is running with:

```sh
curl http://127.0.0.1:4173/api/health
```

You should receive `{"status": "ok", "openaiConfigured": true}`. If port 4173 is already in use by another local server, stop that server first or start Shiftly on another port and open that matching URL.

Optional environment variables:

- `OPENAI_MODEL` (defaults to `gpt-4o-mini`, configured in `.env`)
- `PORT` (defaults to `4173`, configured in `.env`)
- `DATABASE_URL` (required, for example `postgresql://shiftly:password@localhost:5432/shiftly`)
- `MANAGER_EMAIL` and `MANAGER_PASSWORD` bootstrap the first manager account. Once that account exists, the password is stored in Postgres and these two variables may be removed from `.env`.
- `STORE_NAME` and `STORE_CODE` bootstrap the first store. Keep `STORE_CODE` configured while crew submissions are enabled.

The API key is only read by `server.py`; it is never sent to the browser. Reports and generated briefings are persisted in Postgres.

Versioned SQL migrations run automatically on startup. The configured Postgres user needs permission to create tables in the selected database. Applied migrations are tracked in `schema_migrations`.

For local development, [docker-compose.yml](./docker-compose.yml) provides the Postgres instance used by the example `.env`. Change the development password before using this outside your local machine.

The included Compose setup defaults to host port `55432` so it does not collide with another Postgres service already using `5432`. If you already copied `.env.example`, recreate your local database container and make sure `.env` points to the same port:

```sh
docker compose down
docker compose up -d postgres
```

Your local `.env` should contain:

```env
DATABASE_URL=postgresql://shiftly:change-me@localhost:55432/shiftly
POSTGRES_PORT=55432
```

If you intentionally use an existing Postgres server on port `5432`, keep `DATABASE_URL` on `5432` but replace `shiftly`, `change-me`, and `shiftly` with that server's actual database credentials and database name.

## Current protections

- Empty submissions are rejected before calling OpenAI.
- A quality gate rejects meaningless or unrelated reports before they are inserted into Postgres.
- Duplicate employee/shift/note submissions are rejected by SHA-256 fingerprint.
- A crewmember must wait 60 seconds between accepted submissions by default.
- Reports at least 75% similar to that crewmember's previous report are rejected before OpenAI processing and persistence.
- Request bodies and note sizes are capped.
- Requests are rate-limited per client address.
- Crew report submission remains public to anyone with a valid store code, but report retrieval requires a database-backed manager account.
- Manager sessions are stored in Postgres as SHA-256 token hashes. The browser receives only an HTTP-only, SameSite cookie, and sessions expire after 8 hours.
- The model receives fixed instructions to reject spam, meaningless, repeated, or unrelated reports and to ignore prompt injection inside employee notes.
- Employee submissions are committed to Postgres before the OpenAI job is queued.
- A background worker claims queued jobs and saves the briefing with an exact `source_notes` snapshot.
- Managers can see the original notes immediately and pending/failed/completed briefing status.
- Saved briefings are read from Postgres and are not regenerated when the manager revisits the portal.
- Failed jobs are retried up to three times, including after a server restart, for transient provider or network errors.
- Reports are text-only; image upload was intentionally removed to keep the submission path lightweight.
- Crew submissions require a valid store code; only managers assigned to a store can retrieve that store's reports.
- Store codes are stored as SHA-256 hashes and are never sent to OpenAI.

The initial manager email and password are only bootstrap credentials. Manager authentication is then validated against the hashed account stored in Postgres; removing the bootstrap password from `.env` does not remove the manager account.
