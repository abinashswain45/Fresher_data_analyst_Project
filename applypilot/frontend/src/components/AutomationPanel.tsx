"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, CornerDownLeft, Delete, MonitorPlay, Play, ShieldAlert, Square, Undo2 } from "lucide-react";
import { API_URL, auth, request, type AutomationState } from "@/lib/api";
import { Alert, Spinner } from "./ui";

export default function AutomationPanel({ appId, canStart, onUpdate, children }:
  { appId: number; canStart: boolean; onUpdate: () => void; children?: (s: AutomationState) => React.ReactNode }) {
  const [state, setState] = useState<AutomationState | null>(null);
  const [shot, setShot] = useState<string>("");
  const [typed, setTyped] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const lastStatus = useRef<string>("");
  const active = state && !["none", "closed"].includes(state.state);

  const poll = useCallback(async () => {
    try {
      const s = await request<AutomationState>(`/api/automation/${appId}/state`);
      setState(s);
      const sig = `${s.state}:${s.checkpoint?.kind}`;
      if (sig !== lastStatus.current) { lastStatus.current = sig; onUpdate(); }
    } catch { /* transient */ }
  }, [appId, onUpdate]);

  const refreshShot = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/automation/${appId}/screenshot`, { headers: { Authorization: `Bearer ${auth.token}` }, cache: "no-store" });
      if (!res.ok) return;
      const url = URL.createObjectURL(await res.blob());
      setShot((old) => { if (old) URL.revokeObjectURL(old); return url; });
    } catch { /* ignore */ }
  }, [appId]);

  useEffect(() => { poll(); }, [poll]);
  useEffect(() => {
    if (!active) return;
    const t1 = setInterval(poll, 1500);
    const t2 = setInterval(refreshShot, 2000);
    refreshShot();
    return () => { clearInterval(t1); clearInterval(t2); };
  }, [active, poll, refreshShot]);

  async function call(key: string, path: string, json?: unknown) {
    setBusy(key); setError("");
    try {
      const s = await request<AutomationState>(`/api/automation/${appId}/${path}`, { method: "POST", json: json ?? {} });
      if (s && "state" in s) setState(s);
      setTimeout(poll, 600); setTimeout(refreshShot, 700);
    } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }

  // Inputs are queued so taps/keys/text reach the browser strictly in the order the user made them.
  const queue = useRef<Promise<void>>(Promise.resolve());
  function send(json: Record<string, unknown>) {
    queue.current = queue.current.then(async () => {
      try {
        await request(`/api/automation/${appId}/input`, { method: "POST", json });
        setTimeout(refreshShot, 350);
      } catch (e) { setError((e as Error).message); }
    });
    return queue.current;
  }

  function onImageClick(e: React.MouseEvent<HTMLImageElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    send({ action: "click", x: (e.clientX - rect.left) / rect.width, y: (e.clientY - rect.top) / rect.height });
  }

  const cp = state?.checkpoint;
  const paused = state?.state === "paused" || state?.state === "error";

  return (
    <div className="space-y-3">
      {error && <Alert kind="error">{error}</Alert>}
      {!active ? (
        <div className="space-y-3">
          <p className="muted">ApplyPilot opens the official application website in a secure browser, fills in your verified details, uploads your approved resume and drafts answers. It pauses whenever you need to act (account, OTP, CAPTCHA, legal items) and never submits without your final approval.</p>
          <button className="btn-primary" disabled={!canStart || !!busy} onClick={() => call("start", "start")}>
            {busy === "start" ? <Spinner /> : <Play className="h-4 w-4" />}Start automated application</button>
          {!canStart && <p className="text-sm text-amber-700">Approve a resume version first.</p>}
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2">
              {state?.state === "running" || state?.state === "starting" ? <Spinner /> : <MonitorPlay className="h-4 w-4" />}
              <b className="capitalize">{state?.state}</b> · {state?.platform} · page {state?.page_number ?? 0} · {state?.filled_count ?? 0} fields filled
            </span>
            <button className="btn-ghost text-red-600" onClick={() => confirm("Stop and close the browser session? Nothing will be submitted.") && call("stop", "stop")}>
              <Square className="h-4 w-4" />Stop session</button>
          </div>

          {cp && paused && (
            <div className={`rounded-lg border-2 p-4 ${cp.human_verification ? "border-orange-400 bg-orange-50" : cp.kind === "final_approval" ? "border-violet-400 bg-violet-50" : "border-sky-300 bg-sky-50"}`}>
              <p className="flex items-center gap-2 font-semibold">{cp.human_verification && <ShieldAlert className="h-5 w-5 text-orange-600" />}{cp.title}</p>
              <p className="mt-1 text-sm">{cp.message}</p>
              {cp.details?.length > 0 && <ul className="mt-2 list-disc pl-5 text-sm">{cp.details.map((d) => <li key={d}>{d}</li>)}</ul>}
              {cp.kind !== "final_approval" && cp.kind !== "done" && (
                <button className="btn-primary mt-3" disabled={!!busy} onClick={() => call("continue", "continue")}>
                  {busy === "continue" ? <Spinner /> : <Play className="h-4 w-4" />}Continue Application</button>
              )}
            </div>
          )}
          {state && children?.(state)}

          <div className="overflow-hidden rounded-lg border border-slate-300 bg-slate-900">
            {shot ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={shot} alt="Live view of the application website. Tap to click." onClick={onImageClick}
                className={`w-full select-none ${paused ? "cursor-pointer" : "cursor-wait"}`} />
            ) : <div className="flex h-48 items-center justify-center text-slate-400"><Spinner />&nbsp;Opening browser…</div>}
          </div>
          {state?.headless === false && <p className="muted">A browser window is also open on the server machine. You can complete steps there directly.</p>}
          {paused && (
            <div className="space-y-2 rounded-lg bg-slate-50 p-3">
              <p className="text-sm font-medium">Remote control (works on phone & laptop): tap the view to click, then type below.</p>
              <div className="flex gap-2">
                <input className="input" type="password" autoComplete="off" placeholder="Text to type (OTP, password…). Never stored or logged."
                  value={typed} onChange={(e) => setTyped(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && typed) { e.preventDefault(); send({ action: "type", text: typed }); setTyped(""); } }} />
                <button className="btn-secondary shrink-0" disabled={!typed} onClick={() => { send({ action: "type", text: typed }); setTyped(""); }}>Type</button>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-ghost" onClick={() => send({ action: "key", key: "Enter" })}><CornerDownLeft className="h-4 w-4" />Enter</button>
                <button className="btn-ghost" onClick={() => send({ action: "key", key: "Tab" })}>Tab</button>
                <button className="btn-ghost" onClick={() => send({ action: "key", key: "Backspace" })}><Delete className="h-4 w-4" />Backspace</button>
                <button className="btn-ghost" onClick={() => send({ action: "scroll", dy: -500 })}><ArrowUp className="h-4 w-4" />Scroll</button>
                <button className="btn-ghost" onClick={() => send({ action: "scroll", dy: 500 })}><ArrowDown className="h-4 w-4" />Scroll</button>
                <button className="btn-ghost" onClick={() => send({ action: "back" })}><Undo2 className="h-4 w-4" />Back</button>
              </div>
            </div>
          )}
          {state?.log && state.log.length > 0 && (
            <details className="rounded-lg border border-slate-200 p-3 text-sm">
              <summary className="cursor-pointer font-medium">Activity log</summary>
              <ul className="mt-2 max-h-60 space-y-1 overflow-y-auto text-xs text-slate-600">
                {[...state.log].reverse().map((l, i) => <li key={i}><span className="text-slate-400">{new Date(l.ts).toLocaleTimeString()}</span> {l.message}</li>)}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
