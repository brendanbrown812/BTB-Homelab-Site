"use client";

import {
  CalendarClock,
  CheckCircle2,
  CircleDashed,
  Clock3,
  Eye,
  FilePenLine,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Trophy,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

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
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AdminPTGRankingState, apiFetch, PTGRankingManagerStatus, PTGRankingResult } from "@/lib/api";
import { chicagoDateTimeLocal, ordinal, pointsForPosition } from "@/lib/ptgotw-ranking";

export function AdminPTGOTWRankings() {
  const initialYear = Number(new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    timeZone: "America/Chicago",
  }).format(new Date()));
  const [year, setYear] = useState(initialYear);
  const [data, setData] = useState<AdminPTGRankingState | null>(null);
  const [deadline, setDeadline] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [closeConfirm, setCloseConfirm] = useState(false);
  const [viewing, setViewing] = useState<PTGRankingManagerStatus | null>(null);

  const apply = useCallback((value: AdminPTGRankingState) => {
    setData(value);
    setYear(value.year);
    setDeadline(value.closes_at ? chicagoDateTimeLocal(value.closes_at) : "");
  }, []);

  const load = useCallback(async (selectedYear: number) => {
    setLoading(true);
    setError("");
    try {
      apply(await apiFetch<AdminPTGRankingState>(`/admin/ptgotw/rankings/${selectedYear}`));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load ranking status.");
    } finally {
      setLoading(false);
    }
  }, [apply]);

  useEffect(() => {
    let cancelled = false;
    apiFetch<AdminPTGRankingState>(`/admin/ptgotw/rankings/${initialYear}`)
      .then(value => { if (!cancelled) apply(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load ranking status."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [apply, initialYear]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      apiFetch<AdminPTGRankingState>(`/admin/ptgotw/rankings/${year}`)
        .then(apply)
        .catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(interval);
  }, [apply, year]);

  async function mutate(path: string, method: "PUT" | "POST", body?: object) {
    setSaving(true);
    setError("");
    try {
      const value = await apiFetch<AdminPTGRankingState>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      apply(value);
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update ranking settings.");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function saveDeadline() {
    if (!deadline) { setError("Choose a closing date and time first."); return; }
    await mutate(`/admin/ptgotw/rankings/${year}/settings`, "PUT", { closes_at: deadline });
  }

  async function openSubmissions() {
    if (!deadline) { setError("Choose a closing date and time first."); return; }
    if (data?.state === "closed") {
      await mutate(`/admin/ptgotw/rankings/${year}/reopen`, "POST", { closes_at: deadline });
    } else {
      await mutate(`/admin/ptgotw/rankings/${year}/open`, "POST", { closes_at: deadline });
    }
  }

  async function closeNow() {
    if (await mutate(`/admin/ptgotw/rankings/${year}/close`, "POST")) setCloseConfirm(false);
  }

  async function toggleAccepting(checked: boolean) {
    if (checked) await openSubmissions();
    else setCloseConfirm(true);
  }

  const submittedCount = useMemo(() => data?.managers.filter(manager => manager.status === "submitted").length ?? 0, [data]);
  const savedCount = useMemo(() => data?.managers.filter(manager => manager.status !== "not_started").length ?? 0, [data]);

  return <>
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
      <PageHeading eyebrow="Commissioner tools" title="Ranking status">Control PTGOTW voting, inspect saved ballots, and follow live results.</PageHeading>
      <div className="flex items-center gap-2">
        {data && <NativeSelect value={year} onChange={event => { const selected = Number(event.target.value); setYear(selected); void load(selected); }} aria-label="Ranking year">
          {data.available_years.map(option => <NativeSelectOption key={option} value={option}>{option}</NativeSelectOption>)}
        </NativeSelect>}
        <Button variant="secondary" disabled={loading} onClick={() => void load(year)}><RefreshCw className={loading ? "animate-spin" : ""} />Refresh</Button>
      </div>
    </div>

    {error && <p role="alert" className="mb-5 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}
    {loading && !data ? <Loading /> : data && <>
      <section className="mb-5 rounded-2xl border border-white/8 bg-card p-5">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-center">
          <div className="flex items-center gap-3">
            <span className={`grid h-11 w-11 place-items-center rounded-xl ${data.state === "open" ? "bg-emerald-400/10 text-emerald-400" : data.state === "closed" ? "bg-white/5 text-slate-400" : "bg-amber-400/10 text-amber-300"}`}>
              {data.state === "open" ? <Clock3 /> : data.state === "closed" ? <LockKeyhole /> : <CalendarClock />}
            </span>
            <div><h2 className="font-bold">{year} ranking period</h2><p className="text-sm capitalize text-slate-500">{data.state} · {data.candidate_count} eligible writeup{data.candidate_count === 1 ? "" : "s"}</p></div>
          </div>
          <label className="flex items-center gap-3 text-sm font-semibold text-slate-200">
            <Switch checked={data.accepting_submissions} disabled={saving} onCheckedChange={value => void toggleAccepting(value)} aria-label="Accepting ranking submissions" />
            Accepting submissions
          </label>
        </div>
        <div className="mt-5 grid gap-4 border-t border-white/8 pt-5 lg:grid-cols-[minmax(260px,1fr)_auto] lg:items-end">
          <label className="grid gap-2 text-sm font-medium text-slate-300"><span>Closes at <span className="font-normal text-slate-500">(America/Chicago)</span></span><Input type="datetime-local" value={deadline} onChange={event => setDeadline(event.target.value)} disabled={saving} /></label>
          <div className="flex flex-wrap gap-2">
            <Button disabled={saving || !deadline} onClick={() => void saveDeadline()}>
              {saving ? <LoaderCircle className="animate-spin" /> : <CalendarClock />}
              Save deadline
            </Button>
            {data.state === "preparing" && <Button variant="outline" disabled={saving || !deadline} onClick={() => void openSubmissions()}><Clock3 />Open submissions</Button>}
            {data.state === "closed" && <Button variant="outline" disabled={saving || !deadline} onClick={() => void openSubmissions()}><RefreshCw />Reopen submissions</Button>}
            {data.state === "open" && <Button variant="outline" disabled={saving} onClick={() => setCloseConfirm(true)}><LockKeyhole />Close now</Button>}
          </div>
        </div>
      </section>

      <section className="mb-5 flex flex-col gap-4 rounded-2xl border border-white/8 bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Users className="h-5 w-5" /></span><div><h2 className="font-bold">Manager completion</h2><p className="text-sm text-slate-500">{savedCount} started · {submittedCount} submitted</p></div></div>
        <p className="text-sm text-slate-400"><strong className="text-lg text-white">{submittedCount}</strong> of {data.managers.length} managers submitted</p>
      </section>

      <ManagerStatusTable managers={data.managers} onView={setViewing} />

      <section className="mt-7">
        <div className="mb-4"><h2 className="text-xl font-bold">Live results</h2><p className="mt-1 text-sm text-slate-500">Submitted ballots are official. The preview also includes every autosaved draft.</p></div>
        <Tabs defaultValue="submitted">
          <TabsList><TabsTrigger value="submitted">Submitted only ({submittedCount})</TabsTrigger><TabsTrigger value="saved">All saved ballots ({savedCount})</TabsTrigger></TabsList>
          <TabsContent value="submitted"><ResultsTable results={data.submitted_results} empty="No submitted ballots yet." /></TabsContent>
          <TabsContent value="saved"><ResultsTable results={data.all_saved_results} empty="No managers have saved a ballot yet." /></TabsContent>
        </Tabs>
      </section>
    </>}

    <BallotDialog manager={viewing} onOpenChange={open => { if (!open) setViewing(null); }} />
    <AlertDialog open={closeConfirm} onOpenChange={open => { if (!saving) setCloseConfirm(open); }}><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Close ranking submissions now?</AlertDialogTitle><AlertDialogDescription>Managers will immediately lose the ability to edit or submit. You can reopen the period later with a new future deadline.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={saving} onClick={event => { event.preventDefault(); void closeNow(); }}>{saving ? <><LoaderCircle className="animate-spin" />Closing…</> : "Close submissions"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </>;
}

function ManagerStatusTable({ managers, onView }: { managers: PTGRankingManagerStatus[]; onView: (manager: PTGRankingManagerStatus) => void }) {
  return <section className="overflow-x-auto rounded-2xl border border-white/8 bg-card">
    {managers.length ? <Table><TableHeader><TableRow className="border-white/8 hover:bg-transparent"><TableHead className="px-5">Manager</TableHead><TableHead>Last active</TableHead><TableHead>Status</TableHead><TableHead>Last saved</TableHead><TableHead>Last submitted</TableHead><TableHead className="pr-5 text-right">Ballot</TableHead></TableRow></TableHeader><TableBody>{managers.map(manager => <TableRow key={manager.user_id} className="border-white/7 hover:bg-white/[.025]">
      <TableCell className="px-5 py-4 font-semibold text-slate-100">{manager.display_name}</TableCell>
      <TableCell className="whitespace-nowrap text-sm text-slate-400">{formatTimestamp(manager.last_active_at)}</TableCell>
      <TableCell><StatusBadge status={manager.status} /></TableCell>
      <TableCell className="whitespace-nowrap text-sm text-slate-400">{formatTimestamp(manager.updated_at)}</TableCell>
      <TableCell className="whitespace-nowrap text-sm text-slate-400">{formatTimestamp(manager.submitted_at)}</TableCell>
      <TableCell className="pr-5 text-right"><Button variant="ghost" size="sm" disabled={!manager.writeups.length} onClick={() => onView(manager)}><Eye />View</Button></TableCell>
    </TableRow>)}</TableBody></Table> : <div className="px-5 py-10 text-center"><Users className="mx-auto mb-3 h-6 w-6 text-slate-600" /><p className="font-semibold">No active managers</p></div>}
  </section>;
}

function StatusBadge({ status }: { status: PTGRankingManagerStatus["status"] }) {
  const config = status === "submitted" ? { icon: CheckCircle2, label: "Submitted", className: "bg-emerald-400/10 text-emerald-300" } : status === "draft" ? { icon: FilePenLine, label: "Draft", className: "bg-amber-400/10 text-amber-300" } : { icon: CircleDashed, label: "Not started", className: "bg-white/5 text-slate-400" };
  const Icon = config.icon;
  return <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold ${config.className}`}><Icon className="h-3.5 w-3.5" />{config.label}</span>;
}

function BallotDialog({ manager, onOpenChange }: { manager: PTGRankingManagerStatus | null; onOpenChange: (open: boolean) => void }) {
  return <Dialog open={!!manager} onOpenChange={onOpenChange}><DialogContent className="max-h-[85vh] overflow-y-auto border-white/10 bg-card sm:max-w-2xl"><DialogHeader><DialogTitle>{manager?.display_name}&apos;s ranking</DialogTitle><DialogDescription>{manager ? `${manager.status === "submitted" ? "Submitted" : "Draft"} · Last saved ${formatTimestamp(manager.updated_at)}` : ""}</DialogDescription></DialogHeader><div className="grid gap-2">{manager?.writeups.map((writeup, index) => { const points = pointsForPosition(index + 1); return <div key={writeup.id} className={`flex items-center gap-3 rounded-xl border px-4 py-3 ${points ? "border-primary/25 bg-primary/[.06]" : "border-white/7 bg-white/[.02]"}`}><span className={`grid h-9 w-12 shrink-0 place-items-center rounded-lg text-sm font-bold ${points ? "bg-primary text-primary-foreground" : "bg-white/5 text-slate-300"}`}>{ordinal(index + 1)}</span><div className="min-w-0 flex-1"><p className="font-semibold">Week {writeup.week}</p><p className="truncate text-sm text-slate-500">{writeup.author.display_name}</p></div><span className="text-sm font-bold tabular-nums text-slate-400">{points} pt{points === 1 ? "" : "s"}</span></div>; })}</div></DialogContent></Dialog>;
}

function ResultsTable({ results, empty }: { results: PTGRankingResult[]; empty: string }) {
  const ballots = Math.max(0, ...results.map(result => result.ballot_count));
  if (!results.length || ballots === 0) return <div className="mt-2 rounded-2xl border border-white/8 bg-card px-5 py-10 text-center"><Trophy className="mx-auto mb-3 h-6 w-6 text-slate-600" /><p className="font-semibold">{empty}</p></div>;
  const tiedRanks = new Set(results.filter((result, index) => results.some((other, otherIndex) => otherIndex !== index && other.rank === result.rank)).map(result => result.rank));
  return <div className="mt-2 overflow-x-auto rounded-2xl border border-white/8 bg-card"><Table><TableHeader><TableRow className="border-white/8 hover:bg-transparent"><TableHead className="px-4 text-center">Rank</TableHead><TableHead>Manager</TableHead><TableHead className="text-right">Points</TableHead>{["1st", "2nd", "3rd", "4th", "5th"].map(label => <TableHead key={label} className="text-right">{label}</TableHead>)}<TableHead className="text-right">Top 5</TableHead><TableHead className="text-right">Avg.</TableHead><TableHead className="pr-4 text-right">Ballots</TableHead></TableRow></TableHeader><TableBody>{results.map(result => { const qualifier = result.rank <= 5; return <TableRow key={result.writeup_id} className={`border-white/7 ${qualifier ? "bg-primary/[.055] hover:bg-primary/[.08]" : "hover:bg-white/[.025]"}`}>
    <TableCell className="px-4 py-4 text-center"><span className={`inline-flex min-w-8 items-center justify-center rounded-full px-2 py-1 font-black ${qualifier ? "bg-primary text-primary-foreground" : "bg-white/5 text-slate-300"}`}>{result.rank}</span>{tiedRanks.has(result.rank) && <span className="ml-1 text-[10px] font-bold uppercase text-amber-300">Tie</span>}</TableCell>
    <TableCell className="whitespace-nowrap"><p className="font-semibold text-slate-100">{result.author.display_name}</p><p className="text-xs text-slate-500">Week {result.week}{qualifier ? " · Qualifier" : ""}</p></TableCell>
    <TableCell className="text-right text-lg font-black tabular-nums text-primary">{result.points}</TableCell>
    {result.placement_votes.map((count, index) => <TableCell key={index} className="text-right tabular-nums text-slate-300">{count}</TableCell>)}
    <TableCell className="text-right tabular-nums">{result.top_five_appearances}</TableCell><TableCell className="text-right tabular-nums">{result.average_rank?.toFixed(2) ?? "—"}</TableCell><TableCell className="pr-4 text-right tabular-nums">{result.ballot_count}</TableCell>
  </TableRow>; })}</TableBody></Table></div>;
}

function formatTimestamp(value: string | null) {
  if (!value) return "Never";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/Chicago", timeZoneName: "short" }).format(new Date(value));
}

function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
