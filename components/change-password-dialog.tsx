"use client";

import { FormEvent, useState } from "react";
import { KeyRound } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ChangePasswordDialog() {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const newPassword = String(form.get("new_password"));
    if (newPassword !== form.get("confirm_password")) {
      setError("The new passwords do not match.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await apiFetch("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: form.get("current_password"),
          new_password: newPassword,
        }),
      });
      formElement.reset();
      setSuccess(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not change your password.");
    } finally {
      setSaving(false);
    }
  }

  return <Dialog open={open} onOpenChange={value => { setOpen(value); if (!value) { setError(""); setSuccess(false); } }}>
    <DialogTrigger asChild><Button variant="ghost" size="sm" className="mt-3 w-full justify-start text-slate-400 hover:text-white"><KeyRound className="h-4 w-4" />Change password</Button></DialogTrigger>
    <DialogContent className="border-white/10 bg-card">
      <DialogHeader><DialogTitle>Change password</DialogTitle><DialogDescription>Choose a new password with at least 12 characters.</DialogDescription></DialogHeader>
      {success ? <div className="space-y-4"><p role="status" className="rounded-xl bg-emerald-400/10 px-4 py-3 text-sm text-emerald-300">Your password has been changed.</p><Button className="w-full" onClick={() => setOpen(false)}>Done</Button></div> : <form className="space-y-4" onSubmit={submit}>
        <div className="space-y-2"><Label htmlFor="current-password">Current password</Label><Input id="current-password" name="current_password" type="password" required autoComplete="current-password" /></div>
        <div className="space-y-2"><Label htmlFor="new-password">New password</Label><Input id="new-password" name="new_password" type="password" required minLength={12} maxLength={128} autoComplete="new-password" /></div>
        <div className="space-y-2"><Label htmlFor="confirm-password">Confirm new password</Label><Input id="confirm-password" name="confirm_password" type="password" required minLength={12} maxLength={128} autoComplete="new-password" /></div>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <Button disabled={saving} className="w-full bg-primary font-bold text-primary-foreground">{saving ? "Changing…" : "Change password"}</Button>
      </form>}
    </DialogContent>
  </Dialog>;
}
