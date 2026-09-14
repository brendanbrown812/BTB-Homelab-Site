"use client";

/* eslint-disable @next/next/no-img-element -- Local static branding is served directly by Vinext. */

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ArrowLeftRight, BarChart3, BookOpenText, CalendarClock, CalendarDays, ChevronDown, ClipboardCheck, FilePenLine, History, Home, Library, ListPlus, LogOut, Menu, ShieldCheck, Sparkles, Trophy, UsersRound, Vote, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ChangePasswordDialog } from "@/components/change-password-dialog";
import { EditProfileDialog } from "@/components/edit-profile-dialog";
import { apiFetch, CurrentUser, getToken, UpcomingWriteup } from "@/lib/api";

const predictionItems = [
  { href: "/predictions", label: "Current week", icon: CalendarDays },
  { href: "/predictions/results", label: "Results", icon: Trophy },
  { href: "/predictions/standings", label: "Standings", icon: BarChart3 },
  { href: "/predictions/history", label: "History", icon: History },
];

const leagueItems = [
  { href: "/league", label: "Overview", icon: Home },
  { href: "/league/teams", label: "Teams", icon: UsersRound },
  { href: "/league/seasons", label: "Seasons", icon: Library },
  { href: "/league/records", label: "Records & fun facts", icon: Sparkles },
  { href: "/league/trades", label: "Trades", icon: ArrowLeftRight },
  { href: "/league/waivers", label: "Waiver wire", icon: ListPlus },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname(); const router = useRouter();
  const [open, setOpen] = useState(false); const [user, setUser] = useState<CurrentUser | null>(null); const [canSubmitWriteup, setCanSubmitWriteup] = useState(false); const [upcomingWriteup, setUpcomingWriteup] = useState<UpcomingWriteup | null>(null);
  const [predictionsExpanded, setPredictionsExpanded] = useState(true); const [ptgotwExpanded, setPtgotwExpanded] = useState(true); const [leagueExpanded, setLeagueExpanded] = useState(true);
  useEffect(() => {
    function refreshUpcomingWriteup() { apiFetch<UpcomingWriteup | null>("/ptgotw/upcoming").then(setUpcomingWriteup).catch(() => setUpcomingWriteup(null)); }
    window.addEventListener("ptgotw-updated", refreshUpcomingWriteup);
    if (!getToken()) { router.replace("/login"); return () => window.removeEventListener("ptgotw-updated", refreshUpcomingWriteup); }
    apiFetch<CurrentUser>("/auth/me").then(value => {
      setUser(value);
      if (value.role === "admin") setCanSubmitWriteup(true);
      else Promise.all([apiFetch<Array<{ id: string }>>("/ptgotw/editable"), apiFetch<UpcomingWriteup | null>("/ptgotw/upcoming")]).then(([items, upcoming]) => { setCanSubmitWriteup(items.length > 0); setUpcomingWriteup(upcoming); }).catch(() => setCanSubmitWriteup(false));
    }).catch(() => router.replace("/login"));
    return () => window.removeEventListener("ptgotw-updated", refreshUpcomingWriteup);
  }, [router]);
  function logout() { localStorage.removeItem("btb_access_token"); router.replace("/login"); }
  if (!user) return <main className="grid min-h-screen place-items-center"><div className="text-center"><span className="mx-auto mb-4 grid h-11 w-11 animate-pulse place-items-center rounded-[14px] bg-primary font-black text-primary-foreground">BTB</span><p className="text-sm text-slate-500">Checking your account…</p></div></main>;

  const itemClass = (href: string) => `flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] transition ${path === href || (href === "/ptgotw" && path.startsWith("/ptgotw/") && path !== "/ptgotw/submit") || (href.startsWith("/league/") && path.startsWith(`${href}/`)) ? "bg-primary font-semibold text-primary-foreground" : "text-slate-400 hover:bg-white/5 hover:text-white"}`;
  const nav = <>
    <NavSection label="Predictions" expanded={predictionsExpanded} onToggle={() => setPredictionsExpanded(value => !value)} />
    {predictionsExpanded && predictionItems.map(({ href, label, icon: Icon }) => <Link key={href} href={href} onClick={() => setOpen(false)} className={itemClass(href)}><Icon className="h-[18px] w-[18px]" />{label}</Link>)}
    <NavSection label="PTGOTW" expanded={ptgotwExpanded} onToggle={() => setPtgotwExpanded(value => !value)} />
    {ptgotwExpanded && <><Link href="/ptgotw" onClick={() => setOpen(false)} className={itemClass("/ptgotw")}><BookOpenText className="h-[18px] w-[18px]" />Writeups</Link>{canSubmitWriteup && <Link href="/ptgotw/submit" onClick={() => setOpen(false)} className={itemClass("/ptgotw/submit")}><FilePenLine className="h-[18px] w-[18px]" />Submit writeup</Link>}</>}
    <NavSection label="League" expanded={leagueExpanded} onToggle={() => setLeagueExpanded(value => !value)} />
    {leagueExpanded && leagueItems.map(({ href, label, icon: Icon }) => <Link key={href} href={href} onClick={() => setOpen(false)} className={itemClass(href)}><Icon className="h-[18px] w-[18px]" />{label}</Link>)}
    <div className="mt-6 border-t border-white/8 pt-4"><Link href="/polls" onClick={() => setOpen(false)} className={itemClass("/polls")}><Vote className="h-[18px] w-[18px]" />Polls</Link></div>
    {user.role === "admin" && <div className="mt-2 space-y-1"><Link href="/admin" onClick={() => setOpen(false)} className={itemClass("/admin")}><ShieldCheck className="h-[18px] w-[18px]" />Admin</Link><Link href="/admin/submissions" onClick={() => setOpen(false)} className={itemClass("/admin/submissions")}><ClipboardCheck className="h-[18px] w-[18px]" />Pick status</Link></div>}
  </>;

  return <div className="min-h-screen lg:grid lg:grid-cols-[245px_1fr]">
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[245px] flex-col border-r border-white/8 bg-[#0b1019]/95 px-4 lg:flex"><Brand /><nav className="flex-1 overflow-y-auto pb-4">{nav}</nav><Account user={user} onUpdated={setUser} onLogout={logout} /></aside>
    {open && <div className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden" onClick={() => setOpen(false)}><aside className="flex h-full w-[280px] flex-col border-r border-white/10 bg-[#0b1019] px-4" onClick={e => e.stopPropagation()}><div className="flex items-center justify-between"><Brand /><button aria-label="Close navigation" onClick={() => setOpen(false)}><X /></button></div><nav className="flex-1 overflow-y-auto pb-4">{nav}</nav><Account user={user} onUpdated={setUser} onLogout={logout} /></aside></div>}
    <div className="lg:col-start-2"><header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-white/8 bg-[#080b12]/80 px-5 backdrop-blur-xl sm:px-8 lg:px-10"><div className="flex items-center gap-3"><Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setOpen(true)}><Menu /></Button><div><p className="text-xs font-medium uppercase tracking-[.15em] text-slate-500">BTB</p><p className="text-sm font-semibold text-slate-200">Fantasy league hub</p></div></div><span className="hidden rounded-full border border-white/10 bg-white/[.04] px-3 py-2 text-sm text-slate-300 sm:block">Signed in as <strong className="text-white">{user.display_name}</strong></span></header><main className="mx-auto w-full max-w-[1580px] px-5 py-8 sm:px-8 lg:px-10 lg:py-10">{upcomingWriteup && <WriteupDueBanner writeup={upcomingWriteup} />}{children}</main></div>
  </div>;
}

function WriteupDueBanner({ writeup }: { writeup: UpcomingWriteup }) { const timing = writeup.days_remaining < 0 ? `${Math.abs(writeup.days_remaining)} ${Math.abs(writeup.days_remaining) === 1 ? "day" : "days"} overdue` : writeup.days_remaining === 0 ? "due today" : `due in ${writeup.days_remaining} ${writeup.days_remaining === 1 ? "day" : "days"}`; return <Link href={`/ptgotw/submit?id=${writeup.id}`} className="mb-7 flex items-center gap-4 rounded-2xl border border-primary/25 bg-primary/10 px-5 py-4 transition hover:border-primary/50 hover:bg-primary/[.14]"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary text-primary-foreground"><CalendarClock className="h-5 w-5" /></span><span className="min-w-0 flex-1"><span className="block font-bold text-slate-100">You have a Week {writeup.week} writeup {timing}</span><span className="mt-0.5 block text-sm text-slate-400">Due {new Date(`${writeup.due_date}T12:00:00`).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · Open the editor</span></span></Link>; }

function Account({ user, onUpdated, onLogout }: { user: CurrentUser; onUpdated: (user: CurrentUser) => void; onLogout: () => void }) { const initials = user.display_name.split(" ").map(v => v[0]).join("").slice(0, 2).toUpperCase(); return <div className="mb-5 rounded-2xl border border-white/8 bg-white/[.03] p-3"><div className="flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-full bg-[#24334b] text-sm font-bold text-primary">{initials}</div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold">{user.display_name}</p><p className="text-xs capitalize text-slate-500">{user.role}</p></div><button onClick={onLogout} title="Sign out" aria-label="Sign out" className="rounded-lg p-2 text-slate-500 hover:bg-white/5 hover:text-white"><LogOut className="h-4 w-4" /></button></div><EditProfileDialog user={user} onUpdated={onUpdated} /><ChangePasswordDialog /></div>; }
function Brand() {
  return <Link href="/predictions" className="flex h-[84px] items-center gap-3">
    <img src="/images/BTB_Logo-ffcd3c.png" alt="" width={40} height={52} className="h-[52px] w-10 shrink-0 object-contain" />
    <span><span className="block text-[17px] font-extrabold tracking-tight">BTB</span><span className="block text-xs text-slate-500">League home</span></span>
  </Link>;
}

function NavSection({ label, expanded, onToggle }: { label: string; expanded: boolean; onToggle: () => void }) { return <button type="button" aria-expanded={expanded} onClick={onToggle} className="mt-5 flex w-full items-center justify-between border-b border-white/7 px-3 pb-2 pt-3 text-left text-xs font-semibold uppercase tracking-[.18em] text-slate-500 hover:text-slate-300"><span>{label}</span><ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-0" : "-rotate-90"}`} /></button>; }
