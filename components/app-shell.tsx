"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, CalendarDays, History, LogOut, Menu, ShieldCheck, Trophy, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { apiFetch, CurrentUser, getToken } from "@/lib/api";

const items = [
  { href: "/predictions", label: "Current week", icon: CalendarDays },
  { href: "/predictions/results", label: "Results", icon: Trophy },
  { href: "/predictions/standings", label: "Standings", icon: BarChart3 },
  { href: "/predictions/history", label: "History", icon: History },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname(); const router = useRouter();
  const [open, setOpen] = useState(false); const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => {
    if (!getToken()) { router.replace("/login"); return; }
    apiFetch<CurrentUser>("/auth/me").then(setUser).catch(() => router.replace("/login"));
  }, [router]);
  function logout() { localStorage.removeItem("btb_access_token"); router.replace("/login"); }
  if (!user) return <main className="grid min-h-screen place-items-center"><div className="text-center"><span className="mx-auto mb-4 grid h-11 w-11 animate-pulse place-items-center rounded-[14px] bg-primary font-black text-primary-foreground">BTB</span><p className="text-sm text-slate-500">Checking your account…</p></div></main>;

  const nav = <><div className="px-3 pb-3 pt-8 text-xs font-semibold uppercase tracking-[.18em] text-slate-500">Predictions</div>{items.map(({ href, label, icon: Icon }) => <Link key={href} href={href} onClick={() => setOpen(false)} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] transition ${path === href ? "bg-primary font-semibold text-primary-foreground" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}><Icon className="h-[18px] w-[18px]" />{label}</Link>)}{user.role === "admin" && <div className="mt-6 border-t border-white/8 pt-4"><Link href="/admin" onClick={() => setOpen(false)} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] ${path.startsWith("/admin") ? "bg-primary font-semibold text-primary-foreground" : "text-slate-400 hover:bg-white/5 hover:text-white"}`}><ShieldCheck className="h-[18px] w-[18px]" />Admin</Link></div>}</>;

  return <div className="min-h-screen lg:grid lg:grid-cols-[245px_1fr]">
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[245px] flex-col border-r border-white/8 bg-[#0b1019]/95 px-4 lg:flex"><Brand /><nav className="flex-1">{nav}</nav><Account user={user} onLogout={logout} /></aside>
    {open && <div className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden" onClick={() => setOpen(false)}><aside className="flex h-full w-[280px] flex-col border-r border-white/10 bg-[#0b1019] px-4" onClick={e => e.stopPropagation()}><div className="flex items-center justify-between"><Brand /><button aria-label="Close navigation" onClick={() => setOpen(false)}><X /></button></div><nav className="flex-1">{nav}</nav><Account user={user} onLogout={logout} /></aside></div>}
    <div className="lg:col-start-2"><header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-white/8 bg-[#080b12]/80 px-5 backdrop-blur-xl sm:px-8 lg:px-10"><div className="flex items-center gap-3"><Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)}><Menu /></Button><div><p className="text-xs font-medium uppercase tracking-[.15em] text-slate-500">BTB League</p><p className="text-sm font-semibold text-slate-200">Sleeper-connected predictions</p></div></div><span className="hidden rounded-full border border-white/10 bg-white/[.04] px-3 py-2 text-sm text-slate-300 sm:block">Signed in as <strong className="text-white">{user.display_name}</strong></span></header><main className="mx-auto w-full max-w-[1180px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">{children}</main></div>
  </div>;
}

function Account({ user, onLogout }: { user: CurrentUser; onLogout: () => void }) { const initials = user.display_name.split(" ").map(v => v[0]).join("").slice(0, 2).toUpperCase(); return <div className="mb-5 rounded-2xl border border-white/8 bg-white/[.03] p-3"><div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-full bg-[#24334b] text-sm font-bold text-primary">{initials}</div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{user.display_name}</p><p className="text-xs capitalize text-slate-500">{user.role}</p></div><button onClick={onLogout} title="Sign out" aria-label="Sign out" className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"><LogOut className="h-4 w-4" /></button></div><ChangePasswordDialog /></div>; }
function Brand() { return <Link href="/predictions" className="flex h-[84px] items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-[13px] bg-primary font-black tracking-[-.08em] text-primary-foreground">BTB</span><span><span className="block text-[17px] font-extrabold tracking-tight">BTB League</span><span className="block text-xs text-slate-500">League home</span></span></Link>; }
