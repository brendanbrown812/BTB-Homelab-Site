"use client";

import { FormEvent, useState } from "react";
import { UserRoundPen } from "lucide-react";
import { apiFetch, CurrentUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function EditProfileDialog({ user, onUpdated }: { user: CurrentUser; onUpdated: (user: CurrentUser) => void }) {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    try {
      const updated = await apiFetch<CurrentUser>("/auth/me", {
        method: "PATCH",
        body: JSON.stringify({ display_name: form.get("display_name") }),
      });
      onUpdated(updated);
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not update your profile.");
    } finally {
      setSaving(false);
    }
  }

  return <Dialog open={open} onOpenChange={value => { setOpen(value); if (!value) setError(""); }}>
    <DialogTrigger asChild><Button variant="ghost" size="sm" className="mt-3 w-full justify-start text-slate-400 hover:text-white"><UserRoundPen className="h-4 w-4" />Edit profile</Button></DialogTrigger>
    <DialogContent className="border-white/10 bg-card">
      <DialogHeader><DialogTitle>Edit profile</DialogTitle><DialogDescription>Choose the name other league members will see.</DialogDescription></DialogHeader>
      <form className="space-y-4" onSubmit={submit}>
        <div className="space-y-2"><Label htmlFor="profile-display-name">Display name</Label><Input id="profile-display-name" name="display_name" required minLength={1} maxLength={120} defaultValue={user.display_name} autoComplete="name" /></div>
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <Button disabled={saving} className="w-full bg-primary font-bold text-primary-foreground">{saving ? "Saving…" : "Save changes"}</Button>
      </form>
    </DialogContent>
  </Dialog>;
}
