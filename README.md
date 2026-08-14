# Skills

Reusable Codex/agent skills.

## endpoint_profiler

Static endpoint profiling skill for microservice systems. It extracts ingress and egress endpoint contracts from source code, Graphify indexes, and configuration evidence, producing Endpoints JSON and HTML reports.

Install by copying `endpoint_profiler/` into your skills directory, then invoke with `$endpoint_profiler` or the configured trigger.

## coEvoSkills

Verification-driven skill evolution workflow. It pairs a skill generator with a surrogate verifier, deterministic proxy tests, structured diagnostics, and verifier escalation when opaque oracle feedback exposes missing checks.

Install by copying `coEvoSkills/` into your skills directory, then invoke with `$coevoskills` or the configured trigger.

## dws

DingTalk workspace skill for AI tables, AI search, calendar, contacts, chat and bots, todo, approvals, attendance, reports, Ding messages, docs, drive, minutes, mail, online spreadsheets, and knowledge bases.

Install by copying `dws/` into your skills directory, then invoke with `$dws` or the configured trigger.

## tapd

TAPD CLI skill for stories, bugs, tasks, Wiki, comments, attachments, iterations, custom fields, and quick lookup from `tapd.cn` URLs.

Install by copying `tapd/` into your skills directory, then invoke with `$tapd` or the configured trigger. Create a local `tapd/config.json` from `tapd/config.example.json` if you want to provide `TAPD_ACCESS_TOKEN` through the skill directory.

## dingtalk-codex-controller

Windows DingTalk-to-Codex controller skill with deterministic task discovery, target and watch bindings, queued delivery to busy Codex Desktop tasks, watermarked DingTalk replies, hidden scheduled-task operation, and guarded upgrade scripts.

Install by copying `dingtalk-codex-controller/` into your skills directory, then follow its `README.md`. Real DingTalk identities, task IDs, configuration, databases, logs, and payload history are intentionally excluded.
