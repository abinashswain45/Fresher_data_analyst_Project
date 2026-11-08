"use client";

import { useEffect, useState } from "react";
import { Copy, Download, ExternalLink } from "lucide-react";
import { download, request, type AppDetail } from "@/lib/api";
import { Alert, Loading } from "./ui";

interface Guide { job_url: string; resume_download: string | null; fields: { key: string; label: string; value: string }[]; answers: { question: string; answer: string }[]; steps: string[] }

export default function ManualGuide({ appId, onSubmitted }: { appId: number; onSubmitted: (a: AppDetail) => void }) {
  const [g, setG] = useState<Guide | null>(null);
  const [ref, setRef] = useState("");
  const [copied, setCopied] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { request<Guide>(`/api/applications/${appId}/manual-guide`).then(setG).catch((e) => setError(e.message)); }, [appId]);
  const copy = async (k: string, v: string) => { try { await navigator.clipboard.writeText(v); setCopied(k); setTimeout(() => setCopied(""), 1500); } catch { /* clipboard blocked */ } };
  if (error) return <Alert kind="error">{error}</Alert>;
  if (!g) return <Loading />;
  return (
    <div className="space-y-4 text-sm">
      <ol className="list-decimal space-y-1 pl-5">{g.steps.map((s) => <li key={s}>{s}</li>)}</ol>
      <div className="flex flex-wrap gap-2">
        <a className="btn-secondary" href={g.job_url} target="_blank" rel="noopener noreferrer"><ExternalLink className="h-4 w-4" />Open official site</a>
        {g.resume_download && <button className="btn-secondary" onClick={() => download(g.resume_download!, "resume.pdf")}><Download className="h-4 w-4" />Approved resume (PDF)</button>}
      </div>
      <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
        {[...g.fields.filter((f) => f.value), ...g.answers.map((a, i) => ({ key: `a${i}`, label: a.question, value: a.answer }))].map((f) => (
          <div key={f.key} className="flex items-start justify-between gap-2 p-2">
            <div className="min-w-0"><p className="text-xs text-slate-500">{f.label}</p><p className="whitespace-pre-wrap break-words">{f.value}</p></div>
            <button className="btn-ghost shrink-0 px-2" aria-label={`Copy ${f.label}`} onClick={() => copy(f.key, f.value)}><Copy className="h-4 w-4" />{copied === f.key ? "Copied" : ""}</button>
          </div>
        ))}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <input className="input" placeholder="Application reference number (if shown)" value={ref} onChange={(e) => setRef(e.target.value)} />
        <button className="btn-success shrink-0" onClick={() => confirm("Mark this application as submitted?") &&
          request<AppDetail>(`/api/applications/${appId}/manual-submit`, { method: "POST", json: { reference_id: ref } }).then(onSubmitted)}>Mark as submitted</button>
      </div>
    </div>
  );
}
