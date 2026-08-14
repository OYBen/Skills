import { ControllerError } from "./errors.js";

export function summarizeThreadForReconciliation(response, expectedThreadId) {
  const thread = response?.thread ?? response;
  if (!thread || thread.id !== expectedThreadId) {
    throw new ControllerError("THREAD_ID_MISMATCH", "Codex returned a different thread");
  }
  const turns = Array.isArray(thread.turns) ? thread.turns : [];
  return {
    threadIdMatches: true,
    runtimeStatus: thread.status ?? null,
    turns: turns.map((turn) => ({
      id: turn.id ?? null,
      status: turn.status ?? null,
      startedAt: turn.startedAt ?? null,
      completedAt: turn.completedAt ?? null,
      errorPresent: Boolean(turn.error)
    })),
    contentOmitted: true
  };
}

export async function reconcileUnknownStart(context) {
  const { store, codexClient, requestId, threadId, attemptedAfter, attemptedBefore } = context;
  const job = store.getJob(requestId);
  if (!job || job.state !== "START_UNKNOWN") {
    throw new ControllerError("JOB_STATE", "Only START_UNKNOWN jobs can be reconciled");
  }
  const response = await codexClient.readThread(threadId, true);
  const summary = summarizeThreadForReconciliation(response, threadId);
  const lower = new Date(attemptedAfter ?? job.start_attempted_at).getTime();
  const upper = new Date(attemptedBefore ?? new Date(lower + 60_000)).getTime();
  const candidates = summary.turns.filter((turn) => {
    const started = turn.startedAt ? new Date(turn.startedAt).getTime() : Number.NaN;
    return Number.isFinite(started) && started >= lower && started <= upper;
  });
  return {
    status: candidates.length === 1 ? "SINGLE_TIME_CANDIDATE" : candidates.length === 0 ? "NO_TIME_CANDIDATE" : "AMBIGUOUS_TIME_CANDIDATES",
    candidateTurnIds: candidates.map((turn) => turn.id),
    automaticAdoptionAllowed: false,
    summary
  };
}
