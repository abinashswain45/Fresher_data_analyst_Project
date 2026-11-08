"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Rocket } from "lucide-react";
import { auth, request, type User } from "@/lib/api";
import { Alert, Spinner } from "./ui";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await request<{ access_token: string; user: User }>(`/api/auth/${mode}`, {
        method: "POST", json: mode === "login" ? { email, password } : { email, password, full_name: name },
      });
      auth.set(res.access_token);
      router.replace(mode === "register" ? "/resumes?welcome=1" : "/");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50 to-white px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center justify-center gap-2 text-brand-700">
          <Rocket className="h-7 w-7" /><span className="text-2xl font-bold">ApplyPilot AI</span>
        </div>
        <form onSubmit={submit} className="card space-y-4">
          <h1 className="h2">{mode === "login" ? "Sign in" : "Create your account"}</h1>
          {error && <Alert kind="error">{error}</Alert>}
          {mode === "register" && (
            <label className="block"><span className="label">Full name</span>
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></label>
          )}
          <label className="block"><span className="label">Email</span>
            <input className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label>
          <label className="block"><span className="label">Password</span>
            <input className="input" type="password" required minLength={8} value={password}
              onChange={(e) => setPassword(e.target.value)} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            {mode === "register" && <span className="mt-1 block text-xs text-slate-500">At least 8 characters.</span>}
          </label>
          <button className="btn-primary w-full" disabled={busy}>{busy && <Spinner />}{mode === "login" ? "Sign in" : "Create account"}</button>
          <p className="text-center text-sm text-slate-600">
            {mode === "login" ? <>New here? <Link className="font-semibold text-brand-600" href="/register">Create an account</Link></>
              : <>Already registered? <Link className="font-semibold text-brand-600" href="/login">Sign in</Link></>}
          </p>
        </form>
        <p className="mt-4 text-center text-xs text-slate-500">Your data is encrypted. You stay in control of every verification and every submission.</p>
      </div>
    </main>
  );
}
