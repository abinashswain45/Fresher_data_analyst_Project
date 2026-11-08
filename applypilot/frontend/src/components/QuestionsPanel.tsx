"use client";

import { useState } from "react";
import { Check, CheckCheck, Plus, RefreshCw, Trash2 } from "lucide-react";
import { request, type AppDetail, type Question } from "@/lib/api";
import { Alert, Spinner } from "./ui";

function QuestionCard({ appId, q, onSaved, onDeleted }: { appId: number; q: Question; onSaved: (q: Question) => void; onDeleted: () => void }) {
  const [answer, setAnswer] = useState(q.answer);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function call(key: string, fn: () => Promise<Question>) {
    setBusy(key); setError("");
    try { const nq = await fn(); setAnswer(nq.answer); onSaved(nq); } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }
  const regen = (style: string) => call(style, () => request<Question>(`/api/applications/${appId}/questions/${q.id}/regenerate`, { method: "POST", json: { style } }));
  const accept = () => call("accept", () => request<Question>(`/api/applications/${appId}/questions/${q.id}`, { method: "PUT", json: { answer, status: "accepted" } }));

  return (
    <div className={`rounded-lg border p-3 ${q.status !== "suggested" ? "border-emerald-300 bg-emerald-50/40" : q.needs_user_input ? "border-amber-300" : "border-slate-200"}`}>
      <div className="mb-2 flex items-start justify-between gap-2">
        <p className="font-medium">{q.question}{q.required && <span className="text-red-600"> *</span>}</p>
        <span className="shrink-0 text-xs font-semibold uppercase text-slate-500">{q.status === "filled" ? "filled on site" : q.status}</span>
      </div>
      {q.needs_user_input && q.status === "suggested" && <p className="mb-2 text-xs text-amber-700">Your profile may not fully answer this. Personalise it before accepting.</p>}
      {q.options.length > 0 ? (
        <select className="input" value={answer} onChange={(e) => setAnswer(e.target.value)}>
          <option value="">Choose…</option>{q.options.map((o) => <option key={o}>{o}</option>)}
        </select>
      ) : (
        <textarea className="input text-sm" rows={Math.min(8, Math.max(3, Math.ceil(answer.length / 90)))} value={answer} onChange={(e) => setAnswer(e.target.value)} />
      )}
      {error && <div className="mt-2"><Alert kind="error">{error}</Alert></div>}
      <div className="mt-2 flex flex-wrap gap-2">
        <button className="btn-success" disabled={!!busy || !answer.trim() || q.status === "filled"} onClick={accept}>{busy === "accept" ? <Spinner /> : <Check className="h-4 w-4" />}{answer !== q.answer ? "Save & accept" : "Accept"}</button>
        {q.options.length === 0 && <>
          <button className="btn-ghost" disabled={!!busy} onClick={() => regen("default")}>{busy === "default" ? <Spinner /> : <RefreshCw className="h-4 w-4" />}Regenerate</button>
          <button className="btn-ghost" disabled={!!busy} onClick={() => regen("shorter")}>{busy === "shorter" && <Spinner />}Shorter</button>
          <button className="btn-ghost" disabled={!!busy} onClick={() => regen("more_professional")}>{busy === "more_professional" && <Spinner />}More professional</button>
        </>}
        <button className="btn-ghost text-red-600" aria-label="Delete question" onClick={() => request(`/api/applications/${appId}/questions/${q.id}`, { method: "DELETE" }).then(onDeleted)}><Trash2 className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

export default function QuestionsPanel({ app, onChange }: { app: AppDetail; onChange: (a: AppDetail) => void }) {
  const [newQ, setNewQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const replace = (q: Question) => onChange({ ...app, questions: app.questions.map((x) => (x.id === q.id ? q : x)) });

  async function add() {
    setBusy(true); setError("");
    try {
      const q = await request<Question>(`/api/applications/${app.id}/questions`, { method: "POST", json: { question: newQ } });
      onChange({ ...app, questions: [...app.questions, q] }); setNewQ("");
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <div className="space-y-3">
      <p className="muted">Answers are drafted from your saved profile and the job description, with no invented claims. Questions found on the application form appear here automatically. Accepted answers are filled in for you.</p>
      {app.questions.some((q) => q.status === "suggested" && !q.needs_user_input && q.answer) && (
        <button className="btn-secondary" onClick={() => request<Question[]>(`/api/applications/${app.id}/questions/accept-all`, { method: "POST" }).then((qs) => onChange({ ...app, questions: qs }))}>
          <CheckCheck className="h-4 w-4" />Accept all ready answers</button>
      )}
      {app.questions.map((q) => <QuestionCard key={q.id + q.status + q.answer.length} appId={app.id} q={q} onSaved={replace}
        onDeleted={() => onChange({ ...app, questions: app.questions.filter((x) => x.id !== q.id) })} />)}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input className="input" placeholder="Add a question, e.g. Why do you want to join our company?" value={newQ} onChange={(e) => setNewQ(e.target.value)} />
        <button className="btn-primary shrink-0" disabled={busy || newQ.trim().length < 3} onClick={add}>{busy ? <Spinner /> : <Plus className="h-4 w-4" />}Draft answer</button>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
    </div>
  );
}
