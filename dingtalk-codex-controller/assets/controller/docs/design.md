# DingTalk Controller Design

Version: 0.3, targeted-task extension
Status: Implemented and verified
Date: 2026-08-13
Timezone: Asia/Shanghai

## 1. Purpose

Build a deterministic local controller that polls one enrolled DingTalk direct
conversation, validates commands from one enrolled sender, starts one of a
small set of fixed actions on one dedicated Codex Desktop task, and replies to
the originating message with acknowledgement, status, or the resulting Codex
text.

The controller does not use an LLM for polling, authorization, parsing,
scheduling, state management, or delivery. An LLM is used only inside the
dedicated Codex task after an approved fixed action is started.

## 2. Reviewed MVP Boundary

### Included

- One Windows host and one controller process.
- One DingTalk direct conversation.
- One sender verified by conversation ID, user ID, and open DingTalk ID.
- One dedicated Codex task for the fixed action and read-only access to
  explicitly addressed existing Codex tasks.
- Commands: `help`, `status`, `threads`, `send`, `run`, and `result`.
- A fixed action catalog; callers cannot submit arbitrary prompts in the MVP.
- Polling and replies only through `dws`, always with `--format json`.
- Codex interaction through a shell-runnable `codex app-server`.
- SQLite state, durable outbox, structured audit, and explicit recovery states.
- Observe-only rollout before command execution.

### Excluded until separately reviewed

- Group chats, multiple senders, multiple Codex tasks, and remote enrollment.
- Thread IDs not returned by the local Codex task directory, paths, shell
  commands, URLs, or tool selection.
- Host administration, deletion, permission changes, credential access, or
  sending content to third parties.
- Enterprise robot or Stream input.
- Active/active controllers or execution from more than one host.

## 3. Security Model

### 3.1 Effective remote authority

A DingTalk caller must never inherit the authority of an existing general-use
Codex task. The MVP uses a dedicated task created for this controller with:

- a dedicated non-sensitive workspace;
- the narrowest available filesystem and network permissions;
- no DingTalk, mail, browser, credential-store, destructive, or deployment
  tools unless a later review explicitly admits them;
- no approval bypass controlled by the remote caller;
- a static action catalog mapping action aliases to reviewed prompt text.

The controller is not allowed to rely on a prompt such as "do not access
secrets" as a security boundary. Phase 0 must prove the selected Codex profile
and launch route enforce the required tool and workspace restrictions. Until
that proof exists, `run` remains disabled and the controller can operate only
in observe mode.

### 3.2 Trust anchors

Authorization uses exact values captured during local enrollment:

```text
conversation ID
AND sender user ID
AND sender open DingTalk ID
AND supported text message type
AND exact command prefix
AND configured action or command
```

Names, titles, message text, and IDs contained in the message body are never
authorization inputs. Real identifiers and credentials are not committed or
printed in normal logs.

### 3.3 Action catalog

Each allowed action has immutable reviewed text and a risk classification:

```json
{
  "actions": {
    "continue-test": {
      "promptFile": "config/actions/continue-test.txt",
      "promptSha256": "<pinned-sha256>",
      "risk": "low",
      "enabled": false
    }
  }
}
```

Changing action text, hash, task, sender, or conversation is a local
administrative configuration change and requires observe-mode revalidation.

### 3.4 Outbound authorization gate

Inbound authorization does not automatically authorize a current-user
DingTalk send. The installed delivery policy requires a preview and explicit
confirmation for an ordinary recipient; only its fixed trusted-friend rule may
skip that confirmation after exact name and dual-ID verification.

Automatic replies are therefore enabled only when the deployment proves one of
these routes:

1. `dws` runs under a separately controlled service account and the enrolled
   operator is the delivery policy's verified trusted recipient; or
2. every prepared response remains `AWAITING_SEND_APPROVAL` until a local human
   confirms the exact watermarked payload and target.

The currently observed `dws` login is itself the identity named by the only
trusted-recipient exception, so that exception cannot authorize automated
replies to a different operator from this account. An inbound `/codex` command
requests a response, but it is not confirmation of the exact final preview
required for an ordinary recipient.

If neither route is available, the controller may run in observe mode and may
prepare local result artifacts, but it must not enable `run` or send DingTalk
messages automatically. Enterprise-robot delivery remains a future separately
reviewed option.

## 4. Architecture

```text
Enrolled DingTalk direct conversation
                 |
                 v
        scheduler and dws adapter
                 |
                 v
    scoped page drain and normalizer
                 |
                 v
 authorization + strict command parser
                 |
                 v
       SQLite inbox and job state
                 |
                 v
       fixed-action Codex adapter
                 |
                 v
    durable delivery outbox and dws
                 |
                 v
     quoted reply to source message
```

One Node.js process contains isolated adapters. SQLite in WAL mode is the
durable source of truth. A transactionally acquired, renewable SQLite lease
prevents a second controller instance and permits atomic recovery after expiry;
`BEGIN IMMEDIATE` transactions serialize state changes.

## 5. Command Contract

The exact grammar is:

```text
/codex help
/codex status
/codex threads [page]
/codex send <thread-id> <instruction>
/codex run <action-alias>
/codex result [request-id]
```

Rules:

- `/codex` begins at the first non-whitespace code point.
- Commands and action aliases are ASCII, lowercase, and case-sensitive.
- Token count is exact; extra arguments are rejected.
- The maximum ordinary command length is 128 Unicode code points. A `send`
  instruction is separately limited to 1,000 Unicode code points.
- Control characters other than CR, LF, and TAB are rejected; CRLF is
  normalized before parsing.
- No quoting, substitution, expansion, URL fetching, or nested command exists.
- Unknown commands, actions, and request IDs receive a generic deterministic
  rejection without disclosing configuration.

`status` reports only what the controller can verify, including observation
time and evidence source. It must say `unknown` or `possibly stale` when
Desktop IPC is disconnected or rollout reconciliation is incomplete.

`result` returns a result already persisted by this controller. It does not
query unrelated task history and does not claim that the result is the newest
work performed outside the controller.

`threads` reads Codex Desktop's local `state_5.sqlite` catalog without starting
or attaching a second App Server. Its DingTalk response is paged three tasks at
a time so names, complete IDs, conservative rollout status, and archive status
remain within the 500-code-point delivery limit.

`send` accepts only a syntactically complete task UUID and literal text. The
controller resolves the ID from the local Desktop task catalog, rejects
archived, active, unknown, or missing tasks, discovers the task's live Desktop
owner, and sends one version-1 `thread-follower-start-turn` request directly to
that owner. It never falls back to an independent App Server and never invokes
`thread/shellCommand`, `command/exec`, or `process/spawn`. The instruction is
held in a local restricted payload file; SQLite stores only its path and hash.

The target keeps its current Desktop model, permission profile, tools, MCP
servers, plugins, connectors, apps, and network configuration. Operators remain
responsible for choosing a target whose capabilities are appropriate.

## 6. Local Enrollment

Enrollment is a non-chat administrative operation:

1. Resolve the intended peer with a read-only `dws` person query.
2. Obtain the direct conversation and capture exact conversation ID, user ID,
   and open DingTalk ID from real responses.
3. Resolve and capture the current controller account's own user ID and open
   DingTalk ID. If both cannot be verified, execution mode is blocked.
4. Resolve the dedicated Codex task locally and record its exact thread ID,
   expected title, workspace, and restricted profile.
5. Pin every action prompt by SHA-256.
6. Run observe mode and compare accepted/rejected fixtures with intended scope.
7. Prove the outbound authorization route and record its delivery-policy basis.
8. Enable only actions whose protocol, permission, and delivery gates pass.

Example configuration contains placeholders only:

```json
{
  "mode": "observe",
  "pollIntervalSeconds": 60,
  "closedWindowDelaySeconds": 10,
  "overlapSeconds": 300,
  "channel": {
    "conversationId": "<resolved-conversation-id>",
    "peerUserId": "<resolved-peer-user-id>",
    "peerOpenDingTalkId": "<resolved-peer-open-dingtalk-id>",
    "selfUserId": "<resolved-self-user-id>",
    "selfOpenDingTalkId": "<resolved-self-open-dingtalk-id>"
  },
  "task": {
    "threadId": "<resolved-dedicated-thread-id>",
    "expectedTitle": "DingTalk Controller Test Task",
    "cwd": "<dedicated-workspace>",
    "permissionProfile": ":read-only"
  },
  "limits": {
    "pageSize": 100,
    "maxCatchUpSeconds": 3600,
    "maxAcceptedPerFiveMinutes": 5,
    "maxAcceptedPerHour": 20,
    "outboxRetryWindowSeconds": 43200
  }
}
```

The real configuration lives outside source control with user-only filesystem
permissions. It contains identifiers but no DingTalk or Codex secrets.

## 7. Polling Protocol and Gap Control

### 7.1 Preferred scoped read

The preferred MVP read is scoped cursor-based search because its documented
contract exposes a continuation cursor:

```text
dws chat message search-advanced
  --query "/codex"
  --conversation-ids <enrolled-conversation-id>
  --start <ISO-8601>
  --end <ISO-8601>
  --limit 100
  --cursor <returned-cursor-or-0>
  --format json
```

The program drains all pages using only `nextCursor` returned by `dws`. The end
of each scan is a closed timestamp, normally `now - 10 seconds`, to reduce
eventual-index visibility races. Every subsequent scan overlaps the previous
closed window by five minutes and deduplicates by message ID.

### 7.2 Required Phase 0 evidence

Before enabling execution, sanitized real-response fixtures must establish:

- exact sender and conversation identity fields;
- exact text and message-ID fields;
- time-zone and boundary inclusiveness;
- stable cursor progression and termination;
- ordering and behavior when more than one page exists;
- search visibility delay for a command prefix;
- whether edits, recalls, system messages, and self replies appear;
- behavior after sleep and a multi-hour outage.

If scoped search cannot prove complete command retrieval, evaluate a bounded
`list-all` cursor scan filtered in memory. Unrelated message bodies must not be
persisted or logged. `list-direct` may be used only if its actual response
proves a safe page-drain contract.

### 7.3 Gap behavior

The controller maintains a high-water tuple of closed-window end time and all
message IDs observed at that boundary. It advances only after every page has
been parsed and all matching messages have been atomically stored.

Any cursor loop, page-limit exhaustion without continuation, clock regression,
unbounded outage, malformed page, or uncertain boundary sets `POLL_GAP_RISK`.
While that state is active:

- no command is executed;
- already persisted deliveries may continue;
- a local operator alert is raised;
- recovery requires a verified catch-up scan or local acknowledgement.

The design does not claim lossless polling until the Phase 0 evidence passes.

## 8. Normalization, Authorization, and Loop Prevention

For every candidate, the normalizer requires message ID, creation time,
conversation ID, sender user ID, sender open DingTalk ID, message type, and
text. Missing or ambiguous fields cause rejection without execution.

Processing order:

1. Insert the raw message identity and body hash with `SEEN` disposition.
2. Ignore messages whose dual sender IDs match the enrolled current account.
3. Ignore any message ID recorded as a controller outbound message.
4. Ignore non-text messages and text without an exact `/codex` prefix.
5. Require conversation ID plus both enrolled peer identity values.
6. Parse the strict grammar and verify the action catalog.
7. Apply sender and global rate limits.
8. Atomically create one request and one acknowledgement outbox record.

Unauthorized messages are recorded with redacted identifiers and receive no
reply. This avoids both configuration disclosure and reply loops.

## 9. Codex Start Semantics and Concurrency

### 9.1 At-most-once automatic attempt

The controller promises only one automatic `turn/start` attempt per request,
not exactly-once execution. State is committed before the call:

```text
ACCEPTED -> START_INTENT_RECORDED -> START_CALL_IN_FLIGHT
```

If `turn/start` returns a turn ID, it is persisted and the state becomes
`RUNNING`. If the call times out, the process disconnects, or persistence fails
after a possible server acceptance, the state becomes `START_UNKNOWN`.

`START_UNKNOWN` is never retried automatically. The task is quarantined from
new `run` commands until a local operator reconciles it using a Phase 0-verified
thread/turn query. If no reliable query exists, the operator must inspect the
Codex task and explicitly close or adopt the request.

### 9.2 Desktop runtime ownership

The long-running controller connects to `\\.\pipe\codex-ipc`. It initializes as
an IPC client, discovers the live Desktop owner for the exact task, and routes
the start request only to that owner. Service startup does not start a Codex App
Server. The fixed `health-check` path may lazily use the CLI App Server, but that
client is not used by `threads` or `send`.

Only an idle, live-owned target may receive `send`. The Desktop response must
contain a concrete server turn ID; ambiguity enters `START_UNKNOWN` and is
never retried. Completion is read from the target rollout by exact turn ID.
Only a matching `task_complete` becomes the final result; a superseding turn or
explicit abort/interruption becomes `TURN_INTERRUPTED` or `TURN_FAILED`.

## 10. State and Durable Outbox

SQLite uses WAL, foreign keys, busy timeout, and synchronous durability chosen
during implementation testing. Minimum logical records are:

```text
inbound_messages(
  message_id PRIMARY KEY,
  conversation_key_hash,
  sender_key_hash,
  created_at,
  body_sha256,
  disposition,
  request_id UNIQUE,
  recorded_at
)

jobs(
  request_id PRIMARY KEY,
  message_id UNIQUE,
  action_alias,
  prompt_sha256,
  state,
  start_attempted_at,
  codex_turn_id UNIQUE,
  result_path,
  result_sha256,
  accepted_at,
  completed_at,
  observation_time,
  error_code
)

deliveries(
  delivery_id PRIMARY KEY,
  request_id,
  kind,
  target_conversation_hash,
  reference_message_hash,
  reference_sender_hash,
  payload_path,
  payload_sha256,
  payload_codepoints,
  dws_uuid UNIQUE,
  depends_on_delivery_id,
  state,
  lease_owner,
  lease_expires_at,
  attempt_count,
  next_attempt_at,
  automatic_retry_expires_at,
  last_error_code,
  sent_at
)

outbound_messages(
  dws_uuid PRIMARY KEY,
  open_message_id,
  sent_at
)

scan_state(
  channel_key PRIMARY KEY,
  closed_window_end,
  boundary_ids_hash,
  next_cursor,
  state,
  updated_at
)

controller_leases(
  lease_name PRIMARY KEY,
  owner_id,
  expires_at,
  updated_at
)
```

Before any external side effect, the controller commits an immutable intent.
Payload files are written to a temporary file, flushed, renamed atomically,
hashed, and only then referenced by an outbox row. A worker claims rows with a
lease. Summary delivery depends on successful attachment preparation; file
delivery depends on a successful summary when the long-message contract
requires both.

Every visible send receives a new UUID. A retry of that same visible send uses
the original UUID. After the configured automatic retry window or any known
server idempotency limit, unresolved sends move to `DELIVERY_UNKNOWN` and are
not automatically resent.

Sensitive local payload files use user-only ACLs and default seven-day
retention. Logs contain hashes and short redacted suffixes, never message
bodies, Codex output, credentials, or complete identifiers.

Because the MVP admits exactly one enrolled direct conversation and one peer,
delivery recovery reconstructs the conversation and sender from local enrolled
configuration and the reference message from the owning inbox/job record, then
checks all three values against the immutable hashes above. Any changed
enrollment fails closed and requires a newly prepared delivery.

## 11. Job State Machine

```text
SEEN -> IGNORED
SEEN -> REJECTED
SEEN -> ACCEPTED -> ACK_PENDING -> ACK_SENT
ACK_SENT -> START_INTENT_RECORDED -> START_CALL_IN_FLIGHT
                                      |             |
                                      v             v
                                  RUNNING       START_UNKNOWN
                                      |             |
                         +------------+             v
                         v                     LOCAL_REVIEW
                 COMPLETED | FAILED
                         |
                         v
                  RESULT_PREPARED
                         |
                         v
                 RESULT_PENDING -> DELIVERED
                                  -> DELIVERY_UNKNOWN
```

Acknowledgements use precise language:

- `accepted`: persisted but not yet offered to Codex;
- `started`: a turn ID was returned and persisted;
- `unknown`: server acceptance or current state cannot be proved;
- `completed`: a terminal event and persisted result were verified;
- `delivered`: `dws` returned explicit success for every required action.

Unknown is never converted to success by timeout or inference.

## 12. DingTalk Delivery Contract

All text and text attachments produced by this controller use the existing
`dingtalk-chat-assistant` scripts. Because the messages are automatically
generated or combine program and Codex content, the conservative visible
source label is always `【AI生成】`, including deterministic acknowledgements.

Before creating an outbox send, the worker evaluates the outbound authorization
gate in `3.4`. Trusted-recipient delivery repeats the exact person lookup and
dual-ID match required by policy for every send. Ordinary-recipient delivery
creates an immutable `AWAITING_SEND_APPROVAL` preview and cannot pass `--yes`
until a local human approves that exact payload and target. Changing either
invalidates approval. No enrollment flag or DingTalk command can bypass this
check.

Processing order:

1. Write the unwatermarked source to a restricted UTF-8 file.
2. Run `apply_watermark.py --mode generated`.
3. Run `message_metrics.py` on the watermarked final text.
4. Persist the exact final payload, hash, target, reference IDs, and UUID.
5. Send through `dws` with `--format json` and the persisted UUID.
6. Record `SENT` only for an explicit successful response.

At 500 Unicode code points or fewer, send one quoted text reply:

```text
dws chat message reply
  --conversation-id <persisted-conversation-id>
  --ref-msg-id <persisted-source-message-id>
  --ref-sender <persisted-source-open-dingtalk-id>
  --text <watermarked-final-text>
  --uuid <persisted-uuid>
  --yes
  --format json
```

For longer Codex content, prepare a watermarked summary of at most 500 code
points and a watermarked UTF-8 Markdown attachment. Complete shared-space
lookup, file creation, upload, and file metadata lookup before sending the
summary. Persist distinct UUIDs and dependencies for summary and attachment.
If the summary succeeds but the attachment fails, never resend the summary.

Authentication or permission errors stop delivery without bypass. Other
failures receive at most one immediate retry using the same UUID, followed by
scheduled retry only within the configured safe retry window. An ambiguous
send becomes `DELIVERY_UNKNOWN` and is not reported as delivered.

## 13. Windows Operation

Development runs in the foreground. Production-like MVP operation uses a
Windows Scheduled Task under the same user account that owns `dws` and Codex
credentials, with:

- explicit executable paths, working directory, environment, and log path;
- start at user logon and restart on failure;
- a renewable SQLite controller lease with atomic expiry takeover and
  `BEGIN IMMEDIATE` transaction serialization;
- Desktop IPC closure and SQLite lease release on shutdown or orphan detection;
- wake/resume detection followed by a catch-up scan before execution resumes;
- execution disabled after logout, credential expiration, clock regression,
  database errors, disk-pressure threshold, or unbounded catch-up;
- no assumption of continuous operation while the machine sleeps or is off.

Health data includes last complete poll window, poll-gap state, Desktop IPC and
task-catalog availability, task reconciliation state, running request, oldest outbox item,
credential errors, database health, disk free space, and process start time.

Structured logs rotate daily and default to seven-day retention. A local
diagnostic command prints health without secrets or full identifiers. The
runbook covers credential renewal, clearing `POLL_GAP_RISK`, reconciling
`START_UNKNOWN`, handling `DELIVERY_UNKNOWN`, disk recovery, and safe shutdown.

## 14. Failure Policy

| Failure | Required behavior |
| --- | --- |
| `dws` authentication or permission failure | Disable polling and execution; local alert; no bypass |
| read timeout | Retry once; do not advance scan state until a complete page drain |
| cursor loop, missing continuation, or boundary ambiguity | Set `POLL_GAP_RISK`; block execution |
| malformed message or missing identity field | Reject without execution or configuration disclosure |
| duplicate message | Ignore without reply |
| self message in ordinary direct mode, or known outbound message in any mode | Ignore without reply |
| self message in explicitly enrolled self-chat mode | Continue only after exact conversation and dual-ID authorization |
| unauthorized sender or conversation | Ignore and audit a redacted event |
| Codex unavailable before start request | Record failed-to-start; no turn was attempted |
| ambiguous `turn/start` | `START_UNKNOWN`; quarantine task; local reconciliation |
| external or unknown Codex activity | Block new run; reconcile locally |
| Desktop IPC disconnects during start | `START_UNKNOWN`; never retry the start automatically |
| rollout omits terminal state | Preserve running/unknown state; never borrow another turn's output |
| delivery failure within safe retry window | Retry same action with the same UUID according to policy |
| delivery ambiguity or expired retry window | `DELIVERY_UNKNOWN`; no automatic resend |
| SQLite or payload storage unavailable | Stop polling and all external side effects |

## 15. Verification and Acceptance

### 15.1 Phase 0 protocol and permission gates

No command execution is enabled until all of these have evidence:

- sanitized `dws` fixtures prove cursor, ordering, timing, message, and dual-ID
  fields for the enrolled direct chat;
- high-volume, same-time, delayed-index, sleep, and outage cases either catch up
  completely or enter `POLL_GAP_RISK`;
- the controller account's own dual identity is verified;
- quoted replies return a clear success result and expose any useful outbound
  message key without leaking credentials;
- the selected service-account trusted-recipient route or local per-message
  approval route satisfies the outbound delivery policy;
- the Codex executable can resume the exact dedicated task;
- the restricted Codex task cannot access disallowed paths, tools, network
  targets, credentials, or DingTalk operations;
- thread/turn status and restart reconciliation capabilities are documented;
- watermarked 500-code-point boundary behavior is verified with the shipped
  scripts.

Failure of the Codex permission-isolation gate keeps `run` disabled. Failure of
the polling completeness or outbound-authorization gate keeps every command in
observe-only mode.

### 15.2 Automated tests

- strict grammar, Unicode length, and catalog hash verification;
- all combinations of conversation and dual sender identity mismatch;
- self and outbox loop prevention;
- explicit self-chat admission with matching peer/self dual IDs, while known
  outbound message IDs and AI-watermarked output remain non-command inputs;
- cursor page drain, overlapping windows, deduplication, and gap transitions;
- rate limiting and busy-task rejection;
- state-machine invariants and crash points before and after every side effect;
- one automatic `turn/start` attempt under ambiguous failure;
- duplicate/out-of-order App Server events and restart quarantine;
- immutable outbox payload, lease recovery, UUID reuse, retry expiry, and
  summary/attachment dependency;
- watermark and final-text code-point boundaries;
- secret and identifier redaction.

### 15.3 End-to-end acceptance

1. Observe a normal chat message with no reply and no Codex action.
2. Process `help` and return one quoted watermarked reply.
3. Replay the same message and produce no second visible action.
4. Prove unauthorized, incomplete-identity, malformed, and unknown-action
   messages cannot start a turn.
5. Start one harmless fixed action and deliver acknowledgement and result.
6. Crash at every start and delivery boundary and verify no automatic second
   `turn/start`; ambiguous cases enter operator states.
7. Sleep and resume the host; prove catch-up or safe execution blocking.
8. Expire credentials and fill a test disk threshold; prove fail-closed behavior.

Acceptance requires zero unauthorized starts, zero automatic retries of an
ambiguous Codex start, no execution while polling completeness is uncertain,
correct visible watermarks, and traceability from message ID through request,
turn when known, payload hash, UUID, and explicit delivery result.

## 16. Delivery Plan

### Phase 0: evidence only

- Capture sanitized protocol fixtures.
- Validate restricted Codex authority and restart semantics.
- Validate quoted reply and long-message contracts with harmless content.
- Produce a signed-off gate report; do not enable `run`.

### Phase 1: observe-only controller

- Implement polling, normalization, dual-ID authorization, parsing, database,
  gap detection, metrics, and redacted logs.
- Record decisions without sending or starting Codex.

### Phase 2: deterministic local replies

- Enable `help`, verified local `status`, and persisted `result` replies.
- Exercise idempotency and recovery without starting Codex.

### Phase 3: one fixed Codex action

- Enable one low-risk action only after every gate passes.
- Run failure injection and a bounded pilot in the enrolled direct chat.

### Later extensions

- Additional actions, group chat, senders, tasks, or arbitrary natural-language
  prompts each require explicit threat-model and protocol review.
- Enterprise robot Stream input may replace polling later without changing the
  command, authorization, job, Codex, and delivery contracts.

## 17. Final Decisions and Remaining Questions

Final decisions:

- Node.js and SQLite, one process, one instance.
- One direct chat, one dual-ID sender, one dedicated restricted Codex task.
- Fixed action catalog instead of arbitrary remote prompts.
- Cursor-based scoped polling preferred; incompleteness blocks execution.
- One automatic Codex start attempt; ambiguity is permanent until local review.
- Durable immutable outbox and conservative generated watermark for all sends.
- Observe-only and evidence gates before enabling side effects.
- No autonomous current-user reply to an ordinary recipient without exact
  preview confirmation; trusted-recipient automation requires a separate
  deployment identity and the policy's per-send dual-ID verification.

Questions to resolve with Phase 0 evidence:

- Does scoped advanced search provide sufficiently complete and timely command
  retrieval for this account and direct conversation?
- Which exact dual identity fields appear in every relevant inbound message and
  reply response?
- Which App Server method can reconcile a possibly accepted turn after restart?
- Which Codex configuration actually enforces the required workspace and tool
  restrictions on this host?
- What is the observed safe DingTalk UUID retry horizon for this `dws` route?
- Which permitted outbound identity and confirmation route will be used in the
  deployment?

An enrolled self-chat proves the DingTalk account identity, not which physical
device or browser session submitted a command. Any holder of a valid session
for that account can submit the fixed command grammar. This is why the fixed
action catalog, rate limits, dedicated task identity, and `:read-only` Codex
permission remain mandatory before active execution.

These are implementation gates, not assumptions. The design is complete, but
execution mode must remain disabled until the required evidence is recorded.
