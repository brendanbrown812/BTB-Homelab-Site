"use client";

import { Database, LoaderCircle, RefreshCw, RotateCcw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { PageHeading } from "@/components/page-heading";
import { apiFetch, LiveWeek } from "@/lib/api";
import { UserManager } from "@/components/user-manager";
import { LeagueHistoryAdmin } from "@/components/league-history-admin";
import { ScheduledTaskManager } from "@/components/scheduled-task-manager";

export default function AdminPage() {
  const [week, setWeek] = useState<LiveWeek | null>(null); const [notice, setNotice] = useState(""); const [error, setError] = useState(""); const [working, setWorking] = useState("");
  async function load() { try { setWeek(await apiFetch<LiveWeek>("/predictions/current")); } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not load the active week."); } }
  useEffect(() => {
    let cancelled = false;
    apiFetch<LiveWeek>("/predictions/current")
      .then(value => { if (!cancelled) setWeek(value); })
      .catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load the active week."); });
    return () => { cancelled = true; };
  }, []);
  async function run(action: "refresh" | "finalize" | "recalculate") { if (!week) return; setWorking(action); setError(""); setNotice(""); try { await apiFetch(`/admin/predictions/weeks/${week.week.id}/${action}`, { method: "POST" }); setNotice(`${action[0].toUpperCase()}${action.slice(1)} completed.`); await load(); } catch (reason) { setError(reason instanceof Error ? reason.message : `${action} failed.`); } finally { setWorking(""); } }
  return <><PageHeading eyebrow="Commissioner tools" title="Admin">Manage Sleeper sync, BTB accounts, league history, and the prediction lifecycle.</PageHeading>{notice && <p role="status" className="mb-5 rounded-xl bg-emerald-400/10 px-4 py-3 text-sm text-emerald-300">{notice}</p>}{error && <p role="alert" className="mb-5 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}{!week ? <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div> : <><div className="grid gap-4 lg:grid-cols-3"><Panel icon={<RefreshCw />} title="Sleeper sync" body="Fetch the current matchup teams, owners, records, and scores directly from Sleeper."><Button disabled={!!working} onClick={() => run("refresh")} variant="secondary">{working === "refresh" ? "Refreshing…" : "Refresh week"}</Button></Panel><Panel icon={<ShieldCheck />} title={`Finalize Week ${week.week.number}`} body="Lock results, score every saved or blank pick, and calculate the weekly champion."><Button disabled={!!working || week.week.status === "final"} onClick={() => run("finalize")} className="bg-primary font-bold text-primary-foreground">{working === "finalize" ? "Finalizing…" : "Finalize results"}</Button></Panel><Panel icon={<RotateCcw />} title="Recalculate standings" body="Re-score saved picks using the current Sleeper result snapshot."><Button disabled={!!working || week.week.status !== "final"} onClick={() => run("recalculate")} variant="secondary">{working === "recalculate" ? "Recalculating…" : "Recalculate"}</Button></Panel></div><div className="mt-4 flex items-center gap-3 rounded-2xl border border-white/8 bg-card p-5 text-sm text-slate-400"><Database className="h-5 w-5 text-primary" /><span><strong className="text-white">{week.season.year} · Week {week.week.number}</strong> · {week.matchups.length} Sleeper matchups · <span className="capitalize">{week.week.status}</span></span></div></>}<ScheduledTaskManager /><UserManager /><LeagueHistoryAdmin /></>;
}

function Panel({ icon, title, body, children }: { icon: React.ReactNode; title: string; body: string; children: React.ReactNode }) { return <section className="rounded-2xl border border-white/8 bg-card p-6"><div className="mb-5 grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary [&>svg]:h-5 [&>svg]:w-5">{icon}</div><h2 className="text-lg font-bold">{title}</h2><p className="mb-5 mt-2 text-sm leading-relaxed text-slate-400">{body}</p>{children}</section>; }
