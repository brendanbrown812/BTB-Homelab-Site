"use client";

import { LoaderCircle, MessageCircle, Pencil, Reply, ShieldCheck, Trash2 } from "lucide-react";
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

export function PTGOTWComments({ writeupId }: { writeupId: string }) {
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
