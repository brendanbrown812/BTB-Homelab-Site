"use client";

import { FormEvent, useEffect, useState } from "react";
import { BookOpen, CalendarDays, CheckCircle2, Database, Pencil, Plus, RefreshCw, Trash2, TriangleAlert, UsersRound } from "lucide-react";

import {
  apiFetch,
  LeagueHistoryAdminState,
  LeagueManager,
  LeagueSeasonFact,
  LeagueSeasonTeam,
  LeagueWeeklyHighlight,
  ManagedLeagueSeason,
} from "@/lib/api";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

type Mutation = (path: string, init: RequestInit, success: string) => Promise<boolean>;

export function LeagueHistoryAdmin() {
  const [data, setData] = useState<LeagueHistoryAdminState | null>(null);
  const [selectedSeasonId, setSelectedSeasonId] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function load() {
    const value = await apiFetch<LeagueHistoryAdminState>("/admin/league-history");
    setData(value);
    setSelectedSeasonId(current => current && value.seasons.some(season => season.id === current) ? current : value.seasons[0]?.id ?? "");
  }

  useEffect(() => {
    let cancelled = false;
    apiFetch<LeagueHistoryAdminState>("/admin/league-history")
      .then(value => { if (!cancelled) { setData(value); setSelectedSeasonId(value.seasons[0]?.id ?? ""); } })
      .catch(reason => { if (!cancelled) setError(message(reason, "Could not load league history administration.")); });
    return () => { cancelled = true; };
  }, []);

  const mutate: Mutation = async (path, init, success) => {
    setSaving(true); setError(""); setNotice("");
    try {
      await apiFetch(path, init);
      await load();
      setNotice(success);
      return true;
    } catch (reason) {
      setError(message(reason, "Could not save league history."));
      return false;
    } finally {
      setSaving(false);
    }
  };

  return <section className="mt-6 overflow-hidden rounded-2xl border border-white/8 bg-card">
    <div className="flex items-center gap-3 border-b border-white/8 p-5"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><BookOpen className="h-5 w-5" /></span><div><h2 className="font-bold">League history</h2><p className="text-sm text-slate-500">Manage permanent managers, seasons, identities, and manual league records.</p></div></div>
    {notice && <p role="status" className="mx-5 mt-5 rounded-xl bg-emerald-400/10 px-4 py-3 text-sm text-emerald-300">{notice}</p>}
    {error && <p role="alert" className="mx-5 mt-5 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}
    {!data ? <div className="grid min-h-40 place-items-center text-sm text-slate-500">Loading league history…</div> : <Tabs defaultValue="managers" className="p-5">
      <TabsList variant="line" className="mb-5 grid h-auto w-full grid-cols-2 bg-transparent p-0 sm:grid-cols-4"><TabsTrigger value="managers">Managers</TabsTrigger><TabsTrigger value="seasons">Seasons</TabsTrigger><TabsTrigger value="details">Season details</TabsTrigger><TabsTrigger value="imports">Imports</TabsTrigger></TabsList>
      <TabsContent value="managers"><ManagersPanel data={data} mutate={mutate} saving={saving} /></TabsContent>
      <TabsContent value="seasons"><SeasonsPanel seasons={data.seasons} mutate={mutate} saving={saving} /></TabsContent>
      <TabsContent value="details"><SeasonDetails data={data} seasonId={selectedSeasonId} onSeasonChange={setSelectedSeasonId} mutate={mutate} saving={saving} /></TabsContent>
      <TabsContent value="imports"><NotionImportPanel data={data} mutate={mutate} saving={saving} /></TabsContent>
    </Tabs>}
  </section>;
}

function ManagersPanel({ data, mutate, saving }: { data: LeagueHistoryAdminState; mutate: Mutation; saving: boolean }) {
  return <div className="space-y-4">
    <div className="flex items-center justify-between gap-4"><div><h3 className="font-bold">Permanent managers</h3><p className="text-sm text-slate-500">Former managers do not need a BTB account.</p></div><ManagerDialog users={data.users} mutate={mutate} saving={saving} /></div>
    <div className="grid gap-4 xl:grid-cols-2">{data.managers.map(manager => <article key={manager.id} className="rounded-xl border border-white/8 bg-white/[.025] p-4">
      <div className="flex items-start justify-between gap-3"><div><h4 className="font-semibold">{manager.display_name}</h4><p className="text-xs text-slate-500">{manager.is_active ? "Active manager" : "Former manager"}{manager.user_id ? " · BTB account linked" : " · No account linked"}</p></div><ManagerDialog manager={manager} users={data.users} mutate={mutate} saving={saving} /></div>
      {manager.biography && <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-400">{manager.biography}</p>}
      <div className="mt-4 flex flex-wrap gap-2">{manager.aliases.map(alias => <span key={alias.id} className="inline-flex items-center gap-1.5 rounded-full bg-white/5 px-2.5 py-1 text-xs text-slate-300">{alias.provider === "notion_name" ? "Notion" : "Sleeper"}: {alias.external_value}<ConfirmDelete label={`Remove ${alias.external_value}?`} disabled={saving} onDelete={() => mutate(`/admin/league-history/aliases/${alias.id}`, { method: "DELETE" }, "Alias removed.")} compact /></span>)}</div>
      <form className="mt-3 flex flex-col gap-2 sm:flex-row" onSubmit={async event => { event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); if (await mutate(`/admin/league-history/managers/${manager.id}/aliases`, { method: "POST", body: JSON.stringify({ provider: form.get("provider"), external_value: form.get("external_value") }) }, "Alias added.")) formElement.reset(); }}><NativeSelect name="provider" aria-label="Alias provider"><NativeSelectOption value="notion_name">Notion name</NativeSelectOption><NativeSelectOption value="sleeper_user_id">Sleeper user ID</NativeSelectOption></NativeSelect><Input name="external_value" required maxLength={255} placeholder="Name or user ID" /><Button size="sm" variant="secondary" disabled={saving}><Plus className="h-4 w-4" />Alias</Button></form>
    </article>)}</div>
  </div>;
}

function ManagerDialog({ manager, users, mutate, saving }: { manager?: LeagueManager; users: LeagueHistoryAdminState["users"]; mutate: Mutation; saving: boolean }) {
  const [open, setOpen] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget); const userId = optional(form, "user_id");
    const ok = await mutate(manager ? `/admin/league-history/managers/${manager.id}` : "/admin/league-history/managers", {
      method: manager ? "PATCH" : "POST",
      body: JSON.stringify({ display_name: form.get("display_name"), biography: form.get("biography"), is_active: form.get("is_active") === "on", user_id: userId, ...(manager && !userId ? { clear_user_link: true } : {}) }),
    }, manager ? "Manager updated." : "Manager created.");
    if (ok) setOpen(false);
  }
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild>{manager ? <Button size="icon" variant="ghost" aria-label={`Edit ${manager.display_name}`}><Pencil className="h-4 w-4" /></Button> : <Button className="bg-primary font-bold text-primary-foreground"><Plus className="h-4 w-4" />Add manager</Button>}</DialogTrigger><DialogContent className="max-h-[90vh] overflow-y-auto border-white/10 bg-card"><DialogHeader><DialogTitle>{manager ? "Edit manager" : "Add manager"}</DialogTitle><DialogDescription>Manager history remains even when no BTB account is linked.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}>
    <Field label="Display name" id={`${manager?.id ?? "new"}-manager-name`}><Input id={`${manager?.id ?? "new"}-manager-name`} name="display_name" required maxLength={120} defaultValue={manager?.display_name} /></Field>
    <Field label="Linked BTB account" id={`${manager?.id ?? "new"}-manager-user`}><NativeSelect id={`${manager?.id ?? "new"}-manager-user`} name="user_id" defaultValue={manager?.user_id ?? ""} className="w-full"><NativeSelectOption value="">No linked account</NativeSelectOption>{users.map(user => <NativeSelectOption key={user.id} value={user.id}>{user.display_name} (@{user.username})</NativeSelectOption>)}</NativeSelect></Field>
    <Field label="Biography" id={`${manager?.id ?? "new"}-manager-bio`}><Textarea id={`${manager?.id ?? "new"}-manager-bio`} name="biography" maxLength={10000} defaultValue={manager?.biography} /></Field>
    <label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" name="is_active" defaultChecked={manager?.is_active ?? true} className="h-4 w-4 accent-primary" />Active league manager</label>
    <Button className="w-full bg-primary font-bold text-primary-foreground" disabled={saving}>{saving ? "Saving…" : "Save manager"}</Button>
  </form></DialogContent></Dialog>;
}

function SeasonsPanel({ seasons, mutate, saving }: { seasons: ManagedLeagueSeason[]; mutate: Mutation; saving: boolean }) {
  return <div className="space-y-4"><div className="flex items-center justify-between gap-4"><div><h3 className="font-bold">League seasons</h3><p className="text-sm text-slate-500">ESPN seasons require no Sleeper ID.</p></div><SeasonDialog mutate={mutate} saving={saving} /></div><div className="space-y-3">{seasons.map(season => <div key={season.id} className="flex flex-col gap-3 rounded-xl border border-white/8 bg-white/[.025] p-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 font-black text-primary">{String(season.year).slice(-2)}</span><div><h4 className="font-semibold">{season.year} season {season.is_active && <span className="ml-2 rounded-full bg-emerald-400/10 px-2 py-0.5 text-xs text-emerald-300">Active</span>}</h4><p className="text-xs text-slate-500"><span className="uppercase">{season.platform}</span>{season.sleeper_league_id ? ` · ${season.sleeper_league_id}` : " · Manual history"} · {season.teams.length} managers</p></div></div><SeasonDialog season={season} mutate={mutate} saving={saving} /></div>)}</div></div>;
}

function SeasonDialog({ season, mutate, saving }: { season?: ManagedLeagueSeason; mutate: Mutation; saving: boolean }) {
  const [open, setOpen] = useState(false); const [platform, setPlatform] = useState<"espn" | "sleeper">(season?.platform ?? "sleeper");
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const leagueId = optional(form, "sleeper_league_id"); const ok = await mutate(season ? `/admin/league-history/seasons/${season.id}` : "/admin/league-history/seasons", { method: season ? "PATCH" : "POST", body: JSON.stringify({ year: Number(form.get("year")), platform, sleeper_league_id: platform === "sleeper" ? leagueId : null, is_active: form.get("is_active") === "on", ...(season && platform === "espn" ? { clear_sleeper_league_id: true } : {}) }) }, season ? "Season updated." : "Season created."); if (ok) setOpen(false); }
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild>{season ? <Button size="sm" variant="outline"><Pencil className="h-4 w-4" />Edit</Button> : <Button className="bg-primary font-bold text-primary-foreground"><Plus className="h-4 w-4" />Add season</Button>}</DialogTrigger><DialogContent className="border-white/10 bg-card"><DialogHeader><DialogTitle>{season ? `Edit ${season.year}` : "Add season"}</DialogTitle><DialogDescription>Use ESPN for 2020–2021 and Sleeper for later seasons.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}><Field label="Year" id="season-year"><Input id="season-year" name="year" type="number" min={2020} max={2100} required defaultValue={season?.year ?? new Date().getFullYear()} /></Field><Field label="Platform" id="season-platform"><NativeSelect id="season-platform" value={platform} onChange={event => setPlatform(event.target.value as "espn" | "sleeper")} className="w-full"><NativeSelectOption value="espn">ESPN</NativeSelectOption><NativeSelectOption value="sleeper">Sleeper</NativeSelectOption></NativeSelect></Field>{platform === "sleeper" && <Field label="Sleeper league ID" id="season-sleeper-id"><Input id="season-sleeper-id" name="sleeper_league_id" required maxLength={80} defaultValue={season?.sleeper_league_id ?? ""} /></Field>}<label className="flex items-center gap-2 text-sm text-slate-300"><input type="checkbox" name="is_active" defaultChecked={season?.is_active} className="h-4 w-4 accent-primary" />Current active season</label><Button className="w-full bg-primary font-bold text-primary-foreground" disabled={saving}>{saving ? "Saving…" : "Save season"}</Button></form></DialogContent></Dialog>;
}

function SeasonDetails({ data, seasonId, onSeasonChange, mutate, saving }: { data: LeagueHistoryAdminState; seasonId: string; onSeasonChange: (id: string) => void; mutate: Mutation; saving: boolean }) {
  const season = data.seasons.find(item => item.id === seasonId);
  if (!data.seasons.length) return <p className="rounded-xl border border-dashed border-white/10 p-8 text-center text-sm text-slate-500">Create a season before adding its history.</p>;
  if (!season) return null;
  return <div className="space-y-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><h3 className="font-bold">Season details</h3><p className="text-sm text-slate-500">Manual corrections are retained separately from calculated data.</p></div><NativeSelect value={seasonId} onChange={event => onSeasonChange(event.target.value)}>{data.seasons.map(item => <NativeSelectOption key={item.id} value={item.id}>{item.year} · {item.platform.toUpperCase()}</NativeSelectOption>)}</NativeSelect></div>
    {season.platform === "sleeper" && <SleeperImportPanel season={season} data={data} mutate={mutate} saving={saving} />}
    <Subsection title="Teams and managers" icon={<UsersRound />} action={<TeamDialog season={season} managers={data.managers} mutate={mutate} saving={saving} />}><div className="space-y-3">{season.teams.length ? season.teams.map(team => <SeasonTeamRow key={team.id} team={team} season={season} managers={data.managers} mutate={mutate} saving={saving} />) : <Empty text="No managers assigned to this season." />}</div></Subsection>
    <Subsection title="Placements" icon={<CalendarDays />}><div className="grid gap-3 lg:grid-cols-2">{season.teams.length ? season.teams.map(team => <PlacementForm key={team.id} team={team} season={season} manager={data.managers.find(manager => manager.id === team.manager_id)} mutate={mutate} saving={saving} />) : <Empty text="Assign managers before entering placements." />}</div></Subsection>
    <Subsection title="Last-place punishment"><PunishmentForm season={season} managers={data.managers} mutate={mutate} saving={saving} /></Subsection>
    <Subsection title="Custom season facts"><FactsEditor season={season} mutate={mutate} saving={saving} /></Subsection>
    <Subsection title="Manual weekly highlights"><HighlightsEditor season={season} managers={data.managers} mutate={mutate} saving={saving} /></Subsection>
  </div>;
}

function SleeperImportPanel({ season, data, mutate, saving }: { season: ManagedLeagueSeason; data: LeagueHistoryAdminState; mutate: Mutation; saving: boolean }) {
  const latest = data.import_runs.find(run => run.season_id === season.id && run.source === "sleeper");
  const unresolved = Array.isArray(latest?.counts.unresolved_identities) ? latest.counts.unresolved_identities.length : 0;
  return <Subsection title="Sleeper import" icon={<Database />}>
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="text-sm text-slate-400">
        <p>Preview identity mappings before atomically importing teams, matchups, transactions, and placements.</p>
        {latest && <p className="mt-1 text-xs text-slate-500">Last attempt: <span className={latest.status === "succeeded" ? "text-emerald-300" : latest.status === "needs_attention" ? "text-amber-300" : "text-red-300"}>{latest.status.replace("_", " ")}</span>{unresolved ? ` · ${unresolved} unresolved` : ""}{latest.error_details ? ` · ${latest.error_details}` : ""}</p>}
      </div>
      <div className="flex shrink-0 gap-2">
        <Button variant="outline" disabled={saving} onClick={() => void mutate(`/admin/league-history/seasons/${season.id}/sleeper/dry-run`, { method: "POST" }, "Sleeper dry run completed.")}><RefreshCw className="h-4 w-4" />Dry run</Button>
        <Button className="bg-primary font-bold text-primary-foreground" disabled={saving} onClick={() => void mutate(`/admin/league-history/seasons/${season.id}/sleeper/import`, { method: "POST" }, "Sleeper season imported.")}><Database className="h-4 w-4" />Import / refresh</Button>
      </div>
    </div>
  </Subsection>;
}

function NotionImportPanel({ data, mutate, saving }: { data: LeagueHistoryAdminState; mutate: Mutation; saving: boolean }) {
  const notionRuns = data.import_runs.filter(run => run.source === "notion");
  const latest = notionRuns[0];
  const dryRunReady = latest?.counts.mode === "dry_run" && latest.status === "succeeded";
  const counts = latest?.counts ?? {};
  const rows = recordOfNumbers(counts.rows_per_season);
  const inserts = recordOfNumbers(counts.records_to_insert);
  const updates = recordOfNumbers(counts.records_to_update);
  const unresolvedNames = stringArray(counts.unresolved_names);
  const duplicateRows = objectArray(counts.duplicate_rows);
  const invalidRows = objectArray(counts.invalid_records);
  const unresolved = unresolvedNames.length;
  const duplicates = duplicateRows.length;
  const invalid = invalidRows.length;
  const skipped = arrayLength(counts.skipped_out_of_scope);

  return <div className="space-y-5">
    <div><h3 className="font-bold">One-time Notion import</h3><p className="text-sm text-slate-500">Bring the 2020 and 2021 ESPN matchup archive into BTB. Notion credentials stay on the API server and are never sent to this page.</p></div>
    <Subsection title="ESPN game history" icon={<Database />}>
      <div className="space-y-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="text-sm text-slate-400"><p>Run a preview first. BTB will validate seasons, manager aliases, scores, weeks, duplicates, and all two-week playoff series before writing anything.</p>{latest && <p className="mt-2 text-xs text-slate-500">Last attempt: {new Date(latest.started_at).toLocaleString()} · <ImportStatus status={latest.status} />{latest.error_details ? ` · ${latest.error_details}` : ""}</p>}</div>
          <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
            <Button variant="outline" disabled={saving} onClick={() => void mutate("/admin/league-history/notion/dry-run", { method: "POST" }, "Notion dry run completed. Review the report below.")}><RefreshCw className={`h-4 w-4 ${saving ? "animate-spin" : ""}`} />Dry run</Button>
            <AlertDialog><AlertDialogTrigger asChild><Button className="bg-primary font-bold text-primary-foreground" disabled={saving || !dryRunReady}><Database className="h-4 w-4" />Import 2020–2021</Button></AlertDialogTrigger><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Import ESPN game history?</AlertDialogTitle><AlertDialogDescription>This will insert or update the validated 2020 and 2021 matchups in PostgreSQL. Repeating the import is safe, but Notion should no longer be treated as the source of truth afterward.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction onClick={() => void mutate("/admin/league-history/notion/import", { method: "POST" }, "Notion game history imported successfully.")}>Run import</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
          </div>
        </div>
        {!dryRunReady && <p className="rounded-xl border border-amber-300/15 bg-amber-300/[.06] px-4 py-3 text-sm text-amber-200"><TriangleAlert className="mr-2 inline h-4 w-4" />A successful dry run is required before the import button is enabled.</p>}
        {latest && <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><ImportMetric label="2020 rows" value={rows["2020"] ?? 0} /><ImportMetric label="2021 rows" value={rows["2021"] ?? 0} /><ImportMetric label="Will insert" value={sumValues(inserts)} /><ImportMetric label="Will update" value={sumValues(updates)} /></div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><ImportCheck label="Unresolved names" value={unresolved} /><ImportCheck label="Invalid records" value={invalid} /><ImportCheck label="Duplicates" value={duplicates} /><ImportMetric label="Other years skipped" value={skipped} /></div>
          {unresolved > 0 && <ImportIssueList title="Unresolved manager names" items={unresolvedNames} />}
          {invalid > 0 && <ImportIssueList title="Invalid Notion rows" items={invalidRows.map(item => `${String(item.page_id ?? item.season ?? "Unknown row")}: ${stringArray(item.errors).join(", ") || "Invalid data"}`)} />}
          {duplicates > 0 && <ImportIssueList title="Duplicate matchups" items={duplicateRows.map(item => `${String(item.year ?? "Unknown year")} Week ${String(item.week ?? "?")}: ${String(item.duplicate_page_id ?? "duplicate row")}`)} />}
          {latest.status === "succeeded" && unresolved + invalid + duplicates === 0 && <p className="rounded-xl border border-emerald-300/15 bg-emerald-300/[.06] px-4 py-3 text-sm text-emerald-200"><CheckCircle2 className="mr-2 inline h-4 w-4" />Validation passed. The ESPN archive is ready to import.</p>}
        </div>}
      </div>
    </Subsection>
  </div>;
}

function ImportStatus({ status }: { status: LeagueHistoryAdminState["import_runs"][number]["status"] }) {
  return <span className={status === "succeeded" ? "text-emerald-300" : status === "needs_attention" ? "text-amber-300" : status === "running" ? "text-sky-300" : "text-red-300"}>{status.replace("_", " ")}</span>;
}

function ImportMetric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-xl bg-white/[.025] p-3"><p className="text-xs font-semibold uppercase tracking-[.1em] text-slate-500">{label}</p><p className="mt-1 text-xl font-black text-slate-100">{value}</p></div>;
}

function ImportCheck({ label, value }: { label: string; value: number }) {
  return <div className={`rounded-xl p-3 ${value ? "bg-amber-300/[.06]" : "bg-emerald-300/[.05]"}`}><p className="text-xs font-semibold uppercase tracking-[.1em] text-slate-500">{label}</p><p className={`mt-1 text-xl font-black ${value ? "text-amber-200" : "text-emerald-300"}`}>{value}</p></div>;
}

function ImportIssueList({ title, items }: { title: string; items: string[] }) {
  return <details className="rounded-xl border border-amber-300/15 bg-amber-300/[.04] p-4"><summary className="cursor-pointer text-sm font-bold text-amber-200">{title} ({items.length})</summary><ul className="mt-3 space-y-1 pl-5 text-sm text-slate-400">{items.map((item, index) => <li key={`${item}-${index}`} className="list-disc break-words">{item}</li>)}</ul></details>;
}

function recordOfNumbers(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(Object.entries(value).filter((entry): entry is [string, number] => typeof entry[1] === "number"));
}
function arrayLength(value: unknown) { return Array.isArray(value) ? value.length : 0; }
function stringArray(value: unknown): string[] { return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : []; }
function objectArray(value: unknown): Array<Record<string, unknown>> { return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => !!item && typeof item === "object" && !Array.isArray(item)) : []; }
function sumValues(value: Record<string, number>) { return Object.values(value).reduce((total, count) => total + count, 0); }

function TeamDialog({ season, managers, mutate, saving, team }: { season: ManagedLeagueSeason; managers: LeagueManager[]; mutate: Mutation; saving: boolean; team?: LeagueSeasonTeam }) {
  const [open, setOpen] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const sleeperUser = optional(form, "sleeper_user_id"); const roster = optionalNumber(form, "roster_id"); const ok = await mutate(team ? `/admin/league-history/season-teams/${team.id}` : `/admin/league-history/seasons/${season.id}/teams`, { method: team ? "PATCH" : "POST", body: JSON.stringify({ manager_id: form.get("manager_id"), team_name: form.get("team_name"), sleeper_user_id: sleeperUser, roster_id: roster, ...(team && !sleeperUser ? { clear_sleeper_user_id: true } : {}), ...(team && roster === null ? { clear_roster_id: true } : {}) }) }, team ? "Season assignment updated." : "Manager assigned to season."); if (ok) setOpen(false); }
  return <Dialog open={open} onOpenChange={setOpen}><DialogTrigger asChild>{team ? <Button size="icon" variant="ghost" aria-label={`Edit ${team.team_name}`}><Pencil className="h-4 w-4" /></Button> : <Button size="sm" variant="secondary"><Plus className="h-4 w-4" />Assign manager</Button>}</DialogTrigger><DialogContent className="border-white/10 bg-card"><DialogHeader><DialogTitle>{team ? "Edit season assignment" : `Assign manager to ${season.year}`}</DialogTitle><DialogDescription>Names and IDs here are snapshots for this specific season.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}><Field label="Manager" id="team-manager"><NativeSelect id="team-manager" name="manager_id" required defaultValue={team?.manager_id} className="w-full"><NativeSelectOption value="" disabled>Select manager</NativeSelectOption>{managers.map(manager => <NativeSelectOption key={manager.id} value={manager.id}>{manager.display_name}</NativeSelectOption>)}</NativeSelect></Field><Field label="Team name that season" id="team-name"><Input id="team-name" name="team_name" required maxLength={120} defaultValue={team?.team_name} /></Field>{season.platform === "sleeper" && <><Field label="Sleeper user ID" id="team-sleeper-user"><Input id="team-sleeper-user" name="sleeper_user_id" maxLength={80} defaultValue={team?.sleeper_user_id ?? ""} /></Field><Field label="Roster ID" id="team-roster"><Input id="team-roster" name="roster_id" type="number" min={1} defaultValue={team?.roster_id ?? ""} /></Field></>}<Button className="w-full bg-primary font-bold text-primary-foreground" disabled={saving}>{saving ? "Saving…" : "Save assignment"}</Button></form></DialogContent></Dialog>;
}

function SeasonTeamRow({ team, season, managers, mutate, saving }: { team: LeagueSeasonTeam; season: ManagedLeagueSeason; managers: LeagueManager[]; mutate: Mutation; saving: boolean }) {
  return <div className="flex items-center justify-between gap-3 rounded-xl bg-white/[.025] p-3"><div><p className="font-medium">{team.team_name}</p><p className="text-xs text-slate-500">{managers.find(manager => manager.id === team.manager_id)?.display_name ?? "Unknown manager"}{team.roster_id ? ` · Roster ${team.roster_id}` : ""}</p></div><div className="flex gap-1"><TeamDialog team={team} season={season} managers={managers} mutate={mutate} saving={saving} /><ConfirmDelete label={`Remove ${team.team_name} from ${season.year}?`} disabled={saving} onDelete={() => mutate(`/admin/league-history/season-teams/${team.id}`, { method: "DELETE" }, "Season assignment removed.")} /></div></div>;
}

function PlacementForm({ team, season, manager, mutate, saving }: { team: LeagueSeasonTeam; season: ManagedLeagueSeason; manager?: LeagueManager; mutate: Mutation; saving: boolean }) {
  const placement = season.placements.find(item => item.manager_id === team.manager_id);
  return <form className="rounded-xl bg-white/[.025] p-4" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); const calculated = optionalNumber(form, "calculated_placement"); const override = optionalNumber(form, "override_placement"); void mutate(`/admin/league-history/seasons/${season.id}/placements/${team.manager_id}`, { method: "PUT", body: JSON.stringify({ calculated_placement: calculated, override_placement: override, clear_override: override === null }) }, "Placement saved."); }}><p className="mb-3 font-medium">{manager?.display_name ?? team.team_name}</p><div className="grid grid-cols-2 gap-3"><Field label="Calculated" id={`${team.id}-calculated`}><Input id={`${team.id}-calculated`} name="calculated_placement" type="number" min={1} defaultValue={placement?.calculated_placement ?? ""} placeholder="—" /></Field><Field label="Override" id={`${team.id}-override`}><Input id={`${team.id}-override`} name="override_placement" type="number" min={1} defaultValue={placement?.override_placement ?? ""} placeholder="—" /></Field></div><Button size="sm" variant="secondary" className="mt-3" disabled={saving}>Save placement</Button></form>;
}

function PunishmentForm({ season, managers, mutate, saving }: { season: ManagedLeagueSeason; managers: LeagueManager[]; mutate: Mutation; saving: boolean }) {
  return <form className="space-y-3" onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); void mutate(`/admin/league-history/seasons/${season.id}/punishment`, { method: "PUT", body: JSON.stringify({ manager_id: form.get("manager_id"), title: form.get("title") }) }, "Punishment saved."); }}><div className="grid gap-3 md:grid-cols-[220px_1fr_auto]"><NativeSelect name="manager_id" required defaultValue={season.punishment?.manager_id ?? ""}><NativeSelectOption value="" disabled>Select manager</NativeSelectOption>{managers.map(manager => <NativeSelectOption key={manager.id} value={manager.id}>{manager.display_name}</NativeSelectOption>)}</NativeSelect><Input name="title" required maxLength={240} defaultValue={season.punishment?.title ?? ""} placeholder="Punishment title" /><Button disabled={saving}>{saving ? "Saving…" : "Save"}</Button></div>{season.punishment && <ConfirmDelete label={`Remove the ${season.year} punishment?`} disabled={saving} onDelete={() => mutate(`/admin/league-history/seasons/${season.id}/punishment`, { method: "DELETE" }, "Punishment removed.")} textLabel="Remove punishment" />}</form>;
}

function FactsEditor({ season, mutate, saving }: { season: ManagedLeagueSeason; mutate: Mutation; saving: boolean }) {
  return <div className="space-y-3">{season.facts.map(fact => <FactForm key={fact.id} season={season} fact={fact} mutate={mutate} saving={saving} />)}<FactForm season={season} mutate={mutate} saving={saving} /></div>;
}

function FactForm({ season, fact, mutate, saving }: { season: ManagedLeagueSeason; fact?: LeagueSeasonFact; mutate: Mutation; saving: boolean }) {
  return <form className="grid gap-2 rounded-xl bg-white/[.025] p-3 md:grid-cols-[70px_minmax(140px,.7fr)_1fr_auto]" onSubmit={async event => { event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); const ok = await mutate(fact ? `/admin/league-history/facts/${fact.id}` : `/admin/league-history/seasons/${season.id}/facts`, { method: fact ? "PATCH" : "POST", body: JSON.stringify({ display_order: Number(form.get("display_order")), label: form.get("label"), value: form.get("value") }) }, fact ? "Season fact updated." : "Season fact added."); if (ok && !fact) formElement.reset(); }}><Input aria-label="Display order" name="display_order" type="number" min={0} required defaultValue={fact?.display_order ?? season.facts.length} /><Input aria-label="Fact label" name="label" required maxLength={160} defaultValue={fact?.label} placeholder="Label" /><Input aria-label="Fact value" name="value" required maxLength={10000} defaultValue={fact?.value} placeholder="Value" /><div className="flex gap-1"><Button size="sm" variant="secondary" disabled={saving}>{fact ? "Save" : "Add"}</Button>{fact && <ConfirmDelete label={`Remove ${fact.label}?`} disabled={saving} onDelete={() => mutate(`/admin/league-history/facts/${fact.id}`, { method: "DELETE" }, "Season fact removed.")} />}</div></form>;
}

function HighlightsEditor({ season, managers, mutate, saving }: { season: ManagedLeagueSeason; managers: LeagueManager[]; mutate: Mutation; saving: boolean }) {
  return <div className="space-y-3">{season.highlights.map(highlight => <HighlightForm key={highlight.id} season={season} managers={managers} highlight={highlight} mutate={mutate} saving={saving} />)}<HighlightForm season={season} managers={managers} mutate={mutate} saving={saving} /></div>;
}

function HighlightForm({ season, managers, highlight, mutate, saving }: { season: ManagedLeagueSeason; managers: LeagueManager[]; highlight?: LeagueWeeklyHighlight; mutate: Mutation; saving: boolean }) {
  return <form className="grid gap-2 rounded-xl bg-white/[.025] p-3 md:grid-cols-[70px_minmax(140px,1fr)_minmax(140px,1fr)_100px_auto]" onSubmit={async event => { event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); const managerId = optional(form, "manager_id"); const playerName = optional(form, "player_name"); const value = optionalFloat(form, "value"); const ok = await mutate(highlight ? `/admin/league-history/highlights/${highlight.id}` : `/admin/league-history/seasons/${season.id}/highlights`, { method: highlight ? "PATCH" : "POST", body: JSON.stringify({ week: Number(form.get("week")), category: form.get("category"), manager_id: managerId, player_name: playerName, value, ...(highlight && !managerId ? { clear_manager: true } : {}), ...(highlight && !playerName ? { clear_player: true } : {}), ...(highlight && value === null ? { clear_value: true } : {}) }) }, highlight ? "Weekly highlight updated." : "Weekly highlight added."); if (ok && !highlight) formElement.reset(); }}><Input aria-label="Week" name="week" type="number" min={1} max={30} required defaultValue={highlight?.week} placeholder="Week" /><Input aria-label="Category" name="category" required maxLength={80} defaultValue={highlight?.category} placeholder="Category" /><div className="grid grid-cols-2 gap-2"><NativeSelect name="manager_id" aria-label="Manager" defaultValue={highlight?.manager_id ?? ""}><NativeSelectOption value="">No manager</NativeSelectOption>{managers.map(manager => <NativeSelectOption key={manager.id} value={manager.id}>{manager.display_name}</NativeSelectOption>)}</NativeSelect><Input aria-label="Player name" name="player_name" maxLength={160} defaultValue={highlight?.player_name ?? ""} placeholder="Player" /></div><Input aria-label="Value" name="value" type="number" step="any" defaultValue={highlight?.value ?? ""} placeholder="Value" /><div className="flex gap-1"><Button size="sm" variant="secondary" disabled={saving}>{highlight ? "Save" : "Add"}</Button>{highlight && <ConfirmDelete label={`Remove ${highlight.category}?`} disabled={saving} onDelete={() => mutate(`/admin/league-history/highlights/${highlight.id}`, { method: "DELETE" }, "Weekly highlight removed.")} />}</div></form>;
}

function Subsection({ title, icon, action, children }: { title: string; icon?: React.ReactNode; action?: React.ReactNode; children: React.ReactNode }) { return <section className="rounded-xl border border-white/8 p-4"><div className="mb-4 flex items-center justify-between gap-3"><h4 className="flex items-center gap-2 font-semibold text-slate-200">{icon}{title}</h4>{action}</div>{children}</section>; }
function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) { return <div className="space-y-2"><Label htmlFor={id}>{label}</Label>{children}</div>; }
function Empty({ text }: { text: string }) { return <p className="rounded-xl border border-dashed border-white/10 p-5 text-center text-sm text-slate-500">{text}</p>; }

function ConfirmDelete({ label, onDelete, disabled, compact = false, textLabel }: { label: string; onDelete: () => void; disabled: boolean; compact?: boolean; textLabel?: string }) {
  return <AlertDialog><AlertDialogTrigger asChild>{textLabel ? <Button type="button" variant="ghost" size="sm" className="text-slate-500 hover:text-red-300" disabled={disabled}>{textLabel}</Button> : <button type="button" aria-label={label} disabled={disabled} className={`${compact ? "p-0.5" : "rounded-md p-2"} text-slate-500 hover:text-red-300 disabled:opacity-50`}><Trash2 className={compact ? "h-3 w-3" : "h-4 w-4"} /></button>}</AlertDialogTrigger><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Confirm removal</AlertDialogTitle><AlertDialogDescription>{label} This cannot be undone.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" onClick={onDelete}>Remove</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>;
}

function optional(form: FormData, key: string) { const value = String(form.get(key) ?? "").trim(); return value || null; }
function optionalNumber(form: FormData, key: string) { const value = optional(form, key); return value === null ? null : Number(value); }
function optionalFloat(form: FormData, key: string) { const value = optional(form, key); return value === null ? null : Number(value); }
function message(reason: unknown, fallback: string) { return reason instanceof Error ? reason.message : fallback; }
