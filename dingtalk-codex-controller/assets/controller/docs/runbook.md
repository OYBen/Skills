# DingTalk Controller Runbook

Date: 2026-08-13
Timezone: Asia/Shanghai

## Prerequisites

- Node.js 22.5 or later, authenticated `dws`, Python, Codex Desktop, and a
  runnable Codex CLI for the dedicated `health-check` action only.
- DingTalk self-chat for the controller account, enrolled by exact conversation
  ID plus user ID and open DingTalk ID.
- Dedicated Codex task rooted at `C:\Tools\DingTalkCodexController\sandbox`.
- Installed `dingtalk-chat-assistant` watermark and metrics scripts.

Do not commit real IDs, tokens, credentials, `config/config.json`, SQLite data,
payloads, or logs.

## Observe Mode

The checked-in local configuration is intentionally taskless and observe-only.

```powershell
cd C:\Tools\DingTalkCodexController
npm test
node src/cli.js doctor --config config/config.json
node src/cli.js probe-dws --config config/config.json
node src/cli.js scan-once --config config/config.json
npm start
```

`npm start` polls every configured interval until Ctrl+C. Expected scans are
`COMPLETE`; `POLL_GAP_RISK` blocks active processing and requires investigation.

## Active Enrollment

Activation is a local administrative change, not a DingTalk command.

1. Create a dedicated task titled `DingTalk Controller Read-Only` with cwd
   `C:\Tools\DingTalkCodexController\sandbox` and permission profile `:read-only`.
2. Confirm `permissionProfile/list` reports `:read-only` as allowed. Resume the
   exact task with the same cwd, `permissions=:read-only`, and
   `approvalPolicy=never`; require returned `cwd` to match and
   `sandbox.type=readOnly`.
3. Enroll its task ID and title in ignored `config/config.json`.
4. Configure only `health-check`, using
   `config/actions/health-check.txt` and its current SHA-256 from:

   ```powershell
   node src/cli.js hash-actions --config config/config.example.json
   ```

5. Set `delivery.mode=trusted-self` and `trustedRecipientName=欧阳斌`.
6. Validate real inbound field shape, quoted reply success, loop prevention,
   polling catch-up, exact-turn reconciliation, and safe UUID retry behavior.
7. Set each evidence gate to `true` only after its evidence passes; then set
   `mode=active`.
8. Run one bounded cycle before continuous service:

   ```powershell
   node src/cli.js scan-once --config config/config.json
   npm start
   ```

The service rejects active startup unless all constraints above are present.

## Windows Persistent Operation

The production-like local deployment is a Windows Scheduled Task running as
the current interactive user. User logon, rather than pre-login system startup,
is required because DingTalk and Codex credentials are user-scoped.

Install the task, then start it immediately when needed:

```powershell
cd C:\Tools\DingTalkCodexController
pwsh -NoProfile -File ops\install-scheduled-task.ps1 -StartNow
```

The task action uses the no-console `wscript.exe` host, which launches a Node
supervisor with window style `0`; PowerShell is not part of the runtime process
tree. The task uses explicit working and launcher paths, ignores duplicate starts,
runs on battery, has no execution time limit, and restarts an abnormal exit up
to 999 times at one-minute intervals. A second every-minute watchdog trigger
also recovers externally terminated task trees; `IgnoreNew` makes that trigger
a no-op while the task is healthy. The controller's SQLite lease remains the
second single-instance boundary. Logs are written under
`logs\scheduled-task` and files older than seven days are removed at launch.
While healthy, Task Scheduler can report `0x800710E0`; the status script labels
this as the watchdog trigger being ignored because an instance already runs.
The supervisor pins `CODEX_BIN` for the explicit, lazily started
`run health-check` action only. Normal service startup and the `threads` and
`send` commands use Codex Desktop IPC plus the read-only local Desktop task
catalog; they do not start an App Server child.
The hidden WScript host, Node supervisor, and controller have linked lifetimes:
stopping the scheduled task removes the host, the supervisor detects that loss,
and an IPC shutdown lets the controller release the SQLite lease. Supervisor
loss also closes the controller.

Inspect or remove the deployment:

```powershell
pwsh -NoProfile -File ops\status-scheduled-task.ps1
pwsh -NoProfile -File ops\uninstall-scheduled-task.ps1
```

Removing the scheduled task disables future logon starts. It does not change
`config/config.json` or delete the SQLite database, payloads, or logs.

## Sending Commands

Open DingTalk's chat with yourself (`欧阳斌`) and send one command as an
ordinary text message. The command must start at the first non-whitespace
character and must match exactly.

```text
/codex help
/codex status
/codex threads
/codex threads <page>
/codex target <task-id|number|name>
/codex bind <task-id|number|name>
/codex watch <task-id|number|name>
/codex send <task-id|number|"name"> <instruction>
/codex <instruction>
/codex queue
/codex cancel [request-id]
/codex run health-check
/codex result
/codex result <request-id>
```

The controller replies to that exact source message using the current DingTalk
user identity. Replies begin with `【AI生成】`. `run health-check` first sends an
acknowledgement, starts one read-only Codex turn, then sends its final result.
`threads` returns three tasks per page with complete IDs and actionable states.
Its displayed numbers remain valid for one hour and can be used by `target`,
`watch`, or `send`. Exact and uniquely matching task names are also accepted;
quote a name containing spaces in `send`.

`target` (or `bind`) selects the task that receives later shorthand commands.
`watch` selects the task to include as the monitored object. After both are set,
`/codex <instruction>` routes the instruction to the target with the watch task
ID added as explicit context. Use `clear` to remove either binding.

`send` preflights before acknowledging. A task that exists, is unarchived,
verifiably idle, and has a live Desktop owner starts immediately. An active task
or an idle task without a live owner enters `QUEUED`; the controller pushes one
queue notice, rechecks each poll, then pushes a start notice when ready. Use
`queue` to inspect waiting work and `cancel` to close a queued request. The
controller discovers the owner and sends `thread-follower-start-turn` directly
to it. It rejects archived, missing, ambiguous, or unknown-state tasks rather
than steering an existing turn or falling back to an independent App Server.
The target keeps its existing model, permissions,
tools, and collaboration settings. The instruction is never passed to
PowerShell, `cmd.exe`, `thread/shellCommand`, `command/exec`, or
`process/spawn`.

Target-task permissions are not changed by the controller. A target task may
have filesystem writes, MCP servers, plugins, apps, connectors, or network
access that can read data or cause external effects. Review those capabilities
before sending a task ID. Instruction payload files remain local under the
configured payload directory; SQLite stores their path and SHA-256, not the
instruction text.

Completion is reconciled against the target task's rollout using the exact
turn ID returned by Desktop. A matching `task_complete` supplies the LLM result;
a later task start without completion closes the tracked turn as interrupted.
Output from another turn is never returned for the request.

## Incident States

- `QUEUED`: target is active or awaits a live Codex Desktop owner.
- `CANCELED`: user canceled the request before its turn started.
- `POLL_GAP_RISK`: stop active reliance; inspect cursor/time boundaries.
- `START_UNKNOWN`: never start again; reconcile exact task turns locally.
- `START_UNKNOWN_NOTIFIED`: uncertainty was reported once.
- `FAILED_NOTIFIED`: failure was reported once.
- `AWAITING_SEND_APPROVAL`: trusted identity verification failed; no send.
- `SEND_FAILED`: explicit DWS rejection; no verbose retry.
- `DELIVERY_UNKNOWN`: outcome is ambiguous after at most one same-UUID retry;
  do not resend automatically.

Authentication or permission errors are never retried. Only timeout or an
explicitly classified transient process failure gets one `--verbose` retry,
using the same UUID.

## Current Limitation

Long-message attachment upload is not implemented. Any final watermarked result
over 500 Unicode code points is retained locally and replaced by a short notice
in DingTalk. The fixed health prompt requests at most 300 characters to avoid
this path during normal operation.
