"use client";

import { useEffect, useRef, useState } from "react";
import { Bold, List, ListOrdered, LoaderCircle, Save } from "lucide-react";

import { PageHeading } from "@/components/page-heading";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { apiFetch, CurrentUser, PTGWriteup } from "@/lib/api";

type Author = { id: string; display_name: string };

export function PTGWriteupEditor() {
  const [me, setMe] = useState<CurrentUser | null>(null); const [editable, setEditable] = useState<PTGWriteup[]>([]); const [authors, setAuthors] = useState<Author[]>([]);
  const [selectedId, setSelectedId] = useState("new"); const [year, setYear] = useState(new Date().getFullYear()); const [week, setWeek] = useState(1); const [authorId, setAuthorId] = useState(""); const [submittedByAuthor, setSubmittedByAuthor] = useState(false); const [content, setContent] = useState("");
  const [loading, setLoading] = useState(true); const [saving, setSaving] = useState(false); const [error, setError] = useState(""); const [notice, setNotice] = useState("");

  useEffect(() => {
    Promise.all([apiFetch<CurrentUser>("/auth/me"), apiFetch<PTGWriteup[]>("/ptgotw/editable")]).then(async ([user, items]) => {
      setMe(user); setEditable(items);
      if (user.role === "admin") {
        const choices = await apiFetch<Author[]>("/ptgotw/authors"); const requestedId = new URLSearchParams(window.location.search).get("id"); const requested = items.find(item => item.id === requestedId);
        setAuthors(choices);
        if (requested) { setSelectedId(requested.id); setYear(requested.year); setWeek(requested.week); setAuthorId(requested.author.id); setSubmittedByAuthor(requested.submitted_by_author ?? false); setContent(requested.content_html); }
        else setAuthorId(choices[0]?.id ?? "");
      } else if (items[0]) {
        const first = items[0]; setSelectedId(first.id); setYear(first.year); setWeek(first.week); setAuthorId(first.author.id); setSubmittedByAuthor(true); setContent(first.content_html);
      }
    }).catch(reason => setError(reason instanceof Error ? reason.message : "Could not load the editor.")).finally(() => setLoading(false));
  }, []);

  function selectWriteup(writeup: PTGWriteup, source = editable) {
    setSelectedId(writeup.id); setYear(writeup.year); setWeek(writeup.week); setAuthorId(writeup.author.id); setSubmittedByAuthor(writeup.submitted_by_author ?? true); setContent(writeup.content_html); setNotice(""); setError("");
    if (!source.some(item => item.id === writeup.id)) setEditable(items => [writeup, ...items]);
  }
  function changeSelection(value: string) {
    if (value === "new") { setSelectedId("new"); setYear(new Date().getFullYear()); setWeek(1); setAuthorId(authors[0]?.id ?? ""); setSubmittedByAuthor(false); setContent(""); setNotice(""); return; }
    const writeup = editable.find(item => item.id === value); if (writeup) selectWriteup(writeup);
  }
  async function save(isPublished: boolean) {
    if (!me) return; setSaving(true); setError(""); setNotice("");
    const metadata = me.role === "admin" ? { year, week, author_id: authorId, submitted_by_author: submittedByAuthor } : {};
    try {
      const result = selectedId === "new"
        ? await apiFetch<PTGWriteup>("/ptgotw", { method: "POST", body: JSON.stringify({ ...metadata, content_html: content, is_published: isPublished }) })
        : await apiFetch<PTGWriteup>(`/ptgotw/${selectedId}`, { method: "PUT", body: JSON.stringify({ ...metadata, content_html: content, is_published: isPublished }) });
      selectWriteup(result); setEditable(items => [result, ...items.filter(item => item.id !== result.id)]); setNotice(isPublished ? "Writeup published to the archive." : "Draft saved. Only you and commissioners can see it.");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save the writeup."); } finally { setSaving(false); }
  }

  if (loading) return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>;
  if (!me) return <EditorMessage title="Editor unavailable" detail={error || "Your account could not be loaded."} />;
  if (me.role !== "admin" && editable.length === 0) return <EditorMessage title="No writeup assigned" detail="A commissioner needs to assign you a week before you can submit a writeup." />;
  const overLimit = plainText(content).length > 30000;
  return <>
    <PageHeading eyebrow="Prime Time Game of the Week" title={me.role === "admin" ? "Manage writeups" : "Submit your writeup"}>{me.role === "admin" ? "Create weekly writeups or assign a member permission to write their own." : "Write or update the PTGOTW entry assigned to you."}</PageHeading>
    <form onSubmit={event => { event.preventDefault(); void save(true); }} className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)]">
      <aside className="h-fit space-y-5 rounded-2xl border border-white/8 bg-card p-5">
        <div className="space-y-2"><Label htmlFor="writeup-entry">Entry</Label><NativeSelect id="writeup-entry" className="w-full" value={selectedId} onChange={event => changeSelection(event.target.value)}>{me.role === "admin" && <NativeSelectOption value="new">New writeup</NativeSelectOption>}{editable.map(item => <NativeSelectOption key={item.id} value={item.id}>{item.year} · Week {item.week} · {item.author.display_name} · {item.is_published ? "Published" : "Draft"}</NativeSelectOption>)}</NativeSelect></div>
        <div className="grid grid-cols-2 gap-3"><div className="space-y-2"><Label htmlFor="writeup-year">Year</Label><Input id="writeup-year" type="number" min={2000} max={2100} value={year} disabled={me.role !== "admin"} onChange={event => setYear(Number(event.target.value))} /></div><div className="space-y-2"><Label htmlFor="writeup-week">Week</Label><Input id="writeup-week" type="number" min={1} max={18} value={week} disabled={me.role !== "admin"} onChange={event => setWeek(Number(event.target.value))} /></div></div>
        <div className="space-y-2"><Label htmlFor="writeup-author">Author</Label>{me.role === "admin" ? <NativeSelect id="writeup-author" className="w-full" value={authorId} onChange={event => setAuthorId(event.target.value)} required><NativeSelectOption value="" disabled>Choose an author</NativeSelectOption>{authorId && !authors.some(author => author.id === authorId) && <NativeSelectOption value={authorId}>Current credited author</NativeSelectOption>}{authors.map(author => <NativeSelectOption key={author.id} value={author.id}>{author.display_name}</NativeSelectOption>)}</NativeSelect> : <p className="rounded-lg border border-white/8 bg-white/[.025] px-3 py-2 text-sm text-slate-300">{me.display_name}</p>}</div>
        {me.role === "admin" && <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-white/8 bg-white/[.025] p-3"><input type="checkbox" checked={submittedByAuthor} onChange={event => setSubmittedByAuthor(event.target.checked)} className="mt-1 h-4 w-4 accent-[#f8c735]" /><span><span className="block text-sm font-semibold">Submitted by author</span><span className="mt-1 block text-xs leading-relaxed text-slate-500">Lets the selected member see this editor and save the writeup themselves.</span></span></label>}
      </aside>
      <section className="overflow-hidden rounded-2xl border border-white/8 bg-card"><RichTextEditor value={content} onChange={setContent} /><div className="flex flex-col gap-3 border-t border-white/8 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"><div>{error && <p role="alert" className="text-sm text-red-300">{error}</p>}{notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}{overLimit && <p role="alert" className="text-sm text-red-300">Shorten the writeup to 30,000 characters before saving.</p>}</div><div className="flex flex-col gap-2 sm:flex-row"><Button type="button" variant="secondary" disabled={saving || !authorId || overLimit} onClick={() => void save(false)}><Save className="h-4 w-4" />{selectedId !== "new" && editable.find(item => item.id === selectedId)?.is_published ? "Move to draft" : "Save draft"}</Button><Button type="submit" disabled={saving || !authorId || !plainText(content).trim() || overLimit} className="bg-primary font-bold text-primary-foreground">{saving ? "Saving…" : "Publish writeup"}</Button></div></div></section>
    </form>
  </>;
}

function RichTextEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const editor = useRef<HTMLDivElement>(null); const count = plainText(value).length;
  useEffect(() => { if (editor.current && editor.current.innerHTML !== value) editor.current.innerHTML = value; }, [value]);
  function format(command: "bold" | "insertOrderedList" | "insertUnorderedList") { editor.current?.focus(); document.execCommand(command); if (editor.current) onChange(editor.current.innerHTML); }
  return <><div className="flex items-center gap-1 border-b border-white/8 bg-white/[.02] px-4 py-3"><FormatButton label="Bold" onClick={() => format("bold")}><Bold /></FormatButton><FormatButton label="Numbered list" onClick={() => format("insertOrderedList")}><ListOrdered /></FormatButton><FormatButton label="Bulleted list" onClick={() => format("insertUnorderedList")}><List /></FormatButton><span className={`ml-auto text-xs tabular-nums ${count > 30000 ? "font-semibold text-red-300" : "text-slate-500"}`}>{count.toLocaleString()} / 30,000</span></div><div ref={editor} contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label="Writeup" data-placeholder="Paste or write the weekly matchup breakdown here…" onInput={event => onChange(event.currentTarget.innerHTML)} className="min-h-[520px] px-6 py-6 text-base leading-8 text-slate-200 outline-none empty:before:pointer-events-none empty:before:text-slate-600 empty:before:content-[attr(data-placeholder)] [&_ol]:list-decimal [&_ol]:pl-7 [&_ul]:list-disc [&_ul]:pl-7" /></>;
}

function FormatButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) { return <button type="button" title={label} aria-label={label} onClick={onClick} className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-white/7 hover:text-white [&_svg]:h-4 [&_svg]:w-4">{children}</button>; }
function plainText(value: string) { return value.replace(/<br\s*\/?>/gi, "\n").replace(/<[^>]*>/g, "").replace(/&nbsp;/g, " ").replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"); }
function EditorMessage({ title, detail }: { title: string; detail: string }) { return <div className="rounded-2xl border border-white/8 bg-card p-9 text-center"><h2 className="text-xl font-bold">{title}</h2><p className="mt-2 text-sm text-slate-400">{detail}</p></div>; }
