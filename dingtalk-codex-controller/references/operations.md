# Operations

## Validation Sequence

1. Run `npm test` in the deployed runtime.
2. Run `node --check` for every JavaScript file under `src`, `test`, and `ops`.
3. Run `node src/cli.js doctor --config config/config.json`.
4. Require `ACTIVE_READY` before active use.
5. Run `ops/status-scheduled-task.ps1` and require an enabled `Running` task.
6. Require `wscript.exe -> node supervisor -> node controller`, with
   `hasMainWindow=false` for all three.

`0x800710E0` is healthy only while the task state is `Running`; it means the
one-minute watchdog trigger was ignored because the existing instance is still
running.

## Upgrade Boundary

The package never contains or replaces `config/config.json`, `data`, `logs`, or
payload history. Stop/restart the scheduled task only after tests pass. Database
schema upgrades use additive `CREATE TABLE IF NOT EXISTS` and column checks.

## Incident Triage

- `QUEUED / THREAD_ACTIVE`: wait for the current target turn to finish.
- `QUEUED / DESKTOP_THREAD_OWNER_UNAVAILABLE`: open the target in Codex Desktop.
- `THREAD_SELECTOR_AMBIGUOUS`: rerun `/codex threads` and use a short number.
- `START_UNKNOWN`: do not replay automatically; inspect the exact target rollout.
- `TURN_INTERRUPTED`: a later target turn superseded the tracked turn.
- `POLL_GAP_RISK`: stop active reliance and inspect poll boundaries.
- `DELIVERY_UNKNOWN`: do not resend automatically with a new UUID.
