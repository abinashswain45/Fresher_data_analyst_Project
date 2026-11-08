// Typed client for the ApplyPilot FastAPI backend.

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const TOKEN_KEY = "applypilot_token";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export const auth = {
  get token(): string | null {
    if (typeof window === "undefined") return null;
    try { return window.localStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  set(token: string) { try { window.localStorage.setItem(TOKEN_KEY, token); } catch { /* storage unavailable */ } },
  clear() { try { window.localStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ } },
};

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || fallback;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: string }).message);
  return fallback;
}

export async function request<T>(path: string, opts: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(opts.headers);
  const token = auth.token;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = opts.body;
  if (opts.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.json);
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...opts, headers, body });
  } catch {
    throw new ApiError(0, "Cannot reach the ApplyPilot server. Check your connection and try again.");
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/")) {
    auth.clear();
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail: unknown = undefined;
    try { detail = (await res.json()).detail; } catch { /* not json */ }
    throw new ApiError(res.status, messageFrom(detail, `Request failed (${res.status})`), detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  return (ct.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

export async function download(path: string, fallbackName: string) {
  const res = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${auth.token}` } });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") || "";
  const match = /filename\*=UTF-8''([^;]+)|filename=([^;]+)/.exec(cd);
  const name = match ? decodeURIComponent(match[1] || match[2]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export async function blobUrl(path: string): Promise<string> {
  const res = await fetch(`${API_URL}${path}`, { headers: { Authorization: `Bearer ${auth.token}` }, cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, "Not available");
  return URL.createObjectURL(await res.blob());
}

// ---------------------------------------------------------------- types
export interface User { id: number; email: string; full_name: string; created_at: string }
export interface Experience { company: string; title: string; location: string; start_date: string; end_date: string; is_current: boolean; responsibilities: string[] }
export interface Education { institution: string; degree: string; field_of_study: string; start_date: string; end_date: string; grade: string }
export interface Project { name: string; description: string; technologies: string[]; link: string }
export interface Certification { name: string; issuer: string; date: string }
export interface Profile {
  full_name: string; email: string; phone: string; location: string; linkedin_url: string; portfolio_url: string;
  professional_summary: string; total_experience_years: number | null; current_company: string; current_title: string;
  experience: Experience[]; education: Education[]; technical_skills: string[]; soft_skills: string[];
  certifications: Certification[]; projects: Project[]; achievements: string[]; languages: string[];
  notice_period: string; current_ctc: string; expected_ctc: string; preferred_locations: string[];
  preferred_roles: string[]; work_authorization: string; willing_to_relocate: boolean | null;
}
export interface ProfileOut { data: Profile; completeness: number; missing_fields: string[]; updated_at: string | null }
export interface ResumeOut { id: number; label: string; category: string; kind: string; parent_id: number | null; job_id: number | null; original_filename: string; is_default: boolean; created_at: string }
export interface ResumeDetail extends ResumeOut { content: Profile; text_preview: string }
export interface Recommendation { id: string; section: string; target_index: number | null; original: string; suggested: string; reason: string; keywords_added: string[]; evidence: string; status: string; flagged: boolean }
export interface Question { id: number; question: string; answer: string; status: string; field_type: string; options: string[]; required: boolean; needs_user_input: boolean }
export interface AppEvent { id: number; kind: string; message: string; created_at: string }
export interface Job { id: number; url: string; apply_url: string; platform: string; company: string; title: string; location: string; description: string; requirements: Record<string, unknown>; fetch_method: string; fetched_at: string }
export interface AppSummary {
  id: number; job_id: number; company: string; title: string; job_url: string; platform: string; status: string;
  match_score: number | null; resume_id: number | null; resume_label: string; reference_id: string;
  interview_status: string; follow_up_date: string | null; notes: string; submitted_at: string | null;
  created_at: string; updated_at: string;
}
export interface Match {
  score?: number; eligible?: boolean; summary?: string; strengths?: string[]; gaps?: string[]; missing_keywords?: string[];
  ineligibility_reasons?: string[]; mode?: string; recommended_resume_id?: number | null; resume_reason?: string;
  error?: string; needs_manual_description?: boolean;
}
export interface Review {
  generated_at?: string; platform?: string; final_url?: string; submit_button?: string; resume_uploaded?: string;
  filled_fields?: { label: string; value: string; category: string; page: number; source: string }[];
  left_for_user?: { label: string; reason: string; required: boolean; completed?: boolean }[];
  missing_fields?: string[]; validation_warnings?: string[]; pages?: number;
}
export interface AppDetail extends AppSummary {
  job: Job; match: Match; recommendations: Recommendation[]; review: Review; confirmation_text: string;
  confirmation_url: string; has_confirmation_screenshot: boolean; questions: Question[]; events: AppEvent[];
}
export interface Checkpoint { kind: string; title: string; message: string; details: string[]; human_verification: boolean }
export interface AutomationState {
  application_id: number; state: string; headless?: boolean; checkpoint?: Checkpoint | null; page_number?: number;
  url?: string; platform?: string; filled_count?: number; log?: { ts: string; kind: string; message: string }[]; error?: string;
}
export interface Stats { total: number; by_status: Record<string, number>; submitted: number; interviews: number; in_progress: number; average_match: number | null; follow_ups_due: number }
export interface Meta { app: string; ai_enabled: boolean; ai_model: string | null; automation_headless: boolean; adapters: { name: string; display_name: string; requires_account: boolean; notes: string }[]; statuses: string[] }

export const STATUSES = [
  "New", "Analyzing", "Resume Update Required", "Ready for Application", "Account Creation Required",
  "Verification Pending", "Application In Progress", "Ready for Final Approval", "Submitted", "Interview",
  "Rejected", "On Hold",
];

export const emptyProfile = (): Profile => ({
  full_name: "", email: "", phone: "", location: "", linkedin_url: "", portfolio_url: "", professional_summary: "",
  total_experience_years: null, current_company: "", current_title: "", experience: [], education: [],
  technical_skills: [], soft_skills: [], certifications: [], projects: [], achievements: [], languages: [],
  notice_period: "", current_ctc: "", expected_ctc: "", preferred_locations: [], preferred_roles: [],
  work_authorization: "", willing_to_relocate: null,
});
