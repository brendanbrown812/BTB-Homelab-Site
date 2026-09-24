"use client";

import { ChevronDown, ChevronUp, LoaderCircle, MessageCircle, Pencil, Reply, ShieldCheck, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, PTGComment, PTGCommentThread } from "@/lib/api";

type ThreadItem = { comment: PTGComment; depth: number };

function arrangeComments(comments: PTGComment[]): ThreadItem[] {
  const ids = new Set(comments.map(comment => comment.id));
  const children = new Map<string | null, PTGComment[]>();
  for (const comment of comments) {
    const parent = comment.parent_id && ids.has(comment.parent_id) ? comment.parent_id : null;
    children.set(parent, [...(children.get(parent) ?? []), comment]);
  }
  const roots = children.get(null) ?? [];
  roots.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  for (const [parent, replies] of children) {
    if (parent) replies.sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  }
  const result: ThreadItem[] = [];
  const visited = new Set<string>();
  function visit(comment: PTGComment, depth: number) {
    if (visited.has(comment.id)) return;
    visited.add(comment.id); result.push({ comment, depth });
    for (const reply of children.get(comment.id) ?? []) visit(reply, depth + 1);
  }
  for (const root of roots) visit(root, 0);
  for (const comment of comments) if (!visited.has(comment.id)) visit(comment, 0);
  return result;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

export function PTGOTWComments({ writeupId, variant = "default" }: { writeupId: string; variant?: "default" | "work" }) {
  const [thread, setThread] = useState<PTGCommentThread | null>(null);
  const [error, setError] = useState("");
  const [newComment, setNewComment] = useState("");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyText, setReplyText] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [editText, setEditText] = useState("");
  const [deleting, setDeleting] = useState<PTGComment | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<PTGCommentThread>(`/ptgotw/${writeupId}/comments`).then(value => { if (!cancelled) setThread(value); }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load comments."); });
    return () => { cancelled = true; };
  }, [writeupId]);

  async function create(event: FormEvent, parentId: string | null) {
    event.preventDefault();
    const content = parentId ? replyText : newComment;
    if (!content.trim()) return;
    setBusy(true); setError("");
    try {
      const updated = await apiFetch<PTGCommentThread>(`/ptgotw/${writeupId}/comments`, { method: "POST", body: JSON.stringify({ content, parent_id: parentId }) });
      setThread(updated);
      if (parentId) { setReplyingTo(null); setReplyText(""); } else setNewComment("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not post your comment."); }
    finally { setBusy(false); }
  }

  async function saveEdit(event: FormEvent, commentId: string) {
    event.preventDefault();
    if (!editText.trim()) return;
    setBusy(true); setError("");
    try {
      setThread(await apiFetch<PTGCommentThread>(`/ptgotw/${writeupId}/comments/${commentId}`, { method: "PUT", body: JSON.stringify({ content: editText }) }));
      setEditing(null); setEditText("");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save your changes."); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!deleting) return;
    setBusy(true); setError("");
    try {
      setThread(await apiFetch<PTGCommentThread>(`/ptgotw/${writeupId}/comments/${deleting.id}`, { method: "DELETE" }));
      setDeleting(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Could not delete this comment."); }
    finally { setBusy(false); }
  }

  const items = arrangeComments(thread?.comments ?? []);
  const visibleCount = thread?.comments.filter(comment => !comment.is_deleted).length ?? 0;

  if (variant === "work") return <section className="mt-10 border-t border-[#e3e6e8] pt-7" aria-labelledby="work-comments-title">
    <div className="mb-5"><h2 id="work-comments-title" className="text-xl font-normal text-[#232629]">{visibleCount} {visibleCount === 1 ? "Answer" : "Answers"}</h2><p className="mt-1 text-xs text-[#6a737c]">League discussion and follow-up analysis</p></div>
    {error && <p role="alert" className="mb-4 rounded-sm border border-[#e35d6a] bg-[#fff0f1] px-3 py-2 text-sm text-[#b32d3a]">{error}</p>}
    {!thread && !error ? <div className="grid min-h-24 place-items-center"><LoaderCircle className="h-5 w-5 animate-spin text-[#6a737c]" /></div> : items.length === 0 ? <p className="border-y border-[#e3e6e8] py-6 text-sm text-[#6a737c]">No answers yet. Add the first response below.</p> : <div>{items.map(({ comment, depth }) => {
      const own = comment.author?.id === thread?.current_user_id;
      return <div key={comment.id} style={{ marginLeft: `${Math.min(depth, 4) * 18}px` }} className="grid grid-cols-[34px_minmax(0,1fr)] gap-3 border-t border-[#e3e6e8] py-5 first:border-t-0">
        <div className="flex flex-col items-center text-[#6a737c]"><ChevronUp className="h-5 w-5" /><span className="text-xs font-semibold">0</span><ChevronDown className="h-5 w-5" /></div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs"><span className={comment.is_deleted ? "text-[#9199a1]" : "font-semibold text-[#0074cc]"}>{comment.author?.display_name ?? "[deleted]"}</span>{comment.author?.is_admin && <span className="font-semibold text-[#6a5acd]">♦ moderator</span>}<span className="text-[#6a737c]">answered {formatDate(comment.created_at)}</span>{comment.edited_at && <span className="italic text-[#9199a1]">edited</span>}</div>
          {editing === comment.id ? <form onSubmit={event => void saveEdit(event, comment.id)} className="mt-3"><textarea value={editText} onChange={event => setEditText(event.target.value)} maxLength={5000} rows={3} autoFocus disabled={busy} className="w-full resize-y rounded-sm border border-[#babfc4] bg-white px-3 py-2 text-sm text-[#232629] outline-none focus:border-[#6bbbf7] focus:ring-4 focus:ring-[#0a95ff]/15" /><div className="mt-2 flex justify-end gap-2"><button type="button" onClick={() => setEditing(null)} disabled={busy} className="rounded px-3 py-2 text-xs text-[#3b4045] hover:bg-[#f1f2f3]">Cancel</button><button type="submit" disabled={busy || !editText.trim()} className="rounded bg-[#0a95ff] px-3 py-2 text-xs font-semibold text-white hover:bg-[#0074cc] disabled:opacity-50">Save edits</button></div></form> : <p className={`mt-2 whitespace-pre-wrap break-words text-sm leading-6 ${comment.is_deleted ? "italic text-[#9199a1]" : "text-[#232629]"}`}>{comment.is_deleted ? "[deleted]" : comment.content}</p>}
          {!comment.is_deleted && editing !== comment.id && <div className="mt-3 flex items-center gap-4 text-xs"><button type="button" onClick={() => { setReplyingTo(comment.id); setReplyText(""); }} className="text-[#6a737c] hover:text-[#0c0d0e]">reply</button>{own && <button type="button" onClick={() => { setEditing(comment.id); setEditText(comment.content ?? ""); }} className="text-[#6a737c] hover:text-[#0c0d0e]">edit</button>}{thread?.is_admin && <button type="button" onClick={() => setDeleting(comment)} className="text-[#6a737c] hover:text-[#c22e32]">delete</button>}</div>}
          {replyingTo === comment.id && <form onSubmit={event => void create(event, comment.id)} className="mt-3"><textarea value={replyText} onChange={event => setReplyText(event.target.value)} maxLength={5000} rows={2} autoFocus placeholder={`Reply to ${comment.author?.display_name ?? "this thread"}…`} disabled={busy} className="w-full resize-y rounded-sm border border-[#babfc4] bg-white px-3 py-2 text-sm text-[#232629] placeholder:text-[#9199a1] outline-none focus:border-[#6bbbf7] focus:ring-4 focus:ring-[#0a95ff]/15" /><div className="mt-2 flex justify-end gap-2"><button type="button" onClick={() => setReplyingTo(null)} disabled={busy} className="rounded px-3 py-2 text-xs text-[#3b4045] hover:bg-[#f1f2f3]">Cancel</button><button type="submit" disabled={busy || !replyText.trim()} className="rounded bg-[#0a95ff] px-3 py-2 text-xs font-semibold text-white hover:bg-[#0074cc] disabled:opacity-50">Post reply</button></div></form>}
        </div>
      </div>;
    })}</div>}
    <div className="mt-8"><h3 className="text-lg font-normal text-[#232629]">Your Answer</h3><form onSubmit={event => void create(event, null)} className="mt-3"><textarea value={newComment} onChange={event => setNewComment(event.target.value)} maxLength={5000} rows={5} placeholder="Share your analysis…" aria-label="New comment" disabled={busy} className="w-full resize-y rounded-sm border border-[#babfc4] bg-white px-3 py-2 text-sm text-[#232629] placeholder:text-[#9199a1] outline-none focus:border-[#6bbbf7] focus:ring-4 focus:ring-[#0a95ff]/15" /><button type="submit" disabled={busy || !newComment.trim()} className="mt-3 inline-flex items-center gap-2 rounded bg-[#0a95ff] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0074cc] disabled:opacity-50">{busy && <LoaderCircle className="h-4 w-4 animate-spin" />}Post Your Answer</button></form></div>
    {deleting && <div className="fixed inset-0 z-[200] grid place-items-center bg-black/50 p-4" role="presentation" onMouseDown={() => { if (!busy) setDeleting(null); }}><div role="alertdialog" aria-modal="true" aria-labelledby="work-delete-title" aria-describedby="work-delete-description" className="w-full max-w-md rounded-md border border-[#d6d9dc] bg-white p-6 text-[#232629] shadow-2xl" onMouseDown={event => event.stopPropagation()}><h2 id="work-delete-title" className="text-lg font-semibold">Delete this response?</h2><p id="work-delete-description" className="mt-2 text-sm leading-5 text-[#6a737c]">The response will be replaced with [deleted]. Any replies will remain visible.</p><div className="mt-6 flex justify-end gap-2"><button type="button" disabled={busy} onClick={() => setDeleting(null)} className="rounded border border-[#babfc4] bg-white px-4 py-2 text-sm text-[#3b4045] hover:bg-[#f1f2f3] disabled:opacity-50">Cancel</button><button type="button" disabled={busy} onClick={() => void remove()} className="rounded bg-[#d0393e] px-4 py-2 text-sm font-semibold text-white hover:bg-[#b92f34] disabled:opacity-50">{busy ? "Deleting…" : "Delete response"}</button></div></div></div>}
  </section>;

  return <section className="mt-8 border-t border-white/8 pt-8" aria-labelledby="comments-title">
    <div className="mb-5 flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><MessageCircle className="h-5 w-5" /></span><div><h2 id="comments-title" className="text-xl font-bold">Comments</h2><p className="text-sm text-slate-500">{visibleCount} {visibleCount === 1 ? "comment" : "comments"}</p></div></div>
    <form onSubmit={event => void create(event, null)} className="mb-7 rounded-xl border border-white/8 bg-white/[.025] p-4"><Textarea value={newComment} onChange={event => setNewComment(event.target.value)} maxLength={5000} rows={3} placeholder="Join the conversation…" aria-label="New comment" disabled={busy} /><div className="mt-3 flex justify-end"><Button type="submit" disabled={busy || !newComment.trim()}>{busy ? <LoaderCircle className="animate-spin" /> : <MessageCircle />}Post comment</Button></div></form>
    {error && <p role="alert" className="mb-4 rounded-lg border border-red-400/20 bg-red-400/5 px-4 py-3 text-sm text-red-300">{error}</p>}
    {!thread && !error ? <div className="grid min-h-28 place-items-center"><LoaderCircle className="h-5 w-5 animate-spin text-primary" /></div> : items.length === 0 ? <p className="rounded-xl border border-dashed border-white/10 py-8 text-center text-sm text-slate-500">No comments yet. Start the conversation.</p> : <div className="space-y-3">{items.map(({ comment, depth }) => {
      const own = comment.author?.id === thread?.current_user_id;
      return <div key={comment.id} style={{ marginLeft: `${Math.min(depth, 4) * 16}px` }} className="relative rounded-xl border border-white/8 bg-white/[.025] p-4">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1"><span className={`text-sm font-semibold ${comment.is_deleted ? "text-slate-500" : "text-slate-200"}`}>{comment.author?.display_name ?? "[deleted]"}</span>{comment.author?.is_admin && <span className="inline-flex items-center gap-1 rounded-full bg-primary px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-primary-foreground"><ShieldCheck className="h-3 w-3" />Admin</span>}<span className="text-xs text-slate-600">{formatDate(comment.created_at)}</span>{comment.edited_at && <span className="text-xs italic text-slate-600">Edited</span>}</div>
        {editing === comment.id ? <form onSubmit={event => void saveEdit(event, comment.id)} className="mt-3"><Textarea value={editText} onChange={event => setEditText(event.target.value)} maxLength={5000} rows={3} autoFocus disabled={busy} /><div className="mt-2 flex justify-end gap-2"><Button type="button" variant="ghost" size="sm" onClick={() => setEditing(null)} disabled={busy}>Cancel</Button><Button type="submit" size="sm" disabled={busy || !editText.trim()}>Save</Button></div></form> : <p className={`mt-2 whitespace-pre-wrap break-words text-sm leading-6 ${comment.is_deleted ? "italic text-slate-600" : "text-slate-300"}`}>{comment.is_deleted ? "[deleted]" : comment.content}</p>}
        {!comment.is_deleted && editing !== comment.id && <div className="mt-3 flex items-center gap-3"><button type="button" onClick={() => { setReplyingTo(comment.id); setReplyText(""); }} className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-primary"><Reply className="h-3.5 w-3.5" />Reply</button>{own && <button type="button" onClick={() => { setEditing(comment.id); setEditText(comment.content ?? ""); }} className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-primary"><Pencil className="h-3.5 w-3.5" />Edit</button>}{thread?.is_admin && <button type="button" onClick={() => setDeleting(comment)} className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-red-300"><Trash2 className="h-3.5 w-3.5" />Delete</button>}</div>}
        {replyingTo === comment.id && <form onSubmit={event => void create(event, comment.id)} className="mt-3"><Textarea value={replyText} onChange={event => setReplyText(event.target.value)} maxLength={5000} rows={2} autoFocus placeholder={`Reply to ${comment.author?.display_name ?? "this thread"}…`} disabled={busy} /><div className="mt-2 flex justify-end gap-2"><Button type="button" variant="ghost" size="sm" onClick={() => setReplyingTo(null)} disabled={busy}>Cancel</Button><Button type="submit" size="sm" disabled={busy || !replyText.trim()}>Post reply</Button></div></form>}
      </div>;
    })}</div>}
    <AlertDialog open={!!deleting} onOpenChange={open => { if (!open && !busy) setDeleting(null); }}><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Delete this comment?</AlertDialogTitle><AlertDialogDescription>The comment will be replaced with [deleted]. Any replies will remain visible.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={busy} onClick={event => { event.preventDefault(); void remove(); }}>{busy ? "Deleting…" : "Delete comment"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </section>;
}
