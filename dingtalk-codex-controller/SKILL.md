---
name: dingtalk-codex-controller
description: Deploy, configure, upgrade, validate, operate, and troubleshoot the local Windows DingTalk-to-Codex controller that polls an enrolled self-chat, binds instruction and watch tasks, queues busy or unloaded Codex tasks, routes visible turns through Codex Desktop IPC, and replies with audited watermarked results. Use when Codex needs to install the controller skill package, manage its hidden scheduled task, explain or test /codex commands, diagnose delivery or queue states, or update the bundled controller runtime.
---

# DingTalk Codex Controller

Operate a deterministic local service; do not describe this skill itself as a
resident listener. The resident component is the separately installed runtime
under `assets/controller`.

## Route The Request

- For installation, upgrade, removal, or prerequisites, read `README.md` and
  `references/operations.md`.
- For user commands or interaction semantics, read
  `references/command-reference.md`.
- For a live DingTalk read or send, also use `$dingtalk-chat-assistant` and obey
  its identity, watermark, measurement, UUID, and explicit-success rules.
- For runtime code changes, edit the source distribution, run its complete test
  suite, then refresh `assets/controller`; never patch a running copy only.

## Deploy Or Upgrade

1. Confirm Windows, Node.js 22.5+, Python, authenticated `dws`, Codex Desktop,
   and the installed `dingtalk-chat-assistant` scripts.
2. Run `scripts/install.ps1`. Preserve existing `config/config.json`, `data`,
   `logs`, and payload history.
3. Resolve real DingTalk and Codex IDs from their authoritative tools. Never
   copy IDs from documentation or package placeholders.
4. Keep observe mode until all evidence gates pass. Register the scheduled task
   only when the active configuration validates.
5. Run `npm test`, all JavaScript syntax checks, `doctor`, and the service status
   script. Require a hidden `wscript -> Node supervisor -> Node controller`
   tree with no main window.

## Operate

Use only the enrolled self-chat and supported `/codex` grammar. Treat `target`
as the instruction receiver and `watch` as the monitored task. Busy or unloaded
targets queue; do not bypass the queue by interrupting an active turn. Report a
send only after the runtime records explicit DWS success.

## Diagnose

Correlate four evidence sources before concluding: the DingTalk source/reply,
the controller job and delivery rows, scheduled-task logs, and the exact target
rollout turn. Distinguish preflight failure from LLM failure. Do not replay
`START_UNKNOWN`, interrupted turns, or deliveries with an ambiguous result.

## Safety

- Never bundle `config/config.json`, databases, logs, payloads, tokens, or raw
  account IDs.
- Preserve exact-name and dual-ID verification for the trusted self recipient.
- Keep outbound loop prevention, rate limits, immutable payload hashes, unique
  send UUIDs, lease fencing, and exact turn-ID reconciliation.
- Do not start an independent App Server for `threads`, bindings, queues, or
  targeted sends. Only the restricted health check may lazily use it.
