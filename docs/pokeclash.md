# PokeClash account and agent setup

All external writes use one personal account. Set `HELBPLAYS_UID` and `HELBPLAYS_KEY` in the server environment, and restart the web server and worker. The key stays server side; never place credentials in a prompt or reusable script.

Set `HELBPLAYS_OWNER_USERNAME` to the exact Django username allowed to send and configure the agent, including a normal nonstaff account. When unset, active staff users can control the account, but only one agent can be enabled for it at a time. Read-only chat is available to logged-in users. Changing owner configuration requires restarting both processes.

Run migrations (`python manage.py migrate`), then open PokeClash. Save a provider, matching model, editable strategy, optional script from **Scripts**, and a decision interval. Scripts are scoped to their owner. The model receives at most 800 script characters plus 1198 prompt characters and a bounded recent feed. Never put private information in either: API mode sends them and recent public messages to Groq.

Local inference needs `requirements-local.txt` and downloads model weights on first explicit inference. API inference needs `GROQ_API_KEY`. Setup checks do not load models, download weights or call APIs. **Queue one agent decision** asks the worker to perform one real decision and potentially send a message, even with automatic mode off. **Enable automatic decisions** opts in to repeated processing by `python manage.py run_agents`. Inference always runs in that worker, outside HTTP requests. Polling the chat and saving a disabled configuration never run a model. Keep the worker running for automatic play; stopping it stops new decisions. Disabling or editing configuration invalidates an outstanding decision before it reserves a send and cancels a pending one-off request.

Manual and automatic sends share at least a ten second account cooldown, reserved before the network request. A timeout can mean the external service delivered the message; requests are never automatically replayed. Model/feed failures delay later decisions with exponential backoff (up to 30 minutes). An account lease prevents overlapping worker inference, and the worker rechecks ownership, configuration, script content, enablement and lease before reserving a send. A manual message cancels pending inference. A worker crash recovers after a five minute lease expiry.

The plaintext feed format is `[uid;timestamp;message]`. The parser splits on the first two semicolons and preserves the message, including other semicolons and brackets. It never guesses whether text is base64. Messages render through DOM `textContent`. Malformed lines are counted and omitted. The feed may be truncated; displayed messages and group counts are observations, with no asserted current round, reliable countdown or scoreboard.

A round lasts 300 seconds from its first message. Each participant's last message in the round selects their group. The uniquely largest group wins, giving each winner `floor(losers / winners)` points; largest-group ties award no points. A `reset` group of at least 25 participants at round end resets all scores. Model-generated `reset` messages are blocked; manual sends can intentionally request one.

Tests use mocked providers and transport. No external credentials are required and no real messages are sent during tests.
