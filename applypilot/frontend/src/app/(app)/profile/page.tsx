"use client";

import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { request, type Profile, type ProfileOut } from "@/lib/api";
import ProfileEditor from "@/components/ProfileEditor";
import { Alert, Loading, PageHeader, Spinner } from "@/components/ui";

export default function ProfilePage() {
  const [out, setOut] = useState<ProfileOut | null>(null);
  const [data, setData] = useState<Profile | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "success" | "error"; text: string } | null>(null);

  useEffect(() => { request<ProfileOut>("/api/profile").then((p) => { setOut(p); setData(p.data); }).catch((e) => setMsg({ kind: "error", text: e.message })); }, []);

  async function save() {
    if (!data) return;
    setBusy(true); setMsg(null);
    try {
      const p = await request<ProfileOut>("/api/profile", { method: "PUT", json: data });
      setOut(p); setData(p.data); setMsg({ kind: "success", text: "Profile saved. It will be reused for every application." });
    } catch (e) { setMsg({ kind: "error", text: (e as Error).message }); } finally { setBusy(false); }
  }

  if (!data || !out) return msg ? <Alert kind="error">{msg.text}</Alert> : <Loading />;

  const saveBtn = <button className="btn-primary" onClick={save} disabled={busy}>{busy ? <Spinner /> : <Save className="h-4 w-4" />}Save profile</button>;
  return (
    <div className="space-y-5 pb-20">
      <PageHeader title="My Profile" subtitle="Enter this once. ApplyPilot reuses it for every application." actions={saveBtn} />
      <div className="card">
        <div className="mb-2 flex items-center justify-between text-sm"><span className="font-medium">Profile completeness</span><span className="font-bold">{out.completeness}%</span></div>
        <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full bg-brand-600" style={{ width: `${out.completeness}%` }} /></div>
        {out.missing_fields.length > 0 && <p className="muted mt-2">Missing: {out.missing_fields.join(", ")}</p>}
      </div>
      {msg && <Alert kind={msg.kind}>{msg.text}</Alert>}
      <ProfileEditor value={data} onChange={setData} />
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 p-3 backdrop-blur lg:left-64">
        <div className="mx-auto flex max-w-6xl justify-end">{saveBtn}</div>
      </div>
    </div>
  );
}
