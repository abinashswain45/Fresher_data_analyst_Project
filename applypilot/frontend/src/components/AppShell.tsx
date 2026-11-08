"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Bot, CheckSquare, FileText, History, LayoutDashboard, LogOut, Menu, PlusCircle, Rocket, Search, Settings, User, X,
} from "lucide-react";
import { auth, request, type User as UserT } from "@/lib/api";
import { Loading } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/profile", label: "My Profile", icon: User },
  { href: "/resumes", label: "Resume Builder", icon: FileText },
  { href: "/discover", label: "Job Discovery", icon: Search },
  { href: "/apply", label: "New Application", icon: PlusCircle },
  { href: "/automation", label: "Application Automation", icon: Bot },
  { href: "/review", label: "Review & Approval", icon: CheckSquare },
  { href: "/history", label: "Application History", icon: History },
  { href: "/settings", label: "Settings", icon: Settings },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<UserT | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!auth.token) { router.replace("/login"); return; }
    request<UserT>("/api/auth/me").then(setUser).catch(() => router.replace("/login"));
  }, [router]);

  useEffect(() => setOpen(false), [pathname]);

  if (!user) return <Loading />;

  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const nav = (
    <nav className="flex flex-col gap-1 p-3">
      {NAV.map(({ href, label, icon: Icon }) => (
        <Link key={href} href={href}
          className={`flex min-h-[44px] items-center gap-3 rounded-lg px-3 text-sm font-medium transition ${
            isActive(href) ? "bg-brand-600 text-white" : "text-slate-700 hover:bg-slate-100"}`}>
          <Icon className="h-5 w-5 shrink-0" />{label}
        </Link>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:flex lg:flex-col">
        <div className="flex items-center gap-2 px-5 py-5 text-brand-700"><Rocket className="h-6 w-6" /><span className="text-lg font-bold">ApplyPilot AI</span></div>
        <div className="flex-1 overflow-y-auto">{nav}</div>
        <div className="border-t border-slate-200 p-3">
          <p className="truncate px-3 text-xs text-slate-500">{user.email}</p>
          <button className="btn-ghost mt-1 w-full justify-start" onClick={() => { auth.clear(); router.replace("/login"); }}>
            <LogOut className="h-4 w-4" />Sign out</button>
        </div>
      </aside>

      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2 lg:hidden">
        <Link href="/" className="flex items-center gap-2 font-bold text-brand-700"><Rocket className="h-5 w-5" />ApplyPilot AI</Link>
        <button className="btn-ghost px-2" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-6 w-6" /></button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 top-0 h-full w-72 max-w-[85%] overflow-y-auto bg-white shadow-xl">
            <div className="flex items-center justify-between px-4 py-3">
              <span className="font-bold text-brand-700">Menu</span>
              <button className="btn-ghost px-2" aria-label="Close menu" onClick={() => setOpen(false)}><X className="h-6 w-6" /></button>
            </div>
            {nav}
            <div className="border-t p-3">
              <button className="btn-ghost w-full justify-start" onClick={() => { auth.clear(); router.replace("/login"); }}>
                <LogOut className="h-4 w-4" />Sign out</button>
            </div>
          </div>
        </div>
      )}
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-5 sm:px-6 lg:py-8">{children}</main>
    </div>
  );
}
