# Architecture and development notes

This document describes the architecture changes assisted by OpenAI Codex.
It supplements the student's iteration reports without replacing them.

## Corey Schafer foundation

The project originates from Corey Schafer's Python Django Tutorial:
https://github.com/CoreyMSchafer/code_snippets/tree/master/Django_Blog

The Django project configuration, account forms, account views, authentication,
profile concept, Bootstrap layout and stylesheet remain derived from that tutorial.
The original `blog` application is replaced by `game` at the student's request.
The common layout lives in `templates/base.html`; its original CSS now lives in
`static/css/main.css`. This remains a Django application using models, forms,
views, templates, the ORM and Django authentication.

## Responsibilities

- `HELBIncognito`: settings and root routes.
- `users`: registration, authentication and profile forms. `services.update_profile`
  resizes newly uploaded avatars; saving a user never opens an avatar file.
- `game`: existing Game, GamePlayer, Round, RoundAlias, Message, Vote and Script
  models. Services implement joins, round progression, aliases, chat cooldown,
  voting and scoring. Views and agents call these same services.
- `helbplays`: external PokeClash adapter. `client.py` owns HTTP and Base64 encoding;
  services own account authorization and the shared sending cooldown. The page
  polls a read endpoint independently of sending. Network responses render as text.
- `agents`: decision/action boundary for future local and API model providers.
  These entry points execute decisions; they do not yet generate LLM responses
  or schedule autonomous agent runs. Existing per-game AI settings and Script
  models are retained. No fake model or random player is presented as a working LLM.

## Game lifecycle and choices

The creator joins automatically. The first round starts when minimum attendance
is reached. Late joins receive an alias for the current round. Votes may be updated
after sending a message; self-votes and targets outside the round are rejected.
Only voters who actually sent a message count. An active player who leaves without
voting has no recorded vote; the form cannot force a disconnected browser to vote.
A unique leader earns one point; a tied round awards none. Final tied scores
produce no game winner. Winner references on closed rounds preserve the history.

Round deadlines are checked server-side, with a worker to advance games even
without an open browser. The next round starts when progression is processed,
giving it a full duration after downtime. Requests include a round ID so an old
form cannot submit to a new round. Atomic services acquire a write lock before
reading game state (SQLite does not implement row locks via select_for_update).
SQLite serializes writes; it is appropriate for the course prototype, with a
20-second lock timeout. Large deployments would need a different database and
load tests. Scoring is repeat-safe; transient database contention is retried on
the next worker tick.

## PokeClash configuration

Set server environment variables `HELBPLAYS_UID` and `HELBPLAYS_KEY`. No key is
stored in the repository or passed to the browser. This first adapter uses one
personal server account: only active staff accounts may send on its behalf.
For deployment with several staff users, they must all be trusted operators of
that account. Per-user external credentials would require a separate private
credential design. Reading is available to authenticated users.

`HELBPLAYS_CHAT_URL` defaults to `https://helbplays2627.alwaysdata.net/chat.txt`;
the send endpoint uses the same 2627 domain. The previous 2526 domain no longer
resolves. The current reading URL returned HTTP 200 with plain text when checked
on 14 November 2026. Override `HELBPLAYS_CHAT_URL` if the service moves again.
HTTP success is treated as a completed request, not proof that the game accepted
the message. Check the refreshed chat for confirmation.

A sending attempt reserves the ten-second cooldown before making a network call.
Timeouts are not automatically retried because the server might have accepted the
message already. Tests mock all external calls and never send real chat messages.

## Running

Python 3.10 or newer is needed. On Ubuntu, Python's venv/pip support must be
available (install `python3-venv` if the VM does not include it). From the project:

```bash
bash run.sh
```

The script creates a virtual environment, installs requirements, applies committed
migrations, starts one game-clock worker, then starts Django's development server.
It does not generate migrations at startup. Shell files have LF line endings.
The Ubuntu startup still needs verification on the course VM.

For Windows PowerShell after creating the virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
```

Run `.\.venv\Scripts\python.exe manage.py tick_games` in another terminal to keep
clocks advancing without open browsers. Add `--once` for a single pass.

```powershell
.\.venv\Scripts\python.exe manage.py test game users helbplays agents
```

`DJANGO_DEBUG` defaults to 1 for local development. Outside development set it to 0,
set `DJANGO_SECRET_KEY` and configure `DJANGO_ALLOWED_HOSTS`. Environment variables
are read from the process; `.env` files are ignored by Git but not loaded automatically.
`DJANGO_DB_PATH` optionally selects another SQLite database.

The architecture work does not complete every assignment feature: LLM providers,
autonomous agent scheduling, Script management pages and profile activity charts
remain to be implemented. The bonus-point strategy is outside this work.
