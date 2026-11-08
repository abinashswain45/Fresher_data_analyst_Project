"use client";

import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <Loader2 className={`animate-spin ${className}`} aria-hidden />;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="h1">{title}</h1>
        {subtitle && <p className="muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const STATUS_COLORS: Record<string, string> = {
  New: "bg-slate-100 text-slate-700",
  Analyzing: "bg-sky-100 text-sky-800",
  "Resume Update Required": "bg-amber-100 text-amber-800",
  "Ready for Application": "bg-indigo-100 text-indigo-800",
  "Account Creation Required": "bg-orange-100 text-orange-800",
  "Verification Pending": "bg-orange-100 text-orange-800",
  "Application In Progress": "bg-blue-100 text-blue-800",
  "Ready for Final Approval": "bg-violet-100 text-violet-800",
  Submitted: "bg-emerald-100 text-emerald-800",
  Interview: "bg-teal-100 text-teal-800",
  Rejected: "bg-red-100 text-red-700",
  "On Hold": "bg-slate-200 text-slate-700",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${STATUS_COLORS[status] || "bg-slate-100"}`}>
      {status}
    </span>
  );
}

export function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return <span className="text-xs text-slate-400">—</span>;
  const c = score >= 75 ? "bg-emerald-600" : score >= 50 ? "bg-amber-500" : "bg-red-500";
  return <span className={`inline-flex rounded-md px-2 py-0.5 text-xs font-bold text-white ${c}`}>{Math.round(score)}%</span>;
}

export function Alert({ kind = "info", children }: { kind?: "info" | "error" | "success" | "warn"; children: ReactNode }) {
  const c = {
    info: "border-sky-200 bg-sky-50 text-sky-900",
    error: "border-red-200 bg-red-50 text-red-800",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
  }[kind];
  return <div role={kind === "error" ? "alert" : "status"} className={`rounded-lg border px-4 py-3 text-sm ${c}`}>{children}</div>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="muted mt-2">{children}</div>}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Loading() {
  return <div className="flex items-center gap-2 p-6 text-slate-500"><Spinner /> Loading…</div>;
}

export function fmtDate(s?: string | null) {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}
