"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, Circle } from "lucide-react";
import { request, type AppSummary, type Meta, type ProfileOut, type ResumeOut, type Stats } from "@/lib/api";
import { Alert, Loading, PageHeader, ScoreBadge, StatusBadge, fmtDate } from "@/components/ui";

const ACTION_STATUSES = ["Resume Update Required", "Ready for Application", "Account Creation Required",
  "Verification Pending", "Application In Progress", "Ready for Final Approval"];

export default function Overview() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [apps, setApps] = useState<AppSummary[]>([]);
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [resumes, setResumes] = useState<ResumeOut[]>([]);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      request<Stats>("/api/applications/stats"), request<AppSummary[]>("/api/applications"),
      request<ProfileOut>("/api/profile"), request<ResumeOut[]>("/api/resumes"), request<Meta>("/api/meta"),
    ]).then(([s, a, p, r, m]) => { setStats(s); setApps(a); setProfile(p); setResumes(r); setMeta(m); })
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <Alert kind="error">{error}</Alert>;
  if (!stats || !profile) return <Loading />;

  const steps = [
    { done: resumes.length > 0, label: "Upload your latest CV", href: "/resumes" },
    { done: profile.completeness >= 80, label: `Complete your profile (${profile.completeness}%)`, href: "/profile" },
    { done: stats.total > 0, label: "Paste a job application URL", href: "/apply" },
    { done: stats.submitted > 0, label: "Review and approve your first application", href: "/review" },
  ];
  const actions = apps.filter((a) => ACTION_STATUSES.includes(a.status)).slice(0, 6);

  return (
    <div className="space-y-6">
      <PageHeader title="Overview" subtitle="One saved profile, one job URL. AI does the supported work, you approve the important decisions."
        actions={<Link href="/apply" className="btn-primary">New application <ArrowRight className="h-4 w-4" /></Link>} />
      {meta && !meta.ai_enabled && (
        <Alert kind="warn">AI is not configured on the server (ANTHROPIC_API_KEY), so ApplyPilot is running in heuristic mode. Everything works, but analysis and answers are simpler.</Alert>
      )}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {[["Total", stats.total], ["In progress", stats.in_progress], ["Submitted", stats.submitted],
          ["Interviews", stats.interviews], ["Avg. match", stats.average_match !== null ? `${stats.average_match}%` : "—"]]
          .map(([label, value]) => (
            <div key={label as string} className="card"><p className="muted">{label}</p><p className="mt-1 text-2xl font-bold">{value}</p></div>
          ))}
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card lg:col-span-1">
          <h2 className="h2 mb-3">Getting started</h2>
          <ul className="space-y-2">
            {steps.map((s) => (
              <li key={s.label}>
                <Link href={s.href} className="flex min-h-[40px] items-center gap-2 rounded-lg px-2 hover:bg-slate-50">
                  {s.done ? <CheckCircle2 className="h-5 w-5 text-emerald-600" /> : <Circle className="h-5 w-5 text-slate-300" />}
                  <span className={s.done ? "text-slate-500 line-through" : ""}>{s.label}</span>
                </Link>
              </li>
            ))}
          </ul>
          {stats.follow_ups_due > 0 && <div className="mt-4"><Alert kind="info">{stats.follow_ups_due} follow-up(s) due. <Link className="font-semibold underline" href="/history">View</Link></Alert></div>}
        </div>
        <div className="card lg:col-span-2">
          <h2 className="h2 mb-3">Needs your attention</h2>
          {actions.length === 0 ? <p className="muted">Nothing waiting for you right now.</p> : (
            <ul className="divide-y divide-slate-100">
              {actions.map((a) => (
                <li key={a.id}>
                  <Link href={`/applications/${a.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3 hover:bg-slate-50">
                    <div className="min-w-0"><p className="truncate font-medium">{a.title || "Untitled role"}</p><p className="muted truncate">{a.company}</p></div>
                    <div className="flex items-center gap-2"><ScoreBadge score={a.match_score} /><StatusBadge status={a.status} /></div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
      <div className="card">
        <div className="mb-3 flex items-center justify-between"><h2 className="h2">Recent applications</h2><Link href="/history" className="text-sm font-semibold text-brand-600">View all</Link></div>
        {apps.length === 0 ? <p className="muted">No applications yet.</p> : (
          <ul className="divide-y divide-slate-100">
            {apps.slice(0, 5).map((a) => (
              <li key={a.id}><Link href={`/applications/${a.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <span className="min-w-0 truncate"><b>{a.title}</b> · {a.company}</span>
                <span className="flex items-center gap-2 text-xs text-slate-500">{fmtDate(a.updated_at)} <StatusBadge status={a.status} /></span>
              </Link></li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
