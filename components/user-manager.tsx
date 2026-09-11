"use client";

import { FormEvent, useEffect, useState } from "react";
import { Copy, Pencil, Plus, Trash2, Users } from "lucide-react";

import { apiFetch, CurrentUser } from "@/lib/api";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

type ManagedUser = { id: string; username: string; display_name: string; role: "user" | "admin"; is_active: boolean; is_bootstrap: boolean; setup_pending: boolean };

export function UserManager() {
  const [users, setUsers] = useState<ManagedUser[]>([]); const [currentUserId, setCurrentUserId] = useState("");
  const [createOpen, setCreateOpen] = useState(false); const [editUser, setEditUser] = useState<ManagedUser | null>(null); const [deleteUser, setDeleteUser] = useState<ManagedUser | null>(null);
  const [generatedPassword, setGeneratedPassword] = useState(""); const [error, setError] = useState(""); const [saving, setSaving] = useState(false);

  async function load() { try { setUsers(await apiFetch<ManagedUser[]>("/admin/users")); } catch (reason) { setError(message(reason, "Could not load users.")); } }
  useEffect(() => {
    let cancelled = false;
    Promise.all([apiFetch<ManagedUser[]>("/admin/users"), apiFetch<CurrentUser>("/auth/me")]).then(([items, current]) => { if (!cancelled) { setUsers(items); setCurrentUserId(current.id); } }).catch(reason => { if (!cancelled) setError(message(reason, "Could not load users.")); });
    return () => { cancelled = true; };
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError(""); const form = new FormData(event.currentTarget);
    try { const result = await apiFetch<{ generated_password: string }>("/admin/users", { method: "POST", body: JSON.stringify({ username: form.get("username"), display_name: form.get("display_name"), role: form.get("role") }) }); setGeneratedPassword(result.generated_password); await load(); }
    catch (reason) { setError(message(reason, "Could not create account.")); } finally { setSaving(false); }
  }

  async function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editUser) return; setSaving(true); setError(""); const form = new FormData(event.currentTarget); const newPassword = String(form.get("new_password") ?? "");
    try {
      await apiFetch(`/admin/users/${editUser.id}`, { method: "PATCH", body: JSON.stringify({ username: form.get("username"), display_name: form.get("display_name"), role: form.get("role"), ...(newPassword ? { new_password: newPassword } : {}) }) });
      await load(); setEditUser(null);
    } catch (reason) { setError(message(reason, "Could not update account.")); } finally { setSaving(false); }
  }

  async function remove() {
    if (!deleteUser) return; setSaving(true); setError("");
    try { await apiFetch<void>(`/admin/users/${deleteUser.id}`, { method: "DELETE" }); setUsers(items => items.filter(item => item.id !== deleteUser.id)); setDeleteUser(null); }
    catch (reason) { setError(message(reason, "Could not delete account.")); } finally { setSaving(false); }
  }

  return <section className="mt-6 overflow-hidden rounded-2xl border border-white/8 bg-card">
    <div className="flex flex-col gap-4 border-b border-white/8 p-5 sm:flex-row sm:items-center sm:justify-between"><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-primary/10 text-primary"><Users className="h-5 w-5" /></span><div><h2 className="font-bold">BTB accounts</h2><p className="text-sm text-slate-500">Create and manage commissioner and league member accounts.</p></div></div>
      <Dialog open={createOpen} onOpenChange={value => { setCreateOpen(value); if (!value) { setGeneratedPassword(""); setError(""); } }}><DialogTrigger asChild><Button className="bg-primary font-bold text-primary-foreground"><Plus className="h-4 w-4" />Create account</Button></DialogTrigger><DialogContent className="border-white/10 bg-card"><DialogHeader><DialogTitle>Create a BTB account</DialogTitle><DialogDescription>BTB will generate a secure password for you to share with the user.</DialogDescription></DialogHeader>{generatedPassword ? <div className="space-y-4"><div className="rounded-xl bg-white/5 p-4"><Label>Generated password</Label><p className="mt-2 break-all font-mono text-sm text-slate-200">{generatedPassword}</p></div><Button className="w-full" onClick={() => navigator.clipboard.writeText(generatedPassword)}><Copy className="h-4 w-4" />Copy password</Button><p className="text-xs text-slate-500">Save it now—this password is only shown once. The user can change it after signing in.</p></div> : <AccountForm onSubmit={create} saving={saving} error={error} />}</DialogContent></Dialog>
    </div>
    {error && !createOpen && !editUser && !deleteUser && <p className="px-5 py-4 text-sm text-red-300">{error}</p>}
    <div className="divide-y divide-white/7">{users.map(user => <div key={user.id} className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(0,1fr)_120px_100px_auto] sm:items-center"><div><p className="font-semibold">{user.display_name}</p><p className="text-xs text-slate-500">@{user.username}{user.is_bootstrap ? " · environment bootstrap" : ""}</p></div><span className="text-sm capitalize text-slate-400">{user.role}</span><span className={`text-sm ${user.is_active ? "text-emerald-400" : "text-slate-500"}`}>{user.is_active ? "Active" : "Disabled"}</span><div className="flex justify-end gap-2"><Button variant="ghost" size="icon" title="Edit account" aria-label={`Edit ${user.display_name}`} disabled={user.is_bootstrap} onClick={() => { setError(""); setEditUser(user); }}><Pencil className="h-4 w-4" /></Button><Button variant="ghost" size="icon" title="Delete account" aria-label={`Delete ${user.display_name}`} disabled={user.is_bootstrap || user.id === currentUserId} onClick={() => { setError(""); setDeleteUser(user); }} className="text-slate-500 hover:text-red-300"><Trash2 className="h-4 w-4" /></Button></div></div>)}</div>

    <Dialog open={!!editUser} onOpenChange={value => { if (!value) { setEditUser(null); setError(""); } }}><DialogContent className="border-white/10 bg-card"><DialogHeader><DialogTitle>Edit account</DialogTitle><DialogDescription>Update account details, role, or set a new password.</DialogDescription></DialogHeader>{editUser && <AccountForm user={editUser} onSubmit={update} saving={saving} error={error} />}</DialogContent></Dialog>
    <AlertDialog open={!!deleteUser} onOpenChange={value => { if (!value) { setDeleteUser(null); setError(""); } }}><AlertDialogContent className="border-white/10 bg-card"><AlertDialogHeader><AlertDialogTitle>Delete {deleteUser?.display_name}?</AlertDialogTitle><AlertDialogDescription>They will immediately lose access. Their historical picks and credited PTGOTW writeups will remain intact.</AlertDialogDescription></AlertDialogHeader>{error && <p className="text-sm text-red-300">{error}</p>}<AlertDialogFooter><AlertDialogCancel disabled={saving}>Cancel</AlertDialogCancel><AlertDialogAction variant="destructive" disabled={saving} onClick={event => { event.preventDefault(); void remove(); }}>{saving ? "Deleting…" : "Delete account"}</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>
  </section>;
}

function AccountForm({ user, onSubmit, saving, error }: { user?: ManagedUser; onSubmit: (event: FormEvent<HTMLFormElement>) => void; saving: boolean; error: string }) {
  return <form className="space-y-4" onSubmit={onSubmit}><div className="space-y-2"><Label htmlFor={user ? "edit-username" : "new-username"}>Username</Label><Input id={user ? "edit-username" : "new-username"} name="username" required minLength={3} defaultValue={user?.username} autoCapitalize="none" spellCheck={false} /></div><div className="space-y-2"><Label htmlFor={user ? "edit-name" : "new-name"}>Display name</Label><Input id={user ? "edit-name" : "new-name"} name="display_name" required defaultValue={user?.display_name} /></div><div className="space-y-2"><Label htmlFor={user ? "edit-role" : "new-role"}>Role</Label><NativeSelect id={user ? "edit-role" : "new-role"} name="role" defaultValue={user?.role ?? "user"} className="w-full"><NativeSelectOption value="user">User</NativeSelectOption><NativeSelectOption value="admin">Admin</NativeSelectOption></NativeSelect></div>{user && <div className="space-y-2"><Label htmlFor="edit-password">New password <span className="font-normal text-slate-500">(optional)</span></Label><Input id="edit-password" name="new_password" type="password" minLength={12} maxLength={128} autoComplete="new-password" placeholder="Leave blank to keep current password" /><p className="text-xs text-slate-500">Must be at least 12 characters.</p></div>}{error && <p role="alert" className="text-sm text-red-300">{error}</p>}<Button disabled={saving} className="w-full bg-primary font-bold text-primary-foreground">{saving ? "Saving…" : user ? "Save changes" : "Create account"}</Button></form>;
}

function message(reason: unknown, fallback: string) { return reason instanceof Error ? reason.message : fallback; }
