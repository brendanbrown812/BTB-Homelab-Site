"use client";

/* eslint-disable @next/next/no-img-element -- Sleeper player thumbnails come from its CDN. */

import Link from "next/link";
import { ArrowDownLeft, ArrowUpRight, CalendarDays, Coins, LoaderCircle, PackageOpen, RefreshCcw, Search, UsersRound } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import { PageHeading } from "@/components/page-heading";
import { apiFetch, PublicLeagueTransaction, PublicTransactionPlayer, PublicTransactionResponse, PublicTransactionSide } from "@/lib/api";

type Filters = { season: string; manager: string; player: string; transactionType: string; status: string };
const emptyFilters: Filters = { season: "", manager: "", player: "", transactionType: "", status: "" };

function useTransactions(path: string, filters: Filters) {
  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (filters.season) params.set("season", filters.season);
    if (filters.manager) params.set("manager_id", filters.manager);
    if (filters.player) params.set("player", filters.player);
    if (filters.transactionType) params.set("transaction_type", filters.transactionType);
    if (filters.status) params.set("status", filters.status);
    return params.size ? `${path}?${params}` : path;
  }, [filters, path]);
  const [result, setResult] = useState<{ query: string; data: PublicTransactionResponse } | null>(null);
  const [failure, setFailure] = useState<{ query: string; message: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    apiFetch<PublicTransactionResponse>(query)
      .then(value => { if (!cancelled) setResult({ query, data: value }); })
      .catch(reason => { if (!cancelled) setFailure({ query, message: reason instanceof Error ? reason.message : "Could not load transactions." }); });
    return () => { cancelled = true; };
  }, [query]);
  return {
    data: result?.query === query ? result.data : null,
    error: failure?.query === query ? failure.message : "",
  };
}

export function LeagueTradesPage() {
  const [filters, setFilters] = useState(emptyFilters);
  const { data, error } = useTransactions("/league-history/trades", filters);
  const years = data ? Array.from(new Set(data.items.map(item => item.season))).sort((a, b) => b - a) : [];
  return <>
    <PageHeading eyebrow="League history" title="Trades">Every imported deal, from simple swaps to full multi-manager blockbusters.</PageHeading>
    <TransactionFilters filters={filters} setFilters={setFilters} options={data?.options} mode="trades" />
    {error ? <State title="Trades unavailable" detail={error} /> : !data ? <Loading /> : !data.items.length ? <State title="No trades found" detail={emptyMessage(filters, "trades")} /> : <div className="space-y-9">
      {years.map(year => <section key={year}><div className="mb-4 flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 font-black text-primary">{String(year).slice(-2)}</span><div><h2 className="text-xl font-black">{year} season</h2><p className="text-xs text-slate-500">{data.items.filter(item => item.season === year).length} trades</p></div></div><div className="space-y-4">{data.items.filter(item => item.season === year).map(item => <TradeCard key={item.id} item={item} />)}</div></section>)}
    </div>}
  </>;
}

export function LeagueWaiversPage() {
  const [filters, setFilters] = useState(emptyFilters);
  const { data, error } = useTransactions("/league-history/waivers", filters);
  return <>
    <PageHeading eyebrow="League history" title="Waiver wire">Successful and unsuccessful waiver claims plus ordinary free-agent pickups.</PageHeading>
    <TransactionFilters filters={filters} setFilters={setFilters} options={data?.options} mode="waivers" />
    {error ? <State title="Waiver activity unavailable" detail={error} /> : !data ? <Loading /> : !data.items.length ? <State title="No waiver activity found" detail={emptyMessage(filters, "waiver activity")} /> : <div className="space-y-3">{data.items.map(item => <WaiverCard key={item.id} item={item} />)}</div>}
  </>;
}

function TransactionFilters({ filters, setFilters, options, mode }: { filters: Filters; setFilters: (value: Filters) => void; options?: PublicTransactionResponse["options"]; mode: "trades" | "waivers" }) {
  const [player, setPlayer] = useState(filters.player);
  function submit(event: FormEvent) { event.preventDefault(); setFilters({ ...filters, player: player.trim() }); }
  function reset() { setPlayer(""); setFilters(emptyFilters); }
  const active = Object.values(filters).some(Boolean);
  return <form onSubmit={submit} className="mb-7 rounded-2xl border border-white/8 bg-card p-4 sm:p-5">
    <div className={`grid gap-3 ${mode === "waivers" ? "md:grid-cols-2 xl:grid-cols-5" : "md:grid-cols-3"}`}>
      <FilterSelect label="Season" value={filters.season} onChange={value => setFilters({ ...filters, season: value })}><option value="">All seasons</option>{options?.seasons.map(year => <option key={year} value={year}>{year}</option>)}</FilterSelect>
      <FilterSelect label="Manager" value={filters.manager} onChange={value => setFilters({ ...filters, manager: value })}><option value="">All managers</option>{options?.managers.map(manager => <option key={manager.id} value={manager.id}>{manager.display_name}</option>)}</FilterSelect>
      <label className="block"><span className="mb-1.5 block text-xs font-bold uppercase tracking-[.1em] text-slate-500">Player</span><span className="flex rounded-xl border border-white/10 bg-[#0d131e] focus-within:border-primary/50"><input value={player} onChange={event => setPlayer(event.target.value)} placeholder="Name or player ID" className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm outline-none placeholder:text-slate-600" /><button title="Apply player filter" aria-label="Apply player filter" className="px-3 text-slate-500 hover:text-primary"><Search className="h-4 w-4" /></button></span></label>
      {mode === "waivers" && <><FilterSelect label="Activity" value={filters.transactionType} onChange={value => setFilters({ ...filters, transactionType: value })}><option value="">All activity</option>{options?.transaction_types.map(value => <option key={value} value={value}>{labelType(value)}</option>)}</FilterSelect><FilterSelect label="Status" value={filters.status} onChange={value => setFilters({ ...filters, status: value })}><option value="">All statuses</option>{options?.statuses.map(value => <option key={value} value={value}>{titleCase(value)}</option>)}</FilterSelect></>}
    </div>
    {active && <button type="button" onClick={reset} className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-white"><RefreshCcw className="h-3.5 w-3.5" />Clear filters</button>}
  </form>;
}

function FilterSelect({ label, value, onChange, children }: { label: string; value: string; onChange: (value: string) => void; children: ReactNode }) {
  return <label className="block"><span className="mb-1.5 block text-xs font-bold uppercase tracking-[.1em] text-slate-500">{label}</span><select value={value} onChange={event => onChange(event.target.value)} className="w-full rounded-xl border border-white/10 bg-[#0d131e] px-3 py-2.5 text-sm outline-none focus:border-primary/50">{children}</select></label>;
}

function TradeCard({ item }: { item: PublicLeagueTransaction }) {
  return <article className="overflow-hidden rounded-2xl border border-white/8 bg-card"><header className="flex flex-col gap-2 border-b border-white/7 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex flex-wrap items-center gap-2"><Status value={item.status} /><span className="text-sm font-semibold">Week {item.week}</span><span className="text-xs text-slate-600">·</span><span className="text-xs text-slate-500">{formatDate(item.occurred_at)}</span></div><div className="flex items-center gap-2 text-xs text-slate-500"><UsersRound className="h-3.5 w-3.5" />{item.participants.length}-manager trade</div></header><div className={`grid divide-y divide-white/7 ${item.sides.length === 2 ? "lg:grid-cols-2 lg:divide-x lg:divide-y-0" : "lg:grid-cols-3 lg:divide-x lg:divide-y-0"}`}>{item.sides.map(side => <TradeSide key={side.roster_id} side={side} />)}</div></article>;
}

function TradeSide({ side }: { side: PublicTransactionSide }) {
  const empty = !side.adds.length && !side.drops.length && !side.draft_picks_received.length && !side.draft_picks_sent.length && !side.faab_received && !side.faab_sent;
  return <section className="min-w-0 p-5"><Link href={`/league/teams/${side.manager_id}`} className="font-black hover:text-primary">{side.manager_name}</Link>{empty ? <p className="mt-4 text-sm text-slate-600">No normalized assets available.</p> : <div className="mt-4 space-y-4">
    {(side.adds.length > 0 || side.draft_picks_received.length > 0 || side.faab_received > 0) && <AssetGroup label="Received" icon={<ArrowDownLeft className="h-3.5 w-3.5" />} tone="text-emerald-300">{side.adds.map(player => <Player key={`add-${player.player_id}`} player={player} />)}{side.draft_picks_received.map((pick, index) => <Asset key={`received-${index}`} text={`${pick.season} Round ${pick.round} pick (${pick.original_manager_name})`} />)}{side.faab_received > 0 && <Asset text={`$${side.faab_received} FAAB`} coin />}</AssetGroup>}
    {(side.drops.length > 0 || side.draft_picks_sent.length > 0 || side.faab_sent > 0) && <AssetGroup label="Sent" icon={<ArrowUpRight className="h-3.5 w-3.5" />} tone="text-rose-300">{side.drops.map(player => <Player key={`drop-${player.player_id}`} player={player} />)}{side.draft_picks_sent.map((pick, index) => <Asset key={`sent-${index}`} text={`${pick.season} Round ${pick.round} pick`} />)}{side.faab_sent > 0 && <Asset text={`$${side.faab_sent} FAAB`} coin />}</AssetGroup>}
  </div>}</section>;
}

function WaiverCard({ item }: { item: PublicLeagueTransaction }) {
  const manager = item.participants[0];
  return <article className="rounded-2xl border border-white/8 bg-card p-5"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex flex-wrap items-center gap-2"><Type value={item.transaction_type} /><Status value={item.status} />{item.bid_amount !== null && <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2.5 py-1 text-xs font-bold text-primary"><Coins className="h-3 w-3" />${item.bid_amount} FAAB</span>}</div><div className="mt-3 flex flex-wrap items-center gap-2"><p className="font-bold">{manager ? <Link href={`/league/teams/${manager.manager_id}`} className="hover:text-primary">{manager.manager_name}</Link> : "Manager unavailable"}</p>{item.participants.length > 1 && <span className="text-xs text-slate-500">+ {item.participants.length - 1} more</span>}</div></div><div className="flex items-center gap-2 text-xs text-slate-500"><CalendarDays className="h-3.5 w-3.5" />{item.season} · Week {item.week} · {formatDate(item.occurred_at)}</div></div><div className="mt-5 grid gap-4 md:grid-cols-2"><AssetGroup label="Added" icon={<ArrowDownLeft className="h-3.5 w-3.5" />} tone="text-emerald-300">{item.adds.length ? item.adds.map(player => <Player key={`add-${player.player_id}`} player={player} />) : <Muted text="No player add returned" />}</AssetGroup><AssetGroup label="Dropped" icon={<ArrowUpRight className="h-3.5 w-3.5" />} tone="text-rose-300">{item.drops.length ? item.drops.map(player => <Player key={`drop-${player.player_id}`} player={player} />) : <Muted text="No player drop returned" />}</AssetGroup></div></article>;
}

function AssetGroup({ label, icon, tone, children }: { label: string; icon: ReactNode; tone: string; children: ReactNode }) { return <div><p className={`mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-[.1em] ${tone}`}>{icon}{label}</p><div className="space-y-2">{children}</div></div>; }
function Player({ player }: { player: PublicTransactionPlayer }) { const [failed, setFailed] = useState(false); return <div className="flex items-center gap-2.5 rounded-xl bg-white/[.03] p-2.5"><span className="grid h-8 w-8 shrink-0 place-items-center overflow-hidden rounded-full border border-white/8 bg-[#1b2535] text-[8px] font-bold text-slate-500">{player.image_url && !failed ? <img src={player.image_url} alt="" loading="lazy" className="h-full w-full object-cover" onError={() => setFailed(true)} /> : player.position ?? "—"}</span><span className="min-w-0"><strong className="block truncate text-sm">{player.name}</strong><span className="block text-[10px] text-slate-600">{[player.position, player.team].filter(Boolean).join(" · ") || player.player_id}</span></span></div>; }
function Asset({ text, coin = false }: { text: string; coin?: boolean }) { return <div className="flex items-center gap-2 rounded-xl bg-white/[.03] p-2.5 text-sm font-semibold">{coin ? <Coins className="h-4 w-4 text-primary" /> : <PackageOpen className="h-4 w-4 text-slate-500" />}{text}</div>; }
function Muted({ text }: { text: string }) { return <p className="rounded-xl border border-dashed border-white/8 p-3 text-xs text-slate-600">{text}</p>; }
function Type({ value }: { value: string }) { return <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${value === "waiver" ? "bg-violet-400/10 text-violet-300" : "bg-sky-400/10 text-sky-300"}`}>{labelType(value)}</span>; }
function Status({ value }: { value: string }) { const success = ["complete", "completed", "successful"].includes(value.toLowerCase()); const failed = ["failed", "invalid"].includes(value.toLowerCase()); return <span className={`rounded-full px-2.5 py-1 text-xs font-bold ${success ? "bg-emerald-400/10 text-emerald-300" : failed ? "bg-red-400/10 text-red-300" : "bg-amber-400/10 text-amber-300"}`}>{titleCase(value)}</span>; }
function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function State({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-10 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mx-auto mt-2 max-w-lg text-sm text-slate-400">{detail}</p></div>; }
function emptyMessage(filters: Filters, noun: string) { return Object.values(filters).some(Boolean) ? `No ${noun} match the selected filters.` : `No ${noun} have been imported for any season yet. Older ESPN seasons can still be browsed elsewhere in the archive.`; }
function labelType(value: string) { return value === "free_agent" ? "Free agent" : titleCase(value); }
function titleCase(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase()); }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }
