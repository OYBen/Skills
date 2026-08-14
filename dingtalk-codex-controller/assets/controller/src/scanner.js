import { drainCommandPages } from "./dws-client.js";
import { processRawMessage } from "./processor.js";
import { hashIdentifier, sha256 } from "./util.js";

export async function scanOnce(context, options = {}) {
  const { config, store, dwsClient } = context;
  const now = options.now ?? new Date();
  const delayMs = (config.closedWindowDelaySeconds ?? 10) * 1000;
  const overlapMs = (config.overlapSeconds ?? 300) * 1000;
  const closedEnd = new Date(now.getTime() - delayMs);
  const channelKey = hashIdentifier(config.channel.conversationId);
  const previous = store.getScanState(channelKey);
  const previousEnd = previous?.closed_window_end ? new Date(previous.closed_window_end) : null;
  const maxCatchUpMs = (config.limits?.maxCatchUpSeconds ?? 3600) * 1000;
  const start = previousEnd
    ? new Date(previousEnd.getTime() - overlapMs)
    : new Date(closedEnd.getTime() - overlapMs);

  if (previousEnd && closedEnd < previousEnd) {
    store.setScanState(channelKey, "POLL_GAP_RISK", { closedWindowEnd: previous.closed_window_end });
    return { status: "POLL_GAP_RISK", reason: "CLOCK_REGRESSION", processed: [] };
  }
  if (previousEnd && closedEnd.getTime() - previousEnd.getTime() > maxCatchUpMs) {
    store.setScanState(channelKey, "POLL_GAP_RISK", { closedWindowEnd: previous.closed_window_end });
    store.audit("POLL_GAP_RISK", { code: "CATCH_UP_WINDOW_EXCEEDED" });
    return { status: "POLL_GAP_RISK", reason: "CATCH_UP_WINDOW_EXCEEDED", processed: [] };
  }

  try {
    const drained = await drainCommandPages(dwsClient, {
      conversationId: config.channel.conversationId,
      start: start.toISOString(),
      end: closedEnd.toISOString(),
      limit: config.limits?.pageSize ?? 100,
      cursor: "0"
    }, { maxPages: config.limits?.maxPagesPerScan ?? 100 });
    const sorted = [...drained.items].sort((a, b) => {
      const ta = String(a.createTime ?? a.createdAt ?? a.timestamp ?? "");
      const tb = String(b.createTime ?? b.createdAt ?? b.timestamp ?? "");
      return ta.localeCompare(tb) || String(a.openMessageId ?? a.messageId ?? "").localeCompare(String(b.openMessageId ?? b.messageId ?? ""));
    });
    const processed = [];
    for (const raw of sorted) processed.push(await processRawMessage(raw, context));
    const commit = () => {
      const boundaryIds = sorted
        .filter((raw) => String(raw.createTime ?? raw.createdAt ?? raw.timestamp ?? "").startsWith(closedEnd.toISOString().slice(0, 19)))
        .map((raw) => String(raw.openMessageId ?? raw.messageId ?? ""))
        .sort();
      store.setScanState(channelKey, "COMPLETE", {
        closedWindowEnd: closedEnd.toISOString(),
        boundaryIdsHash: sha256(boundaryIds.join("\n")),
        nextCursor: null
      });
      return { status: "COMPLETE", pages: drained.pages, fetched: sorted.length, processed };
    };
    if (context.leaseTransaction) return context.leaseTransaction(commit);
    context.assertLease?.();
    return store.transaction(commit);
  } catch (error) {
    if (error.code === "CONTROLLER_LEASE_LOST") throw error;
    store.setScanState(channelKey, "POLL_GAP_RISK", {
      closedWindowEnd: previous?.closed_window_end ?? null,
      nextCursor: previous?.next_cursor ?? null
    });
    store.audit("POLL_GAP_RISK", { code: error.code ?? "SCAN_FAILED" });
    return { status: "POLL_GAP_RISK", reason: error.code ?? "SCAN_FAILED", processed: [] };
  }
}
