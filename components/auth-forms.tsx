"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

export function LoginForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: data.get("username"), password: data.get("password") }) });
      if (!response.ok) throw new Error("That username or password didn’t match.");
      const body = await response.json(); localStorage.setItem("btb_access_token", body.access_token); router.push("/predictions");
    } catch (reason) { setError(reason instanceof TypeError ? "The browser could not reach the BTB API. Confirm the backend window is running, then refresh this page." : reason instanceof Error ? reason.message : "Sign in failed."); } finally { setLoading(false); }
  }
  return <><form className="mt-7 space-y-5" onSubmit={submit}>{error && <p role="alert" className="rounded-xl bg-red-400/10 px-3 py-2 text-sm text-red-300">{error}</p>}<div className="space-y-2"><Label htmlFor="username">Username</Label><Input id="username" name="username" required autoComplete="username" autoCapitalize="none" spellCheck={false} className="h-11 bg-white/[.035]" /></div><div className="space-y-2"><Label htmlFor="password">Password</Label><Input id="password" name="password" required type="password" autoComplete="current-password" className="h-11 bg-white/[.035]" /></div><Button disabled={loading} className="h-11 w-full bg-primary font-bold text-primary-foreground">{loading ? "Signing in…" : "Sign in"}</Button></form><Dialog><DialogTrigger asChild><button type="button" className="mx-auto mt-4 block text-sm font-medium text-slate-400 transition hover:text-primary">Forgot password?</button></DialogTrigger><DialogContent className="border-white/10 bg-card"><DialogHeader><DialogTitle>Forgot password?</DialogTitle><DialogDescription className="pt-2 text-base text-slate-200">Dumbass. Text Brendan</DialogDescription></DialogHeader></DialogContent></Dialog></>;
}

export function SetupForm() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setLoading(true); setError("");
    const data = new FormData(event.currentTarget); const password = String(data.get("password"));
    if (password !== data.get("confirm")) { setError("The passwords do not match."); setLoading(false); return; }
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) { setError("This setup link is missing its credential."); setLoading(false); return; }
    try {
      const response = await fetch(`${API}/auth/setup-account`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ token, password }) });
      if (!response.ok) { const body = await response.json(); throw new Error(body.detail ?? "Account setup failed."); }
      router.push("/login");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Account setup failed."); } finally { setLoading(false); }
  }
  return <form className="mt-7 space-y-5" onSubmit={submit}>{error && <p role="alert" className="rounded-xl bg-red-400/10 px-3 py-2 text-sm text-red-300">{error}</p>}<div className="space-y-2"><Label htmlFor="password">New password</Label><Input id="password" name="password" minLength={12} required type="password" autoComplete="new-password" className="h-11 bg-white/[.035]" /><p className="text-xs text-slate-500">Use at least 12 characters.</p></div><div className="space-y-2"><Label htmlFor="confirm">Confirm password</Label><Input id="confirm" name="confirm" minLength={12} required type="password" autoComplete="new-password" className="h-11 bg-white/[.035]" /></div><Button disabled={loading} className="h-11 w-full bg-primary font-bold text-primary-foreground">{loading ? "Finishing…" : "Finish setup"}</Button></form>;
}
