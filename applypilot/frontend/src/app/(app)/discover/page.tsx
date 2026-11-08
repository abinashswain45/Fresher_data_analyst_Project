"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { request } from "@/lib/api";
import { Alert, Loading, PageHeader } from "@/components/ui";

interface Search { role: string; location: string; boards: { name: string; url: string }[]; companies: { company: string; url: string }[] }

export default function DiscoverPage() {
  const [role, setRole] = useState("");
  const [loc, setLoc] = useState("");
  const [data, setData] = useState<Search[] | null>(null);
  const [error, setError] = useState("");
  const load = (r = role, l = loc) => request<{ searches: Search[] }>(`/api/discovery?role=${encodeURIComponent(r)}&location=${encodeURIComponent(l)}`).then((d) => setData(d.searches)).catch((e) => setError(e.message));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load("", ""); }, []);
  return (
    <div className="space-y-5">
      <PageHeader title="Job Discovery" subtitle="Search official career portals and job boards using your preferences, then paste a posting URL into New Application." />
      <form className="card grid gap-3 sm:grid-cols-[1fr_1fr_auto]" onSubmit={(e) => { e.preventDefault(); load(); }}>
        <input className="input" placeholder="Role (defaults to your preferred roles)" value={role} onChange={(e) => setRole(e.target.value)} />
        <input className="input" placeholder="Location (defaults to your preferences)" value={loc} onChange={(e) => setLoc(e.target.value)} />
        <button className="btn-primary">Search</button>
      </form>
      {error && <Alert kind="error">{error}</Alert>}
      {!data ? <Loading /> : data.map((s) => (
        <section key={s.role + s.location} className="card space-y-3">
          <h2 className="h2">{s.role}{s.location && ` · ${s.location}`}</h2>
          <div><p className="mb-2 text-sm font-semibold text-slate-600">Job boards</p>
            <div className="flex flex-wrap gap-2">{s.boards.map((b) => <a key={b.name} href={b.url} target="_blank" rel="noopener noreferrer" className="btn-secondary">{b.name}<ExternalLink className="h-3 w-3" /></a>)}</div></div>
          <div><p className="mb-2 text-sm font-semibold text-slate-600">Official company career portals</p>
            <div className="flex flex-wrap gap-2">{s.companies.map((c) => <a key={c.company} href={c.url} target="_blank" rel="noopener noreferrer" className="btn-ghost border border-slate-200">{c.company}<ExternalLink className="h-3 w-3" /></a>)}</div></div>
        </section>
      ))}
    </div>
  );
}
