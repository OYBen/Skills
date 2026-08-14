# Command Reference

All commands must begin at the first non-whitespace character.

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

`threads` returns three tasks per page. Displayed numbers are stable for one
hour. Names resolve by exact normalized match first, then by a unique partial
match; ambiguous names fail closed.

`target` and `bind` are aliases. They select the task that receives shorthand
instructions. `watch` selects a separate monitored task. Query either command
without an argument to display current bindings; use `clear` to remove one.

An active target queues. An idle target without a live Desktop owner also
queues and asks the user to open it. A queued request is revalidated before
every start and never interrupts the target's current turn.
