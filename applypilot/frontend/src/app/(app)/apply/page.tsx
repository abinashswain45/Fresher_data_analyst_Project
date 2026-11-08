"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Link2, Sparkles } from "lucide-react";
import { ApiError, request, type AppDetail } from "@/lib/api";
import { Alert, PageHeader, Spinner } from "@/components/ui";

export default function NewApplication() {
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [manual, setManual] = useState("");
  const [showManual, setShowManual] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [duplicate, setDuplicate] = useState<{ application_id: number; message: string } | null>(null);

  async function submit(force = false) {
    setBusy(true); setError(""); setDuplicate(null);
    try {
      const app = await request<AppDetail>("/api/applications/analyze", {
        method: "POST", json: { url, force, manual_description: showManual && manual.trim() ? manual : null },
      });
      router.push(`/applications/${app.id}`);
    } catch (e) {
      const err = e as ApiError;
      if (err.status === 409 && err.detail && typeof err.detail === "object") setDuplicate(err.detail as { application_id: number; message: string });
      else setError(err.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="New Application" subtitle="Paste the official job posting URL. ApplyPilot reads the job, scores your fit and prepares your resume." />
      <form className="card space-y-4" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label className="block">
          <span className="label">Paste Job Application URL</span>
          <div className="relative">
            <Link2 className="pointer-events-none absolute left-3 top-3 h-5 w-5 text-slate-400" />
            <input className="input pl-10" type="url" inputMode="url" required placeholder="https://careers.example.com/job/data-analyst"
              value={url} onChange={(e) => setUrl(e.target.value)} />
          </div>
        </label>
        <button type="button" className="text-sm font-medium text-brand-600" onClick={() => setShowManual(!showManual)}>
          {showManual ? "Hide" : "Site blocks automated reading? Paste the job description instead"}
        </button>
        {showManual && (
          <textarea className="input min-h-[160px]" placeholder="Paste the full job description here" value={manual} onChange={(e) => setManual(e.target.value)} />
        )}
        {error && <Alert kind="error">{error}</Alert>}
        {duplicate && (
          <Alert kind="warn">
            <p>{duplicate.message} Applying twice to the same job can hurt your candidacy.</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button type="button" className="btn-secondary" onClick={() => router.push(`/applications/${duplicate.application_id}`)}>Open existing</button>
              <button type="button" className="btn-ghost" onClick={() => submit(true)}>Create a new application anyway</button>
            </div>
          </Alert>
        )}
        <button className="btn-primary w-full sm:w-auto" disabled={busy || !url}>{busy ? <Spinner /> : <Sparkles className="h-4 w-4" />}Analyse job</button>
      </form>
      <div className="card mt-5">
        <h2 className="h2 mb-2">What happens next</h2>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-700">
          <li>ApplyPilot opens the official posting and extracts the company, title and full description.</li>
          <li>It identifies required skills, experience and qualifications, and scores your fit with reasons.</li>
          <li>It picks your best resume version and suggests factual improvements for you to approve.</li>
          <li>Once you approve a resume, the automation fills the application. You handle login, OTP and CAPTCHA, and give final approval.</li>
        </ol>
      </div>
    </div>
  );
}
