import { randomUUID } from "node:crypto";
import { ControllerError } from "./errors.js";

export function acquireControllerLease(store, options = {}) {
  const leaseName = options.leaseName ?? "controller";
  const ownerId = options.ownerId ?? randomUUID();
  const ttlSeconds = options.ttlSeconds ?? 60;
  const heartbeatMilliseconds = options.heartbeatMilliseconds ?? Math.max(1000, Math.floor(ttlSeconds * 1000 / 3));
  if (!store.acquireLease(leaseName, ownerId, ttlSeconds)) {
    throw new ControllerError("INSTANCE_ALREADY_RUNNING", "Another controller holds the database lease");
  }

  let released = false;
  let lost = false;
  const timer = setInterval(() => {
    try {
      if (!store.renewLease(leaseName, ownerId, ttlSeconds)) lost = true;
    } catch {
      lost = true;
    }
  }, heartbeatMilliseconds);
  timer.unref?.();

  return {
    ownerId,
    assertHeld() {
      if (released || lost || !store.isLeaseHeld(leaseName, ownerId)) {
        lost = true;
        throw new ControllerError("CONTROLLER_LEASE_LOST", "Controller database lease is no longer held");
      }
    },
    transaction(callback) {
      if (released || lost) {
        throw new ControllerError("CONTROLLER_LEASE_LOST", "Controller database lease is no longer held");
      }
      try {
        return store.withLeaseTransaction(leaseName, ownerId, callback);
      } catch (error) {
        if (error.code === "CONTROLLER_LEASE_LOST") lost = true;
        throw error;
      }
    },
    release() {
      if (released) return;
      released = true;
      clearInterval(timer);
      store.releaseLease(leaseName, ownerId);
    }
  };
}
