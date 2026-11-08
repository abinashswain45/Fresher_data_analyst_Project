"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { request, STATUSES, type AppSummary, type Stats } from "@/lib/api";
import { Alert, Empty, Loading, PageHeader, ScoreBadge, StatusBadge, fmtDate } from "@/components/ui";

export default function HistoryPage() {
  const [apps, setApps] = useState<AppSummary[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("updated");
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      const params = new URLSearchParams({ sort });
      if (q) params.set("q", q);
      if (status) params.set("status", status);
      request<AppSummary[]>(`/api/applications?${params}`).then(setApps).catch((e) => setError(e.message));
    }, 250);
    return () => clearTimeout(t);
  }, [q, status, sort]);
  useEffect(() => { request<Stats>("/api/applications/stats").then(setStats).catch(() => {}); }, []);

  const csv = useMemo(() => {
    if (!apps) return "";
    const rows = [["Company", "Job title", "Job URL", "Application date", "Resume version", "Status", "Reference ID", "Interview status", "Follow-up date", "Notes"],
      ...apps.map((a) => [a.company, a.title, a.job_url, a.submitted_at || a.created_at, a.resume_label, a.status, a.reference_id, a.interview_status, a.follow_up_date || "", a.notes])];
    return "data:text/csv;charset=utf-8," + encodeURIComponent(rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n"));
  }, [apps]);

  return (
    <div className="space-y-5">
      <PageHeader title="Application History" subtitle="Every application, its status, reference and follow-ups."
        actions={apps && apps.length > 0 ? <a className="btn-secondary" href={csv} download="applications.csv">Export CSV</a> : null} />
      {stats && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(stats.by_status).filter(([, n]) => n > 0).map(([s, n]) => (
            <button key={s} onClick={() => setStatus(status === s ? "" : s)} className={`rounded-full border px-3 py-1 text-xs font-medium ${status === s ? "border-brand-600 bg-brand-50" : "border-slate-200 bg-white"}`}>{s}: {n}</button>
          ))}
        </div>
      )}
      <div className="grid gap-2 sm:grid-cols-[1fr_auto_auto]">
        <div className="relative"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-400" />
          <input className="input pl-9" placeholder="Search company, title, notes, reference" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select className="input" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{STATUSES.map((s) => <option key={s}>{s}</option>)}</select>
        <select className="input" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="updated">Recently updated</option><option value="created">Newest</option><option value="score">Best match</option><option value="company">Company A–Z</option></select>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {!apps ? <Loading /> : apps.length === 0 ? <Empty title="No applications found"><Link className="text-brand-600 underline" href="/apply">Start a new application</Link></Empty> : (
        <>
          <div className="hidden overflow-x-auto rounded-xl border border-slate-200 bg-white md:block">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr><th className="p-3">Company / role</th><th className="p-3">Match</th><th className="p-3">Status</th><th className="p-3">Resume</th><th className="p-3">Applied</th><th className="p-3">Reference</th><th className="p-3">Follow-up</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {apps.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50">
                    <td className="p-3"><Link href={`/applications/${a.id}`} className="font-medium text-brand-700 hover:underline">{a.title || "Untitled"}</Link><p className="text-xs text-slate-500">{a.company} · {a.platform}</p></td>
                    <td className="p-3"><ScoreBadge score={a.match_score} /></td>
                    <td className="p-3"><StatusBadge status={a.status} />{a.interview_status && <p className="mt-1 text-xs text-slate-500">{a.interview_status}</p>}</td>
                    <td className="max-w-[160px] truncate p-3 text-xs">{a.resume_label || "—"}</td>
                    <td className="p-3 text-xs">{fmtDate(a.submitted_at)}</td>
                    <td className="p-3 text-xs">{a.reference_id || "—"}</td>
                    <td className="p-3 text-xs">{fmtDate(a.follow_up_date)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="space-y-2 md:hidden">
            {apps.map((a) => (
              <li key={a.id}><Link href={`/applications/${a.id}`} className="card block">
                <div className="flex items-start justify-between gap-2"><div className="min-w-0"><p className="truncate font-semibold">{a.title || "Untitled"}</p><p className="muted truncate">{a.company}</p></div><ScoreBadge score={a.match_score} /></div>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500"><StatusBadge status={a.status} />{a.reference_id && <span>Ref {a.reference_id}</span>}<span>Updated {fmtDate(a.updated_at)}</span></div>
              </Link></li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
