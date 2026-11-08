"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, ExternalLink, RefreshCw, Trash2, XCircle } from "lucide-react";
import { blobUrl, request, STATUSES, type AppDetail, type ResumeOut } from "@/lib/api";
import AutomationPanel from "@/components/AutomationPanel";
import FinalReview from "@/components/FinalReview";
import ManualGuide from "@/components/ManualGuide";
import QuestionsPanel from "@/components/QuestionsPanel";
import RecommendationsPanel from "@/components/RecommendationsPanel";
import { Alert, Loading, ScoreBadge, Spinner, StatusBadge, fmtDate } from "@/components/ui";

function Step({ n, title, done, children, id }: { n: number; title: string; done?: boolean; children: React.ReactNode; id?: string }) {
  return (
    <section id={id} className="card scroll-mt-20">
      <h2 className="h2 mb-3 flex items-center gap-2">
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${done ? "bg-emerald-600 text-white" : "bg-brand-100 text-brand-700"}`}>{done ? "✓" : n}</span>{title}
      </h2>
      {children}
    </section>
  );
}

export default function ApplicationPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [app, setApp] = useState<AppDetail | null>(null);
  const [resumes, setResumes] = useState<ResumeOut[]>([]);
  const [error, setError] = useState("");
  const [manualJD, setManualJD] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [shot, setShot] = useState("");
  const automationRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => request<AppDetail>(`/api/applications/${id}`).then(setApp).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); request<ResumeOut[]>("/api/resumes").then(setResumes).catch(() => {}); }, [load]);
  useEffect(() => {
    if (app?.status !== "Analyzing") return;
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, [app?.status, load]);
  useEffect(() => { if (app?.has_confirmation_screenshot) blobUrl(`/api/applications/${id}/confirmation-screenshot`).then(setShot).catch(() => {}); }, [app?.has_confirmation_screenshot, id]);

  if (error) return <Alert kind="error">{error}</Alert>;
  if (!app) return <Loading />;

  const m = app.match || {};
  const reqs = app.job.requirements as { required_skills?: string[]; preferred_skills?: string[]; min_experience_years?: number | null; education_requirements?: string[] };
  const analyzed = app.status !== "Analyzing" && m.score !== undefined;
  const resumeApproved = !!app.resume_id && !["Analyzing", "Resume Update Required", "On Hold", "New"].includes(app.status);
  const submitted = ["Submitted", "Interview", "Rejected"].includes(app.status);

  async function approveSubmit() {
    setSubmitting(true);
    try { await request(`/api/automation/${id}/approve-submit`, { method: "POST" }); setTimeout(load, 1500); }
    catch (e) { setError((e as Error).message); } finally { setSubmitting(false); }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="muted"><Link href="/history" className="hover:underline">Applications</Link> / #{app.id}</p>
          <h1 className="h1 break-words">{app.job.title || "Analysing job…"}</h1>
          <p className="text-slate-600">{app.job.company} {app.job.location && `· ${app.job.location}`}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={app.status} /><ScoreBadge score={app.match_score} />
            <a href={app.job.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-brand-600 hover:underline">Official posting <ExternalLink className="h-3 w-3" /></a>
          </div>
        </div>
        <div className="flex gap-2">
          {!submitted && <button className="btn-secondary" onClick={() => request<AppDetail>(`/api/applications/${id}/reanalyze`, { method: "POST" }).then(setApp)}><RefreshCw className="h-4 w-4" />Re-analyse</button>}
          <button className="btn-ghost text-red-600" aria-label="Delete application" onClick={() => confirm("Delete this application from your tracker?") && request(`/api/applications/${id}`, { method: "DELETE" }).then(() => router.push("/history"))}><Trash2 className="h-4 w-4" /></button>
        </div>
      </div>

      {submitted && (
        <section className="card border-emerald-300 bg-emerald-50">
          <h2 className="h2 flex items-center gap-2 text-emerald-800"><CheckCircle2 className="h-5 w-5" />Application submitted</h2>
          <p className="mt-1 text-sm">Submitted {fmtDate(app.submitted_at)}{app.reference_id && <> · Reference <b>{app.reference_id}</b></>}</p>
          {app.confirmation_text && <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{app.confirmation_text}</p>}
          {app.confirmation_url && <a className="mt-1 block truncate text-sm text-brand-600" href={app.confirmation_url} target="_blank" rel="noopener noreferrer">{app.confirmation_url}</a>}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {shot && <img src={shot} alt="Confirmation page screenshot" className="mt-3 max-h-96 rounded border object-top" />}
        </section>
      )}

      <Step n={1} title="Job analysis & compatibility" done={analyzed}>
        {app.status === "Analyzing" ? (
          <p className="flex items-center gap-2 text-slate-600"><Spinner />Opening the official posting and analysing the job description…</p>
        ) : m.error ? (
          <div className="space-y-3">
            <Alert kind="error">{m.error}</Alert>
            <textarea className="input min-h-[140px]" placeholder="Paste the job description here" value={manualJD} onChange={(e) => setManualJD(e.target.value)} />
            <button className="btn-primary" disabled={manualJD.trim().length < 50} onClick={() =>
              request<AppDetail>(`/api/applications/${id}/reanalyze`, { method: "POST", json: { url: app.job.url, manual_description: manualJD } }).then(setApp)}>Analyse pasted description</button>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
              <div className={`flex h-24 w-24 shrink-0 flex-col items-center justify-center rounded-full border-8 ${(m.score ?? 0) >= 75 ? "border-emerald-500" : (m.score ?? 0) >= 50 ? "border-amber-400" : "border-red-400"}`}>
                <span className="text-2xl font-bold">{m.score}</span><span className="text-[10px] uppercase text-slate-500">match</span>
              </div>
              <div>
                <p className="flex items-center gap-1 font-semibold">{m.eligible ? <><CheckCircle2 className="h-4 w-4 text-emerald-600" />You appear eligible</> : <><XCircle className="h-4 w-4 text-red-600" />You may not be eligible</>}</p>
                <p className="text-sm text-slate-700">{m.summary}</p>
                {m.mode === "heuristic" && <p className="text-xs text-slate-400">Heuristic analysis (AI not configured)</p>}
              </div>
            </div>
            {!m.eligible && (m.ineligibility_reasons?.length ?? 0) > 0 && (
              <Alert kind="warn"><p className="font-semibold">Why this may not be a fit:</p><ul className="list-disc pl-5">{m.ineligibility_reasons!.map((r) => <li key={r}>{r}</li>)}</ul>
                <p className="mt-2">ApplyPilot won&apos;t proceed blindly. You can still continue if you believe you qualify.</p></Alert>
            )}
            <div className="grid gap-4 md:grid-cols-2">
              <div><p className="mb-1 text-sm font-semibold text-emerald-700">Strengths</p><ul className="list-disc space-y-0.5 pl-5 text-sm">{(m.strengths || []).map((s) => <li key={s}>{s}</li>)}</ul></div>
              <div><p className="mb-1 text-sm font-semibold text-amber-700">Gaps</p><ul className="list-disc space-y-0.5 pl-5 text-sm">{(m.gaps || []).map((s) => <li key={s}>{s}</li>)}</ul></div>
            </div>
            <details className="text-sm"><summary className="cursor-pointer font-medium">Job requirements & description</summary>
              <div className="mt-2 space-y-2">
                {reqs.required_skills?.length ? <p><b>Required skills:</b> {reqs.required_skills.join(", ")}</p> : null}
                {reqs.preferred_skills?.length ? <p><b>Preferred:</b> {reqs.preferred_skills.join(", ")}</p> : null}
                {reqs.min_experience_years ? <p><b>Experience:</b> {reqs.min_experience_years}+ years</p> : null}
                {reqs.education_requirements?.length ? <p><b>Education:</b> {reqs.education_requirements.join("; ")}</p> : null}
                <pre className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded bg-slate-50 p-3 font-sans text-xs">{app.job.description}</pre>
              </div>
            </details>
          </div>
        )}
      </Step>

      {analyzed && (
        <Step n={2} title="Resume recommendations & approval" done={resumeApproved}>
          {resumes.length === 0 ? <Alert kind="warn">Upload a CV in <Link className="underline" href="/resumes">Resume Builder</Link> first.</Alert>
            : <RecommendationsPanel app={app} resumes={resumes} onChange={(a) => { setApp(a); request<ResumeOut[]>("/api/resumes").then(setResumes); }} />}
        </Step>
      )}

      {analyzed && (
        <Step n={3} title="Application questions" done={app.questions.length > 0 && app.questions.every((q) => q.status !== "suggested")}>
          <QuestionsPanel app={app} onChange={setApp} />
        </Step>
      )}

      {analyzed && !submitted && (
        <div ref={automationRef}>
          <Step n={4} id="automation" title="Automated application (you stay in control)" done={app.status === "Ready for Final Approval"}>
            <AutomationPanel appId={app.id} canStart={resumeApproved} onUpdate={load}>
              {(s) => s.checkpoint?.kind === "final_approval" && s.state === "paused" ? (
                <div className="rounded-lg border-2 border-violet-300 p-3">
                  <h3 className="h2 mb-3">Final review & submission</h3>
                  <FinalReview app={app} busy={submitting} onApprove={approveSubmit}
                    onEdit={() => alert("Make your changes in the live browser view below (tap to click, type with the remote-control box), then come back here and approve. The summary updates when you press Continue Application.")} />
                </div>
              ) : null}
            </AutomationPanel>
          </Step>
        </div>
      )}

      {analyzed && !submitted && (
        <section className="card">
          <details><summary className="h2 cursor-pointer">Site doesn&apos;t allow automation? Manual completion workflow</summary>
            <div className="mt-3"><ManualGuide appId={app.id} onSubmitted={setApp} /></div></details>
        </section>
      )}

      <section className="card space-y-4">
        <h2 className="h2">Tracking</h2>
        <div className="grid gap-4 sm:grid-cols-3">
          <label><span className="label">Status</span>
            <select className="input" value={app.status} onChange={(e) => request<AppDetail>(`/api/applications/${id}`, { method: "PATCH", json: { status: e.target.value } }).then(setApp).catch((er) => setError(er.message))}>
              {STATUSES.map((s) => <option key={s} disabled={s === "Submitted" && !submitted}>{s}</option>)}
            </select></label>
          <label><span className="label">Interview status</span>
            <input className="input" defaultValue={app.interview_status} placeholder="e.g. HR round on 12 Nov" onBlur={(e) => request<AppDetail>(`/api/applications/${id}`, { method: "PATCH", json: { interview_status: e.target.value } }).then(setApp)} /></label>
          <label><span className="label">Follow-up date</span>
            <input className="input" type="date" defaultValue={app.follow_up_date ?? ""} onChange={(e) => request<AppDetail>(`/api/applications/${id}`, { method: "PATCH", json: { follow_up_date: e.target.value || null } }).then(setApp)} /></label>
        </div>
        <label className="block"><span className="label">Notes</span>
          <textarea className="input" rows={3} defaultValue={app.notes} onBlur={(e) => request<AppDetail>(`/api/applications/${id}`, { method: "PATCH", json: { notes: e.target.value } }).then(setApp)} /></label>
        <details><summary className="cursor-pointer text-sm font-medium">Timeline ({app.events.length})</summary>
          <ul className="mt-2 space-y-1 text-sm">{[...app.events].reverse().map((e) => <li key={e.id}><span className="text-slate-400">{new Date(e.created_at).toLocaleString()}</span> · {e.message}</li>)}</ul>
        </details>
      </section>
    </div>
  );
}
