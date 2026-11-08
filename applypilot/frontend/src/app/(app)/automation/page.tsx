"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { request, type AppSummary, type Meta } from "@/lib/api";
import { Empty, Loading, PageHeader, StatusBadge } from "@/components/ui";

const ACTIVE = ["Ready for Application", "Account Creation Required", "Verification Pending", "Application In Progress", "Ready for Final Approval"];

export default function AutomationPage() {
  const [apps, setApps] = useState<AppSummary[] | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  useEffect(() => {
    request<AppSummary[]>(`/api/applications?status=${encodeURIComponent(ACTIVE.join(","))}`).then(setApps).catch(() => setApps([]));
    request<Meta>("/api/meta").then(setMeta).catch(() => {});
  }, []);
  return (
    <div className="space-y-5">
      <PageHeader title="Application Automation" subtitle="Applications ready for, or in, automated form filling." />
      {!apps ? <Loading /> : apps.length === 0 ? <Empty title="No applications ready for automation">Approve a resume on an analysed job to start.</Empty> : (
        <ul className="grid gap-3 md:grid-cols-2">{apps.map((a) => (
          <li key={a.id}><Link href={`/applications/${a.id}#automation`} className="card block hover:border-brand-500">
            <p className="font-semibold">{a.title}</p><p className="muted">{a.company} · {a.platform}</p><div className="mt-2"><StatusBadge status={a.status} /></div>
          </Link></li>))}</ul>
      )}
      {meta && (
        <section className="card">
          <h2 className="h2 mb-2">Supported recruitment platforms</h2>
          <p className="muted mb-3">Each platform has an adapter, and fields are detected dynamically on every page. ApplyPilot respects site restrictions: if a portal blocks automation, use the manual workflow.</p>
          <ul className="grid gap-2 sm:grid-cols-2">{meta.adapters.map((ad) => (
            <li key={ad.name} className="rounded-lg border border-slate-200 p-3 text-sm"><p className="font-semibold">{ad.display_name}{ad.requires_account && <span className="ml-2 rounded bg-orange-100 px-1.5 py-0.5 text-[11px] text-orange-800">account required</span>}</p><p className="text-slate-600">{ad.notes}</p></li>
          ))}</ul>
        </section>
      )}
    </div>
  );
}
