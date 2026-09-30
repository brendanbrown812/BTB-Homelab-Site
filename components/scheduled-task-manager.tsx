"use client";

import { Clock3, Eye, LoaderCircle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { apiFetch, ScheduledTaskState } from "@/lib/api";


function formatDate(value: string | null) {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}


function resultLabel(key: string) {
  return key.replaceAll("_", " ").replace(/^./, value => value.toUpperCase());
}


function resultValue(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}


function TaskDetails({ task }: { task: ScheduledTaskState }) {
  const run = task.last_run;
  return <Dialog>
    <DialogTrigger asChild>
      <Button variant="outline" size="sm"><Eye className="h-4 w-4" />View details</Button>
    </DialogTrigger>
    <DialogContent className="max-h-[85vh] overflow-y-auto border-white/10 bg-card sm:max-w-xl">
      <DialogHeader>
        <DialogTitle>{task.description}</DialogTitle>
        <DialogDescription>Latest recorded execution. Viewing this does not run the task again.</DialogDescription>
      </DialogHeader>
      {!run ? <p className="rounded-xl bg-white/[.03] p-4 text-sm text-slate-400">This task has not run yet.</p> : <div className="space-y-5">
        <div className="grid gap-3 rounded-xl bg-white/[.03] p-4 sm:grid-cols-2">
          <Detail label="Status" value={run.status} capitalize />
          <Detail label="Scheduled for" value={formatDate(run.scheduled_for)} />
          <Detail label="Started" value={formatDate(run.started_at)} />
          <Detail label="Finished" value={formatDate(run.finished_at)} />
        </div>
        {run.result && Object.keys(run.result).length > 0 && <div>
          <h3 className="mb-2 text-xs font-bold uppercase tracking-[.14em] text-slate-500">Result</h3>
          <dl className="divide-y divide-white/7 rounded-xl border border-white/8 px-4">
            {Object.entries(run.result).map(([key, value]) => <div key={key} className="grid gap-1 py-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] sm:gap-4">
              <dt className="text-sm text-slate-500">{resultLabel(key)}</dt>
              <dd className="break-words text-sm font-medium text-slate-200 sm:text-right">{resultValue(value)}</dd>
            </div>)}
          </dl>
        </div>}
        {run.error && <div className="rounded-xl bg-red-400/10 p-4"><p className="text-xs font-bold uppercase tracking-[.14em] text-red-300">Error</p><p className="mt-2 whitespace-pre-wrap text-sm text-red-200">{run.error}</p></div>}
      </div>}
    </DialogContent>
  </Dialog>;
}


function Detail({ label, value, capitalize = false }: { label: string; value: string; capitalize?: boolean }) {
  return <div><p className="text-xs text-slate-500">{label}</p><p className={`mt-1 text-sm font-medium text-slate-200 ${capitalize ? "capitalize" : ""}`}>{value}</p></div>;
}


export function ScheduledTaskManager() {
  const [tasks, setTasks] = useState<ScheduledTaskState[] | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    setError("");
    try {
      setTasks(await apiFetch<ScheduledTaskState[]>("/admin/tasks"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load scheduled tasks.");
    }
  }

  useEffect(() => {
    let cancelled = false;
    apiFetch<ScheduledTaskState[]>("/admin/tasks")
      .then(value => { if (!cancelled) setTasks(value); })
      .catch(reason => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load scheduled tasks.");
      });
    return () => { cancelled = true; };
  }, []);

  async function refresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  return <section className="mt-8 rounded-2xl border border-white/8 bg-card p-5 sm:p-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-3">
        <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Clock3 className="h-5 w-5" /></span>
        <div><h2 className="font-bold">Scheduled tasks</h2><p className="text-sm text-slate-400">Persistent schedules and the latest execution state.</p></div>
      </div>
      <Button variant="secondary" size="sm" onClick={refresh} disabled={refreshing}>
        <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
      </Button>
    </div>
    {error && <p role="alert" className="mt-4 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}
    {!tasks && !error ? <div className="grid min-h-24 place-items-center"><LoaderCircle className="h-5 w-5 animate-spin text-primary" /></div>
      : tasks?.length === 0 ? <p className="mt-4 text-sm text-slate-400">No tasks are registered yet. The scheduler registers them when it starts.</p>
      : <div className="mt-5 grid gap-3">{tasks?.map(task => <article key={task.key} className="grid gap-3 rounded-xl border border-white/8 bg-white/[0.025] p-4 md:grid-cols-[minmax(0,1fr)_auto_auto_auto] md:items-center">
        <div><p className="font-semibold">{task.description}</p><p className="mt-1 text-xs text-slate-500">{task.schedule}</p></div>
        <div className="text-sm"><span className="text-slate-500">Next run</span><p className="font-medium text-slate-200">{formatDate(task.next_run_at)}</p></div>
        <div className="text-sm md:min-w-32"><span className="text-slate-500">Last result</span><p className={task.last_status === "failed" ? "font-semibold text-red-300" : "font-medium capitalize text-slate-200"}>{task.last_status ?? "Never run"}</p></div>
        <TaskDetails task={task} />
        {task.last_error && <p className="text-sm text-red-300 md:col-span-4">{task.last_error}</p>}
      </article>)}</div>}
  </section>;
}
