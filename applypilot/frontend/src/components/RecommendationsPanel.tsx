"use client";

import { useState } from "react";
import { AlertTriangle, Check, Download, Sparkles, Wand2, X } from "lucide-react";
import { download, request, type AppDetail, type Recommendation, type ResumeOut } from "@/lib/api";
import { Alert, Spinner } from "./ui";

type Decision = { status: string; suggested: string };

export default function RecommendationsPanel({ app, resumes, onChange }:
  { app: AppDetail; resumes: ResumeOut[]; onChange: (a: AppDetail) => void }) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>(() =>
    Object.fromEntries(app.recommendations.map((r) => [r.id, { status: r.status, suggested: r.suggested }])));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const selected = resumes.find((r) => r.id === app.resume_id);
  const recommended = resumes.find((r) => r.id === app.match.recommended_resume_id);
  const approved = ["Ready for Application", "Account Creation Required", "Verification Pending", "Application In Progress",
    "Ready for Final Approval", "Submitted", "Interview"].includes(app.status) && !!app.resume_id;

  async function run(key: string, fn: () => Promise<AppDetail>) {
    setBusy(key); setError("");
    try {
      const a = await fn();
      onChange(a);
      setDecisions(Object.fromEntries(a.recommendations.map((r) => [r.id, { status: r.status, suggested: r.suggested }])));
    } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }

  const tailor = (mode: "review" | "auto") => run(mode, () => request<AppDetail>(`/api/applications/${app.id}/tailor`, {
    method: "POST", json: { mode, decisions: Object.entries(decisions).map(([id, d]) => ({ id, ...d })) },
  }));
  const approve = (resumeId: number) => run("approve", () => request<AppDetail>(`/api/applications/${app.id}/approve-resume?resume_id=${resumeId}`, { method: "POST" }));
  const setD = (r: Recommendation, patch: Partial<Decision>) => setDecisions({ ...decisions, [r.id]: { ...decisions[r.id], ...patch } });
  const contentRecs = app.recommendations.filter((r) => r.section !== "formatting");
  const tips = app.recommendations.filter((r) => r.section === "formatting");

  return (
    <div className="space-y-4">
      {error && <Alert kind="error">{error}</Alert>}
      {recommended && <Alert kind="info"><b>Recommended version:</b> {app.match.resume_reason}</Alert>}

      {contentRecs.length > 0 && (
        <div className="space-y-3">
          <p className="muted">Option A: review each suggestion, then approve or reject it (you can edit the text). Every change must be true. Suggestions that add skills or numbers not found in your profile are flagged.</p>
          {contentRecs.map((r) => {
            const d = decisions[r.id] || { status: "pending", suggested: r.suggested };
            return (
              <div key={r.id} className={`rounded-lg border p-3 ${d.status === "approved" ? "border-emerald-300 bg-emerald-50/50" : d.status === "rejected" ? "border-slate-200 opacity-60" : "border-slate-200"}`}>
                <div className="mb-2 flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold uppercase">{r.section}</span>
                  {r.flagged && <span className="inline-flex items-center gap-1 rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800"><AlertTriangle className="h-3 w-3" />Check facts</span>}
                  {r.keywords_added.map((k) => <span key={k} className="rounded-full bg-brand-50 px-2 py-0.5 text-xs text-brand-700">+{k}</span>)}
                </div>
                {r.original && <p className="mb-2 text-sm text-slate-500 line-through decoration-slate-300">{r.original}</p>}
                <textarea className="input text-sm" rows={Math.min(6, Math.ceil(d.suggested.length / 90) + 1)} value={d.suggested}
                  onChange={(e) => setD(r, { suggested: e.target.value })} />
                <p className="mt-2 text-xs text-slate-600"><b>Why:</b> {r.reason}{r.evidence && <> · <b>Based on:</b> {r.evidence}</>}</p>
                <div className="mt-2 flex gap-2">
                  <button className={d.status === "approved" ? "btn-success" : "btn-secondary"} onClick={() => setD(r, { status: "approved" })}><Check className="h-4 w-4" />Approve</button>
                  <button className="btn-ghost" onClick={() => setD(r, { status: "rejected" })}><X className="h-4 w-4" />Reject</button>
                </div>
              </div>
            );
          })}
          <div className="flex flex-wrap gap-2">
            <button className="btn-primary" disabled={!!busy || !Object.values(decisions).some((d) => d.status === "approved")} onClick={() => tailor("review")}>
              {busy === "review" ? <Spinner /> : <Check className="h-4 w-4" />}Create CV from approved changes</button>
            <button className="btn-secondary" disabled={!!busy} onClick={() => tailor("auto")}>
              {busy === "auto" ? <Spinner /> : <Wand2 className="h-4 w-4" />}Option B: generate updated CV automatically</button>
          </div>
        </div>
      )}
      {tips.length > 0 && (
        <div className="rounded-lg bg-slate-50 p-3 text-sm">
          <p className="mb-1 font-semibold"><Sparkles className="mr-1 inline h-4 w-4" />ATS tips</p>
          <ul className="list-disc space-y-1 pl-5">{tips.map((t) => <li key={t.id}>{t.suggested}</li>)}</ul>
        </div>
      )}

      <div className="rounded-lg border border-slate-200 p-3">
        <p className="mb-2 font-semibold">Resume for this application</p>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select className="input sm:max-w-sm" value={app.resume_id ?? app.match.recommended_resume_id ?? ""}
            onChange={(e) => request<AppDetail>(`/api/applications/${app.id}`, { method: "PATCH", json: { resume_id: Number(e.target.value) } }).then(onChange)}>
            <option value="" disabled>Select a resume version</option>
            {resumes.map((r) => <option key={r.id} value={r.id}>{r.label} ({r.kind})</option>)}
          </select>
          {(app.resume_id ?? app.match.recommended_resume_id) && (
            <button className="btn-secondary" onClick={() => download(`/api/resumes/${app.resume_id ?? app.match.recommended_resume_id}/download?format=pdf`, "resume.pdf")}><Download className="h-4 w-4" />Preview PDF</button>
          )}
        </div>
        {approved ? (
          <p className="mt-3 text-sm font-medium text-emerald-700"><Check className="mr-1 inline h-4 w-4" />Approved: {selected?.label}. Ready for the application step.</p>
        ) : (
          <button className="btn-success mt-3" disabled={!!busy || !(app.resume_id ?? app.match.recommended_resume_id)}
            onClick={() => approve((app.resume_id ?? app.match.recommended_resume_id)!)}>
            {busy === "approve" ? <Spinner /> : <Check className="h-4 w-4" />}I have reviewed it. Approve this CV</button>
        )}
      </div>
    </div>
  );
}
