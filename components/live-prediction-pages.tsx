"use client";

import { useEffect, useState } from "react";
import { Check, CircleDashed, Clock3, LoaderCircle, Minus, Trophy, X } from "lucide-react";
import { apiFetch, CurrentUser, LiveWeek } from "@/lib/api";
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
  const [data, setData] = useState<LiveWeek | null>(null); const [user, setUser] = useState<CurrentUser | null>(null); const [error, setError] = useState("");
  useEffect(() => { Promise.all([apiFetch<LiveWeek>("/predictions/current"), apiFetch<CurrentUser>("/auth/me")]).then(([week, currentUser]) => { setData(week); setUser(currentUser); }).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load results.")); }, []);
  return <><PageHeading eyebrow="Live from Sleeper" title="Matchup results">Scores for the active BTB week. Prediction outcomes become final after commissioner finalization.</PageHeading>{error ? <Message title="Results unavailable" detail={error} /> : !data || !user ? <Loading /> : <><div className="mb-5 flex items-center gap-3 rounded-2xl border border-white/8 bg-card p-5"><Trophy className="h-5 w-5 text-primary" /><span><strong>Week {data.week.number}</strong> · <span className="capitalize text-slate-400">{data.week.status}</span></span></div><div className="grid gap-3">{data.matchups.map(m => { const pick = data.picks.find(item => item.user_id === user.id && item.matchup_id === m.id); const pickedRosterId = pick?.selected_roster_id ?? null; const aWon = m.winner_roster_id === m.team_a.roster_id; return <div key={m.id} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_36px] items-center gap-3 rounded-2xl border border-white/8 bg-card p-4 sm:gap-6 sm:px-6"><TeamResult team={m.team_a} winner={aWon} picked={pickedRosterId === m.team_a.roster_id} /><span className="text-xs font-bold text-slate-600">VS</span><TeamResult team={m.team_b} winner={m.winner_roster_id === m.team_b.roster_id} picked={pickedRosterId === m.team_b.roster_id} right /><PickResultIcon result={pick?.result ?? null} picked={pickedRosterId !== null} finalized={data.week.status === "final"} /></div>; })}</div></>}</>;
}

function TeamResult({ team, winner, picked, right }: { team: LiveWeek["matchups"][number]["team_a"]; winner: boolean; picked: boolean; right?: boolean }) { return <div className={right ? "text-right sm:text-left" : ""}><div className={`flex flex-wrap items-center gap-2 ${right ? "justify-end sm:justify-start" : ""}`}><p className={`font-bold ${winner ? "text-primary" : ""}`}>{team.name}</p>{picked && <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-[.08em] text-primary">Your pick</span>}</div><p className={`mt-1 text-2xl font-black tabular-nums ${winner ? "text-primary" : "text-slate-200"}`}>{team.score === null ? "—" : team.score.toFixed(2)}</p></div>; }
function PickResultIcon({ result, picked, finalized }: { result: "win" | "loss" | "push" | null; picked: boolean; finalized: boolean }) {
  const state = !picked
    ? { label: finalized ? "No pick submitted" : "No pick yet", style: finalized ? "bg-red-400/10 text-red-400" : "bg-white/5 text-slate-500", icon: finalized ? <X className="h-4 w-4" /> : <CircleDashed className="h-4 w-4" /> }
    : result === "win"
      ? { label: "Correct pick", style: "bg-emerald-400/10 text-emerald-400", icon: <Check className="h-4 w-4" /> }
      : result === "loss"
        ? { label: "Incorrect pick", style: "bg-red-400/10 text-red-400", icon: <X className="h-4 w-4" /> }
        : result === "push"
          ? { label: "Push", style: "bg-blue-400/10 text-blue-400", icon: <Minus className="h-4 w-4" /> }
          : { label: "Awaiting final result", style: "bg-white/5 text-slate-500", icon: <Clock3 className="h-4 w-4" /> };
  return <span title={state.label} aria-label={state.label} className={`grid h-9 w-9 place-items-center rounded-full ${state.style}`}>{state.icon}</span>;
}
function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function Message({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-8 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mt-2 text-sm text-slate-400">{detail}</p></div>; }
