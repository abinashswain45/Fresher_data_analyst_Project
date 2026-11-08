"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Download, ShieldCheck, Trash2 } from "lucide-react";
import { auth, download, request, type Meta, type User } from "@/lib/api";
import { Alert, Loading, PageHeader, Spinner } from "@/components/ui";

export default function SettingsPage() {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [pw, setPw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { request<User>("/api/auth/me").then(setUser); request<Meta>("/api/meta").then(setMeta); }, []);
  if (!user || !meta) return <Loading />;

  async function del() {
    if (!confirm("Permanently delete your account, profile, resumes and application history? This cannot be undone.")) return;
    setBusy(true); setError("");
    try { await request("/api/account/delete", { method: "POST", json: { password: pw } }); auth.clear(); router.replace("/register"); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-5">
      <PageHeader title="Settings" />
      <section className="card space-y-2"><h2 className="h2">Account</h2><p className="text-sm">{user.full_name} · {user.email}</p></section>
      <section className="card space-y-2">
        <h2 className="h2">AI & automation</h2>
        <p className="text-sm">AI engine: {meta.ai_enabled ? <b>Claude ({meta.ai_model})</b> : <b>Heuristic mode (no API key configured)</b>}</p>
        <p className="text-sm">Browser mode: {meta.automation_headless ? "Cloud (remote view: control it from any device)" : "Local visible browser window"}</p>
      </section>
      <section className="card space-y-2">
        <h2 className="h2 flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-emerald-600" />Privacy & security</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-slate-700">
          <li>Your profile, resume content and files are encrypted at rest. All traffic should be served over HTTPS.</li>
          <li>ApplyPilot never asks for, stores or logs your recruitment-portal passwords or OTPs. You enter them yourself.</li>
          <li>Contact details and compensation are stripped from AI prompts that don&apos;t need them.</li>
          <li>CAPTCHAs, OTPs, legal declarations and voluntary disclosures are always left to you.</li>
          <li>The final submit button is only clicked after your explicit approval.</li>
        </ul>
      </section>
      <section className="card space-y-3">
        <h2 className="h2">Your data</h2>
        <button className="btn-secondary" onClick={() => download("/api/account/export", "applypilot-export.json")}><Download className="h-4 w-4" />Export all my data (JSON)</button>
        <div className="space-y-2 rounded-lg border border-red-200 p-3">
          <p className="font-semibold text-red-700">Delete account</p>
          <p className="muted">Deletes your account, profile, all resume files and the application history.</p>
          <input className="input" type="password" placeholder="Confirm with your password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" />
          {error && <Alert kind="error">{error}</Alert>}
          <button className="btn-danger" disabled={!pw || busy} onClick={del}>{busy ? <Spinner /> : <Trash2 className="h-4 w-4" />}Delete everything</button>
        </div>
      </section>
    </div>
  );
}
