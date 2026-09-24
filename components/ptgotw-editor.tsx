"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Bold, Check, List, ListOrdered, LoaderCircle, RefreshCw, Save } from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { apiFetch, CurrentUser, PTGWriteup, WriteupDraft } from "@/lib/api";
import { createDraftAutosave } from "@/lib/draft-autosave";

type Author = { id: string; display_name: string };
type DraftForm = { creation_id?: string; year: number; week: number; author_id: string; submitted_by_author: boolean; due_date: string; content_html: string };

function initialForm(entry: PTGWriteup | null, me: CurrentUser, authors: Author[]): DraftForm {
  return {
    year: entry?.year ?? new Date().getFullYear(), week: entry?.week ?? 1,
    author_id: entry?.author.id ?? authors[0]?.id ?? me.id,
    submitted_by_author: entry?.submitted_by_author ?? me.role !== "admin",
    due_date: entry?.due_date ?? "", content_html: entry?.draft?.content_html ?? entry?.content_html ?? "",
    ...(me.role === "admin" ? entry?.draft : {}),
  } as DraftForm;
}

export function PTGWriteupEditor() {
  const [context, setContext] = useState<{ me: CurrentUser; items: PTGWriteup[]; authors: Author[]; initial: PTGWriteup | null } | null>(null);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState<{ entry: PTGWriteup | null; key: number } | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all([apiFetch<CurrentUser>("/auth/me"), apiFetch<PTGWriteup[]>("/ptgotw/editable")]).then(async ([me, items]) => {
      const authors = me.role === "admin" ? await apiFetch<Author[]>("/ptgotw/authors") : [];
      const requested = items.find(item => item.id === new URLSearchParams(window.location.search).get("id"));
      if (!cancelled) setContext({ me, items, authors, initial: requested ?? (me.role === "admin" ? null : items[0] ?? null) });
    }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load the editor."); });
    return () => { cancelled = true; };
  }, []);
  if (error) return <EditorMessage title="Editor unavailable" detail={error} />;
  if (!context) return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>;
  if (context.me.role !== "admin" && !context.items.length) return <EditorMessage title="No writeup assigned" detail="A commissioner needs to assign you a week before you can submit a writeup." />;
  return <WriteupForm key={selection?.key ?? 0} me={context.me} authors={context.authors} items={context.items} initial={selection ? selection.entry : context.initial}
    onSelect={entry => setSelection(previous => ({ entry, key: (previous?.key ?? 0) + 1 }))}
    onSaved={entry => setContext(current => current ? { ...current, items: [entry, ...current.items.filter(item => item.id !== entry.id)] } : current)} />;
}

function WriteupForm({ me, authors, items, initial, onSelect, onSaved }: { me: CurrentUser; authors: Author[]; items: PTGWriteup[]; initial: PTGWriteup | null; onSelect: (entry: PTGWriteup | null) => void; onSaved: (entry: PTGWriteup) => void }) {
  const [form, setForm] = useState<DraftForm>(() => ({ ...initialForm(initial, me, authors), creation_id: initial ? undefined : crypto.randomUUID() }));
  const [entry, setEntry] = useState(initial);
  const [notice, setNotice] = useState("");
  const [localWarning, setLocalWarning] = useState("");
  const targetId = useRef(initial?.id);
  const recoveryKey = useRef(`btb-writeup-draft:${me.id}:${initial?.id ?? "new"}`);
  const [recovery, setRecovery] = useState<DraftForm | null>(null);
  // The controller only invokes these ref-reading callbacks after an edit/save.
  // eslint-disable-next-line react-hooks/refs
  const [controller] = useState(() => createDraftAutosave<DraftForm>({
    initial: form,
    remember(value) {
      try { localStorage.setItem(recoveryKey.current, JSON.stringify(value)); }
      catch { setLocalWarning("Local recovery is unavailable in this browser. Keep this page open until your draft is saved."); }
    },
    forget(value) {
      try {
        if (localStorage.getItem(recoveryKey.current) === JSON.stringify(value)) localStorage.removeItem(recoveryKey.current);
      } catch { /* Server save still succeeded. */ }
    },
    async save(value, publish) {
      if (plainText(value.content_html).length > 30000 || value.content_html.length > 120000) throw new Error("Shorten the writeup to 30,000 characters before saving.");
      if (!value.author_id || !Number.isInteger(value.year) || value.year < 2000 || value.year > 2100 || !Number.isInteger(value.week) || value.week < 1 || value.week > 18) throw new Error("Choose a valid year, week, and author to save your draft.");
      if (me.role === "admin" && value.submitted_by_author && !value.due_date) throw new Error("Add a due date for the assigned author to save your draft.");
      const metadata = me.role === "admin" ? { year: value.year, week: value.week, author_id: value.author_id, submitted_by_author: value.submitted_by_author, due_date: value.submitted_by_author ? value.due_date || null : null } : {};
      const body: WriteupDraft & { is_published?: boolean } = { ...metadata, content_html: value.content_html };
      if (publish !== undefined) body.is_published = publish;
      if (!targetId.current) {
        // A stable ID makes a retry safe even if the first POST response is lost.
        const created = await apiFetch<PTGWriteup>("/ptgotw", { method: "POST", body: JSON.stringify({ ...body, id: value.creation_id, is_published: false }) });
        const oldKey = recoveryKey.current;
        targetId.current = created.id;
        recoveryKey.current = `btb-writeup-draft:${me.id}:${created.id}`;
        try {
          const backup = localStorage.getItem(oldKey);
          if (backup) localStorage.setItem(recoveryKey.current, backup);
          localStorage.removeItem(oldKey);
        } catch { setLocalWarning("Local recovery is unavailable in this browser."); }
      }
      const result = await apiFetch<PTGWriteup>(`/ptgotw/${targetId.current}${publish === undefined ? "/draft" : ""}`, { method: "PUT", body: JSON.stringify(body) });
      // Do not reset the editor: the response may describe an older keystroke.
      setEntry(result);
      onSaved(result);
      window.dispatchEvent(new Event("ptgotw-updated"));
    },
  }));
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => {
    controller.resume();
    try {
      const raw = localStorage.getItem(recoveryKey.current);
      if (raw) {
        const candidate = JSON.parse(raw) as DraftForm;
        if (typeof candidate.content_html === "string" && typeof candidate.author_id === "string" && typeof candidate.year === "number" && typeof candidate.week === "number" && typeof candidate.submitted_by_author === "boolean" && (typeof candidate.due_date === "string" || candidate.due_date === null) && JSON.stringify(candidate) !== JSON.stringify(initialForm(initial, me, authors))) setRecovery(candidate);
      }
    } catch { setLocalWarning("The browser recovery copy could not be read. Your server draft is loaded."); }
    return () => controller.dispose();
  }, [controller, initial, me, authors]);
  useEffect(() => {
    const message = "Your latest writeup changes have not been saved to the server. Leave anyway?";
    const warn = (event: BeforeUnloadEvent) => { if (controller.getSnapshot().dirty || controller.getSnapshot().publishing) { event.preventDefault(); event.returnValue = ""; } };
    const warnLink = (event: MouseEvent) => {
      if (!(controller.getSnapshot().dirty || controller.getSnapshot().publishing) || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || link.target === "_blank" || link.hasAttribute("download")) return;
      const url = new URL(link.href);
      if (url.origin === location.origin && url.pathname === location.pathname && url.search === location.search) return;
      if (!window.confirm(message)) { event.preventDefault(); event.stopPropagation(); }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", warnLink, true);
    return () => { window.removeEventListener("beforeunload", warn); document.removeEventListener("click", warnLink, true); };
  }, [controller]);
  function edit(patch: Partial<DraftForm>) {
    const next = { ...form, ...patch };
    setForm(next); setNotice(""); controller.edit(next);
  }
  async function save(publish: boolean) {
    setNotice("");
    if (await controller.saveExplicit(publish)) setNotice(publish ? "Writeup published to the archive." : "Draft saved. Only you and commissioners can see it.");
  }
  function changeSelection(id: string) {
    if (state.publishing) return;
    if (state.dirty && !window.confirm("Your latest changes have not been saved to the server. Switch entries anyway?")) return;
    onSelect(id === "new" ? null : items.find(item => item.id === id) ?? null);
  }
  const overLimit = plainText(form.content_html).length > 30000 || form.content_html.length > 120000;
  const daysUntilDue = form.due_date ? calendarDaysUntil(form.due_date) : null;
  const authorCanPublish = me.role === "admin" || !!entry?.is_published || (daysUntilDue !== null && daysUntilDue <= 7 && daysUntilDue >= -7);
  const blocked = state.publishing || recovery !== null;
  const invalid = !form.author_id || overLimit || (me.role === "admin" && form.submitted_by_author && !form.due_date);
  const statusLabel = state.status === "saving" ? "Saving…" : state.status === "waiting" ? "Unsaved changes…" : state.status === "saved" ? "Draft saved" : state.status === "error" ? "Couldn’t save" : "Draft autosave on";
  return <>
    <PageHeading eyebrow="Prime Time Game of the Week" title={me.role === "admin" ? "Manage writeups" : "Submit your writeup"}>Drafts save automatically after you stop typing. Publishing remains up to you.</PageHeading>
    {recovery && <div className="mb-5 rounded-xl border border-primary/30 bg-primary/10 p-4"><p className="text-sm">A local recovery copy is available for this entry. Restore it or keep the server version.</p><div className="mt-3 flex gap-2"><Button onClick={() => { setForm(recovery); controller.edit(recovery); setRecovery(null); }}>Restore edits</Button><Button variant="secondary" onClick={() => { try { localStorage.removeItem(recoveryKey.current); } catch {} setRecovery(null); }}>Keep server version</Button></div></div>}
    <form onSubmit={event => { event.preventDefault(); if (!blocked && !invalid && authorCanPublish) void save(true); }} className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="h-fit space-y-5 rounded-2xl border border-white/8 bg-card p-5">
        <div className="space-y-2"><Label htmlFor="writeup-entry">Entry</Label><NativeSelect id="writeup-entry" className="w-full" value={entry?.id ?? "new"} disabled={blocked} onChange={event => changeSelection(event.target.value)}>{me.role === "admin" && <NativeSelectOption value="new">New writeup</NativeSelectOption>}{items.map(item => <NativeSelectOption key={item.id} value={item.id}>{item.year} · Week {item.week} · {item.author.display_name} · {item.is_published ? "Published" : "Draft"}</NativeSelectOption>)}</NativeSelect></div>
        <div className="grid grid-cols-2 gap-3"><div className="space-y-2"><Label htmlFor="writeup-year">Year</Label><Input id="writeup-year" type="number" min={2000} max={2100} value={form.year} disabled={blocked || me.role !== "admin"} onChange={event => edit({ year: Number(event.target.value) })} /></div><div className="space-y-2"><Label htmlFor="writeup-week">Week</Label><Input id="writeup-week" type="number" min={1} max={18} value={form.week} disabled={blocked || me.role !== "admin"} onChange={event => edit({ week: Number(event.target.value) })} /></div></div>
        <div className="space-y-2"><Label htmlFor="writeup-author">Author</Label>{me.role === "admin" ? <NativeSelect id="writeup-author" className="w-full" value={form.author_id} disabled={blocked} onChange={event => edit({ author_id: event.target.value })} required><NativeSelectOption value="" disabled>Choose an author</NativeSelectOption>{form.author_id && !authors.some(author => author.id === form.author_id) && <NativeSelectOption value={form.author_id}>Current credited author</NativeSelectOption>}{authors.map(author => <NativeSelectOption key={author.id} value={author.id}>{author.display_name}</NativeSelectOption>)}</NativeSelect> : <p className="text-sm text-slate-300">{me.display_name}</p>}</div>
        {me.role === "admin" && <label className="flex items-start gap-3 rounded-xl border border-white/8 p-3"><input type="checkbox" checked={form.submitted_by_author} disabled={blocked} onChange={event => edit({ submitted_by_author: event.target.checked })} className="mt-1 h-4 w-4 accent-[#f8c735]" /><span><span className="block text-sm font-semibold">Submitted by author</span><span className="mt-1 block text-xs text-slate-500">Lets the selected member write their assigned entry.</span></span></label>}
        {form.submitted_by_author && <div className="space-y-2"><Label htmlFor="writeup-due-date">Due date</Label>{me.role === "admin" ? <Input id="writeup-due-date" type="date" value={form.due_date ?? ""} disabled={blocked} onChange={event => edit({ due_date: event.target.value })} required /> : <p className="text-sm text-slate-300">{form.due_date ? new Date(`${form.due_date}T12:00:00`).toLocaleDateString() : "No due date"}</p>}<p className="text-xs leading-relaxed text-slate-500">The author can edit immediately, publish starting 7 days before, and make changes through 7 days after this date.</p></div>}
        {entry?.is_published && <p className="text-xs leading-relaxed text-slate-400">Your published version stays live while you edit this private draft. Choose Publish changes when it’s ready.</p>}
        {me.role === "admin" && <p className="text-xs leading-relaxed text-slate-400">Assignment changes remain in the draft until you choose Save draft or Publish.</p>}
      </aside>
      <section className="overflow-hidden rounded-2xl border border-white/8 bg-card">
        <RichTextEditor value={form.content_html} disabled={blocked} onChange={content_html => edit({ content_html })} />
        <div className="space-y-3 border-t border-white/8 px-5 py-4">
          <div role="status" aria-live="polite" className={`flex items-center gap-2 text-sm ${state.status === "error" ? "text-red-300" : state.status === "saved" ? "text-emerald-300" : "text-slate-400"}`}>{state.status === "saving" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : state.status === "saved" ? <Check className="h-4 w-4" /> : null}{statusLabel}{state.status === "error" && state.dirty && <Button type="button" variant="secondary" disabled={blocked} onClick={() => void controller.flush()}><RefreshCw className="h-4 w-4" />Retry</Button>}</div>
          {state.status === "error" && <p role="alert" className="text-sm text-red-300">{state.error instanceof Error ? state.error.message : "Could not save the draft."} Your edits remain in this editor.</p>}
          {localWarning && <p role="alert" className="text-sm text-amber-300">{localWarning}</p>}
          {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}
          {overLimit && <p role="alert" className="text-sm text-red-300">Shorten the writeup to 30,000 characters before saving.</p>}
          {!authorCanPublish && daysUntilDue !== null && <p className="text-sm text-amber-300">Publishing opens 7 days before the due date. You can keep saving drafts now.</p>}
          <div className="flex flex-col gap-2 sm:flex-row sm:justify-end"><Button type="button" variant="secondary" disabled={blocked || invalid} onClick={() => void save(false)}><Save className="h-4 w-4" />{entry?.is_published ? "Move to draft" : "Save draft"}</Button><Button type="submit" disabled={blocked || invalid || !plainText(form.content_html).trim() || !authorCanPublish} className="bg-primary font-bold text-primary-foreground">{state.publishing ? "Saving…" : entry?.is_published ? "Publish changes" : "Publish writeup"}</Button></div>
        </div>
      </section>
    </form>
  </>;
}

function RichTextEditor({ value, onChange, disabled }: { value: string; onChange: (value: string) => void; disabled: boolean }) {
  const editor = useRef<HTMLDivElement>(null); const count = plainText(value).length;
  useEffect(() => { if (editor.current && editor.current.innerHTML !== value) editor.current.innerHTML = value; }, [value]);
  function format(command: "bold" | "insertOrderedList" | "insertUnorderedList") { if (disabled) return; editor.current?.focus(); document.execCommand(command); if (editor.current) onChange(editor.current.innerHTML); }
  return <><div className="flex items-center gap-1 border-b border-white/8 bg-white/[.02] px-4 py-3"><FormatButton label="Bold" onClick={() => format("bold")}><Bold /></FormatButton><FormatButton label="Numbered list" onClick={() => format("insertOrderedList")}><ListOrdered /></FormatButton><FormatButton label="Bulleted list" onClick={() => format("insertUnorderedList")}><List /></FormatButton><span className={`ml-auto text-xs tabular-nums ${count > 30000 ? "font-semibold text-red-300" : "text-slate-500"}`}>{count.toLocaleString()} / 30,000</span></div><div ref={editor} contentEditable={!disabled} aria-disabled={disabled} suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Writeup" data-placeholder="Paste or write the weekly matchup breakdown here…" onInput={event => onChange(event.currentTarget.innerHTML)} className="min-h-[520px] px-6 py-6 text-base leading-8 text-slate-200 outline-none empty:before:pointer-events-none empty:before:text-slate-600 empty:before:content-[attr(data-placeholder)] [&_ol]:list-decimal [&_ol]:pl-7 [&_ul]:list-disc [&_ul]:pl-7" /></>;
}

function FormatButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) { return <button type="button" title={label} aria-label={label} onClick={onClick} className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-white/7 hover:text-white [&_svg]:h-4 [&_svg]:w-4">{children}</button>; }
function plainText(value: string) { return value.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"); }
function calendarDaysUntil(value: string) { const today = new Date(); const [year, month, day] = value.split("-").map(Number); return Math.round((Date.UTC(year, month - 1, day) - Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / 86400000); }
function EditorMessage({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-9 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mt-2 text-sm text-slate-400">{detail}</p></div>; }
