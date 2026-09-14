"use client";

import { CheckCircle2, CircleDashed, LoaderCircle, RefreshCw, Users } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { PageHeading } from "@/components/page-heading";
import { apiFetch, CurrentSubmissionStatus } from "@/lib/api";

export default function SubmissionStatusPage() {
  const [data, setData] = useState<CurrentSubmissionStatus | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await apiFetch<CurrentSubmissionStatus>("/admin/predictions/current/submissions"));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load submission status.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiFetch<CurrentSubmissionStatus>("/admin/predictions/current/submissions")
      .then(value => { if (!cancelled) setData(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load submission status."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const completeUsers = useMemo(
    () => data?.users.filter(user => data.total_matchups > 0 && user.submitted_picks >= data.total_matchups).length ?? 0,
    [data],
  );

  return <>
    <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
      <PageHeading eyebrow="Commissioner tools" title="Pick status">See who has finished the current week without revealing any selections.</PageHeading>
      <Button variant="secondary" disabled={loading} onClick={() => void load()} className="shrink-0">
        <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh
      </Button>
    </div>

    {error && <p role="alert" className="mb-5 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}

    {loading && !data ? <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div> : data && <>
      <section className="mb-5 flex flex-col gap-4 rounded-2xl border border-white/8 bg-card p-5 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Users className="h-5 w-5" /></span>
          <div><h2 className="font-bold">{data.season} · Week {data.week}</h2><p className="text-sm text-slate-500">{data.total_matchups} matchup{data.total_matchups === 1 ? "" : "s"} on this week&apos;s card</p></div>
        </div>
        <p className="text-sm text-slate-400"><strong className="text-lg text-white">{completeUsers}</strong> of {data.users.length} members complete</p>
      </section>

      <section className="overflow-hidden rounded-2xl border border-white/8 bg-card">
        {data.users.length ? <Table>
          <TableHeader><TableRow className="border-white/8 hover:bg-transparent"><TableHead className="px-5 text-slate-500">Member</TableHead><TableHead className="px-5 text-right text-slate-500">Picks submitted</TableHead></TableRow></TableHeader>
          <TableBody>{data.users.map(user => {
            const complete = data.total_matchups > 0 && user.submitted_picks >= data.total_matchups;
            const progress = data.total_matchups ? (user.submitted_picks / data.total_matchups) * 100 : 0;
            return <TableRow key={user.user_id} className="border-white/7 hover:bg-white/[.025]">
              <TableCell className="px-5 py-4"><div className="flex items-center gap-3">{complete ? <CheckCircle2 className="h-5 w-5 text-emerald-400" /> : <CircleDashed className="h-5 w-5 text-slate-600" />}<span className="font-semibold text-slate-100">{user.display_name}</span></div></TableCell>
              <TableCell className="px-5 py-4"><div className="ml-auto flex w-[150px] items-center justify-end gap-3"><Progress value={progress} className="h-1.5 w-20 bg-white/8 [&>div]:bg-primary" /><span className={`min-w-12 text-right font-bold tabular-nums ${complete ? "text-emerald-400" : "text-slate-300"}`}>{user.submitted_picks}/{data.total_matchups}</span></div></TableCell>
            </TableRow>;
          })}</TableBody>
        </Table> : <div className="px-5 py-10 text-center"><Users className="mx-auto mb-3 h-6 w-6 text-slate-600" /><p className="font-semibold">No other active users</p><p className="mt-1 text-sm text-slate-500">Create league member accounts to track their weekly status.</p></div>}
      </section>
    </>}
  </>;
}
