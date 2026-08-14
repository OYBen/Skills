# DingTalk Controller

Deterministic local bridge from one enrolled DingTalk self-chat to local Codex
tasks. It accepts only these commands:

```text
/codex help
/codex status
/codex threads [page]
/codex target|bind [task-id|number|name|clear]
/codex watch [task-id|number|name|clear]
/codex send <task-id|number|"name"> <instruction>
/codex <instruction>
/codex queue
/codex cancel [request-id]
/codex run health-check
/codex result [request-id]
```

Polling, parsing, identity checks, bindings, queues, state transitions, retries,
and delivery are ordinary Node.js code. `threads` lists tasks three at a time,
stores stable one-hour short-number selections, and reports whether each task is
ready, queueable, needs to be opened, or unavailable. `target` binds the task
that receives instructions; `watch` separately binds the task the receiver
should monitor. A shorthand `/codex <instruction>` uses both bindings.

`send` preflights the task before acknowledging it. Busy or unloaded tasks are
queued and retried after they become idle and have a live Codex Desktop owner.
The controller pushes queued, started, and final states. It never executes a
shell command directly and never falls back to another App Server.

## Safety Boundary

- Observe mode records authorized commands but never replies or starts Codex.
- Active mode requires an enrolled `self-chat`, delivery mode `trusted-self`,
  trusted name `欧阳斌`, one enabled `health-check`, a dedicated task using
  `:read-only`, and all four evidence gates set to `true`.
- Every send re-resolves `欧阳斌` and verifies both fixed identity fields.
- Every text is watermarked and measured with the installed DingTalk assistant
  scripts. Full replies are capped at 500 Unicode code points.
- A result over the limit is replaced by a short local-review notice. Attachment
  delivery is not implemented.
- `turn/start` is attempted once. An ambiguous response enters
  `START_UNKNOWN`; it is never started again automatically.
- Targeted instructions are limited to 1,000 Unicode code points, stored only
  in a local payload file with a SHA-256 recorded in SQLite, and routed through
  the target task's current Codex Desktop owner. The target keeps its existing
  model, permission profile, tools, and collaboration settings.
- Bindings store only Codex task IDs under a hashed DingTalk conversation key.
  Short-number selections expire after one hour. A queued request can be
  inspected or canceled and is always revalidated immediately before start.
- Target-task permissions may allow files, MCP servers, plugins, connectors,
  apps, network access, or external side effects. Only use task IDs whose
  capabilities are understood. `:read-only` applies only to the dedicated
  `health-check` task.

## Commands

```powershell
npm test
node src/cli.js doctor --config config/config.json
node src/cli.js probe-dws --config config/config.json
node src/cli.js probe-codex --config config/config.json
node src/cli.js scan-once --config config/config.json
npm start
npm run service:install
npm run service:status
npm run service:remove
```

The Windows scheduled task runs under the current interactive user at logon,
keeps one instance, and recovers a stopped process tree within about one
minute. Its runtime is `wscript.exe //B -> Node supervisor -> controller`, so no
PowerShell window is created or retained. Normal startup, `threads`, and `send`
do not start a Codex App Server process. It does not store a Windows password.
See [docs/runbook.md](docs/runbook.md) for deployment and recovery details.

See [docs/runbook.md](docs/runbook.md) for enrollment, activation, and DingTalk
usage. The real `config/config.json`, SQLite database, payloads, and logs remain
local and are excluded from source control.
