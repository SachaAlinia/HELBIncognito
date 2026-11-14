# Architecture and development notes

This document describes the repository as updated on 14 November 2026, with
assistance from OpenAI Codex. It supplements the student's dated iteration reports.

## Foundation and responsibilities

The project derives from [Corey Schafer's Django tutorial](https://github.com/CoreyMSchafer/code_snippets/tree/master/Django_Blog).
Account forms, authentication, the profile concept, Bootstrap layout and base CSS
retain that foundation. The original blog application has been replaced by `game`.

- `HELBIncognito`: environment settings and root routes.
- `users`: account/profile editing and publicly readable player statistics.
  Avatar resizing happens only when a newly uploaded image is saved.
- `game`: game models, rules, HTTP controls, reusable scripts and round history.
  Humans and agents call the same service functions.
- `agents`: real local/API providers, structured decisions and autonomous worker.
- `helbplays`: PokeClash transport, plaintext protocol parser, account authorization,
  shared cooldown, manual sends and autonomous strategy configuration.

## Incognito lifecycle and scoring

The creator joins automatically. Reaching the configured minimum starts the first
round; a late join receives an alias in the current round. Each new round generates
fresh aliases. A message with another player present requires either a saved vote
or a valid target submitted with that message. Combined vote/message creation is
atomic: an invalid message, expired round, invalid target or cooldown violation
cannot leave a partial vote. A solo player may chat without a vote; after another
player joins a target is required for the next message if no vote exists yet.

Separate vote changes require a previous message in that round. Self-votes and
targets outside the round are rejected. Only voters who actually sent a message
count toward the result. A unique vote leader earns one point; tied leaders and
rounds without votes award none. A final game winner exists only when one player
has the highest total score. A tie at zero is still a tie.

The game page shows the user's own alias and current vote, a client countdown
based on the server deadline, rankings linked to public profiles, and completed
rounds. Each completed round lists every game player: one or zero points for an
existing round alias, or “Did not participate” when the player joined later.
The private JSON feed updates only that user's agent status and vote, alongside
anonymous chat. Remote/chat text is inserted using DOM `textContent`.

`tick_games` advances waiting and active games without browser traffic. HTTP
requests also check deadlines. A next round gets its full duration from the time
progression is processed after downtime. Forms carry a round ID to reject stale
submissions. Scoring is repeat-safe. Services acquire a game write lock before
reading state because SQLite does not implement row locks with `select_for_update`.
SQLite serializes writes; larger deployments need another database and load tests.

## Scripts, prompts and public statistics

The script library requires authentication and scopes all list/read/edit/delete
operations to `Script.owner`. Deletes use POST and Django CSRF protection.
Incognito configuration is scoped to the current user's `GamePlayer`; a posted
player ID cannot select another player's settings. The form validates provider/model
pairs against `agents.providers.MODEL_CHOICES`, with dynamic model options in the UI.

Applying an Incognito script copies its content before the custom prompt. Later
script changes do not silently alter that player's running instructions. The
combined prompt must fit 2,000 characters; validation rejects overflow. PokeClash
stores an owner-scoped script reference and documents its context limits in its
[dedicated guide](pokeclash.md).

Public statistics count actual `GamePlayer` participation, including waiting and
unfinished games, on `joined_at`. Merely creating a game is not participation.
Wins count only finished games with a recorded finishing date and a unique
highest-scoring player, on `finished_at`. Round wins and tied final scores do not
inflate game wins. Dates use the configured Django timezone, UTC by default.
The daily HTML chart includes empty days and an accessible table of exact counts;
account email and agent settings are not public.

## Model providers and worker

The local provider uses `HuggingFaceTB/SmolLM2-135M-Instruct` with PyTorch CPU and
Transformers. Optional `requirements-local.txt` installs CPU-specific dependencies.
Imports and readiness checks never load weights; the first explicit local
inference downloads them. API mode uses Groq with `GROQ_API_KEY` from the server
environment. Supported IDs are centralized in `MODEL_CHOICES`. Provider readiness
and safe fixed error messages appear only in the owner's configuration panel.

Prompts receive bounded recent context and anonymous aliases. Providers return
validated JSON decisions containing a short message and a permitted vote target.
Model responses cannot call arbitrary application operations. Human and agent
actions share cooldowns, voting rules and round validation.

`python manage.py run_agents` polls every two seconds and processes bounded
passes. Incognito claims a due player's lease while holding the game lock,
releases the transaction during model inference, then reacquires the lock before
applying the result. It checks the lease token, active round, account activity and
the entire configuration including `ai_config_revision`. Every save or stop
increments the revision, invalidating even an off/on cycle or a later reversion
to identical settings. Configuration edits clear prior errors/backoff without
releasing an active worker lease. The finishing worker discards obsolete results;
expired leases permit crash recovery after five minutes.

Incognito stores attempt/error status and a next-run date. Normal attempts are
spaced by at least ten seconds or the game's longer cooldown. Errors use
15-second exponential backoff capped at five minutes. Unexpected provider errors
are summarized without response bodies or credentials. No HTTP page or polling
request performs inference. `--once` executes one pass; `--incognito-only` skips
PokeClash. `--dry-run` only reads Incognito eligibility and performs no writes or
model calls.

## PokeClash boundary

Reading is available to authenticated users. Writes use one personal server
account configured with `HELBPLAYS_UID` and `HELBPLAYS_KEY`. Setting
`HELBPLAYS_OWNER_USERNAME` authorizes that exact active Django account, including
a nonstaff user. When unset, active staff users are trusted operators. Only one
agent can control the shared external account at a time. No credential goes to
the browser, a prompt or the database.

The default read endpoint is `https://helbplays2627.alwaysdata.net/chat.txt`; sends
use the same 2627 host. A different read URL may be configured through
`HELBPLAYS_CHAT_URL`. Feed parsing preserves semicolons inside messages and never
guesses Base64. Available feed observations do not establish a trustworthy current
round, countdown or scoreboard. The displayed group counts are observations.

Manual sends and agent decisions share an account-level cooldown reserved before
the network call. A successful HTTP response proves a completed request, not game
acceptance; inspect refreshed chat. A timed-out send is not automatically replayed.
A human send invalidates pending model inference. PokeClash configuration,
script content, ownership, lease and enablement are rechecked before sending.
Its separate error backoff is capped at thirty minutes. The “run once” action
queues work for the worker instead of running inference in an HTTP request.

## Running and validation limits

See the [README](../README.md) for Ubuntu/WSL setup and commands. Python 3.10+
and working venv/pip support are required. `run.sh` starts both `tick_games` and
`run_agents` alongside Django's development server and stops its child workers
when exiting. It applies committed migrations rather than creating new ones.

`requirements.txt` is currently entirely commented. Dependency point 1 is outside
this intervention's scope, so the file remains unchanged. A fresh
installation cannot rely on that file yet. Existing validation uses the already
populated WSL virtual environment. `requirements-local.txt` is optional and must
be installed explicitly for local inference.

Environment variables are read from the process; `.env` is ignored by Git but
is not loaded automatically. Restart both web and worker processes after changing
credentials or owner configuration. For nondevelopment use, set `DJANGO_DEBUG=0`,
`DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`. `DJANGO_DB_PATH` selects another
SQLite database. Never use real credentials or user data as fixtures.

Tests run against Django's test database, using mocked external transport and
provider responses. They verify rules, authorization, structured parsing,
configuration invalidation, leases and UI rendering. Template rendering tests do
not establish visual browser correctness. No course VM validation, authenticated
Groq call or real PokeClash send is claimed. Separate local-model smoke results
must identify whether real weights were actually loaded.
