"use client";

import { useEffect, useState } from "react";
import { Check, LoaderCircle, Minus, Trophy, X } from "lucide-react";
import { apiFetch, LiveWeek } from "@/lib/api";
import { PageHeading } from "@/components/page-heading";

type Standing = { user_id: string; display_name: string; wins: number; losses: number; pushes: number };
type WeekHistory = { week: number; finalized_at: string; champions: string[]; records: Array<{ name: string; wins: number; losses: number; pushes: number }> };

function useSeasonData<T>(path: "standings" | "history") {
  const [data, setData] = useState<T | null>(null); const [error, setError] = useState("");
  useEffect(() => { apiFetch<LiveWeek>("/predictions/current").then(current => apiFetch<T>(`/predictions/seasons/${current.season.id}/${path}`)).then(setData).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load data.")); }, [path]);
  return { data, error };
}

export function LiveStandings() {
  const { data, error } = useSeasonData<Standing[]>("standings");
  return <><PageHeading eyebrow="Live BTB data" title="Prediction standings">Finalized prediction records for the active Sleeper season.</PageHeading>{error ? <Message title="Standings unavailable" detail={error} /> : !data ? <Loading /> : data.length === 0 ? <Message title="No finalized predictions yet" detail="Standings will appear after the first week is finalized." /> : <div className="overflow-hidden rounded-2xl border border-white/9 bg-card"><div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left"><thead className="border-b border-white/8 bg-white/[.025] text-xs uppercase tracking-[.12em] text-slate-500"><tr><th className="px-6 py-4">Rank</th><th className="px-4 py-4">Predictor</th><th className="px-4 py-4">Record</th><th className="px-4 py-4 text-right">Accuracy</th></tr></thead><tbody>{data.map((row, i) => { const decided = row.wins + row.losses; return <tr key={row.user_id} className="border-b border-white/6 last:border-0"><td className="px-6 py-5"><span className={`grid h-8 w-8 place-items-center rounded-full text-sm font-bold ${i === 0 ? "bg-primary text-primary-foreground" : "bg-white/5 text-slate-400"}`}>{i + 1}</span></td><td className="px-4 py-5 font-bold">{row.display_name}</td><td className="px-4 py-5">{row.wins}–{row.losses}{row.pushes ? `–${row.pushes}` : ""}</td><td className="px-4 py-5 text-right font-bold text-primary">{decided ? `${((row.wins / decided) * 100).toFixed(1)}%` : "—"}</td></tr>; })}</tbody></table></div></div>}</>;
}

export function LiveHistory() {
  const { data, error } = useSeasonData<WeekHistory[]>("history");
  return <><PageHeading eyebrow="Live BTB data" title="Prediction history">Finalized weekly results retained in the BTB database.</PageHeading>{error ? <Message title="History unavailable" detail={error} /> : !data ? <Loading /> : data.length === 0 ? <Message title="No finalized weeks yet" detail="Weekly history will appear after the commissioner finalizes a week." /> : <div className="overflow-hidden rounded-2xl border border-white/8 bg-card">{data.map(week => <div key={week.week} className="grid gap-3 border-b border-white/7 px-5 py-5 last:border-0 sm:grid-cols-[1fr_1fr_auto] sm:items-center"><div><p className="font-bold">Week {week.week}</p><p className="text-xs text-slate-500">{new Date(week.finalized_at).toLocaleDateString()}</p></div><p className="text-sm text-slate-400"><span className="text-slate-600">Champion</span> · {week.champions.join(", ")}</p><p className="text-sm font-semibold text-primary">{week.records.length} records</p></div>)}</div>}</>;
}

export function LiveResults() {
  const [data, setData] = useState<LiveWeek | null>(null); const [error, setError] = useState("");
  useEffect(() => { apiFetch<LiveWeek>("/predictions/current").then(setData).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load results.")); }, []);
  return <><PageHeading eyebrow="Live from Sleeper" title="Matchup results">Scores for the active BTB week. Prediction outcomes become final after commissioner finalization.</PageHeading>{error ? <Message title="Results unavailable" detail={error} /> : !data ? <Loading /> : <><div className="mb-5 flex items-center gap-3 rounded-2xl border border-white/8 bg-card p-5"><Trophy className="h-5 w-5 text-primary" /><span><strong>Week {data.week.number}</strong> · <span className="capitalize text-slate-400">{data.week.status}</span></span></div><div className="grid gap-3">{data.matchups.map(m => { const tied = m.team_a.score !== null && m.team_a.score === m.team_b.score; const aWon = m.winner_roster_id === m.team_a.roster_id; return <div key={m.id} className="grid grid-cols-[1fr_auto_1fr_auto] items-center gap-3 rounded-2xl border border-white/8 bg-card p-4 sm:gap-6 sm:px-6"><TeamResult team={m.team_a} winner={aWon} /><span className="text-xs font-bold text-slate-600">VS</span><TeamResult team={m.team_b} winner={m.winner_roster_id === m.team_b.roster_id} right /><span className={`grid h-9 w-9 place-items-center rounded-full ${tied ? "bg-blue-400/10 text-blue-400" : m.winner_roster_id ? "bg-emerald-400/10 text-emerald-400" : "bg-white/5 text-slate-500"}`}>{tied ? <Minus className="h-4" /> : m.winner_roster_id ? <Check className="h-4" /> : <X className="h-4" />}</span></div>; })}</div></>}</>;
}

function TeamResult({ team, winner, right }: { team: LiveWeek["matchups"][number]["team_a"]; winner: boolean; right?: boolean }) { return <div className={right ? "text-right sm:text-left" : ""}><p className={`font-bold ${winner ? "text-primary" : ""}`}>{team.name}</p><p className="text-xs text-slate-500">{team.score ?? "Not scored"}</p></div>; }
function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function Message({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-8 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mt-2 text-sm text-slate-400">{detail}</p></div>; }
