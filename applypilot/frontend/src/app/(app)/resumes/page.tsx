"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileUp, Pencil, Star, Trash2, UserCheck } from "lucide-react";
import { download, request, type ProfileOut, type ResumeDetail, type ResumeOut } from "@/lib/api";
import ProfileEditor from "@/components/ProfileEditor";
import { Alert, Empty, Loading, PageHeader, Spinner, fmtDate } from "@/components/ui";

export default function ResumesPage() {
  const [resumes, setResumes] = useState<ResumeOut[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "success" | "error" | "info"; text: string } | null>(null);
  const [label, setLabel] = useState("");
  const [category, setCategory] = useState("General");
  const [editing, setEditing] = useState<ResumeDetail | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => request<ResumeOut[]>("/api/resumes").then(setResumes).catch((e) => setMsg({ kind: "error", text: e.message })), []);
  useEffect(() => {
    load();
    if (typeof window !== "undefined" && window.location.search.includes("welcome")) setMsg({ kind: "info", text: "Welcome! Start by uploading your latest CV. ApplyPilot extracts everything into your reusable profile." });
  }, [load]);

  async function upload(file: File) {
    setBusy(true); setMsg(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("label", label);
    fd.append("category", category);
    fd.append("update_profile", "true");
    try {
      await request<ResumeDetail>("/api/resumes", { method: "POST", body: fd });
      setMsg({ kind: "success", text: "CV processed. Empty profile fields were filled from it. Review My Profile to confirm the details." });
      setLabel(""); load();
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  }

  async function act(fn: () => Promise<unknown>, ok: string) {
    try { await fn(); setMsg({ kind: "success", text: ok }); load(); } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); }
  }

  async function saveEdit() {
    if (!editing) return;
    await act(() => request(`/api/resumes/${editing.id}`, { method: "PATCH", json: { label: editing.label, category: editing.category, content: editing.content } }), "Resume version saved.");
    setEditing(null);
  }

  if (editing) {
    return (
      <div className="space-y-5">
        <PageHeader title={`Edit: ${editing.label}`} subtitle="Edit this resume version's content. Only include facts that are true."
          actions={<><button className="btn-secondary" onClick={() => setEditing(null)}>Cancel</button><button className="btn-primary" onClick={saveEdit}>Save version</button></>} />
        <div className="card grid gap-4 sm:grid-cols-2">
          <label><span className="label">Version name</span><input className="input" value={editing.label} onChange={(e) => setEditing({ ...editing, label: e.target.value })} /></label>
          <label><span className="label">Job category</span><input className="input" value={editing.category} onChange={(e) => setEditing({ ...editing, category: e.target.value })} /></label>
        </div>
        <ProfileEditor value={editing.content} onChange={(c) => setEditing({ ...editing, content: c })} showPreferences={false} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Resume Builder" subtitle="Upload your CV (PDF or DOCX). Keep multiple versions for different job categories." />
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <div className="card space-y-4">
        <h2 className="h2">Upload latest CV</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <label><span className="label">Version name (optional)</span><input className="input" value={label} placeholder="e.g. Data Analyst CV" onChange={(e) => setLabel(e.target.value)} /></label>
          <label><span className="label">Job category</span><input className="input" value={category} onChange={(e) => setCategory(e.target.value)} /></label>
        </div>
        <input ref={fileRef} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          className="hidden" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        <button className="btn-primary w-full sm:w-auto" disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? <><Spinner />Reading your CV…</> : <><FileUp className="h-4 w-4" />Choose PDF or DOCX</>}</button>
        <p className="muted">Files are encrypted at rest and never shared. Max 10 MB. Scanned image-only PDFs can&apos;t be read.</p>
      </div>
      <div>
        <h2 className="h2 mb-3">Resume versions</h2>
        {!resumes ? <Loading /> : resumes.length === 0 ? <Empty title="No resumes yet">Upload your CV to get started.</Empty> : (
          <div className="grid gap-3 md:grid-cols-2">
            {resumes.map((r) => (
              <div key={r.id} className="card space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{r.label} {r.is_default && <Star className="inline h-4 w-4 fill-amber-400 text-amber-400" />}</p>
                    <p className="muted">{r.category} · {r.kind === "tailored" ? "AI-tailored (approved changes)" : "Uploaded"} · {fmtDate(r.created_at)}</p>
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button className="btn-secondary" onClick={() => download(`/api/resumes/${r.id}/download?format=pdf`, "resume.pdf")}><Download className="h-4 w-4" />PDF</button>
                  <button className="btn-secondary" onClick={() => download(`/api/resumes/${r.id}/download?format=docx`, "resume.docx")}><Download className="h-4 w-4" />DOCX</button>
                  <button className="btn-ghost" onClick={() => request<ResumeDetail>(`/api/resumes/${r.id}`).then(setEditing)}><Pencil className="h-4 w-4" />Edit</button>
                  {!r.is_default && <button className="btn-ghost" onClick={() => act(() => request(`/api/resumes/${r.id}`, { method: "PATCH", json: { is_default: true } }), "Default resume updated.")}><Star className="h-4 w-4" />Default</button>}
                  {r.kind === "uploaded" && <button className="btn-ghost" onClick={() => act(() => request<ProfileOut>(`/api/profile/import/${r.id}`, { method: "POST" }), "Empty profile fields filled from this CV.")}><UserCheck className="h-4 w-4" />Fill profile</button>}
                  <button className="btn-ghost text-red-600" onClick={() => confirm(`Delete "${r.label}"?`) && act(() => request(`/api/resumes/${r.id}`, { method: "DELETE" }), "Resume deleted.")}><Trash2 className="h-4 w-4" /></button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
