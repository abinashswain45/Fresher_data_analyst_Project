"use client";

import { Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { Certification, Education, Experience, Profile, Project } from "@/lib/api";
import { Field } from "./ui";

function Tags({ value, onChange, placeholder }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const items = draft.split(",").map((s) => s.trim()).filter(Boolean);
    if (items.length) onChange(Array.from(new Set([...value, ...items])));
    setDraft("");
  };
  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {value.map((t) => (
          <span key={t} className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700">
            {t}<button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((x) => x !== t))}><X className="h-3 w-3" /></button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input className="input" value={draft} placeholder={placeholder || "Type and press Enter (comma separates)"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        <button type="button" className="btn-secondary" onClick={add}>Add</button>
      </div>
    </div>
  );
}

function Lines({ value, onChange, rows = 4 }: { value: string[]; onChange: (v: string[]) => void; rows?: number }) {
  return (
    <textarea className="input" rows={rows} value={value.join("\n")} placeholder="One item per line"
      onChange={(e) => onChange(e.target.value.split("\n"))}
      onBlur={(e) => onChange(e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))} />
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="card space-y-4"><h2 className="h2">{title}</h2>{children}</section>;
}

export default function ProfileEditor({ value, onChange, showPreferences = true }:
  { value: Profile; onChange: (p: Profile) => void; showPreferences?: boolean }) {
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => onChange({ ...value, [k]: v });
  const text = (k: keyof Profile, label: string, type = "text", hint?: string) => (
    <Field label={label} hint={hint}>
      <input className="input" type={type} value={(value[k] as string) ?? ""} onChange={(e) => set(k, e.target.value as never)} />
    </Field>
  );
  const updateList = <T,>(k: "experience" | "education" | "projects" | "certifications", i: number, patch: Partial<T>) => {
    const list = [...(value[k] as unknown as T[])];
    list[i] = { ...list[i], ...patch };
    set(k, list as never);
  };
  const removeAt = (k: "experience" | "education" | "projects" | "certifications", i: number) =>
    set(k, (value[k] as unknown[]).filter((_, j) => j !== i) as never);

  return (
    <div className="space-y-5">
      <Section title="Personal & contact">
        <div className="grid gap-4 sm:grid-cols-2">
          {text("full_name", "Full name")}{text("email", "Email address", "email")}
          {text("phone", "Mobile number", "tel")}{text("location", "Current location")}
          {text("linkedin_url", "LinkedIn profile", "url")}{text("portfolio_url", "Portfolio / GitHub", "url")}
        </div>
      </Section>

      <Section title="Professional summary">
        <textarea className="input" rows={4} value={value.professional_summary} onChange={(e) => set("professional_summary", e.target.value)} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Total experience (years)">
            <input className="input" type="number" step="0.5" min="0" value={value.total_experience_years ?? ""}
              onChange={(e) => set("total_experience_years", e.target.value === "" ? null : Number(e.target.value))} />
          </Field>
          {text("current_title", "Current job title")}{text("current_company", "Current employer")}
        </div>
      </Section>

      <Section title="Employment history">
        {value.experience.map((e, i) => (
          <div key={i} className="space-y-3 rounded-lg border border-slate-200 p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Job title"><input className="input" value={e.title} onChange={(ev) => updateList<Experience>("experience", i, { title: ev.target.value })} /></Field>
              <Field label="Company"><input className="input" value={e.company} onChange={(ev) => updateList<Experience>("experience", i, { company: ev.target.value })} /></Field>
              <Field label="Start"><input className="input" value={e.start_date} placeholder="Jan 2023" onChange={(ev) => updateList<Experience>("experience", i, { start_date: ev.target.value })} /></Field>
              <Field label="End"><input className="input" value={e.end_date} placeholder="Present" disabled={e.is_current} onChange={(ev) => updateList<Experience>("experience", i, { end_date: ev.target.value })} /></Field>
            </div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" className="h-5 w-5" checked={e.is_current}
              onChange={(ev) => updateList<Experience>("experience", i, { is_current: ev.target.checked })} /> Current role</label>
            <Field label="Responsibilities & achievements"><Lines value={e.responsibilities} onChange={(v) => updateList<Experience>("experience", i, { responsibilities: v })} /></Field>
            <button type="button" className="btn-ghost text-red-600" onClick={() => removeAt("experience", i)}><Trash2 className="h-4 w-4" />Remove</button>
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => set("experience", [...value.experience,
          { company: "", title: "", location: "", start_date: "", end_date: "", is_current: false, responsibilities: [] }])}>
          <Plus className="h-4 w-4" />Add role</button>
      </Section>

      <Section title="Skills">
        <Field label="Technical skills"><Tags value={value.technical_skills} onChange={(v) => set("technical_skills", v)} /></Field>
        <Field label="Professional skills"><Tags value={value.soft_skills} onChange={(v) => set("soft_skills", v)} /></Field>
        <Field label="Languages"><Tags value={value.languages} onChange={(v) => set("languages", v)} /></Field>
      </Section>

      <Section title="Education">
        {value.education.map((e, i) => (
          <div key={i} className="grid gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-2">
            <Field label="Degree"><input className="input" value={e.degree} onChange={(ev) => updateList<Education>("education", i, { degree: ev.target.value })} /></Field>
            <Field label="Field of study"><input className="input" value={e.field_of_study} onChange={(ev) => updateList<Education>("education", i, { field_of_study: ev.target.value })} /></Field>
            <Field label="Institution"><input className="input" value={e.institution} onChange={(ev) => updateList<Education>("education", i, { institution: ev.target.value })} /></Field>
            <Field label="Graduation (year)"><input className="input" value={e.end_date} onChange={(ev) => updateList<Education>("education", i, { end_date: ev.target.value })} /></Field>
            <Field label="Grade / CGPA"><input className="input" value={e.grade} onChange={(ev) => updateList<Education>("education", i, { grade: ev.target.value })} /></Field>
            <div className="flex items-end"><button type="button" className="btn-ghost text-red-600" onClick={() => removeAt("education", i)}><Trash2 className="h-4 w-4" />Remove</button></div>
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => set("education", [...value.education,
          { institution: "", degree: "", field_of_study: "", start_date: "", end_date: "", grade: "" }])}><Plus className="h-4 w-4" />Add education</button>
      </Section>

      <Section title="Projects">
        {value.projects.map((p, i) => (
          <div key={i} className="space-y-3 rounded-lg border border-slate-200 p-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Project name"><input className="input" value={p.name} onChange={(ev) => updateList<Project>("projects", i, { name: ev.target.value })} /></Field>
              <Field label="Link"><input className="input" value={p.link} onChange={(ev) => updateList<Project>("projects", i, { link: ev.target.value })} /></Field>
            </div>
            <Field label="Description"><textarea className="input" rows={3} value={p.description} onChange={(ev) => updateList<Project>("projects", i, { description: ev.target.value })} /></Field>
            <Field label="Technologies"><Tags value={p.technologies} onChange={(v) => updateList<Project>("projects", i, { technologies: v })} /></Field>
            <button type="button" className="btn-ghost text-red-600" onClick={() => removeAt("projects", i)}><Trash2 className="h-4 w-4" />Remove</button>
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => set("projects", [...value.projects, { name: "", description: "", technologies: [], link: "" }])}><Plus className="h-4 w-4" />Add project</button>
      </Section>

      <Section title="Certifications & achievements">
        {value.certifications.map((c, i) => (
          <div key={i} className="grid gap-3 rounded-lg border border-slate-200 p-3 sm:grid-cols-4">
            <div className="sm:col-span-2"><Field label="Certification"><input className="input" value={c.name} onChange={(ev) => updateList<Certification>("certifications", i, { name: ev.target.value })} /></Field></div>
            <Field label="Issuer"><input className="input" value={c.issuer} onChange={(ev) => updateList<Certification>("certifications", i, { issuer: ev.target.value })} /></Field>
            <div className="flex items-end gap-2"><Field label="Date"><input className="input" value={c.date} onChange={(ev) => updateList<Certification>("certifications", i, { date: ev.target.value })} /></Field>
              <button type="button" aria-label="Remove certification" className="btn-ghost text-red-600" onClick={() => removeAt("certifications", i)}><Trash2 className="h-4 w-4" /></button></div>
          </div>
        ))}
        <button type="button" className="btn-secondary" onClick={() => set("certifications", [...value.certifications, { name: "", issuer: "", date: "" }])}><Plus className="h-4 w-4" />Add certification</button>
        <Field label="Achievements"><Lines value={value.achievements} onChange={(v) => set("achievements", v)} /></Field>
      </Section>

      {showPreferences && (
        <Section title="Job preferences & compensation">
          <p className="muted -mt-2">Used only to answer application questions. Compensation is never sent to the AI for resume analysis.</p>
          <div className="grid gap-4 sm:grid-cols-3">
            {text("notice_period", "Notice period", "text", "e.g. Immediate, 30 days")}
            {text("current_ctc", "Current CTC")}{text("expected_ctc", "Expected CTC")}
          </div>
          <Field label="Preferred locations"><Tags value={value.preferred_locations} onChange={(v) => set("preferred_locations", v)} /></Field>
          <Field label="Preferred job roles"><Tags value={value.preferred_roles} onChange={(v) => set("preferred_roles", v)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            {text("work_authorization", "Work authorisation", "text", "e.g. Indian citizen. Legal declarations on portals are always left to you.")}
            <Field label="Willing to relocate?">
              <select className="input" value={value.willing_to_relocate === null ? "" : value.willing_to_relocate ? "yes" : "no"}
                onChange={(e) => set("willing_to_relocate", e.target.value === "" ? null : e.target.value === "yes")}>
                <option value="">Not specified</option><option value="yes">Yes</option><option value="no">No</option>
              </select>
            </Field>
          </div>
        </Section>
      )}
    </div>
  );
}
