# ApplyPilot AI

An AI-powered personal job application platform. **One saved profile, one job URL. AI handles the supported work, and you approve the important decisions.**

```
Upload CV → Paste job URL → AI analyses the JD → AI recommends resume changes → You approve the CV
→ AI opens the official site → You sign in / create account → You complete OTP / CAPTCHA
→ AI fills supported fields + drafts answers → You review → You click "Approve & Submit"
→ AI submits, captures confirmation + reference → Status saved in your tracker
```

| Area | What is implemented |
|---|---|
| Auth | Email/password accounts (bcrypt), JWT bearer sessions, login rate-limiting, per-user data isolation |
| Candidate profile | All fields from the brief (contact, summary, experience, education, skills, projects, certifications, achievements, notice period, CTC, preferences), entered once and reused. Encrypted at rest. Completeness meter |
| CV management | PDF/DOCX upload → text extraction → AI (or heuristic) structured parsing → profile auto-fill (never overwrites what you typed). Multiple versions by job category, editable, default version, **PDF + DOCX download** (ATS-friendly single-column) |
| Job URL analysis | Greenhouse API, Lever API, Workday CXS endpoint, schema.org `JobPosting` JSON-LD, generic HTML, and a Playwright-rendered fallback for JS sites. Paste-the-JD fallback when a site blocks reading. Extracts company, title, location, full JD, required/preferred skills, experience, education, hard requirements |
| Matching | 0–100 compatibility score with strengths, gaps, missing keywords. **Honest ineligibility** (e.g. 5+ yrs required vs 0.5) puts the application On Hold with reasons instead of proceeding blindly. Picks the best resume version |
| Resume tailoring | Option A: approve/reject/edit each recommendation. Option B: generate an updated CV automatically (guardrail-clean suggestions only). **Guardrails**: every suggestion is checked against your data, and skills or numbers not found in your profile are flagged; skills can only be reordered, never added |
| Question assistant | Drafts answers from your profile + JD. Accept, edit, regenerate, shorter, more professional. Salary/notice answers come straight from your profile (never guessed). Flags answers needing personal input |
| Browser automation | Playwright engine with **dynamic field discovery** (labels, aria, placeholders, names, ATS automation ids, surrounding text), multi-page navigation, resume upload, select/radio matching, iframes. Adapters: **Workday, SAP SuccessFactors, Greenhouse, Lever, Oracle Recruiting/Taleo, generic career portals** |
| Human-in-the-loop | Mandatory pauses for account creation, sign-in, email/mobile OTP, CAPTCHA, passwords, T&Cs, sensitive info, voluntary disclosures, legal declarations, validation errors and **final submission**. Shows *"Human verification required. Please complete this step in the browser."* + **Continue Application** |
| Remote browser view | Live screenshot view of the automation browser with tap-to-click, type, keys, scroll and back, so you can do OTP/CAPTCHA/login **from an Android phone** while the browser runs in the cloud. Typed text is never stored or logged. In local mode (`AUTOMATION_HEADLESS=false`) a real browser window opens on your machine |
| Final review | Company, title, candidate details, resume uploaded, education, employment, every filled field, answers, disclosures left to you, missing required fields, site warnings. **Edit Application** / **Approve & Submit** (with confirmation checkbox) |
| After submission | Confirmation text, reference number (auto-detected), submission date, confirmation URL and full-page screenshot (encrypted) |
| Manual workflow | Copy-ready values, approved resume download, answers, steps, and "Mark as submitted" for portals that don't permit automation |
| Tracking | All 12 statuses from the brief, search, status filters, sorting, summary stats, follow-up dates, interview status, notes, timeline/audit log, CSV export. **Duplicate prevention** (URL normalised, tracking params stripped) |
| Discovery | Role/location search links to official career portals (PwC, Deloitte, EY, KPMG, Accenture, TCS, Infosys, Wipro, L&T, Amazon, Microsoft) and job boards, built from your preferences. No scraping |
| Privacy | Field-level + file encryption (Fernet), data export (JSON), account deletion (password-confirmed), no portal passwords/OTPs ever collected, contact info + compensation stripped from AI prompts that don't need them, security headers, SSRF protection on job fetching |

## Architecture

```
frontend/  Next.js 15 (App Router) · TypeScript · Tailwind. Responsive (phone drawer nav, desktop sidebar)
backend/   FastAPI · SQLAlchemy 2 (PostgreSQL or SQLite) · Anthropic Claude · Playwright
  app/
    routers/       auth, profile, resumes, applications (analysis, tailoring, questions, tracking), automation, account
    services/      cv_parser, job_fetcher, ai (Claude + heuristics + guardrails), analysis pipeline,
                   resume_service (tailoring), resume_render (PDF/DOCX), storage (encrypted files)
    automation/    engine (sessions, checkpoints, fill loop, submit, remote control),
                   fields (discovery + classification), adapters/ (one class per ATS), browser
  tests/           API tests + end-to-end automation tests against a local fake portal
e2e/ui_flow.py     full-stack UI test (Android Pixel 7 + Windows Chrome viewports)
```

**Adding a recruitment platform**: subclass `BaseAdapter` in `backend/app/automation/adapters/__init__.py` (URL matcher, ATS attribute → profile-key map, next/submit button ids, how to open the form) and add it to `ADAPTERS`. The generic engine does the rest.

**AI**: `services/ai.py` uses the official `anthropic` SDK with structured outputs (`messages.parse` + Pydantic schemas), model `claude-opus-5-5`, and server-side refusal fallbacks. Without `ANTHROPIC_API_KEY` every feature still works in **heuristic mode** (keyword-based parsing, matching and templated answers), which is clearly labelled in the UI.

## Local setup

Prerequisites: Python 3.11+, Node 20+, (optional) PostgreSQL 14+.

```bash
# Backend
cd applypilot/backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium                             # browser for automation
cp .env.example .env                                    # then fill JWT_SECRET, ENCRYPTION_KEY, ANTHROPIC_API_KEY
# For a quick start you can delete the DATABASE_URL line to use SQLite.
uvicorn app.main:app --reload --port 8000               # API docs: http://localhost:8000/api/docs

# Frontend (new terminal)
cd applypilot/frontend
cp .env.example .env.local                              # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                                             # http://localhost:3000
```

Tip: running the backend on your own laptop with `AUTOMATION_HEADLESS=false` opens a real Chrome window for each application, so you can sign in and solve CAPTCHAs directly in it.

Or everything with Docker: `cp backend/.env.example backend/.env` (fill secrets) → `docker compose up --build`.

### Environment variables

Backend (`backend/.env`, all documented in `backend/.env.example`):

| Variable | Required | Description |
|---|---|---|
| `ENVIRONMENT` | | `production` enforces `JWT_SECRET` + `ENCRYPTION_KEY` and enables HSTS |
| `DATABASE_URL` | prod | PostgreSQL URL (`postgresql://…` or `postgres://…`). SQLite if unset |
| `JWT_SECRET` | prod | Long random string for signing sessions |
| `ENCRYPTION_KEY` | prod | Fernet key for profile/resume encryption. **Back it up**: losing it makes stored data unreadable |
| `CORS_ORIGINS` | prod | Comma-separated frontend origins, e.g. `https://applypilot.vercel.app` |
| `ANTHROPIC_API_KEY` | for AI | Claude API key. Empty = heuristic mode |
| `AI_MODEL` / `AI_EFFORT` / `AI_ENABLE_FALLBACKS` | | Defaults: `claude-opus-5-5` / `medium` / `true` |
| `STORAGE_DIR` | | Encrypted file storage path (persistent volume in production) |
| `MAX_UPLOAD_MB` | | CV upload limit (default 10) |
| `AUTOMATION_HEADLESS` | | `true` for servers (remote view), `false` for a visible local browser |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE` | | Custom Chromium path |
| `AUTOMATION_TIMEOUT_MS` / `AUTOMATION_MAX_PAGES` / `AUTOMATION_MAX_SESSIONS` | | Engine limits |
| `ALLOW_PRIVATE_URLS` | | `true` only for local testing against localhost portals |

Frontend: `NEXT_PUBLIC_API_URL`, the public URL of the backend (inlined at build time).

## Deployment

1. **Database**: create a managed PostgreSQL (Neon, Supabase, Render, RDS). Tables are created automatically on first start.
2. **Backend**: deploy `backend/Dockerfile` to a container host that supports long-lived processes and enough memory for Chromium (≥1 GB): Render, Railway, Fly.io, Google Cloud Run (min instances = 1, session affinity on) or a small VM.
   - Run **one** instance with one worker: automation browser sessions live in-process.
   - Attach a persistent private volume at `/data/storage` (or set `STORAGE_DIR`).
   - Set the env vars above with `ENVIRONMENT=production`. Serve over HTTPS (all of these hosts provide TLS).
3. **Frontend**: import `applypilot/frontend` into **Vercel** (root directory `applypilot/frontend`), set `NEXT_PUBLIC_API_URL=https://<your-api-host>`, deploy. Add the Vercel URL to the backend's `CORS_ORIGINS`.
4. Visit the site, create your account, upload your CV.

## Testing

```bash
cd backend && pytest -q          # 15 tests: API flows + browser automation end-to-end against tests/fixtures/portal
```

The automation tests drive a local fake recruitment portal through: job page → "Apply now" → sign-in wall (paused; the test plays the user) → profile fields filled, resume uploaded, degree selected, gender left untouched, terms left unticked, question drafted (paused for approval) → page 2 → final approval gate (asserts nothing was submitted) → Approve & Submit → reference `APP-48213` captured. They also cover CAPTCHA detection, the classifier, and the Continue endpoint.

### End-to-end UI test (Android Chrome + Windows Chrome)

```bash
(cd backend/tests/fixtures/portal && python -m http.server 8765 --bind 127.0.0.1) &
(cd backend && ALLOW_PRIVATE_URLS=true uvicorn app.main:app --port 8000) &
(cd frontend && npm run build && npm start) &
python e2e/ui_flow.py android     # Pixel 7 emulation (Chrome on Android)
python e2e/ui_flow.py desktop     # Windows Chrome UA, 1366×768
```

This drives the real UI through the entire workflow, including signing in on the portal and ticking the terms box **through the remote browser view**, and has been run passing on both profiles. It uses Playwright device emulation; please also try a real Android phone and Windows laptop against your deployment.

## Responsible automation & limitations

- ApplyPilot **never** bypasses CAPTCHA, OTP or other security controls, never invents OTPs, never creates passwords, and never accepts terms, declarations or voluntary disclosures for you. These always pause for you.
- It only clicks a final submit button after your explicit **Approve & Submit**.
- Respect each website's terms of use. Some portals prohibit automated access or use bot detection. When automation is blocked or a step can't be detected, ApplyPilot pauses and you can finish in the remote view or use the **manual completion workflow**.
- Real ATS sites change often. Adapters encode known patterns (e.g. Workday `data-automation-id`s), but the engine relies on dynamic field detection, and some custom widgets (complex date pickers, multi-select typeaheads) may need you to complete them in the browser view. The included automated tests run against a local fixture portal, not live Workday/Greenhouse/Lever tenants.
- Without an AI key, analysis and answers use heuristics. With a key, CV text and the job description are sent to Anthropic's API for processing.
- Never commit `.env` files, CVs or exported data. `.gitignore` excludes them.
