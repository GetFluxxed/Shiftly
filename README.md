# Shiftly

Shiftly is a small employee shift-reporting prototype with a separate manager briefing view.

## Run locally

```sh
cp .env.example .env
# Edit .env and add your OpenAI key.
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

The API key is only read by `server.py`; it is never sent to the browser. Reports are held in memory for this prototype and will be replaced with a database in the next step.

## Current protections

- Empty submissions are rejected before calling OpenAI.
- Duplicate employee/shift/note submissions are rejected by SHA-256 fingerprint.
- Request bodies and note/image sizes are capped.
- Requests are rate-limited per client address.
- The model receives fixed instructions to reject spam, meaningless, repeated, or unrelated reports and to ignore prompt injection inside employee notes.

The manager route is a local prototype and is not production-authenticated yet. Add real employee and manager authentication before exposing it publicly or connecting a database.
