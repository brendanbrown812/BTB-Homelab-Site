"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { CalendarClock, Check, CirclePlus, LoaderCircle, LockKeyhole, Plus, RotateCcw, Trash2, UsersRound, Vote } from "lucide-react";

import { PageHeading } from "@/components/page-heading";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch, Poll, PollList } from "@/lib/api";

export function PollsPage() {
  const [data, setData] = useState<PollList | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [warning, setWarning] = useState("");
  const [closeTarget, setCloseTarget] = useState<Poll | null>(null);
  const [closing, setClosing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Poll | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [showCompleted, setShowCompleted] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<PollList>("/polls").then(value => { if (!cancelled) setData(value); }).catch(reason => { if (!cancelled) setError(reason instanceof Error ? reason.message : "Could not load polls."); });
    return () => { cancelled = true; };
  }, []);

  function replacePoll(updated: Poll) {
    setData(current => current ? { ...current, polls: current.polls.map(poll => poll.id === updated.id ? updated : poll) } : current);
  }

  async function closePoll() {
    if (!closeTarget) return;
    setClosing(true);
    try {
      replacePoll(await apiFetch<Poll>(`/polls/${closeTarget.id}/close`, { method: "POST" }));
      setCloseTarget(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not close the poll.");
    } finally {
      setClosing(false);
    }
  }

  async function deletePoll() {
    if (!deleteTarget) return;
    setDeleting(true); setError("");
    try {
      await apiFetch<void>(`/polls/${deleteTarget.id}`, { method: "DELETE" });
      setData(current => current ? { ...current, polls: current.polls.filter(poll => poll.id !== deleteTarget.id) } : current);
      setDeleteTarget(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not delete the poll.");
    } finally {
      setDeleting(false);
    }
  }

  const visiblePolls = data?.polls.filter(poll => showCompleted || poll.is_open) ?? [];

  return <>
    <div className="mb-8 flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
      <PageHeading eyebrow="League decisions" title="Polls">Cast your vote and see where the rest of the league stands.</PageHeading>
      <div className="mb-8 flex flex-wrap items-center gap-4"><Label htmlFor="show-completed-polls" className="flex items-center gap-2 text-sm font-medium text-slate-300"><Switch id="show-completed-polls" checked={showCompleted} onCheckedChange={setShowCompleted} />Show completed polls</Label>{data?.is_admin && <PollFormDialog onSaved={poll => { setData(current => current ? { ...current, polls: [poll, ...current.polls] } : current); setNotice(poll.notification_status === "sent" ? "Poll created and posted to Discord." : poll.notification_status === "bypassed" ? "Poll created without a Discord notification." : ""); setWarning(poll.notification_status === "failed" ? "Poll created, but the Discord notification failed." : poll.notification_status === "not_configured" ? "Poll created, but Discord notifications are not configured." : ""); }} />}</div>
    </div>
    {notice && <p role="status" className="mb-5 rounded-xl bg-emerald-400/10 px-4 py-3 text-sm text-emerald-300">{notice}</p>}
    {warning && <p role="status" className="mb-5 rounded-xl bg-amber-400/10 px-4 py-3 text-sm text-amber-300">{warning}</p>}
    {error && <p role="alert" className="mb-5 rounded-xl bg-red-400/10 px-4 py-3 text-sm text-red-300">{error}</p>}
    {!data ? <Loading /> : visiblePolls.length === 0 ? <EmptyState admin={data.is_admin} hasCompleted={data.polls.some(poll => !poll.is_open)} /> : <div className="space-y-5">{visiblePolls.map(poll => <PollCard key={poll.id} poll={poll} isAdmin={data.is_admin} onChanged={replacePoll} onClose={() => setCloseTarget(poll)} onDelete={() => setDeleteTarget(poll)} />)}</div>}
    <AlertDialog open={!!closeTarget} onOpenChange={open => { if (!open && !closing) setCloseTarget(null); }}><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Close this poll?</AlertDialogTitle><AlertDialogDescription>Voting will stop immediately. Everyone will still be able to see the final named results.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={closing}>Cancel</AlertDialogCancel><AlertDialogAction disabled={closing} onClick={event => { event.preventDefault(); void closePoll(); }}>{closing ? "Closing…" : "Close poll"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
    <AlertDialog open={!!deleteTarget} onOpenChange={open => { if (!open && !deleting) setDeleteTarget(null); }}><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Delete this poll?</AlertDialogTitle><AlertDialogDescription>This permanently removes “{deleteTarget?.question},” including every vote and answer option. This action cannot be undone.</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={deleting} onClick={event => { event.preventDefault(); void deletePoll(); }}>{deleting ? "Deleting…" : "Delete poll"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </>;
}

function PollCard({ poll, isAdmin, onChanged, onClose, onDelete }: { poll: Poll; isAdmin: boolean; onChanged: (poll: Poll) => void; onClose: () => void; onDelete: () => void }) {
  const [selected, setSelected] = useState<string[]>(poll.current_user_option_ids);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const participantCount = poll.options.reduce((userIds, option) => {
    option.voters.forEach(voter => userIds.add(voter.id));
    return userIds;
  }, new Set<string>()).size;

  function toggle(optionId: string, checked: boolean) {
    setSelected(current => checked ? [...current, optionId] : current.filter(id => id !== optionId));
  }

  async function saveVote() {
    if (!selected.length) { setError("Choose at least one option."); return; }
    setSaving(true); setError("");
    try { onChanged(await apiFetch<Poll>(`/polls/${poll.id}/vote`, { method: "PUT", body: JSON.stringify({ option_ids: selected }) })); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not save your vote."); }
    finally { setSaving(false); }
  }

  return <article className="overflow-hidden rounded-2xl border border-white/8 bg-card">
    <header className="border-b border-white/8 p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0"><div className="mb-2 flex flex-wrap items-center gap-2"><span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${poll.is_open ? "bg-emerald-400/10 text-emerald-300" : "bg-white/5 text-slate-400"}`}>{poll.is_open ? "Open" : "Closed"}</span><span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">{poll.selection_mode === "single" ? "Select one" : "Select all that apply"}</span></div><h2 className="text-xl font-black tracking-tight sm:text-2xl">{poll.question}</h2>{poll.description && <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-400">{poll.description}</p>}<p className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500"><span>Created by {poll.created_by.display_name}</span><span className="flex items-center gap-1.5"><CalendarClock className="h-3.5 w-3.5" />{poll.is_open ? poll.closes_at ? `Closes ${formatDate(poll.closes_at)}` : "No closing date" : `Closed ${formatDate(poll.closed_at ?? poll.closes_at)}`}</span></p></div>
        {isAdmin && <div className="flex flex-wrap gap-2">{poll.is_open ? <Button variant="outline" size="sm" onClick={onClose}><LockKeyhole className="h-4 w-4" />Close poll</Button> : <PollFormDialog poll={poll} onSaved={onChanged} />}<Button variant="outline" size="sm" className="text-slate-400 hover:border-red-400/40 hover:text-red-300" onClick={onDelete}><Trash2 className="h-4 w-4" />Delete</Button></div>}
      </div>
    </header>
    <div className="grid gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,.8fr)]">
      <section><h3 className="mb-3 text-sm font-bold">Your vote</h3>{poll.selection_mode === "single" ? <RadioGroup value={selected[0] ?? ""} onValueChange={value => setSelected([value])} disabled={!poll.is_open}>{poll.options.map(option => <Label key={option.id} htmlFor={`${poll.id}-${option.id}`} className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/8 p-4 font-medium hover:border-primary/30"><RadioGroupItem id={`${poll.id}-${option.id}`} value={option.id} />{option.text}</Label>)}</RadioGroup> : <div className="grid gap-3">{poll.options.map(option => <Label key={option.id} htmlFor={`${poll.id}-${option.id}`} className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/8 p-4 font-medium hover:border-primary/30"><Checkbox id={`${poll.id}-${option.id}`} checked={selected.includes(option.id)} onCheckedChange={checked => toggle(option.id, checked === true)} disabled={!poll.is_open} />{option.text}</Label>)}</div>}
        {poll.is_open ? <><Button className="mt-4 bg-primary font-bold text-primary-foreground" disabled={saving || !selected.length} onClick={() => void saveVote()}><Check className="h-4 w-4" />{saving ? "Saving…" : poll.current_user_option_ids.length ? "Update vote" : "Submit vote"}</Button>{error && <p role="alert" className="mt-3 text-sm text-red-300">{error}</p>}</> : <p className="mt-4 flex items-center gap-2 text-sm text-slate-500"><LockKeyhole className="h-4 w-4" />Voting is closed.</p>}
      </section>
      <section><div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm font-bold">Live results</h3><span className="text-xs text-slate-500">{participantCount} voted</span></div><div className="space-y-3">{poll.options.map(option => { const percent = participantCount ? Math.round(option.voters.length / participantCount * 100) : 0; return <div key={option.id} className="rounded-xl bg-white/[.035] p-4"><div className="flex items-start justify-between gap-3"><p className="font-semibold">{option.text}</p><span className="shrink-0 text-sm font-bold text-primary">{option.voters.length}</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/5"><div className="h-full rounded-full bg-primary" style={{ width: `${percent}%` }} /></div><p className="mt-2 text-xs leading-5 text-slate-500">{option.voters.length ? option.voters.map(voter => voter.display_name).join(", ") : "No votes yet"}</p></div>; })}</div>{poll.not_voted.length > 0 && <div className="mt-4 flex items-start gap-2 rounded-xl border border-white/7 p-3 text-xs leading-5 text-slate-500"><UsersRound className="mt-0.5 h-4 w-4 shrink-0" /><span><strong className="text-slate-400">Not voted:</strong> {poll.not_voted.map(user => user.display_name).join(", ")}</span></div>}</section>
    </div>
  </article>;
}

function PollFormDialog({ poll, onSaved }: { poll?: Poll; onSaved: (poll: Poll) => void }) {
  const initialOptions = () => poll ? poll.options.map((option, key) => ({ key, text: option.text })) : [{ key: 0, text: "" }, { key: 1, text: "" }];
  const [open, setOpen] = useState(false); const [options, setOptions] = useState(initialOptions); const nextOptionKey = useRef(options.length); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  function reset() { const resetOptions = initialOptions(); setOptions(resetOptions); nextOptionKey.current = resetOptions.length; setError(""); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const formElement = event.currentTarget; const form = new FormData(formElement); const closesAt = String(form.get("closes_at") ?? "");
    setSaving(true); setError("");
    try {
      const savedPoll = await apiFetch<Poll>(poll ? `/polls/${poll.id}` : "/polls", { method: poll ? "PUT" : "POST", body: JSON.stringify({ question: form.get("question"), description: form.get("description") || null, selection_mode: form.get("selection_mode"), options: options.map(option => option.text), closes_at: closesAt ? new Date(closesAt).toISOString() : null, bypass_notification: !poll && form.get("bypass_notification") === "on" }) });
      onSaved(savedPoll); formElement.reset(); reset(); setOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : `Could not ${poll ? "re-open" : "create"} the poll.`); }
    finally { setSaving(false); }
  }
  const formKey = poll?.id ?? "new";
  return <Dialog open={open} onOpenChange={value => { setOpen(value); if (!value) reset(); }}><DialogTrigger asChild>{poll ? <Button variant="outline" size="sm"><RotateCcw className="h-4 w-4" />Re-open</Button> : <Button className="bg-primary font-bold text-primary-foreground"><CirclePlus className="h-4 w-4" />Create poll</Button>}</DialogTrigger><DialogContent className="max-h-[90vh] overflow-y-auto border-white/10 bg-card sm:max-w-xl"><DialogHeader><DialogTitle>{poll ? "Edit and re-open poll" : "Create a poll"}</DialogTitle><DialogDescription>{poll ? "Update the poll, then save it to resume voting." : "Add any number of choices and optionally schedule when voting closes."}</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}><div className="space-y-2"><Label htmlFor={`${formKey}-poll-question`}>Question</Label><Input id={`${formKey}-poll-question`} name="question" required maxLength={240} defaultValue={poll?.question} /></div><div className="space-y-2"><Label htmlFor={`${formKey}-poll-description`}>Description <span className="font-normal text-slate-500">(optional)</span></Label><Textarea id={`${formKey}-poll-description`} name="description" maxLength={10000} defaultValue={poll?.description ?? ""} /></div><div className="space-y-2"><Label htmlFor={`${formKey}-poll-mode`}>Response type</Label><NativeSelect id={`${formKey}-poll-mode`} name="selection_mode" defaultValue={poll?.selection_mode ?? "single"} className="w-full"><NativeSelectOption value="single">Select one</NativeSelectOption><NativeSelectOption value="multiple">Select all that apply</NativeSelectOption></NativeSelect></div><div className="space-y-2"><Label>Answer options</Label>{options.map((option, index) => <div key={option.key} className="flex gap-2"><Input value={option.text} onChange={event => setOptions(current => current.map(value => value.key === option.key ? { ...value, text: event.target.value } : value))} required maxLength={240} aria-label={`Answer option ${index + 1}`} placeholder={`Option ${index + 1}`} /><Button type="button" variant="ghost" size="icon" aria-label={`Remove option ${index + 1}`} disabled={options.length <= 2} onClick={() => setOptions(current => current.filter(value => value.key !== option.key))}><Trash2 className="h-4 w-4" /></Button></div>)}<Button type="button" variant="outline" size="sm" onClick={() => setOptions(current => [...current, { key: nextOptionKey.current++, text: "" }])}><Plus className="h-4 w-4" />Add option</Button>{poll && <p className="text-xs text-amber-300/80">Changing answer options or the response type will clear existing votes.</p>}</div><div className="space-y-2"><Label htmlFor={`${formKey}-poll-closes-at`}>Closing date <span className="font-normal text-slate-500">(optional)</span></Label><Input id={`${formKey}-poll-closes-at`} name="closes_at" type="datetime-local" defaultValue={toDateTimeLocal(poll?.closes_at)} /><p className="text-xs text-slate-500">{poll ? "Use a future date or leave this blank to re-open the poll indefinitely." : "Leave blank to keep the poll open until an admin closes it."}</p></div>{!poll && <Label htmlFor="bypass-poll-notification" className="flex cursor-pointer items-center gap-3 rounded-xl border border-white/8 p-3 font-medium"><Checkbox id="bypass-poll-notification" name="bypass_notification" />Bypass notification</Label>}{error && <p role="alert" className="text-sm text-red-300">{error}</p>}<Button disabled={saving} className="w-full bg-primary font-bold text-primary-foreground">{saving ? "Saving…" : poll ? "Save and re-open" : "Create poll"}</Button></form></DialogContent></Dialog>;
}

function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : ""; }
function toDateTimeLocal(value?: string | null) { if (!value) return ""; const date = new Date(value); const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000); return local.toISOString().slice(0, 16); }
function Loading() { return <div className="grid min-h-52 place-items-center rounded-2xl border border-white/8 bg-card"><LoaderCircle className="h-6 w-6 animate-spin text-primary" /></div>; }
function EmptyState({ admin, hasCompleted }: { admin: boolean; hasCompleted: boolean }) { return <div className="rounded-2xl border border-white/8 bg-card p-10 text-center"><Vote className="mx-auto mb-3 h-7 w-7 text-slate-600" /><h2 className="text-xl font-bold">{hasCompleted ? "No open polls" : "No polls yet"}</h2><p className="mt-2 text-sm text-slate-400">{hasCompleted ? "Turn on Show completed polls to view previous results." : admin ? "Create the first poll to start collecting league votes." : "A league poll will appear here when an admin creates one."}</p></div>; }
