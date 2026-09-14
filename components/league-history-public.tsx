"use client";

/* eslint-disable @next/next/no-img-element -- Sleeper serves player thumbnails from its CDN. */
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, ArrowRight, Award, CalendarDays, Crown, History, LoaderCircle, Shield, Sparkles, Trophy, UserRound, UsersRound } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { PageHeading } from "@/components/page-heading";
import { apiFetch, LivePlayer, PublicLeagueManager, PublicLeagueSeason, PublicManagerDetail, PublicSeasonDetail } from "@/lib/api";

function useLeagueData<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!path) return;
    let cancelled = false;
    apiFetch<T>(path)
      .then(value => { if (!cancelled) setData(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load league history."); });
    return () => { cancelled = true; };
  }, [path]);
  return { data, error };
}

export function LeagueTeamsPage() {
  const { data, error } = useLeagueData<{ managers: PublicLeagueManager[] }>("/league-history/teams");
  return <><PageHeading eyebrow="League history" title="Teams">Every manager and franchise identity in BTB history, including former league members.</PageHeading>
    {error ? <State title="Teams unavailable" detail={error} /> : !data ? <Loading /> : !data.managers.length ? <State title="No managers yet" detail="Manager profiles will appear after league history is configured." /> : <div className="space-y-8">
      <ManagerGroup title="Active managers" managers={data.managers.filter(manager => manager.is_active)} />
      <ManagerGroup title="Former managers" managers={data.managers.filter(manager => !manager.is_active)} />
    </div>}
  </>;
}

function ManagerGroup({ title, managers }: { title: string; managers: PublicLeagueManager[] }) {
  if (!managers.length) return null;
  return <section><h2 className="mb-4 text-sm font-bold uppercase tracking-[.16em] text-slate-500">{title}</h2><div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{managers.map(manager => <Link key={manager.id} href={`/league/teams/${manager.id}`} className="group rounded-2xl border border-white/8 bg-card p-5 transition hover:-translate-y-0.5 hover:border-primary/35 hover:bg-white/[.045]">
    <div className="flex items-start gap-4"><Initials name={manager.display_name} /><div className="min-w-0 flex-1"><h3 className="truncate text-lg font-bold transition group-hover:text-primary">{manager.display_name}</h3><p className="truncate text-sm text-slate-500">{manager.latest_team_name ?? "No recorded team name"}</p></div><ArrowRight className="mt-2 h-4 w-4 text-slate-600 transition group-hover:translate-x-1 group-hover:text-primary" /></div>
    {manager.biography && <p className="mt-4 line-clamp-2 text-sm leading-6 text-slate-400">{manager.biography}</p>}
    <div className="mt-5 grid grid-cols-3 gap-2"><MiniStat label="Seasons" value={manager.seasons_played} /><MiniStat label="Titles" value={manager.championships} /><MiniStat label="Record" value={`${manager.career.wins}-${manager.career.losses}${manager.career.ties ? `-${manager.career.ties}` : ""}`} /></div>
  </Link>)}</div></section>;
}

export function LeagueManagerPage() {
  const params = useParams(); const rawId = params?.id; const id = Array.isArray(rawId) ? rawId[0] : rawId;
  const invalid = !id || !/^[0-9a-f-]{36}$/i.test(id);
  const { data, error } = useLeagueData<PublicManagerDetail>(invalid ? null : `/league-history/teams/${id}`);
  if (invalid) return <><Back href="/league/teams" label="All teams" /><State title="Manager not found" detail="This manager profile link is invalid." /></>;
  if (error) return <><Back href="/league/teams" label="All teams" /><State title="Manager unavailable" detail={error} /></>;
  if (!data) return <Loading />;
  const names = Array.from(new Set(data.seasons.map(season => season.team_name)));
  return <><Back href="/league/teams" label="All teams" /><header className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-center"><Initials name={data.manager.display_name} large /><div><div className="flex flex-wrap items-center gap-3"><h1 className="text-3xl font-black tracking-[-.035em] sm:text-4xl">{data.manager.display_name}</h1><span className={`rounded-full px-2.5 py-1 text-xs font-bold ${data.manager.is_active ? "bg-emerald-400/10 text-emerald-300" : "bg-white/5 text-slate-400"}`}>{data.manager.is_active ? "Active" : "Former manager"}</span></div><p className="mt-2 text-slate-400">{names.length ? names.join(" · ") : "No recorded team names"}</p></div></header>
    <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5"><Stat label="Seasons" value={data.seasons.length} /><Stat label="Championships" value={data.championships} /><Stat label="Career record" value={`${data.career.wins}-${data.career.losses}${data.career.ties ? `-${data.career.ties}` : ""}`} /><Stat label="Points scored" value={data.career.points_for.toFixed(2)} /><Stat label="Transactions" value={data.transactions.total} /></div>
    <div className="grid gap-6 xl:grid-cols-[1.25fr_.75fr]"><div className="space-y-6">
      <Panel title="Biography" icon={<UserRound />}>{data.manager.biography ? <p className="whitespace-pre-wrap text-sm leading-7 text-slate-300">{data.manager.biography}</p> : <Empty text="No biography has been added yet." />}</Panel>
      <Panel title="Season history" icon={<History />}><div className="divide-y divide-white/6">{data.seasons.length ? data.seasons.map(season => <Link href={`/league/seasons/${season.season_id}`} key={season.season_id} className="flex items-center justify-between gap-4 py-4 first:pt-0 last:pb-0"><div><p className="font-bold">{season.year} · {season.team_name}</p><p className="mt-1 text-xs uppercase tracking-[.12em] text-slate-500">{season.platform}</p></div><div className="text-right"><p className="font-bold text-primary">{season.placement ? ordinal(season.placement) : "—"}</p><Provenance value={season.placement_source} /></div></Link>) : <Empty text="No season participation has been recorded." />}</div></Panel>
      {data.current_roster && <Panel title={`${data.current_roster.season_year} current roster`} icon={<Shield />}><p className="mb-4 text-sm text-slate-500">{data.current_roster.team_name} · Live roster only</p>{data.current_roster.error ? <Empty text={data.current_roster.error} /> : data.current_roster.players.length ? <div className="grid gap-2 md:grid-cols-2">{data.current_roster.players.map(player => <PlayerCard key={player.player_id} player={player} />)}</div> : <Empty text="Sleeper returned an empty roster." />}</Panel>}
    </div><div className="space-y-6">
      <Panel title="Transaction activity"><div className="space-y-3">{Object.keys(data.transactions.by_type).length ? Object.entries(data.transactions.by_type).map(([type, count]) => <div key={type} className="flex items-center justify-between rounded-xl bg-white/[.025] px-4 py-3"><span className="capitalize text-slate-400">{type.replaceAll("_", " ")}</span><strong>{count}</strong></div>) : <Empty text="No imported transactions." />}</div></Panel>
      <Panel title="Punishment history"><div className="space-y-3">{data.punishments.length ? data.punishments.map(item => <Link key={item.season_id} href={`/league/seasons/${item.season_id}`} className="block rounded-xl bg-red-400/[.06] px-4 py-3"><p className="text-xs font-bold uppercase tracking-[.12em] text-red-300">{item.year}</p><p className="mt-1 font-semibold">{item.title}</p></Link>) : <Empty text="No punishment history." />}</div></Panel>
    </div></div>
  </>;
}

export function LeagueSeasonsPage() {
  const { data, error } = useLeagueData<{ seasons: PublicLeagueSeason[] }>("/league-history/seasons");
  return <><PageHeading eyebrow="League history" title="Seasons">Every BTB season from the ESPN beginnings through the current Sleeper league.</PageHeading>{error ? <State title="Seasons unavailable" detail={error} /> : !data ? <Loading /> : !data.seasons.length ? <State title="No seasons yet" detail="Seasons will appear after league history is configured." /> : <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.seasons.map(season => <Link key={season.id} href={`/league/seasons/${season.id}`} className="group rounded-2xl border border-white/8 bg-card p-5 transition hover:border-primary/35 hover:bg-white/[.045]"><div className="flex items-start justify-between"><span className="grid h-12 w-12 place-items-center rounded-2xl bg-primary/10 text-lg font-black text-primary">{String(season.year).slice(-2)}</span><ArrowRight className="mt-2 h-4 w-4 text-slate-600 transition group-hover:translate-x-1 group-hover:text-primary" /></div><div className="mt-5 flex flex-wrap items-center gap-2"><h2 className="text-2xl font-black">{season.year}</h2>{season.is_active && <span className="rounded-full bg-emerald-400/10 px-2 py-0.5 text-xs font-bold text-emerald-300">Current</span>}</div><p className="mt-1 text-xs font-semibold uppercase tracking-[.14em] text-slate-500">{season.platform}</p><div className="mt-5 grid grid-cols-3 gap-2"><MiniStat label="Managers" value={season.manager_count} /><MiniStat label="Matchups" value={season.matchup_count} /><MiniStat label="Placed" value={season.placement_count} /></div></Link>)}</div>}</>;
}

export function LeagueSeasonPage() {
  const params = useParams(); const rawId = params?.id; const id = Array.isArray(rawId) ? rawId[0] : rawId;
  const invalid = !id || !/^[0-9a-f-]{36}$/i.test(id);
  const { data, error } = useLeagueData<PublicSeasonDetail>(invalid ? null : `/league-history/seasons/${id}`);
  if (invalid) return <><Back href="/league/seasons" label="All seasons" /><State title="Season not found" detail="This season link is invalid." /></>;
  if (error) return <><Back href="/league/seasons" label="All seasons" /><State title="Season unavailable" detail={error} /></>;
  if (!data) return <Loading />;
  const weekGroups = Array.from(new Map(data.weekly_results.map(result => [`${result.week}-${result.week_end ?? ""}`, { week: result.week, week_end: result.week_end }])).values()).sort((a, b) => a.week - b.week || (a.week_end ?? a.week) - (b.week_end ?? b.week));
  return <><Back href="/league/seasons" label="All seasons" /><PageHeading eyebrow={`${data.season.platform} season`} title={`${data.season.year} season`}>{data.season.is_active ? "The current BTB season." : "Standings, results, awards, and league notes retained in BTB history."}</PageHeading>
    <div className="space-y-6">
      <Panel title="Final placements" icon={<Trophy />}><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{data.placements.length ? data.placements.map(item => <Link href={`/league/teams/${item.manager_id}`} key={item.manager_id} className="flex items-center gap-3 rounded-xl bg-white/[.025] p-3"><span className={`grid h-9 w-9 place-items-center rounded-xl font-black ${item.placement === 1 ? "bg-primary text-primary-foreground" : "bg-white/5 text-slate-400"}`}>{item.placement ?? "—"}</span><div className="min-w-0"><p className="truncate font-semibold">{item.manager_name}</p><p className="truncate text-xs text-slate-500">{item.team_name}</p><Provenance value={item.placement_source} /></div></Link>) : <Empty text="No placements have been recorded." />}</div></Panel>
      <Panel title="Season standings" icon={<UsersRound />}><div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm"><thead className="border-b border-white/8 text-xs uppercase tracking-[.12em] text-slate-500"><tr><th className="pb-3">Place</th><th className="pb-3">Manager</th><th className="pb-3">Record</th><th className="pb-3 text-right">PF</th><th className="pb-3 text-right">PA</th></tr></thead><tbody>{data.standings.map(item => <tr key={item.manager_id} className="border-b border-white/6 last:border-0"><td className="py-4 font-bold text-primary">{item.placement ? ordinal(item.placement) : "—"}</td><td className="py-4"><Link href={`/league/teams/${item.manager_id}`} className="font-bold hover:text-primary">{item.manager_name}</Link><p className="text-xs text-slate-500">{item.team_name}</p></td><td className="py-4 font-semibold">{item.wins}-{item.losses}{item.ties ? `-${item.ties}` : ""}</td><td className="py-4 text-right tabular-nums">{item.points_for.toFixed(2)}</td><td className="py-4 text-right tabular-nums text-slate-500">{item.points_against.toFixed(2)}</td></tr>)}</tbody></table>{!data.standings.length && <Empty text="No standings are available." />}</div></Panel>
      <div className="grid gap-6 xl:grid-cols-[1.25fr_.75fr]"><Panel title="Weekly results" icon={<CalendarDays />}><div className="space-y-5">{weekGroups.length ? weekGroups.map(group => <section key={`${group.week}-${group.week_end ?? ""}`}><h3 className="mb-2 text-xs font-bold uppercase tracking-[.14em] text-slate-500">{group.week_end ? `Weeks ${group.week}\u2013${group.week_end} playoff series` : `Week ${group.week}`}</h3><div className="space-y-2">{data.weekly_results.filter(result => result.week === group.week && result.week_end === group.week_end).map(result => <div key={result.id} className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 rounded-xl bg-white/[.025] p-3"><TeamScore name={result.team_a_name} score={result.score_a} won={result.score_a !== null && result.score_b !== null && result.score_a > result.score_b} /><span className="text-[10px] font-bold text-slate-600">VS</span><TeamScore name={result.team_b_name} score={result.score_b} won={result.score_a !== null && result.score_b !== null && result.score_b > result.score_a} right /><span className="col-span-3 text-center"><Provenance value={result.source === "notion" ? "imported" : result.source} /></span></div>)}</div></section>) : <Empty text="No weekly results have been imported." />}</div></Panel>
        <div className="space-y-6"><Panel title="Awards" icon={<Award />}><div className="space-y-3">{data.awards.length ? data.awards.map(item => <Highlight key={item.id} item={item} />) : <Empty text="No weekly awards recorded." />}</div></Panel>
        <Panel title="Fun facts" icon={<Sparkles />}><div className="space-y-3">{data.facts.length ? data.facts.map(item => <div key={item.id} className="rounded-xl bg-white/[.025] p-3"><div className="flex items-center justify-between gap-2"><p className="font-semibold">{item.label}</p><Provenance value={item.source} /></div><p className="mt-1 text-sm text-slate-400">{item.value}</p></div>) : <Empty text="No custom season facts yet." />}</div></Panel>
        <Panel title="Last-place punishment" icon={<Crown />}>{data.punishment ? <div><div className="flex items-center justify-between gap-3"><p className="font-bold text-red-300">{data.punishment.manager_name}</p><Provenance value={data.punishment.source} /></div><p className="mt-2 text-slate-300">{data.punishment.title}</p></div> : <Empty text="No punishment recorded." />}</Panel></div>
      </div>
    </div>
  </>;
}

function Panel({ title, icon, children }: { title: string; icon?: ReactNode; children: ReactNode }) { return <section className="rounded-2xl border border-white/8 bg-card p-5 sm:p-6"><div className="mb-5 flex items-center gap-2"><span className="text-primary [&_svg]:h-4 [&_svg]:w-4">{icon}</span><h2 className="font-bold">{title}</h2></div>{children}</section>; }
function Stat({ label, value }: { label: string; value: string | number }) { return <div className="rounded-2xl border border-white/8 bg-card p-4"><p className="text-xs font-semibold uppercase tracking-[.12em] text-slate-500">{label}</p><p className="mt-2 text-2xl font-black text-slate-100">{value}</p></div>; }
function MiniStat({ label, value }: { label: string; value: string | number }) { return <div className="rounded-xl bg-white/[.035] px-2 py-3 text-center"><p className="text-lg font-black">{value}</p><p className="text-[10px] uppercase tracking-[.08em] text-slate-500">{label}</p></div>; }
function Initials({ name, large = false }: { name: string; large?: boolean }) { const initials = name.split(" ").map(part => part[0]).join("").slice(0, 2).toUpperCase(); return <span className={`grid shrink-0 place-items-center rounded-2xl bg-primary/10 font-black text-primary ${large ? "h-20 w-20 text-2xl" : "h-12 w-12"}`}>{initials}</span>; }
function Back({ href, label }: { href: string; label: string }) { return <Link href={href} className="mb-6 inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />{label}</Link>; }
function Empty({ text }: { text: string }) { return <p className="rounded-xl border border-dashed border-white/10 p-5 text-center text-sm text-slate-500">{text}</p>; }
function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function State({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-10 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-slate-400">{detail}</p></div>; }
function Provenance({ value }: { value: string }) { const label = value === "overridden" ? "Commissioner override" : value === "notion" || value === "sleeper" || value === "imported" ? "Imported" : value === "calculated" ? "Calculated" : value === "manual" ? "Manual" : "Not available"; return <span title={`Data source: ${label}`} className="text-[10px] font-semibold uppercase tracking-[.08em] text-slate-600">{label}</span>; }
function TeamScore({ name, score, won, right = false }: { name: string; score: number | null; won: boolean; right?: boolean }) { return <div className={right ? "text-right" : ""}><p className={`truncate text-xs sm:text-sm ${won ? "font-bold text-primary" : "text-slate-300"}`}>{name}</p><p className={`mt-1 text-lg font-black tabular-nums ${won ? "text-primary" : ""}`}>{score === null ? "—" : score.toFixed(2)}</p></div>; }

function Highlight({ item }: { item: PublicSeasonDetail["awards"][number] }) {
  const [failed, setFailed] = useState(false);
  return <div className="rounded-xl bg-white/[.025] p-3"><div className="flex items-start justify-between gap-2"><div><p className="text-xs text-slate-500">Week {item.week}</p><p className="font-semibold">{item.category}</p></div><Provenance value={item.source} /></div><div className="mt-2 flex items-center gap-2">{item.player_image_url && !failed && <img src={item.player_image_url} alt="" loading="lazy" className="h-8 w-8 rounded-full object-cover" onError={() => setFailed(true)} />}<div className="min-w-0"><p className="truncate text-sm font-semibold text-primary">{item.player_name ?? item.manager_name ?? "League highlight"}{item.value !== null ? ` · ${item.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}` : ""}</p>{item.player_name && item.manager_name && <p className="text-xs text-slate-500">Started by {item.manager_name}</p>}{item.detail && <p className="truncate text-xs text-slate-500">{item.detail}</p>}</div></div></div>;
}

function PlayerCard({ player }: { player: LivePlayer }) {
  const [failed, setFailed] = useState(false);
  return <div className="grid grid-cols-[38px_minmax(0,1fr)] items-center gap-3 rounded-xl bg-white/[.025] p-3"><span className="grid h-9 w-9 place-items-center overflow-hidden rounded-full border border-white/8 bg-[#1b2535] text-[9px] font-bold text-slate-500">{player.image_url && !failed ? <img src={player.image_url} alt="" loading="lazy" className="h-full w-full object-cover" onError={() => setFailed(true)} /> : player.position}</span><div className="min-w-0"><div className="flex items-center gap-2"><span className="rounded-md bg-white/5 px-1.5 py-0.5 text-[9px] font-bold text-slate-400">{player.position}</span><p className="truncate text-sm font-semibold">{player.name}</p></div><p className="mt-0.5 text-[11px] text-slate-600">{player.team ?? "Free agent"}{player.injury_status ? <span className="text-amber-400"> · {player.injury_status}</span> : null}</p></div></div>;
}

function ordinal(value: number) { const mod100 = value % 100; const suffix = mod100 >= 11 && mod100 <= 13 ? "th" : value % 10 === 1 ? "st" : value % 10 === 2 ? "nd" : value % 10 === 3 ? "rd" : "th"; return `${value}${suffix}`; }
