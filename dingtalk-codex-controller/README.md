# DingTalk Codex Controller Skill

This skill packages a deterministic Windows service that accepts commands from
one enrolled DingTalk self-chat and routes them to visible Codex Desktop tasks.
Routing, bindings, queuing, identity checks, and status replies do not require an
LLM. The target Codex task handles the instruction itself.

## Prerequisites

- Windows 10/11 with Task Scheduler and Windows Script Host
- Node.js 22.5 or later
- Python 3
- Authenticated `dws`
- Codex Desktop and Codex CLI
- Installed `dingtalk-chat-assistant` skill and its watermark scripts

## Install Or Upgrade

The installer copies the bundled runtime without overwriting an existing real
configuration, database, logs, or payload history.

```powershell
$codexHome = if ($env:CODEX_HOME) {
  $env:CODEX_HOME
} else {
  Join-Path $env:USERPROFILE ".codex"
}
$skill = Join-Path $codexHome "skills\dingtalk-codex-controller"
$destination = Join-Path $env:LOCALAPPDATA "DingTalkCodexController"
pwsh -NoProfile -File "$skill\scripts\install.ps1" `
  -Destination $destination
```

For a first installation, create `config\config.json` from
`config\config.example.json`, resolve all identity and task placeholders using
the authoritative tools, start in observe mode, and follow
`references/operations.md` before enabling active mode.

After active configuration is validated:

```powershell
pwsh -NoProfile -File "$skill\scripts\install.ps1" `
  -Destination $destination -RegisterTask -StartNow
pwsh -NoProfile -File "$skill\scripts\status.ps1" `
  -Destination $destination
```

## Everyday Use

```text
/codex threads
/codex target 示例任务-执行
/codex watch 示例任务-监控
/codex 查询当前状态
```

`target` is the Codex task that receives and handles the instruction. `watch`
is the task included as the monitored object. If the target is busy or is not
currently loaded by Codex Desktop, the request queues and runs when both idle
state and a live Desktop owner are verified.

Use `/codex queue` to inspect waiting requests and `/codex cancel [request-id]`
to cancel one. Results are pushed automatically. See
`references/command-reference.md` for the complete grammar.

## Remove The Scheduled Task

```powershell
pwsh -NoProfile -File "$skill\scripts\uninstall.ps1" `
  -Destination $destination
```

Removal stops and unregisters the scheduled task. It intentionally leaves the
runtime directory, configuration, database, logs, and payloads in place.
