# Shiftly

Shiftly is a small employee shift-reporting prototype with a separate manager briefing view.

## Run locally

```sh
cp .env.example .env
# Edit .env and add your OpenAI key, manager password, and Postgres URL.
python3 -m pip install -r requirements.txt
docker compose up -d postgres
python3 server.py
```

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

The API key is only read by `server.py`; it is never sent to the browser. Reports and generated briefings are persisted in Postgres.

Run the schema automatically on startup. The configured Postgres user needs permission to create tables in the selected database.

For local development, [docker-compose.yml](./docker-compose.yml) provides the Postgres instance used by the example `.env`. Change the development password before using this outside your local machine.

## Current protections

- Empty submissions are rejected before calling OpenAI.
- Duplicate employee/shift/note submissions are rejected by SHA-256 fingerprint.
- Request bodies and note/image sizes are capped.
- Requests are rate-limited per client address.
- Crew report submission remains public, but report retrieval requires the manager password.
- Manager sessions use an HTTP-only, SameSite cookie and expire after 8 hours.
- The model receives fixed instructions to reject spam, meaningless, repeated, or unrelated reports and to ignore prompt injection inside employee notes.
- Employee submissions are committed to Postgres before the OpenAI job is queued.
- A background worker claims queued jobs and saves the briefing with an exact `source_notes` snapshot.
- Managers can see the original notes immediately and pending/failed/completed briefing status.
- Saved briefings are read from Postgres and are not regenerated when the manager revisits the portal.

The manager route uses a single shared password for this first version. Replace it with real identity-based authentication before exposing it publicly or connecting a production database.
