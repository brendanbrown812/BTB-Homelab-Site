"use client";

/* eslint-disable @next/next/no-img-element -- Sleeper CDN URLs are dynamic and need client-side error fallbacks. */

import { useEffect, useMemo, useState } from "react";
import { Check, ChevronDown, CircleAlert, LoaderCircle, RefreshCw, Save } from "lucide-react";
import { apiFetch, LivePlayer, LiveTeam, LiveWeek } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

export function PredictionBoard() {
  const [data, setData] = useState<LiveWeek | null>(null);
  const [picks, setPicks] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function load() {
    setError("");
    try {
      const live = await apiFetch<LiveWeek>("/predictions/current?include_rosters=true");
      setData(live);
      setPicks(Object.fromEntries(live.picks.filter(p => p.selected_roster_id !== null).map(p => [p.matchup_id, p.selected_roster_id as number])));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load Sleeper matchups.");
    }
  }

  useEffect(() => {
    let cancelled = false;
    apiFetch<LiveWeek>("/predictions/current?include_rosters=true")
      .then(live => {
        if (cancelled) return;
        setData(live);
        setPicks(Object.fromEntries(live.picks.filter(p => p.selected_roster_id !== null).map(p => [p.matchup_id, p.selected_roster_id as number])));
      })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load Sleeper matchups."); });
    return () => { cancelled = true; };
  }, []);
  const count = Object.keys(picks).length;
  const locked = data ? data.week.status !== "open" || new Date(data.week.lock_at) <= new Date() : true;
  const deadline = useMemo(() => data ? new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(data.week.lock_at)) : "", [data]);

  async function save() {
    if (!data) return;
    setSaving(true);
    setError("");
    try {
      await apiFetch(`/predictions/weeks/${data.week.id}/picks`, {
        method: "PUT",
        body: JSON.stringify({ picks: data.matchups.map(matchup => ({ matchup_id: matchup.id, selected_roster_id: picks[matchup.id] ?? null })) }),
      });
      setSaved(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save picks.");
    } finally {
      setSaving(false);
    }
  }

  if (error && !data) return <State title="Couldn’t load live Sleeper data" detail={error}><Button onClick={load} variant="secondary"><RefreshCw className="h-4 w-4" />Try again</Button></State>;
  if (!data) return <State title="Loading your BTB matchups" detail="Syncing matchups and rosters from Sleeper…"><LoaderCircle className="mx-auto mt-5 h-6 w-6 animate-spin text-primary" /></State>;
  if (!data.matchups.length) return <State title="No matchups returned by Sleeper" detail={`Sleeper did not return matchups for Week ${data.week.number}. Check the league ID and season in your .env file.`}><Button onClick={load} variant="secondary"><RefreshCw className="h-4 w-4" />Refresh</Button></State>;

  return <>
    <section className="mb-8 flex flex-col justify-between gap-5 md:flex-row md:items-end">
      <div>
        <div className="mb-3 flex items-center gap-2"><Badge className="rounded-full bg-primary/10 px-2.5 py-1 text-primary hover:bg-primary/10">Week {data.week.number}</Badge><span className="text-sm text-slate-500">{data.season.year} season · Live from Sleeper</span></div>
        <h1 className="text-3xl font-black tracking-[-.035em] sm:text-4xl">{locked ? "Your picks" : "Make your picks"}</h1>
        <p className="mt-2 max-w-xl text-base leading-relaxed text-slate-400">{locked ? "This card is locked. Picks are visible to the league after the deadline." : `Compare the full rosters and choose each matchup winner. Picks lock ${deadline}.`}</p>
      </div>
      <div className="w-full rounded-2xl border border-white/8 bg-white/[.035] p-4 md:w-[260px]"><div className="mb-2 flex justify-between text-sm"><span className="text-slate-400">Your card</span><span className={saved ? "font-semibold text-emerald-400" : "font-semibold text-white"}>{saved ? "Picks saved" : `${count} of ${data.matchups.length} selected`}</span></div><Progress value={(count / data.matchups.length) * 100} className="h-2 bg-white/8 [&>div]:bg-primary" /></div>
    </section>

    {error && <p role="alert" className="mb-5 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}

    <div className="grid gap-5">
      {data.matchups.map(matchup => <MatchupCard
        key={matchup.id}
        matchup={matchup}
        locked={locked}
        selectedRosterId={picks[matchup.id]}
        onSelect={rosterId => { setPicks(current => ({ ...current, [matchup.id]: rosterId })); setSaved(false); }}
      />)}
    </div>

    {!locked && <div className="sticky bottom-4 z-10 mt-7 flex flex-col items-center justify-between gap-3 rounded-2xl border border-white/10 bg-[#151c28]/95 p-3 pl-4 shadow-2xl backdrop-blur-xl sm:flex-row"><div className="flex items-center gap-3 text-sm text-slate-300">{count < data.matchups.length ? <CircleAlert className="h-5 w-5 text-primary" /> : <Check className="h-5 w-5 text-emerald-400" />}<span>{count < data.matchups.length ? `${data.matchups.length - count} matchup${data.matchups.length - count === 1 ? "" : "s"} still need a pick. Blanks score as losses.` : "Your pick card is complete."}</span></div><Button disabled={saving} onClick={save} className="w-full bg-primary font-bold text-primary-foreground sm:w-auto"><Save className="h-4 w-4" />{saving ? "Saving…" : "Save picks"}</Button></div>}
  </>;
}

type Matchup = LiveWeek["matchups"][number];

function MatchupCard({ matchup, locked, selectedRosterId, onSelect }: { matchup: Matchup; locked: boolean; selectedRosterId?: number; onSelect: (rosterId: number) => void }) {
  const [benchOpen, setBenchOpen] = useState(false);

  return <article className="overflow-hidden rounded-2xl border border-white/9 bg-card">
    <div className="flex items-center justify-between border-b border-white/7 px-5 py-3 text-xs font-medium text-slate-500"><span>SLEEPER MATCHUP {matchup.sleeper_matchup_id}</span><span>{matchup.team_a.score ?? "—"} – {matchup.team_b.score ?? "—"}</span></div>
    <div className="grid lg:grid-cols-[minmax(0,1fr)_48px_minmax(0,1fr)]">
      <TeamPanel team={matchup.team_a} locked={locked} selected={selectedRosterId === matchup.team_a.roster_id} onSelect={() => onSelect(matchup.team_a.roster_id)} benchOpen={benchOpen} onToggleBench={() => setBenchOpen(current => !current)} />
      <div className="flex items-center justify-center border-y border-white/7 py-2 text-[11px] font-bold text-slate-600 lg:border-x lg:border-y-0 lg:py-0">VS</div>
      <TeamPanel team={matchup.team_b} locked={locked} selected={selectedRosterId === matchup.team_b.roster_id} onSelect={() => onSelect(matchup.team_b.roster_id)} benchOpen={benchOpen} onToggleBench={() => setBenchOpen(current => !current)} />
    </div>
  </article>;
}

function TeamPanel({ team, locked, selected, onSelect, benchOpen, onToggleBench }: { team: LiveTeam; locked: boolean; selected: boolean; onSelect: () => void; benchOpen: boolean; onToggleBench: () => void }) {
  const initials = team.name.split(" ").map(value => value[0]).join("").slice(0, 2).toUpperCase();
  return <section className="min-w-0">
    <button disabled={locked} onClick={onSelect} aria-pressed={selected} className={`group relative flex w-full items-center gap-4 px-5 py-5 text-left transition disabled:cursor-default ${selected ? "bg-primary/[.09]" : !locked ? "hover:bg-white/[.025]" : ""}`}>
      {selected && <span className="absolute right-4 top-4 grid h-6 w-6 place-items-center rounded-full bg-primary text-primary-foreground"><Check className="h-3.5 w-3.5" /></span>}
      <TeamAvatar url={team.avatar_url} initials={initials} selected={selected} />
      <span className="min-w-0 pr-7"><span className="block truncate text-[15px] font-bold leading-tight text-white">{team.name}</span><span className="mt-1 block truncate text-xs text-slate-500">{team.owner} · {team.record}</span><span className={`mt-2 block text-xs font-semibold ${selected ? "text-primary" : "text-slate-500"}`}>{selected ? "Your pick" : locked ? "Not selected" : "Select winner"}</span></span>
    </button>
    <div className="border-t border-white/7">
      <RosterSection label="Starters" players={team.starters ?? []} />
      <BenchSection players={team.bench ?? []} rosterId={team.roster_id} open={benchOpen} onToggle={onToggleBench} />
    </div>
  </section>;
}

function BenchSection({ players, rosterId, open, onToggle }: { players: LivePlayer[]; rosterId: number; open: boolean; onToggle: () => void }) {
  const contentId = `bench-${rosterId}`;

  return <div className="border-t border-white/6 bg-black/10">
    <button
      type="button"
      disabled={!players.length}
      aria-expanded={open}
      aria-controls={contentId}
      onClick={onToggle}
      className="flex w-full items-center justify-between px-5 py-3 text-left transition hover:bg-white/[.025] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary disabled:cursor-default disabled:hover:bg-transparent"
    >
      <span className="text-[11px] font-bold uppercase tracking-[.14em] text-slate-500">Bench · {players.length}</span>
      <span className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[.12em] text-slate-600">
        {players.length ? (open ? "Hide" : "Show") : "Empty"}
        {players.length > 0 && <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} />}
      </span>
    </button>
    {open && <div id={contentId} className="divide-y divide-white/5 border-t border-white/6">
      {players.map(player => <PlayerRow key={player.player_id} player={player} muted />)}
    </div>}
  </div>;
}

function RosterSection({ label, players, muted = false }: { label: string; players: LivePlayer[]; muted?: boolean }) {
  return <div className={muted ? "bg-black/10" : ""}>
    <div className="flex items-center justify-between border-b border-white/6 px-5 py-2.5"><h3 className="text-[11px] font-bold uppercase tracking-[.14em] text-slate-500">{label} · {players.length}</h3><span className="text-[10px] font-semibold uppercase tracking-[.12em] text-slate-600">Week pts</span></div>
    {players.length ? <div className="divide-y divide-white/5">{players.map(player => <PlayerRow key={player.player_id} player={player} muted={muted} />)}</div> : <p className="px-5 py-4 text-sm text-slate-600">No {label.toLowerCase()} returned by Sleeper.</p>}
  </div>;
}

function PlayerRow({ player, muted }: { player: LivePlayer; muted: boolean }) {
  return <div className={`grid grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-3 px-5 py-2.5 ${muted ? "text-slate-400" : ""}`}>
    <PlayerAvatar player={player} />
    <div className="min-w-0"><div className="flex min-w-0 items-center gap-2"><span className="shrink-0 rounded-md bg-white/5 px-1.5 py-0.5 text-[9px] font-bold text-slate-400">{player.position}</span><p className={`truncate text-sm font-semibold ${muted ? "text-slate-300" : "text-slate-100"}`}>{player.name}</p></div><p className="mt-0.5 truncate text-[11px] text-slate-600">{player.team ?? "Free agent"}{player.injury_status ? <span className="text-amber-400"> · {player.injury_status}</span> : null}</p></div>
    <span className={`tabular-nums text-sm font-semibold ${player.points && player.points > 0 ? "text-primary" : "text-slate-500"}`}>{player.points === null ? "—" : player.points.toFixed(1)}</span>
  </div>;
}

function TeamAvatar({ url, initials, selected }: { url?: string | null; initials: string; selected: boolean }) {
  const [failed, setFailed] = useState(false);
  const style = selected ? "border-primary bg-primary text-primary-foreground" : "border-white/10 bg-[#1b2535] text-slate-300";
  return <span className={`grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-2xl border text-sm font-black ${style}`}>
    {url && !failed ? <img src={url} alt="" loading="lazy" className="h-full w-full object-cover" onError={() => setFailed(true)} /> : initials}
  </span>;
}

function PlayerAvatar({ player }: { player: LivePlayer }) {
  const [failed, setFailed] = useState(false);
  return <span className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full border border-white/8 bg-[#1b2535] text-[9px] font-bold text-slate-500">
    {player.image_url && !failed ? <img src={player.image_url} alt="" loading="lazy" className="h-full w-full object-cover" onError={() => setFailed(true)} /> : player.position}
  </span>;
}

function State({ title, detail, children }: { title: string; detail: string; children: React.ReactNode }) {
  return <div className="mx-auto mt-20 max-w-xl rounded-2xl border border-white/9 bg-card p-8 text-center"><h1 className="text-2xl font-black">{title}</h1><p className="mx-auto mb-5 mt-2 max-w-md text-sm leading-relaxed text-slate-400">{detail}</p>{children}</div>;
}
