#!/usr/bin/env bash
# Assisted by OpenAI Codex: reproducible Ubuntu startup.
set -euo pipefail
cd -- "$(dirname -- "$0")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py tick_games &
worker_pid=$!
trap 'kill "$worker_pid" 2>/dev/null || true' EXIT INT TERM
.venv/bin/python manage.py runserver --noreload
