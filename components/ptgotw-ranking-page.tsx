"use client";

import {
  closestCenter,
  DndContext,
  DragEndEvent,
  KeyboardSensor,
  MouseSensor,
  TouchSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import Link from "next/link";
import {
  ArrowDown,
  ArrowUp,
  BookOpenText,
  Check,
  CheckCircle2,
  Clock3,
  GripVertical,
  LoaderCircle,
  LockKeyhole,
  RotateCw,
  Save,
  Send,
  Trophy,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { PageHeading } from "@/components/page-heading";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { apiFetch, PTGRankingState, PTGRankingWriteup } from "@/lib/api";
import { createAutosaveQueue } from "@/lib/autosave-queue";
import { moveRanking, ordinal, pointsForPosition } from "@/lib/ptgotw-ranking";

export function PTGOTWRankingPage() {
  const [data, setData] = useState<PTGRankingState | null>(null);
  const [loadError, setLoadError] = useState("");
  const [submitError, setSubmitError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const revisionRef = useRef(0);
  const dataRef = useRef<PTGRankingState | null>(null);

  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 180, tolerance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const applyServerState = useCallback((value: PTGRankingState, preserveOrder = false) => {
    revisionRef.current = value.revision;
    setData(current => preserveOrder && current ? { ...value, writeups: current.writeups } : value);
  }, []);

  const persist = useCallback(async (writeupIds: string[], preserveOrder = true) => {
    const current = dataRef.current;
    const query = current ? `?year=${current.year}` : "";
    const value = await apiFetch<PTGRankingState>(`/ptgotw/rankings/current${query}`, {
      method: "PUT",
      body: JSON.stringify({ writeup_ids: writeupIds, revision: revisionRef.current }),
    });
    applyServerState(value, preserveOrder);
    return value;
  }, [applyServerState]);

  // The queue stores this callback and invokes it only after a user action; its
  // constructor does not read revisionRef or dataRef during render.
  // eslint-disable-next-line react-hooks/refs
  const autosave = useMemo(() => createAutosaveQueue<string[]>(persist), [persist]);
  const autosaveState = useSyncExternalStore(autosave.subscribe, autosave.getSnapshot, autosave.getSnapshot);
  const saveError = autosaveState.error instanceof Error ? autosaveState.error.message : autosaveState.error ? "Could not save your ranking." : "";

  useEffect(() => {
    let cancelled = false;
    apiFetch<PTGRankingState>("/ptgotw/rankings/current")
      .then(value => {
        if (cancelled) return;
        revisionRef.current = value.revision;
        dataRef.current = value;
        setData(value);
      })
      .catch(reason => {
        if (!cancelled) setLoadError(reason instanceof Error ? reason.message : "Could not load rankings.");
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => { dataRef.current = data; }, [data]);

  useEffect(() => {
    if (data?.state !== "open" || !data.closes_at) return;
    let timer: ReturnType<typeof setTimeout>;
    const deadline = new Date(data.closes_at).getTime();
    function scheduleDeadlineLock() {
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        setData(current => current ? { ...current, state: "closed", can_edit: false, can_submit: false } : current);
        return;
      }
      // Recheck hourly so even deadlines months away do not exceed browser
      // timeout limits or remain stale after a system clock adjustment.
      timer = setTimeout(scheduleDeadlineLock, Math.min(remaining, 60 * 60 * 1000));
    }
    scheduleDeadlineLock();
    return () => clearTimeout(timer);
  }, [data?.closes_at, data?.state]);

  useEffect(() => {
    function warnBeforeLeaving(event: BeforeUnloadEvent) {
      if (!autosave.hasUnsavedChanges()) return;
      event.preventDefault();
    }
    window.addEventListener("beforeunload", warnBeforeLeaving);
    return () => window.removeEventListener("beforeunload", warnBeforeLeaving);
  }, [autosave]);

  function updateOrder(next: PTGRankingWriteup[]) {
    if (!data?.can_edit || next.every((item, index) => item.id === data.writeups[index]?.id)) return;
    const nextData: PTGRankingState = {
      ...data,
      writeups: next,
      ballot_status: data.ballot_status === "submitted" ? "draft" : data.ballot_status,
      submitted_at: data.ballot_status === "submitted" ? null : data.submitted_at,
    };
    dataRef.current = nextData;
    setData(nextData);
    autosave.submit(next.map(item => item.id));
  }

  function move(from: number, to: number) {
    if (!data) return;
    updateOrder(moveRanking(data.writeups, from, to));
  }

  function dragEnded(event: DragEndEvent) {
    if (!data || !event.over || event.active.id === event.over.id) return;
    const from = data.writeups.findIndex(item => item.id === event.active.id);
    const to = data.writeups.findIndex(item => item.id === event.over?.id);
    move(from, to);
  }

  async function submit() {
    if (!data) return;
    setSubmitting(true);
    setSubmitError("");
    try {
      // Persist the visible order again so a server-prepended writeup is never
      // omitted from the ballot merely because the manager did not move it.
      const saved = await persist(data.writeups.map(item => item.id), false);
      const submitted = await apiFetch<PTGRankingState>(
        `/ptgotw/rankings/current/submit?year=${saved.year}`,
        { method: "POST", body: JSON.stringify({ revision: saved.revision }) },
      );
      applyServerState(submitted);
      setConfirming(false);
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : "Could not submit your ranking.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loadError) return <StateMessage title="Rankings unavailable" detail={loadError} />;
  if (!data) return <Loading />;

  const readOnly = !data.can_edit;
  const deadline = data.closes_at ? formatDeadline(data.closes_at) : null;
  const canConfirm = data.can_submit && data.writeups.length > 0 && autosaveState.status !== "saving" && autosaveState.status !== "error" && !autosave.hasUnsavedChanges() && !submitting;

  return <>
    <PageHeading eyebrow="Prime Time Game of the Week" title="Rank writeups">
      Put every published writeup in order. Your top five award 5, 4, 3, 2, and 1 point.
    </PageHeading>

    <RankingWindow state={data.state} deadline={deadline} ballotStatus={data.ballot_status} />

    <div className="mb-4 flex min-h-9 flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-slate-500">Drag the handle, use your keyboard, or use the arrow buttons to reorder.</p>
      <SaveIndicator state={autosaveState.status} error={saveError} onRetry={() => void autosave.retry()} />
    </div>

    {data.writeups.length === 0 ? <StateMessage title={`No ${data.year} writeups to rank yet`} detail="Published Weeks 1–12 will appear here automatically." /> : <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={dragEnded}>
      <SortableContext items={data.writeups.map(item => item.id)} strategy={verticalListSortingStrategy}>
        <div className="grid gap-3">
          {data.writeups.map((writeup, index) => <SortableWriteup
            key={writeup.id}
            writeup={writeup}
            position={index + 1}
            disabled={readOnly}
            onMoveUp={() => move(index, index - 1)}
            onMoveDown={() => move(index, index + 1)}
            canMoveUp={!readOnly && index > 0}
            canMoveDown={!readOnly && index < data.writeups.length - 1}
          />)}
        </div>
      </SortableContext>
    </DndContext>}

    <div className="mt-7 flex flex-col items-start justify-between gap-4 rounded-2xl border border-white/8 bg-card p-5 sm:flex-row sm:items-center">
      <div>
        <p className="font-bold text-slate-100">{submissionHeading(data)}</p>
        <p className="mt-1 text-sm text-slate-500">{submissionDetail(data, deadline)}</p>
      </div>
      {data.can_submit && <Button disabled={!canConfirm} onClick={() => { setSubmitError(""); setConfirming(true); }} className="shrink-0">
        <Send className="h-4 w-4" />{data.ballot_status === "submitted" ? "Resubmit rankings" : "Submit rankings"}
      </Button>}
    </div>

    <AlertDialog open={confirming} onOpenChange={open => { if (!submitting) setConfirming(open); }}>
      <AlertDialogContent className="border-white/10 bg-card">
        <AlertDialogHeader>
          <AlertDialogTitle>Submit this ranking?</AlertDialogTitle>
          <AlertDialogDescription>
            Your current first through fifth choices will receive 5, 4, 3, 2, and 1 point. You can edit and resubmit until the deadline.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {submitError && <p role="alert" className="text-sm text-red-300">{submitError}</p>}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction disabled={submitting} onClick={event => { event.preventDefault(); void submit(); }}>
            {submitting ? <><LoaderCircle className="animate-spin" />Submitting…</> : <><Check />Submit rankings</>}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </>;
}

function SortableWriteup({ writeup, position, disabled, onMoveUp, onMoveDown, canMoveUp, canMoveDown }: {
  writeup: PTGRankingWriteup;
  position: number;
  disabled: boolean;
  onMoveUp: () => void;
  onMoveDown: () => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: writeup.id, disabled });
  const { onKeyDown, ...cardDragListeners } = listeners ?? {};
  const points = pointsForPosition(position);
  return <article
    ref={setNodeRef}
    style={{ transform: CSS.Transform.toString(transform), transition }}
    {...cardDragListeners}
    className={`relative flex items-center gap-3 rounded-2xl border p-3 transition-colors sm:gap-4 sm:p-4 ${points ? "border-primary/35 bg-primary/[.075]" : "border-white/8 bg-card"} ${disabled ? "" : "cursor-grab active:cursor-grabbing"} ${isDragging ? "z-10 opacity-80 shadow-2xl ring-2 ring-primary/50" : ""}`}
  >
    <div className={`grid h-12 w-14 shrink-0 place-items-center rounded-xl text-center ${points ? "bg-primary text-primary-foreground" : "bg-white/[.05] text-slate-300"}`}>
      <span><strong className="block text-base leading-4">{ordinal(position)}</strong><span className="mt-1 block text-[10px] font-semibold uppercase tracking-wide">{points ? `${points} pt${points === 1 ? "" : "s"}` : "0 pts"}</span></span>
    </div>
    <button
      type="button"
      disabled={disabled}
      className="touch-none rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-35"
      aria-label={`Drag Week ${writeup.week} to reorder`}
      {...attributes}
      onKeyDown={onKeyDown}
    ><GripVertical className="h-5 w-5" /></button>
    <div className="min-w-0 flex-1">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-bold text-slate-100">Week {writeup.week}</h2>
        {position <= 5 && <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-[11px] font-bold uppercase tracking-wide text-primary"><Trophy className="h-3 w-3" />Scoring</span>}
      </div>
      <p className="mt-1 truncate text-sm text-slate-500">{writeup.author.display_name}</p>
    </div>
    <Link href={`/ptgotw/${writeup.id}`} aria-label={`Read the Week ${writeup.week} writeup`} onMouseDown={event => event.stopPropagation()} onTouchStart={event => event.stopPropagation()} className="inline-flex h-8 w-8 items-center justify-center gap-2 rounded-lg text-sm font-semibold text-slate-400 hover:bg-white/5 hover:text-primary sm:h-auto sm:w-auto sm:px-3 sm:py-2"><BookOpenText className="h-4 w-4" /><span className="hidden sm:inline">Read</span></Link>
    <div className="flex shrink-0 flex-col gap-1 sm:flex-row" onMouseDown={event => event.stopPropagation()} onTouchStart={event => event.stopPropagation()}>
      <Button variant="ghost" size="icon-sm" disabled={!canMoveUp} onClick={onMoveUp} aria-label={`Move Week ${writeup.week} up`}><ArrowUp /></Button>
      <Button variant="ghost" size="icon-sm" disabled={!canMoveDown} onClick={onMoveDown} aria-label={`Move Week ${writeup.week} down`}><ArrowDown /></Button>
    </div>
  </article>;
}

function RankingWindow({ state, deadline, ballotStatus }: { state: PTGRankingState["state"]; deadline: string | null; ballotStatus: PTGRankingState["ballot_status"] }) {
  const config = state === "open"
    ? { icon: Clock3, title: "Rankings are open", detail: deadline ? `Submit by ${deadline}.` : "Submit before the commissioner closes voting.", className: "border-primary/30 bg-primary/[.07] text-primary" }
    : state === "closed"
      ? { icon: LockKeyhole, title: "Rankings are closed", detail: deadline ? `This ranking is read-only. The scheduled deadline was ${deadline}.` : "This ranking is now read-only.", className: "border-slate-600/40 bg-white/[.035] text-slate-300" }
      : { icon: Trophy, title: "Build your ranking now", detail: "Published writeups will be added automatically. Submission opens after Week 12.", className: "border-amber-400/25 bg-amber-400/[.06] text-amber-300" };
  const Icon = config.icon;
  return <section className={`mb-6 flex flex-col justify-between gap-4 rounded-2xl border p-5 sm:flex-row sm:items-center ${config.className}`}>
    <div className="flex items-center gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-black/15"><Icon className="h-5 w-5" /></span><div><h2 className="font-bold">{config.title}</h2><p className="mt-0.5 text-sm opacity-75">{config.detail}</p></div></div>
    <span className="inline-flex w-fit items-center gap-2 rounded-full border border-current/20 px-3 py-1.5 text-xs font-bold uppercase tracking-wide"><CheckCircle2 className="h-4 w-4" />{ballotStatus.replace("_", " ")}</span>
  </section>;
}

function SaveIndicator({ state, error, onRetry }: { state: "idle" | "saving" | "saved" | "error"; error: string; onRetry: () => void }) {
  if (state === "saving") return <span role="status" className="inline-flex items-center gap-2 text-sm text-slate-400"><LoaderCircle className="h-4 w-4 animate-spin" />Saving…</span>;
  if (state === "saved") return <span role="status" className="inline-flex items-center gap-2 text-sm text-emerald-400"><Save className="h-4 w-4" />Saved</span>;
  if (state === "error") return <span role="alert" className="inline-flex flex-wrap items-center justify-end gap-2 text-sm text-red-300"><span>{error || "Could not save."}</span><Button variant="outline" size="xs" onClick={onRetry}><RotateCw />Retry</Button></span>;
  return null;
}

function submissionHeading(data: PTGRankingState) {
  if (data.state === "closed") return data.ballot_status === "submitted" ? "Your final ranking was submitted" : "Your ranking was not submitted";
  if (data.ballot_status === "submitted") return "Your ranking is submitted";
  return data.state === "open" ? "Ready to make it official?" : "Submission is not open yet";
}

function submissionDetail(data: PTGRankingState, deadline: string | null) {
  if (data.state === "closed") return "The saved order is read-only.";
  if (data.ballot_status === "submitted") return `You may still edit and resubmit${deadline ? ` until ${deadline}` : " while voting remains open"}.`;
  if (data.state === "open") return deadline ? `Submit before ${deadline}.` : "Submit before voting closes.";
  return "Keep arranging writeups as they are published.";
}

function formatDeadline(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Chicago",
    timeZoneName: "short",
  }).format(new Date(value));
}

function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function StateMessage({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-9 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mt-2 text-sm text-slate-400">{detail}</p></div>; }
