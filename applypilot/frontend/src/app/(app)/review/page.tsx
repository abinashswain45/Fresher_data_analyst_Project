"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { request, type AppSummary } from "@/lib/api";
import { Empty, Loading, PageHeader, ScoreBadge, StatusBadge } from "@/components/ui";

const GROUPS: { title: string; statuses: string[]; hint: string }[] = [
  { title: "Ready for final approval", statuses: ["Ready for Final Approval"], hint: "Review the completed application and approve submission." },
  { title: "Verification needed", statuses: ["Account Creation Required", "Verification Pending"], hint: "Complete login, OTP or CAPTCHA, then continue." },
  { title: "Resume approval needed", statuses: ["Resume Update Required"], hint: "Review AI recommendations and approve a CV." },
  { title: "Not eligible / on hold", statuses: ["On Hold"], hint: "Check why ApplyPilot paused before proceeding." },
];

export default function ReviewPage() {
  const [apps, setApps] = useState<AppSummary[] | null>(null);
  useEffect(() => { request<AppSummary[]>("/api/applications").then(setApps).catch(() => setApps([])); }, []);
  if (!apps) return <Loading />;
  const any = GROUPS.some((g) => apps.some((a) => g.statuses.includes(a.status)));
  return (
    <div className="space-y-5">
      <PageHeader title="Review & Approval" subtitle="Everything that is waiting for your decision." />
      {!any && <Empty title="You're all caught up">Nothing needs your approval right now.</Empty>}
      {GROUPS.map((g) => {
        const items = apps.filter((a) => g.statuses.includes(a.status));
        if (!items.length) return null;
        return (
          <section key={g.title} className="card">
            <h2 className="h2">{g.title} <span className="text-slate-400">({items.length})</span></h2>
            <p className="muted mb-3">{g.hint}</p>
            <ul className="divide-y divide-slate-100">{items.map((a) => (
              <li key={a.id}><Link href={`/applications/${a.id}${g.statuses.includes("Ready for Final Approval") || g.title.startsWith("Verification") ? "#automation" : ""}`} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <span className="min-w-0"><b>{a.title}</b> · {a.company}</span><span className="flex gap-2"><ScoreBadge score={a.match_score} /><StatusBadge status={a.status} /></span></Link></li>
            ))}</ul>
          </section>
        );
      })}
    </div>
  );
}
