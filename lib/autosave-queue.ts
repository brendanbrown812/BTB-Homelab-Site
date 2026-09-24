export type AutosaveState = {
  status: "idle" | "saving" | "saved" | "error";
  error: unknown;
};

// Only one write can be in flight. Changes made during a write replace the
// pending snapshot, which is sent after the current request has completed.
export function createAutosaveQueue<T>(save: (value: T) => Promise<unknown>) {
  let pending: { value: T } | null = null;
  let running = false;
  let state: AutosaveState = { status: "idle", error: null };
  const listeners = new Set<() => void>();
  function publish(next: AutosaveState) {
    state = next;
    listeners.forEach(listener => listener());
  }
  async function flush() {
    if (running || !pending) return;
    running = true;
    publish({ status: "saving", error: null });
    try {
      while (pending) {
        const snapshot: { value: T } = pending;
        await save(snapshot.value);
        if (pending === snapshot) pending = null;
      }
      publish({ status: "saved", error: null });
    } catch (error) {
      // Retain the latest snapshot so Retry never sends an older selection.
      publish({ status: "error", error });
    } finally {
      running = false;
    }
  }
  return {
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => state,
    hasUnsavedChanges: () => pending !== null,
    submit(value: T) { pending = { value }; void flush(); },
    retry: flush,
  };
}
