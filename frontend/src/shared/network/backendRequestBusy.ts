import { useSyncExternalStore } from "react";

type Listener = () => void;

const listeners = new Set<Listener>();
let pendingRequestCount = 0;
let suppressBusyDepth = 0;

const emit = () => {
  for (const listener of listeners) listener();
};

export const subscribeBackendRequestBusy = (listener: Listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const getBackendRequestBusySnapshot = () => pendingRequestCount > 0;

export function beginBackendRequest() {
  if (suppressBusyDepth > 0) {
    return () => undefined;
  }

  pendingRequestCount += 1;
  emit();

  let finished = false;
  return () => {
    if (finished) return;
    finished = true;
    pendingRequestCount = Math.max(0, pendingRequestCount - 1);
    emit();
  };
}

export function runWithoutBackendRequestBusy<T>(callback: () => T): T {
  suppressBusyDepth += 1;
  try {
    return callback();
  } finally {
    suppressBusyDepth = Math.max(0, suppressBusyDepth - 1);
  }
}

export function useBackendRequestBusy() {
  return useSyncExternalStore(
    subscribeBackendRequestBusy,
    getBackendRequestBusySnapshot,
    () => false,
  );
}
