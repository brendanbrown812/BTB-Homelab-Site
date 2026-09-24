export type DraftSaveState = { status: "idle" | "waiting" | "saving" | "saved" | "error"; error: unknown; dirty: boolean; publishing: boolean };

// One session owns one editor entry, including its initial POST and later PUTs.
export function createDraftAutosave<T>(options: {
  initial: T;
  save: (value: T, publish?: boolean) => Promise<void>;
  remember: (value: T) => void;
  forget: (value: T) => void;
  delay?: number;
}) {
  let latest = options.initial;
  let revision = 0, savedRevision = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let flight: Promise<void> | null = null;
  let manual = false, disposed = false;
  let state: DraftSaveState = { status: "idle", error: null, dirty: false, publishing: false };
  const listeners = new Set<() => void>();
  function emit(status: DraftSaveState["status"], error: unknown = null) {
    state = { status, error, dirty: revision !== savedRevision, publishing: manual };
    listeners.forEach(listener => listener());
  }
  async function work() {
    try {
      while (revision !== savedRevision && !manual && !disposed) {
        const sendingRevision = revision;
        const snapshot = latest;
        emit("saving");
        await options.save(snapshot);
        savedRevision = sendingRevision;
        if (revision === savedRevision) options.forget(snapshot);
      }
      emit(revision === savedRevision ? "saved" : "waiting");
    } catch (error) { emit("error", error); }
  }
  function flush() {
    clearTimeout(timer);
    if (flight) return flight;
    if (manual || disposed || revision === savedRevision) return Promise.resolve();
    flight = work().finally(() => { flight = null; });
    return flight;
  }
  return {
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    getSnapshot: () => state,
    edit(value: T) {
      if (manual || disposed) return;
      latest = value;
      revision++;
      options.remember(value);
      emit(flight ? "saving" : "waiting");
      clearTimeout(timer);
      timer = setTimeout(() => void flush(), options.delay ?? 2000);
    },
    flush,
    async saveExplicit(publish: boolean) {
      if (manual || disposed) return false;
      manual = true;
      clearTimeout(timer);
      emit("saving");
      if (flight) await flight;
      try {
        emit("saving");
        await options.save(latest, publish);
        savedRevision = revision;
        options.forget(latest);
        manual = false;
        emit("saved");
        return true;
      } catch (error) {
        manual = false;
        emit("error", error);
        return false;
      }
    },
    dispose() { disposed = true; clearTimeout(timer); },
    resume() { disposed = false; },
  };
}
