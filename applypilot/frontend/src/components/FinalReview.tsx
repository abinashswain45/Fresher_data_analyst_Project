"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Pencil, Send } from "lucide-react";
import { request, type AppDetail, type Profile, type ProfileOut } from "@/lib/api";
import { Alert, Spinner } from "./ui";

export default function FinalReview({ app, onApprove, onEdit, busy }:
  { app: AppDetail; onApprove: () => void; onEdit: () => void; busy: boolean }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  useEffect(() => { request<ProfileOut>("/api/profile").then((p) => setProfile(p.data)).catch(() => {}); }, []);
  const r = app.review || {};
  const missing = r.missing_fields || [];
  const warnings = r.validation_warnings || [];
  const left = r.left_for_user || [];

  const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
    <div className="grid grid-cols-1 gap-1 py-2 sm:grid-cols-3"><dt className="text-sm text-slate-500">{k}</dt><dd className="text-sm sm:col-span-2 break-words">{v || "—"}</dd></div>
  );

  return (
    <div className="space-y-4">
      <Alert kind="info">Nothing has been submitted yet. Check every detail below. ApplyPilot clicks the final submit button only after you click <b>Approve & Submit</b>.</Alert>
      <dl className="divide-y divide-slate-100 rounded-lg border border-slate-200 px-3">
        <Row k="Company" v={app.job.company} />
        <Row k="Job title" v={app.job.title} />
        <Row k="Portal" v={`${r.platform || app.job.platform} · ${r.pages ?? "?"} page(s)`} />
        <Row k="Candidate" v={profile && `${profile.full_name} · ${profile.email} · ${profile.phone}`} />
        <Row k="Resume uploaded" v={r.resume_uploaded || app.resume_label} />
        <Row k="Education" v={profile?.education.map((e) => `${e.degree}${e.field_of_study ? ` in ${e.field_of_study}` : ""}, ${e.institution} ${e.end_date}`).join("; ")} />
        <Row k="Employment" v={profile?.experience.map((e) => `${e.title} at ${e.company}${e.is_current ? " (current)" : ""}`).join("; ")} />
      </dl>

      <div>
        <h3 className="mb-2 font-semibold">Fields filled on the website ({r.filled_fields?.length || 0})</h3>
        <div className="max-h-80 overflow-y-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {(r.filled_fields || []).map((f, i) => (
                <tr key={i}><td className="w-2/5 p-2 align-top text-slate-500">{f.label}<span className="block text-[11px] text-slate-400">page {f.page} · {f.source}</span></td>
                  <td className="p-2 align-top whitespace-pre-wrap break-words">{f.value}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {app.questions.length > 0 && (
        <div>
          <h3 className="mb-2 font-semibold">Application answers</h3>
          <ul className="space-y-2">{app.questions.map((q) => (
            <li key={q.id} className="rounded-lg border border-slate-200 p-2 text-sm"><p className="font-medium">{q.question}</p><p className="whitespace-pre-wrap text-slate-700">{q.answer || <i>Not answered</i>}</p><p className="text-[11px] uppercase text-slate-400">{q.status}</p></li>
          ))}</ul>
        </div>
      )}

      {left.length > 0 && (
        <div>
          <h3 className="mb-2 font-semibold">Voluntary disclosures & declarations (your responsibility)</h3>
          <ul className="space-y-1 text-sm">{left.map((l, i) => (
            <li key={i} className="flex flex-wrap justify-between gap-2 rounded bg-slate-50 px-2 py-1"><span>{l.label}{l.required && <b className="text-red-600"> *</b>}</span><span className="text-slate-500">{l.completed ? "Completed by you" : l.reason}</span></li>
          ))}</ul>
        </div>
      )}

      {(missing.length > 0 || warnings.length > 0) && (
        <Alert kind="warn">
          <p className="flex items-center gap-1 font-semibold"><AlertTriangle className="h-4 w-4" />Please check before submitting</p>
          {missing.length > 0 && <p className="mt-1">Required fields still empty: {missing.join(", ")}</p>}
          {warnings.length > 0 && <p className="mt-1">Site warnings: {warnings.join(" · ")}</p>}
        </Alert>
      )}

      <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 h-5 w-5" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
        I have reviewed this application and confirm the information is accurate and that I want it submitted.</label>
      <div className="flex flex-col gap-2 sm:flex-row">
        <button className="btn-secondary" onClick={onEdit}><Pencil className="h-4 w-4" />Edit Application</button>
        <button className="btn-success" disabled={!confirmed || busy} onClick={onApprove}>{busy ? <Spinner /> : <Send className="h-4 w-4" />}Approve & Submit</button>
      </div>
    </div>
  );
}
