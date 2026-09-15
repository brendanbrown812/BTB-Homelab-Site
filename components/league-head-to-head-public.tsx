"use client";

import Link from "next/link";
import { CalendarDays, Equal, LoaderCircle, Swords, Trophy } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeading } from "@/components/page-heading";
import { apiFetch, PublicHeadToHead } from "@/lib/api";

export function LeagueHeadToHeadPage() {
  const [result, setResult] = useState<{ key: string; data: PublicHeadToHead } | null>(null);
  const [managerA, setManagerA] = useState("");
  const [managerB, setManagerB] = useState("");
  const [failure, setFailure] = useState<{ key: string; message: string } | null>(null);

  useEffect(() => {
    let cancelled = false;
    if ((managerA && !managerB) || (!managerA && managerB)) return;
    const key = managerA && managerB ? `${managerA}:${managerB}` : "options";
    const query = managerA && managerB ? `?manager_a_id=${managerA}&manager_b_id=${managerB}` : "";
    apiFetch<PublicHeadToHead>(`/league-history/head-to-head${query}`)
      .then(value => { if (!cancelled) setResult({ key, data: value }); })
      .catch(reason => { if (!cancelled) setFailure({ key, message: reason instanceof Error ? reason.message : "Could not load the head-to-head record." }); });
    return () => { cancelled = true; };
  }, [managerA, managerB]);

  const key = managerA && managerB ? `${managerA}:${managerB}` : "options";
  const current = result?.key === key ? result.data : null;
  const managers = result?.data.managers ?? [];
  const comparison = current?.comparison;
  const error = failure?.key === key ? failure.message : "";
  const loading = (!managerA && !managerB && !current) || (!!managerA && !!managerB && !current && !error);
  return <><PageHeading eyebrow="League history" title="Head to Head">Settle the argument with every recorded matchup between any two BTB managers.</PageHeading>
    <section className="mb-6 rounded-2xl border border-white/8 bg-card p-5 sm:p-6"><div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-end"><ManagerSelect label="First manager" value={managerA} onChange={setManagerA} managers={managers} blockedId={managerB} /><span className="hidden pb-3 text-xs font-black uppercase tracking-[.16em] text-slate-600 md:block">vs</span><ManagerSelect label="Second manager" value={managerB} onChange={setManagerB} managers={managers} blockedId={managerA} /></div></section>
    {error ? <State title="Comparison unavailable" detail={error} /> : loading ? <Loading /> : !managerA || !managerB ? <State title="Choose two managers" detail="Select any two current or former managers to see their complete series." /> : !comparison ? <State title="No comparison available" detail="The selected managers could not be compared." /> : <Comparison data={comparison} />}
  </>;
}

function ManagerSelect({ label, value, onChange, managers, blockedId }: { label: string; value: string; onChange: (value: string) => void; managers: PublicHeadToHead["managers"]; blockedId: string }) {
  return <label><span className="mb-2 block text-xs font-bold uppercase tracking-[.12em] text-slate-500">{label}</span><select value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-xl border border-white/10 bg-[#0d131e] px-4 py-3 text-sm font-semibold outline-none focus:border-primary/50"><option value="">Select manager</option>{managers.map(manager => <option key={manager.id} value={manager.id} disabled={manager.id === blockedId}>{manager.display_name}{manager.is_active ? "" : " (Former)"}</option>)}</select></label>;
}

function Comparison({ data }: { data: NonNullable<PublicHeadToHead["comparison"]> }) {
  const leader = data.manager_a.wins === data.manager_b.wins ? null : data.manager_a.wins > data.manager_b.wins ? data.manager_a : data.manager_b;
  return <div className="space-y-6"><section className="grid gap-3 lg:grid-cols-[1fr_auto_1fr]"><SeriesSide side={data.manager_a} /><div className="flex min-w-36 flex-col items-center justify-center rounded-2xl border border-white/8 bg-card px-5 py-4 text-center"><Swords className="h-5 w-5 text-primary" /><p className="mt-2 text-xs font-bold uppercase tracking-[.12em] text-slate-500">All-time series</p><p className="mt-1 text-2xl font-black">{data.manager_a.wins}–{data.manager_b.wins}{data.ties ? `–${data.ties}` : ""}</p><p className="mt-1 text-xs text-slate-500">{data.total_matchups} matchups{leader ? ` · ${leader.display_name} leads` : data.total_matchups ? " · Series tied" : ""}</p></div><SeriesSide side={data.manager_b} right /></section>
    <section className="rounded-2xl border border-white/8 bg-card p-5 sm:p-6"><header className="mb-5 flex items-center gap-2"><CalendarDays className="h-4 w-4 text-primary" /><h2 className="font-bold">Matchup history</h2></header>{data.games.length ? <div className="space-y-3">{data.games.map(game => <article key={game.id} className="rounded-xl border border-white/7 bg-white/[.02] p-4"><div className="mb-3 flex flex-wrap items-center justify-between gap-2"><Link href={`/league/seasons/${game.season_id}`} className="text-xs font-bold uppercase tracking-[.1em] text-slate-500 hover:text-primary">{game.year} · {game.week_end ? `Weeks ${game.week}–${game.week_end}` : `Week ${game.week}`}</Link><span className="text-[10px] font-semibold uppercase tracking-[.08em] text-slate-600">{game.source === "notion" ? "Imported from Notion" : game.source}</span></div><div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3"><GameSide manager={data.manager_a} teamName={game.team_a_name} score={game.score_a} won={game.winner_id === data.manager_a.id} /><div className="text-center"><span className="text-[10px] font-black text-slate-600">VS</span><p className="mt-1 text-[10px] text-slate-600">{formatNumber(game.margin)} pt margin</p></div><GameSide manager={data.manager_b} teamName={game.team_b_name} score={game.score_b} won={game.winner_id === data.manager_b.id} right /></div>{game.winner_id === null && <p className="mt-3 flex items-center justify-center gap-1 text-xs text-slate-500"><Equal className="h-3 w-3" />Tie</p>}</article>)}</div> : <State title="No recorded matchups" detail="These managers have not played each other in the imported league history." />}</section>
  </div>;
}

function SeriesSide({ side, right = false }: { side: NonNullable<PublicHeadToHead["comparison"]>["manager_a"]; right?: boolean }) {
  return <Link href={`/league/teams/${side.id}`} className={`rounded-2xl border border-white/8 bg-card p-5 hover:border-primary/30 ${right ? "text-right" : ""}`}><div className={`flex items-center gap-2 ${right ? "justify-end" : ""}`}><Trophy className="h-4 w-4 text-primary" /><h2 className="truncate text-xl font-black">{side.display_name}</h2></div><p className="mt-4 text-4xl font-black text-primary">{side.wins}</p><p className="text-xs font-bold uppercase tracking-[.12em] text-slate-500">Series wins</p><div className={`mt-4 flex gap-4 text-xs text-slate-400 ${right ? "justify-end" : ""}`}><span>{formatNumber(side.points_for)} points</span><span>{formatNumber(side.average_score)} avg</span></div></Link>;
}

function GameSide({ manager, teamName, score, won, right = false }: { manager: NonNullable<PublicHeadToHead["comparison"]>["manager_a"]; teamName: string; score: number; won: boolean; right?: boolean }) {
  return <div className={right ? "text-right" : ""}><Link href={`/league/teams/${manager.id}`} className={`truncate text-sm font-bold hover:text-primary ${won ? "text-primary" : ""}`}>{manager.display_name}</Link><p className="truncate text-xs text-slate-500">{teamName}</p><p className={`mt-2 text-2xl font-black tabular-nums ${won ? "text-primary" : "text-slate-200"}`}>{formatNumber(score)}</p></div>;
}

function formatNumber(value: number) { return value.toLocaleString(undefined, { maximumFractionDigits: 2 }); }
function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function State({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-10 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-slate-400">{detail}</p></div>; }
