"use client";

import Link from "next/link";
import { ArrowRight, BarChart3, CalendarDays, Equal, LoaderCircle, Trophy } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeading } from "@/components/page-heading";
import { apiFetch, PublicLeagueRecord } from "@/lib/api";

type RecordsResponse = {
  records: PublicLeagueRecord[];
  custom_facts: Array<{ id: string; season_id: string; year: number; label: string; value: string }>;
};

export function LeagueRecordsPage() {
  const [data, setData] = useState<RecordsResponse | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    apiFetch<RecordsResponse>("/league-history/records")
      .then(value => { if (!cancelled) setData(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not calculate league records."); });
    return () => { cancelled = true; };
  }, []);
  const categories = data ? Array.from(new Set(data.records.map(record => record.category))) : [];
  return <>
    <PageHeading eyebrow="League history" title="Records & fun facts">Calculated exclusively from imported league matchups, placements, and transactions.</PageHeading>
    {error ? <State title="Records unavailable" detail={error} /> : !data ? <Loading /> : !data.records.length && !data.custom_facts.length ? <State title="No records yet" detail="Records will appear after completed matchup or transaction history is imported. Missing ESPN details are never guessed." /> : <div className="space-y-9">{categories.map(category => <section key={category}><div className="mb-4 flex items-center gap-2"><BarChart3 className="h-4 w-4 text-primary" /><h2 className="text-sm font-bold uppercase tracking-[.16em] text-slate-400">{category}</h2></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.records.filter(record => record.category === category).map(record => <RecordCard key={record.key} record={record} />)}</div></section>)}{data.custom_facts.length > 0 && <section><div className="mb-4 flex items-center gap-2"><Trophy className="h-4 w-4 text-primary" /><h2 className="text-sm font-bold uppercase tracking-[.16em] text-slate-400">Season fun facts</h2></div><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.custom_facts.map(fact => <Link key={fact.id} href={`/league/seasons/${fact.season_id}`} className="rounded-2xl border border-white/8 bg-card p-5 transition hover:border-primary/30"><p className="text-xs font-bold uppercase tracking-[.12em] text-primary">{fact.year}</p><h3 className="mt-2 font-black">{fact.label}</h3><p className="mt-2 text-sm leading-6 text-slate-400">{fact.value}</p></Link>)}</div></section>}</div>}
  </>;
}

function RecordCard({ record }: { record: PublicLeagueRecord }) {
  return <article className="rounded-2xl border border-white/8 bg-card p-5"><header className="flex items-start justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[.12em] text-slate-500">{record.label}</p><p className="mt-2 text-3xl font-black text-primary">{formatValue(record.entries[0]?.value, record.key)}</p></div>{record.key.includes("championship") ? <Trophy className="h-5 w-5 text-primary" /> : record.tied ? <span className="inline-flex items-center gap-1 rounded-full bg-white/5 px-2 py-1 text-[10px] font-bold uppercase tracking-[.08em] text-slate-400"><Equal className="h-3 w-3" />Tied</span> : null}</header><div className="mt-5 divide-y divide-white/6">{record.entries.map((entry, index) => <div key={`${entry.manager_id}-${entry.season_id}-${entry.week}-${index}`} className="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"><div className="min-w-0"><Link href={`/league/teams/${entry.manager_id}`} className="truncate font-bold hover:text-primary">{entry.manager_name}</Link><p className="truncate text-xs text-slate-400">{entry.detail}</p>{entry.year && <Link href={entry.season_id ? `/league/seasons/${entry.season_id}` : "/league/seasons"} className="mt-1 flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300"><CalendarDays className="h-3 w-3" />{entry.year}{entry.week ? ` · Week ${entry.week}` : ""}</Link>}</div><ArrowRight className="h-4 w-4 shrink-0 text-slate-700" /></div>)}</div></article>;
}

function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function State({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-10 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-slate-400">{detail}</p></div>; }
function formatValue(value: number | undefined, key: string) { if (value === undefined) return "—"; if (key === "best_season_record" || key === "worst_season_record") return `${(value * 100).toFixed(1)}%`; return value.toLocaleString(undefined, { maximumFractionDigits: 2 }); }
