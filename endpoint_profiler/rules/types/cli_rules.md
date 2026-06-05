# CLI Rules

## Purpose

`CLI` is an ingress endpoint for a user-invokable command exposed by the
service or tool.

## Evidence

- Explicit command declarations in CLI frameworks.
- Command parser registrations with command names and handlers.
- Shell entrypoints paired with command metadata.

## Identifier

- Use the command name and subcommand path, for example `sync guide`.
- Store options and flags in `match_rule.options` when relevant.

## Exclusions

- Application bootstrap classes such as `CommandLineRunner` are not CLI
  endpoints unless they define user-selectable commands.
- Build scripts, test scripts, and local maintenance scripts are out of scope
  unless the target system exposes them as runtime commands.
