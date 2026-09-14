"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, BookOpenText, CalendarDays, LoaderCircle, Pencil, Trash2, UserRound } from "lucide-react";
import { useEffect, useState } from "react";

import { PageHeading } from "@/components/page-heading";
import { PTGOTWComments } from "@/components/ptgotw-comments";
import { PTGOTWWorkMode } from "@/components/ptgotw-work-mode";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { apiFetch, PTGWriteup, PTGWriteupList } from "@/lib/api";

export function PTGWriteupIndex() {
  const [data, setData] = useState<PTGWriteupList | null>(null);
  const [error, setError] = useState("");
  const [pendingDelete, setPendingDelete] = useState<PTGWriteupList["writeups"][number] | null>(null); const [deleting, setDeleting] = useState(false); const [deleteError, setDeleteError] = useState("");

  function load(year?: number) {
    setError("");
    apiFetch<PTGWriteupList>(`/ptgotw${year ? `?year=${year}` : ""}`).then(setData).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load writeups."));
  }
  useEffect(() => {
    let cancelled = false;
    apiFetch<PTGWriteupList>("/ptgotw").then(value => { if (!cancelled) setData(value); }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load writeups."); });
    return () => { cancelled = true; };
  }, []);

  async function removeWriteup() {
    if (!pendingDelete) return; setDeleting(true); setDeleteError("");
    try { await apiFetch<void>(`/ptgotw/${pendingDelete.id}`, { method: "DELETE" }); setData(current => current ? { ...current, writeups: current.writeups.filter(item => item.id !== pendingDelete.id) } : current); setPendingDelete(null); }
    catch (reason) { setDeleteError(reason instanceof Error ? reason.message : "Could not delete the writeup."); }
    finally { setDeleting(false); }
  }

  return <>
    <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <PageHeading eyebrow="Prime Time Game of the Week" title="PTGOTW writeups">The weekly matchup stories, marquee game, and league lore—all in one place.</PageHeading>
      {data && <label className="mb-8 flex items-center gap-3 text-sm text-slate-400"><span>Season</span><NativeSelect value={data.year} onChange={event => load(Number(event.target.value))} aria-label="Writeup season">{data.available_years.map(year => <NativeSelectOption key={year} value={year}>{year}</NativeSelectOption>)}</NativeSelect></label>}
    </div>
    {error ? <StateMessage title="Writeups unavailable" detail={error} /> : !data ? <Loading /> : data.writeups.length === 0 ? <StateMessage title={`No ${data.year} writeups yet`} detail="The first PTGOTW writeup will appear here once it is saved." /> : <div className="grid gap-3">{data.writeups.map(writeup => <WriteupCard key={writeup.id} writeup={writeup} admin={data.is_admin_view} onDelete={() => { setDeleteError(""); setPendingDelete(writeup); }} />)}</div>}
    <AlertDialog open={!!pendingDelete} onOpenChange={open => { if (!open && !deleting) { setPendingDelete(null); setDeleteError(""); } }}><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Delete the {pendingDelete?.year} Week {pendingDelete?.week} writeup?</AlertDialogTitle><AlertDialogDescription>This permanently removes the writeup or assignment. This action cannot be undone.</AlertDialogDescription></AlertDialogHeader>{deleteError && <p role="alert" className="text-sm text-red-300">{deleteError}</p>}<AlertDialogFooter><AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={deleting} onClick={event => { event.preventDefault(); void removeWriteup(); }}>{deleting ? "Deleting…" : "Delete writeup"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </>;
}

function WriteupCard({ writeup, admin, onDelete }: { writeup: PTGWriteupList["writeups"][number]; admin: boolean; onDelete: () => void }) {
  const status = writeup.is_published ? "Published" : writeup.has_content ? "Draft" : writeup.submitted_by_author ? "Awaiting author" : "Not started";
  const statusClass = writeup.is_published ? "bg-emerald-400/10 text-emerald-300" : writeup.has_content ? "bg-amber-400/10 text-amber-300" : "bg-white/5 text-slate-400";
  return <div className="group flex flex-col gap-4 rounded-2xl border border-white/8 bg-card px-5 py-5 transition hover:border-primary/40 hover:bg-white/[.045] sm:flex-row sm:items-center sm:justify-between sm:px-6">
    <Link href={`/ptgotw/${writeup.id}`} className="flex min-w-0 flex-1 items-center gap-4"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-primary/10 text-primary"><CalendarDays className="h-5 w-5" /></span><div><div className="flex flex-wrap items-center gap-2"><h2 className="text-lg font-bold group-hover:text-primary">Week {writeup.week}</h2>{admin && <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusClass}`}>{status}</span>}</div><p className="mt-1 text-sm text-slate-500">{writeup.author.display_name}{admin && writeup.due_date ? ` · Due ${new Date(`${writeup.due_date}T12:00:00`).toLocaleDateString()}` : ""}</p></div></Link>
    {admin ? <div className="flex gap-2"><Link href={`/ptgotw/submit?id=${writeup.id}`} className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-white/10 px-3 text-sm font-semibold text-slate-300 transition hover:border-primary/40 hover:text-primary"><Pencil className="h-4 w-4" />Edit</Link><button type="button" onClick={onDelete} className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-white/10 px-3 text-sm font-semibold text-slate-400 transition hover:border-red-400/40 hover:text-red-300"><Trash2 className="h-4 w-4" />Delete</button></div> : <BookOpenText className="hidden h-5 w-5 shrink-0 text-slate-600 transition group-hover:text-primary sm:block" />}
  </div>;
}

export function PTGWriteupDetail() {
  const params = useParams();
  const rawId = params?.id; const id = Array.isArray(rawId) ? rawId[0] : rawId;
  const invalidId = !id || !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(id);
  const [writeup, setWriteup] = useState<PTGWriteup | null>(null); const [error, setError] = useState(""); const [missing, setMissing] = useState(false); const [workMode, setWorkMode] = useState(false);
  useEffect(() => {
    if (invalidId) return;
    apiFetch<PTGWriteup>(`/ptgotw/${id}`).then(setWriteup).catch(reason => { if (reason instanceof Error && reason.message === "Writeup not found") setMissing(true); else setError(reason instanceof Error ? reason.message : "Could not load this writeup."); });
  }, [id, invalidId]);
  if (invalidId || missing) return <><Link href="/ptgotw" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />All writeups</Link><StateMessage title="Writeup not found" detail="There is no PTGOTW writeup for this link. It may have been deleted, or the link may be incorrect." /></>;
  if (error) return <><Link href="/ptgotw" className="mb-6 inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />All writeups</Link><StateMessage title="Writeup unavailable" detail={error} /></>;
  if (!writeup) return <Loading />;
  if (workMode) return <PTGOTWWorkMode writeup={writeup} onExit={() => setWorkMode(false)} />;
  return <article className="mx-auto max-w-4xl">
    <div className="mb-7 flex items-center justify-between gap-4"><Link href="/ptgotw" className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white"><ArrowLeft className="h-4 w-4" />All writeups</Link><label className="flex items-center gap-2 text-sm font-medium text-slate-300"><span>Work mode</span><Switch checked={workMode} onCheckedChange={setWorkMode} aria-label="Toggle work mode" /></label></div>
    <header className="mb-8 border-b border-white/8 pb-8"><p className="mb-3 text-xs font-semibold uppercase tracking-[.18em] text-primary">{writeup.year} · Prime Time Game of the Week</p><h1 className="text-4xl font-black tracking-[-.04em] sm:text-5xl">Week {writeup.week}</h1><div className="mt-4 flex flex-wrap items-center gap-3"><p className="flex items-center gap-2 text-sm text-slate-400"><UserRound className="h-4 w-4 text-primary" />Written by <strong className="text-slate-200">{writeup.author.display_name}</strong></p>{writeup.submitted_by_author !== undefined && <span className="rounded-full border border-white/8 bg-white/[.035] px-2.5 py-1 text-xs text-slate-400">{writeup.submitted_by_author ? "Submitted by author" : "Submitted by commissioner"}</span>}</div></header>
    <div className="rounded-2xl border border-white/8 bg-card p-6 sm:p-9"><div className="text-base leading-8 text-slate-200 [&_b]:font-bold [&_div]:mb-5 [&_em]:italic [&_i]:italic [&_li]:mb-2 [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:pl-7 [&_p]:mb-5 [&_strong]:font-bold [&_u]:underline [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:pl-7" dangerouslySetInnerHTML={{ __html: writeup.content_html }} /></div>
    {writeup.is_published !== false && <PTGOTWComments writeupId={writeup.id} />}
  </article>;
}

function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function StateMessage({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-9 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mt-2 text-sm text-slate-400">{detail}</p></div>; }
