import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { hashIdentifier, isoNow, newRequestId, sha256 } from "./util.js";
import { ControllerError } from "./errors.js";

const SCHEMA = `
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = FULL;

CREATE TABLE IF NOT EXISTS inbound_messages (
  message_id TEXT PRIMARY KEY,
  conversation_key_hash TEXT NOT NULL,
  sender_key_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  body_sha256 TEXT NOT NULL,
  disposition TEXT NOT NULL,
  request_id TEXT UNIQUE,
  recorded_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  request_id TEXT PRIMARY KEY,
  message_id TEXT NOT NULL UNIQUE REFERENCES inbound_messages(message_id),
  action_alias TEXT,
  prompt_sha256 TEXT,
  command TEXT NOT NULL,
  state TEXT NOT NULL,
  start_attempted_at TEXT,
  codex_turn_id TEXT UNIQUE,
  result_path TEXT,
  result_sha256 TEXT,
  accepted_at TEXT NOT NULL,
  completed_at TEXT,
  observation_time TEXT NOT NULL,
  error_code TEXT
);

CREATE TABLE IF NOT EXISTS deliveries (
  delivery_id TEXT PRIMARY KEY,
  request_id TEXT REFERENCES jobs(request_id),
  kind TEXT NOT NULL,
  target_conversation_hash TEXT NOT NULL,
  reference_message_hash TEXT NOT NULL,
  reference_sender_hash TEXT NOT NULL,
  payload_path TEXT,
  payload_sha256 TEXT,
  payload_codepoints INTEGER,
  dws_uuid TEXT NOT NULL UNIQUE,
  depends_on_delivery_id TEXT REFERENCES deliveries(delivery_id),
  state TEXT NOT NULL,
  lease_owner TEXT,
  lease_expires_at TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  automatic_retry_expires_at TEXT,
  last_error_code TEXT,
  sent_at TEXT
);

CREATE TABLE IF NOT EXISTS outbound_messages (
  dws_uuid TEXT PRIMARY KEY,
  open_message_id_hash TEXT,
  sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scan_state (
  channel_key TEXT PRIMARY KEY,
  closed_window_end TEXT,
  boundary_ids_hash TEXT,
  next_cursor TEXT,
  state TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  event_id TEXT PRIMARY KEY,
  request_id TEXT,
  event_type TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS controller_leases (
  lease_name TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS controller_bindings (
  conversation_key_hash TEXT PRIMARY KEY,
  target_thread_id TEXT,
  watch_thread_id TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thread_selections (
  conversation_key_hash TEXT NOT NULL,
  selection_number INTEGER NOT NULL,
  thread_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  PRIMARY KEY (conversation_key_hash, selection_number)
);
`;

export class Store {
  constructor(databasePath, options = {}) {
    if (databasePath !== ":memory:") mkdirSync(path.dirname(databasePath), { recursive: true });
    this.clock = options.clock ?? (() => new Date());
    this.db = new DatabaseSync(databasePath);
    this.db.exec(SCHEMA);
    this.ensureColumn("jobs", "requested_request_id", "TEXT");
    this.ensureColumn("jobs", "target_thread_id", "TEXT");
    this.ensureColumn("jobs", "instruction_path", "TEXT");
    this.ensureColumn("jobs", "instruction_sha256", "TEXT");
    this.ensureColumn("jobs", "thread_page", "INTEGER");
    this.ensureColumn("jobs", "target_selector", "TEXT");
    this.ensureColumn("jobs", "watch_thread_id", "TEXT");
    this.ensureColumn("jobs", "queue_reason", "TEXT");
    this.transactionDepth = 0;
  }

  ensureColumn(table, column, type) {
    const columns = this.db.prepare(`PRAGMA table_info(${table})`).all();
    if (!columns.some((item) => item.name === column)) {
      this.db.exec(`ALTER TABLE ${table} ADD COLUMN ${column} ${type}`);
    }
  }

  close() { this.db.close(); }

  transaction(callback) {
    if (this.transactionDepth > 0) return callback();
    this.db.exec("BEGIN IMMEDIATE");
    this.transactionDepth += 1;
    try {
      const result = callback();
      this.db.exec("COMMIT");
      return result;
    } catch (error) {
      this.db.exec("ROLLBACK");
      throw error;
    } finally {
      this.transactionDepth -= 1;
    }
  }

  hasMessage(messageId) {
    return Boolean(this.db.prepare("SELECT 1 FROM inbound_messages WHERE message_id = ?").get(messageId));
  }

  hasOutboundMessage(messageId) {
    const digest = hashIdentifier(messageId);
    return Boolean(this.db.prepare("SELECT 1 FROM outbound_messages WHERE open_message_id_hash = ?").get(digest));
  }

  recordOutboundMessage(dwsUuid, messageId) {
    this.db.prepare(`
      INSERT OR IGNORE INTO outbound_messages(dws_uuid, open_message_id_hash, sent_at)
      VALUES (?, ?, ?)
    `).run(dwsUuid, hashIdentifier(messageId), isoNow(this.clock));
  }

  acceptedCountSince(sinceIso) {
    return Number(this.db.prepare("SELECT COUNT(*) AS count FROM jobs WHERE accepted_at >= ?").get(sinceIso).count);
  }

  recordDisposition(message, disposition) {
    const now = isoNow(this.clock);
    const result = this.db.prepare(`
      INSERT OR IGNORE INTO inbound_messages
      (message_id, conversation_key_hash, sender_key_hash, created_at, body_sha256, disposition, recorded_at)
      VALUES (?, ?, ?, ?, ?, ?, ?)
    `).run(
      message.messageId,
      hashIdentifier(message.conversationId),
      hashIdentifier(`${message.senderUserId}:${message.senderOpenDingTalkId}`),
      message.createdAt,
      sha256(message.text),
      disposition,
      now
    );
    return result.changes === 1;
  }

  acceptCommand(message, parsed, action = null, initialState = "OBSERVED", values = {}) {
    return this.transaction(() => {
      if (this.hasMessage(message.messageId)) return { duplicate: true };
      const now = isoNow(this.clock);
      const requestId = values.requestId ?? newRequestId(this.clock);
      this.db.prepare(`
        INSERT INTO inbound_messages
        (message_id, conversation_key_hash, sender_key_hash, created_at, body_sha256, disposition, request_id, recorded_at)
        VALUES (?, ?, ?, ?, ?, 'ACCEPTED_OBSERVE', ?, ?)
      `).run(
        message.messageId,
        hashIdentifier(message.conversationId),
        hashIdentifier(`${message.senderUserId}:${message.senderOpenDingTalkId}`),
        message.createdAt,
        sha256(message.text),
        requestId,
        now
      );
      this.db.prepare(`
        INSERT INTO jobs
        (request_id, message_id, action_alias, prompt_sha256, command, state,
         accepted_at, observation_time, requested_request_id, target_thread_id,
         instruction_path, instruction_sha256, thread_page, target_selector,
         watch_thread_id, queue_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).run(
        requestId, message.messageId, parsed.actionAlias ?? null,
        action?.promptSha256 ?? null, parsed.command, initialState, now, now,
        parsed.requestId ?? null, parsed.targetThreadId ?? null,
        values.instructionPath ?? null, values.instructionSha256 ?? null,
        parsed.page ?? null, parsed.targetSelector ?? null,
        parsed.watchThreadId ?? null, null
      );
      return { duplicate: false, requestId, state: initialState };
    });
  }

  setScanState(channelKey, state, values = {}) {
    const now = isoNow(this.clock);
    this.db.prepare(`
      INSERT INTO scan_state(channel_key, closed_window_end, boundary_ids_hash, next_cursor, state, updated_at)
      VALUES (?, ?, ?, ?, ?, ?)
      ON CONFLICT(channel_key) DO UPDATE SET
        closed_window_end = excluded.closed_window_end,
        boundary_ids_hash = excluded.boundary_ids_hash,
        next_cursor = excluded.next_cursor,
        state = excluded.state,
        updated_at = excluded.updated_at
    `).run(channelKey, values.closedWindowEnd ?? null, values.boundaryIdsHash ?? null, values.nextCursor ?? null, state, now);
  }

  getScanState(channelKey) {
    return this.db.prepare("SELECT * FROM scan_state WHERE channel_key = ?").get(channelKey) ?? null;
  }

  audit(eventType, details = {}, requestId = null) {
    this.db.prepare(`
      INSERT INTO audit_events(event_id, request_id, event_type, details_json, created_at)
      VALUES (?, ?, ?, ?, ?)
    `).run(randomUUID(), requestId, eventType, JSON.stringify(details), isoNow(this.clock));
  }

  health() {
    const counts = {};
    for (const table of ["inbound_messages", "jobs", "deliveries", "audit_events"]) {
      counts[table] = Number(this.db.prepare(`SELECT COUNT(*) AS count FROM ${table}`).get().count);
    }
    return {
      counts,
      scans: this.db.prepare("SELECT channel_key, closed_window_end, state, updated_at FROM scan_state").all()
    };
  }

  getJob(requestId) {
    return this.db.prepare("SELECT * FROM jobs WHERE request_id = ?").get(requestId) ?? null;
  }

  listJobsByStates(states, limit = 100) {
    if (!Array.isArray(states) || states.length === 0) return [];
    const placeholders = states.map(() => "?").join(", ");
    return this.db.prepare(`
      SELECT * FROM jobs WHERE state IN (${placeholders})
      ORDER BY accepted_at ASC LIMIT ?
    `).all(...states, limit);
  }

  latestJob(options = {}) {
    const excludedRequestId = options.excludeRequestId ?? null;
    return excludedRequestId
      ? this.db.prepare("SELECT * FROM jobs WHERE request_id <> ? ORDER BY accepted_at DESC LIMIT 1").get(excludedRequestId) ?? null
      : this.db.prepare("SELECT * FROM jobs ORDER BY accepted_at DESC LIMIT 1").get() ?? null;
  }

  getBinding(conversationId) {
    return this.db.prepare(`
      SELECT target_thread_id, watch_thread_id, updated_at
      FROM controller_bindings WHERE conversation_key_hash = ?
    `).get(hashIdentifier(conversationId)) ?? null;
  }

  setBinding(conversationId, values = {}) {
    const key = hashIdentifier(conversationId);
    const current = this.getBinding(conversationId) ?? {};
    const targetThreadId = Object.hasOwn(values, "targetThreadId") ? values.targetThreadId : current.target_thread_id ?? null;
    const watchThreadId = Object.hasOwn(values, "watchThreadId") ? values.watchThreadId : current.watch_thread_id ?? null;
    this.db.prepare(`
      INSERT INTO controller_bindings(conversation_key_hash, target_thread_id, watch_thread_id, updated_at)
      VALUES (?, ?, ?, ?)
      ON CONFLICT(conversation_key_hash) DO UPDATE SET
        target_thread_id = excluded.target_thread_id,
        watch_thread_id = excluded.watch_thread_id,
        updated_at = excluded.updated_at
    `).run(key, targetThreadId, watchThreadId, isoNow(this.clock));
    return { target_thread_id: targetThreadId, watch_thread_id: watchThreadId };
  }

  saveThreadSelections(conversationId, selections, ttlSeconds = 3600) {
    const key = hashIdentifier(conversationId);
    const createdAt = isoNow(this.clock);
    const expiresAt = new Date(this.clock().getTime() + ttlSeconds * 1000).toISOString();
    return this.transaction(() => {
      this.db.prepare("DELETE FROM thread_selections WHERE conversation_key_hash = ?").run(key);
      const insert = this.db.prepare(`
        INSERT INTO thread_selections(conversation_key_hash, selection_number, thread_id, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
      `);
      for (const selection of selections) {
        insert.run(key, selection.number, selection.threadId, createdAt, expiresAt);
      }
      return selections.length;
    });
  }

  getThreadSelection(conversationId, selectionNumber) {
    const row = this.db.prepare(`
      SELECT thread_id FROM thread_selections
      WHERE conversation_key_hash = ? AND selection_number = ? AND expires_at > ?
    `).get(hashIdentifier(conversationId), selectionNumber, isoNow(this.clock));
    return row?.thread_id ?? null;
  }

  queuePosition(requestId) {
    const row = this.db.prepare(`
      SELECT COUNT(*) AS position FROM jobs
      WHERE state = 'QUEUED' AND accepted_at <= (SELECT accepted_at FROM jobs WHERE request_id = ?)
    `).get(requestId);
    return Number(row?.position ?? 0);
  }

  queuedJobs(limit = 20) {
    return this.db.prepare(`
      SELECT * FROM jobs WHERE state = 'QUEUED' ORDER BY accepted_at ASC LIMIT ?
    `).all(limit);
  }

  cancelQueuedJob(requestId = null) {
    const job = requestId
      ? this.db.prepare("SELECT * FROM jobs WHERE request_id = ? AND state = 'QUEUED'").get(requestId)
      : this.db.prepare("SELECT * FROM jobs WHERE state = 'QUEUED' ORDER BY accepted_at DESC LIMIT 1").get();
    if (!job) return null;
    return this.transitionJob(job.request_id, "QUEUED", "CANCELED", {
      completed_at: isoNow(this.clock), error_code: "CANCELED_BY_USER"
    }) ? { ...job, state: "CANCELED" } : null;
  }

  transitionJob(requestId, expectedState, nextState, values = {}) {
    const allowedColumns = new Set([
      "start_attempted_at", "codex_turn_id", "result_path", "result_sha256",
      "completed_at", "observation_time", "error_code", "target_thread_id",
      "watch_thread_id", "queue_reason"
    ]);
    const assignments = ["state = ?"];
    const parameters = [nextState];
    for (const [column, value] of Object.entries(values)) {
      if (!allowedColumns.has(column)) throw new Error(`Unsupported job column: ${column}`);
      assignments.push(`${column} = ?`);
      parameters.push(value);
    }
    parameters.push(requestId, expectedState);
    const result = this.db.prepare(`
      UPDATE jobs SET ${assignments.join(", ")} WHERE request_id = ? AND state = ?
    `).run(...parameters);
    return result.changes === 1;
  }

  createDelivery(values) {
    const deliveryId = values.deliveryId ?? randomUUID();
    const dwsUuid = values.dwsUuid ?? randomUUID();
    this.db.prepare(`
      INSERT INTO deliveries(
        delivery_id, request_id, kind, target_conversation_hash,
        reference_message_hash, reference_sender_hash, payload_path,
        payload_sha256, payload_codepoints, dws_uuid, depends_on_delivery_id,
        state, automatic_retry_expires_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).run(
      deliveryId,
      values.requestId ?? null,
      values.kind,
      hashIdentifier(values.targetConversationId),
      hashIdentifier(values.referenceMessageId),
      hashIdentifier(values.referenceSenderId),
      values.payloadPath,
      values.payloadSha256,
      values.payloadCodepoints,
      dwsUuid,
      values.dependsOnDeliveryId ?? null,
      values.state ?? "AWAITING_SEND_APPROVAL",
      values.automaticRetryExpiresAt ?? null
    );
    return { deliveryId, dwsUuid };
  }

  getDelivery(deliveryId) {
    return this.db.prepare("SELECT * FROM deliveries WHERE delivery_id = ?").get(deliveryId) ?? null;
  }

  getDeliveryForRequest(requestId, kind) {
    return this.db.prepare(`
      SELECT * FROM deliveries WHERE request_id = ? AND kind = ?
      ORDER BY rowid DESC LIMIT 1
    `).get(requestId, kind) ?? null;
  }

  listDeliveriesByStates(states, limit = 100) {
    if (!Array.isArray(states) || states.length === 0) return [];
    const placeholders = states.map(() => "?").join(", ");
    return this.db.prepare(`
      SELECT * FROM deliveries WHERE state IN (${placeholders})
      ORDER BY rowid ASC LIMIT ?
    `).all(...states, limit);
  }

  transitionDelivery(deliveryId, expectedState, nextState, values = {}) {
    const allowedColumns = new Set([
      "attempt_count", "last_error_code", "sent_at", "open_message_id_hash"
    ]);
    const assignments = ["state = ?"];
    const parameters = [nextState];
    for (const [column, value] of Object.entries(values)) {
      if (column === "open_message_id_hash") continue;
      if (!allowedColumns.has(column)) throw new Error(`Unsupported delivery column: ${column}`);
      assignments.push(`${column} = ?`);
      parameters.push(value);
    }
    parameters.push(deliveryId, expectedState);
    return this.db.prepare(`
      UPDATE deliveries SET ${assignments.join(", ")}
      WHERE delivery_id = ? AND state = ?
    `).run(...parameters).changes === 1;
  }

  recoverInFlightStates() {
    return this.transaction(() => {
      const jobs = this.db.prepare(`
        UPDATE jobs SET state = 'START_UNKNOWN', error_code = 'RECOVERED_AFTER_CRASH'
        WHERE state IN ('START_INTENT_RECORDED', 'START_CALL_IN_FLIGHT')
      `).run().changes;
      const deliveries = this.db.prepare(`
        UPDATE deliveries SET state = 'DELIVERY_UNKNOWN', last_error_code = 'RECOVERED_AFTER_CRASH'
        WHERE state = 'SEND_CALL_IN_FLIGHT'
      `).run().changes;
      if (jobs > 0 || deliveries > 0) {
        this.audit("IN_FLIGHT_RECOVERED", { jobs, deliveries });
      }
      return { jobs, deliveries };
    });
  }

  acquireLease(leaseName, ownerId, ttlSeconds) {
    return this.transaction(() => {
      const now = isoNow(this.clock);
      const expiresAt = new Date(this.clock().getTime() + ttlSeconds * 1000).toISOString();
      const current = this.db.prepare("SELECT owner_id, expires_at FROM controller_leases WHERE lease_name = ?").get(leaseName);
      if (current && current.owner_id !== ownerId && current.expires_at > now) return false;
      this.db.prepare(`
        INSERT INTO controller_leases(lease_name, owner_id, expires_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(lease_name) DO UPDATE SET
          owner_id = excluded.owner_id,
          expires_at = excluded.expires_at,
          updated_at = excluded.updated_at
      `).run(leaseName, ownerId, expiresAt, now);
      return true;
    });
  }

  renewLease(leaseName, ownerId, ttlSeconds) {
    const now = isoNow(this.clock);
    const expiresAt = new Date(this.clock().getTime() + ttlSeconds * 1000).toISOString();
    const result = this.db.prepare(`
      UPDATE controller_leases SET expires_at = ?, updated_at = ?
      WHERE lease_name = ? AND owner_id = ? AND expires_at > ?
    `).run(expiresAt, now, leaseName, ownerId, now);
    return result.changes === 1;
  }

  isLeaseHeld(leaseName, ownerId) {
    const now = isoNow(this.clock);
    return Boolean(this.db.prepare(`
      SELECT 1 FROM controller_leases
      WHERE lease_name = ? AND owner_id = ? AND expires_at > ?
    `).get(leaseName, ownerId, now));
  }

  releaseLease(leaseName, ownerId) {
    return this.db.prepare("DELETE FROM controller_leases WHERE lease_name = ? AND owner_id = ?")
      .run(leaseName, ownerId).changes === 1;
  }

  withLeaseTransaction(leaseName, ownerId, callback) {
    return this.transaction(() => {
      const now = isoNow(this.clock);
      const held = this.db.prepare(`
        SELECT 1 FROM controller_leases
        WHERE lease_name = ? AND owner_id = ? AND expires_at > ?
      `).get(leaseName, ownerId, now);
      if (!held) {
        throw new ControllerError("CONTROLLER_LEASE_LOST", "Controller database lease is no longer held");
      }
      return callback();
    });
  }
}
