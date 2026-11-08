"""Browser automation engine with mandatory human-in-the-loop checkpoints.

The engine drives one Playwright browser per application:

    open official site -> (account/login checkpoint) -> per page: detect checkpoints, discover fields,
    fill verified profile data, upload approved resume, draft answers -> pause for review ->
    next page ... -> final page: pause for explicit final approval -> submit -> capture confirmation

It never fills passwords or OTPs, never solves CAPTCHAs, never ticks legal declarations or voluntary
disclosures, and never clicks a final submit button unless `approve_and_submit` is called after the
user's explicit approval. While paused, the user completes steps either in the visible browser window
(local/headed mode) or through the remote browser view (screenshot + click/type forwarding), which
lets them finish verification from a phone. Text typed through the remote view is never logged.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Frame, Page, Playwright

from ..config import get_settings
from ..db import SessionLocal
from ..models import Application, ApplicationEvent, ApplicationQuestion, ApplicationStatus, Resume
from ..schemas import CandidateProfileData
from ..services import storage
from ..services.ai import ai_service
from ..services.profile_service import load_profile
from ..services.resume_service import resume_file_for_upload
from .adapters import BaseAdapter, get_adapter
from .browser import launch_browser
from .fields import (
    BUTTONS_JS,
    CHECKPOINT_JS,
    COLLECT_JS,
    CONFIRM_RE,
    LOGIN_TEXT_RE,
    NEXT_RE,
    REFERENCE_RE,
    SUBMIT_RE,
    Field,
    best_option,
    classify,
    profile_value,
)

log = logging.getLogger("applypilot.automation")

HUMAN_MSG = "Human verification required. Please complete this step in the browser."
ALLOWED_KEYS = {"Enter", "Tab", "Backspace", "Delete", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft",
                "ArrowRight", "Home", "End", "PageUp", "PageDown", "Space"}
VIEWPORT = {"width": 1280, "height": 860}


class AutomationError(RuntimeError):
    pass


@dataclass
class Checkpoint:
    kind: str  # account | login | captcha | otp | review_page | user_fields | validation | final_approval | manual | post_submit
    title: str
    message: str
    details: list[str] = field(default_factory=list)
    human_verification: bool = False


@dataclass
class FilledField:
    label: str
    value: str
    category: str
    page: int
    source: str = "profile"


class AutomationSession:
    def __init__(self, application_id: int, user_id: int, headless: bool | None = None) -> None:
        s = get_settings()
        self.application_id = application_id
        self.user_id = user_id
        self.headless = s.automation_headless if headless is None else headless
        self.state = "starting"  # starting | running | paused | submitted | error | closed
        self.checkpoint: Checkpoint | None = None
        self.log: list[dict] = []
        self.filled: dict[str, FilledField] = {}
        self.left_for_user: dict[str, dict] = {}
        self.page_no = 0
        self.error = ""
        self.lock = asyncio.Lock()
        self.last_activity = time.monotonic()
        self.tmpdir = Path(tempfile.mkdtemp(prefix="applypilot-"))
        self.resume_path: Path | None = None
        self.resume_label = ""
        self.adapter: BaseAdapter = BaseAdapter()
        self.profile = CandidateProfileData()
        self.job_title = self.company = self.description = ""
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self._task: asyncio.Task | None = None
        self._submit_clicked = False

    # ----------------------------------------------------------- utilities
    def note(self, msg: str, kind: str = "info", persist: bool = False) -> None:
        self.log.append({"ts": datetime.now(UTC).isoformat(), "kind": kind, "message": msg})
        self.log = self.log[-200:]
        log.info("[app %s] %s", self.application_id, msg)
        if persist:
            with SessionLocal() as db:
                db.add(ApplicationEvent(application_id=self.application_id, kind=kind, message=msg))
                db.commit()

    def set_status(self, status: ApplicationStatus, message: str | None = None) -> None:
        with SessionLocal() as db:
            app = db.get(Application, self.application_id)
            if app and app.status != ApplicationStatus.SUBMITTED.value:
                app.status = status.value
                if message:
                    db.add(ApplicationEvent(application_id=app.id, kind="status", message=f"{status.value}: {message}"))
                db.commit()

    def pause(self, cp: Checkpoint, status: ApplicationStatus) -> None:
        self.checkpoint = cp
        self.state = "paused"
        self.set_status(status, cp.title)
        self.note(f"Paused - {cp.title}", "checkpoint")

    def touch(self) -> None:
        self.last_activity = time.monotonic()

    def to_dict(self) -> dict:
        return {
            "application_id": self.application_id,
            "state": self.state,
            "headless": self.headless,
            "checkpoint": asdict(self.checkpoint) if self.checkpoint else None,
            "page_number": self.page_no,
            "url": self.page.url if self.page and not self.page.is_closed() else "",
            "platform": self.adapter.display_name,
            "filled_count": len(self.filled),
            "log": self.log[-40:],
            "error": self.error,
        }

    def _frames(self) -> list[Frame]:
        assert self.page is not None
        return [self.page.main_frame] + [f for f in self.page.frames if f != self.page.main_frame and f.url and f.url != "about:blank"]

    def _loc(self, f: Field):
        frame = self._frames()[min(f.frame_index, len(self._frames()) - 1)]
        return frame.locator(f'[data-ap-id="{f.ref}"]').first

    # --------------------------------------------------------- lifecycle
    def _load_context(self) -> str:
        with SessionLocal() as db:
            app = db.get(Application, self.application_id)
            if not app:
                raise AutomationError("Application not found")
            if not app.resume_id:
                raise AutomationError("Approve a resume version for this application before starting automation.")
            self.profile = load_profile(db, self.user_id)
            job = app.job
            self.job_title, self.company, self.description = job.title, job.company, job.description
            self.adapter = get_adapter(job.apply_url or job.url, job.platform)
            resume = db.get(Resume, app.resume_id)
            name, data = resume_file_for_upload(resume)
            self.resume_label = resume.label
            self.resume_path = self.tmpdir / name
            self.resume_path.write_bytes(data)
            return self.adapter.application_url(job.url, job.apply_url)

    async def start(self) -> None:
        async with self.lock:
            self.touch()
            try:
                url = self._load_context()
                self.note(f"Using adapter: {self.adapter.display_name}")
                self._pw, self._browser = await launch_browser(self.headless)
                self._context = await self._browser.new_context(viewport=VIEWPORT, accept_downloads=False)
                self.page = await self._context.new_page()
                self.page.set_default_timeout(get_settings().automation_timeout_ms)
                self.note(f"Opening official application site: {url}", persist=True)
                self.set_status(ApplicationStatus.APPLICATION_IN_PROGRESS, "Automation started")
                await self.adapter.open(self.page, url, 45000)
                await self._run_loop()
            except Exception as exc:  # surfaced to the UI
                await self._fail(exc)

    async def _fail(self, exc: Exception) -> None:
        self.state = "error"
        self.error = str(exc)[:500]
        self.note(f"Automation error: {self.error}", "error", persist=True)
        self.checkpoint = Checkpoint(
            "manual", "Automation could not continue",
            "The site could not be automated at this step. You can complete it manually in the browser view, "
            "then press Continue, or use the manual completion workflow.", [self.error])
        if self.page and not self.page.is_closed():
            self.state = "paused"

    async def close(self) -> None:
        self.state = "closed"
        for closer in (self._context, self._browser):
            try:
                if closer:
                    await closer.close()
            except Exception:
                pass
        try:
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # --------------------------------------------------------- detection
    async def _detect_checkpoint(self, fields: list[Field]) -> Checkpoint | None:
        assert self.page is not None
        info = await self.page.evaluate(CHECKPOINT_JS)
        captcha = info["captcha"]
        for fr in self._frames()[1:]:
            if re.search(r"recaptcha|hcaptcha|turnstile|captcha", fr.url, re.I):
                captcha = True
        if captcha:
            return Checkpoint("captcha", "CAPTCHA detected", HUMAN_MSG + " Solve the CAPTCHA yourself, then press "
                              "Continue Application.", human_verification=True)
        cats = {f.category for f in fields}
        if "otp" in cats:
            return Checkpoint("otp", "Verification code (OTP) required", HUMAN_MSG + " Enter the code sent to your "
                              "email or phone, submit it, then press Continue Application.", human_verification=True)
        if "password" in cats:
            text = info["bodyText"].lower()
            pw_count = sum(1 for f in fields if f.category == "password")
            creating = pw_count >= 2 or re.search(r"create (an |your )?account|register|sign up|confirm password", text)
            if creating:
                return Checkpoint("account", "Account creation required", HUMAN_MSG + " This portal needs a "
                                  "candidate account. Create it yourself (choose your own password and accept the "
                                  "terms only if you agree), complete any verification, then press Continue Application.",
                                  ["ApplyPilot never sees or stores your portal password."], human_verification=True)
            return Checkpoint("login", "Sign-in required", HUMAN_MSG + " Sign in to your candidate account on this "
                              "portal, then press Continue Application.",
                              ["ApplyPilot never sees or stores your portal password."], human_verification=True)
        return None

    async def _collect_fields(self) -> list[Field]:
        fields: list[Field] = []
        for idx, frame in enumerate(self._frames()):
            try:
                raw = await frame.evaluate(COLLECT_JS)
            except Exception:
                continue
            for r in raw:
                f = Field(**{k: v for k, v in r.items() if k in Field.__dataclass_fields__}, frame_index=idx)
                key = self.adapter.attribute_map.get(f.automation_id) or self.adapter.attribute_map.get(f.name)
                classify(f)
                if key and f.category not in ("password", "otp", "sensitive", "legal"):
                    f.category, f.profile_key = "profile", key
                fields.append(f)
        return fields

    async def _collect_buttons(self) -> list[tuple[int, dict]]:
        out = []
        for idx, frame in enumerate(self._frames()):
            try:
                out += [(idx, b) for b in await frame.evaluate(BUTTONS_JS)]
            except Exception:
                continue
        return out

    async def _find_nav(self, fields: list[Field]) -> tuple[str, tuple[int, dict] | None]:
        buttons = await self._collect_buttons()
        has_form = any(f.category in ("profile", "resume", "question", "choice") for f in fields)
        nxt = sub = entry = None
        for idx, b in buttons:
            text = b["text"].strip()
            if b["automation_id"] in self.adapter.next_button_ids:
                nxt = nxt or (idx, b)
            elif b["automation_id"] in self.adapter.submit_button_ids:
                sub = sub or (idx, b)
            elif NEXT_RE.match(text) and (b["tag"] == "button" or b["in_form"] or b["type"] == "submit"):
                nxt = nxt or (idx, b)
            elif SUBMIT_RE.search(text) and (b["tag"] in ("button", "input") or b["type"] == "submit"):
                if re.match(r"^apply", text, re.I) and not (has_form and b["in_form"]):
                    entry = entry or (idx, b)
                else:
                    sub = sub or (idx, b)
            elif self.adapter.is_apply_entry(text):
                entry = entry or (idx, b)
        if nxt:
            return "next", nxt
        if sub and has_form:
            return "submit", sub
        if entry and not has_form:
            return "entry", entry
        if sub:
            return "submit", sub
        return "none", None

    def _button_locator(self, btn: tuple[int, dict]):
        idx, b = btn
        frames = self._frames()
        return frames[min(idx, len(frames) - 1)].locator(f'[data-ap-btn="{b["ref"]}"]').first

    async def _validation_errors(self) -> list[str]:
        assert self.page is not None
        js = r"""() => Array.from(document.querySelectorAll('[role=alert], .error, .errors, .field-error, .invalid-feedback, [class*="error" i][class*="message" i], [data-automation-id="errorMessage"]'))
            .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
            .map(e => (e.innerText || '').trim()).filter(t => t && t.length < 300).slice(0, 10)"""
        try:
            return await self.page.evaluate(js)
        except Exception:
            return []

    # ------------------------------------------------------------ filling
    async def _fill_text(self, f: Field, value: str) -> bool:
        loc = self._loc(f)
        try:
            await loc.scroll_into_view_if_needed(timeout=3000)
            await loc.fill(value, timeout=5000)
            return True
        except Exception:
            try:  # custom widgets (comboboxes): type + Enter
                await loc.click(timeout=3000)
                await loc.press_sequentially(value, delay=20)
                await loc.press("Enter")
                return True
            except Exception as exc:
                self.note(f"Could not fill '{f.display_label}': {type(exc).__name__}", "warn")
                return False

    async def _choose(self, f: Field, value: str) -> bool:
        option = best_option(value, f.options)
        if not option:
            return False
        try:
            if f.tag == "select":
                await self._loc(f).select_option(label=option, timeout=5000)
            elif f.type == "radio":
                ref = f.option_refs[f.options.index(option)]
                frame = self._frames()[min(f.frame_index, len(self._frames()) - 1)]
                await frame.locator(f'[data-ap-id="{ref}"]').first.check(timeout=5000)
            else:
                return await self._fill_text(f, option)
            return True
        except Exception as exc:
            self.note(f"Could not select '{option}' for '{f.display_label}': {type(exc).__name__}", "warn")
            return False

    async def _set_field(self, f: Field, value: str) -> bool:
        if f.tag == "select" or f.type == "radio":
            return await self._choose(f, value)
        return await self._fill_text(f, value)

    def _question_row(self, db, f: Field) -> ApplicationQuestion | None:
        label = f.display_label
        return db.query(ApplicationQuestion).filter_by(application_id=self.application_id, question=label).first()

    async def _fill_page(self, fields: list[Field]) -> list[str]:
        """Fill everything the agent may fill. Returns labels that still need the user's attention."""
        pending: list[str] = []
        for f in fields:
            key = f"{self.page_no}:{f.display_label}"
            if f.category == "profile":
                value = profile_value(f.profile_key, self.profile)
                if not value:
                    if f.required and not f.has_value:
                        self.left_for_user[key] = {"label": f.display_label, "reason": "Not in your profile", "required": True}
                        pending.append(f.display_label)
                    continue
                if f.has_value and f.tag != "select":
                    self.filled.setdefault(key, FilledField(f.display_label, "(already filled on site)", "profile", self.page_no, "site"))
                    continue
                if await self._set_field(f, value):
                    self.filled[key] = FilledField(f.display_label, value, f.profile_key, self.page_no)
                elif f.required:
                    pending.append(f.display_label)
            elif f.category == "resume":
                if not f.has_value and self.resume_path:
                    try:
                        await self._loc(f).set_input_files(str(self.resume_path), timeout=8000)
                        self.filled[key] = FilledField(f.display_label, self.resume_label, "resume", self.page_no)
                        self.note(f"Uploaded approved resume: {self.resume_label}")
                    except Exception as exc:
                        self.note(f"Resume upload failed: {type(exc).__name__}", "warn")
                        pending.append(f.display_label)
            elif f.category in ("question", "choice", "unknown"):
                if f.category == "unknown" and not f.required:
                    continue
                if await self._handle_question(f):
                    pending.append(f.display_label)
            elif f.category in ("sensitive", "legal"):
                reason = ("Voluntary disclosure / sensitive personal information - only you can answer"
                          if f.category == "sensitive" else "Legal declaration / consent - only you can accept")
                self.left_for_user[key] = {"label": f.display_label, "reason": reason, "required": f.required,
                                           "completed": f.has_value}
                if f.required and not f.has_value:
                    pending.append(f.display_label)
        return pending

    async def _handle_question(self, f: Field) -> bool:
        """Draft/fill an application question. Returns True if it is still waiting for the user."""
        with SessionLocal() as db:
            row = self._question_row(db, f)
            if row is None:
                answer, needs_input = "", False
                if f.options:
                    answer = await asyncio.to_thread(ai_service.choose_option, f.display_label, f.options, self.profile)
                    needs_input = not answer
                else:
                    res = await asyncio.to_thread(ai_service.answer_question, f.display_label, self.profile,
                                                  self.company, self.job_title, self.description)
                    answer, needs_input = res["answer"], bool(res.get("needs_user_input"))
                row = ApplicationQuestion(
                    application_id=self.application_id, question=f.display_label, answer=answer,
                    status="suggested", field_ref=f.ref, options=f.options,
                    field_type="select" if f.options else ("textarea" if f.tag == "textarea" else "text"),
                    required=f.required, needs_user_input=needs_input)
                db.add(row)
                db.commit()
                self.note(f"Drafted answer for: {f.display_label[:80]}")
            if row.status == "filled":
                return False
            if row.status == "accepted" and row.answer:
                if await self._set_field(f, row.answer):
                    row.status = "filled"
                    db.commit()
                    self.filled[f"{self.page_no}:{f.display_label}"] = FilledField(
                        f.display_label, row.answer, "answer", self.page_no, "approved answer")
                    return False
                return True
            if f.has_value:  # the user answered it directly in the browser
                return False
            if not f.required and not row.answer:
                return False
            return True

    # ------------------------------------------------------------ main loop
    async def _run_loop(self) -> None:
        assert self.page is not None
        self.state = "running"
        self.checkpoint = None
        s = get_settings()
        same_page_guard = 0
        last_signature = None
        for _ in range(s.automation_max_pages * 3):
            self.touch()
            await self.adapter.settle(self.page)
            fields = await self._collect_fields()
            cp = await self._detect_checkpoint(fields)
            if cp:
                status = (ApplicationStatus.ACCOUNT_CREATION_REQUIRED if cp.kind in ("account", "login")
                          else ApplicationStatus.VERIFICATION_PENDING)
                self.pause(cp, status)
                return
            signature = (self.page.url, tuple(sorted(f.display_label for f in fields)))
            if signature != last_signature:
                self.page_no += 1
                last_signature = signature
                same_page_guard = 0
            else:
                same_page_guard += 1
            form_fields = [f for f in fields if f.category not in ("unknown",)]
            if not form_fields:
                kind, btn = await self._find_nav(fields)
                if kind == "entry" and btn and same_page_guard < 2:
                    self.note(f"Opening application form via '{btn[1]['text']}'")
                    await self._button_locator(btn).click()
                    continue
                if await self.adapter.click_apply_entry(self.page) and same_page_guard < 2:
                    self.note("Opened application form")
                    continue
                body = (await self.page.evaluate("document.body ? document.body.innerText : ''"))[:3000]
                if LOGIN_TEXT_RE.search(body):
                    self.pause(Checkpoint("login", "Sign-in or account step", HUMAN_MSG + " Sign in or create your "
                                          "account in the browser, then press Continue Application.",
                                          human_verification=True), ApplicationStatus.ACCOUNT_CREATION_REQUIRED)
                    return
                self.pause(Checkpoint("manual", "Could not find the application form",
                                      "Navigate to the application form in the browser view (or complete this step "
                                      "manually), then press Continue Application."), ApplicationStatus.APPLICATION_IN_PROGRESS)
                return

            self.note(f"Page {self.page_no}: found {len(fields)} fields")
            pending = await self._fill_page(fields)
            if pending:
                self.pause(Checkpoint(
                    "review_page", f"Your input needed on page {self.page_no}",
                    "Review the AI-drafted answers and complete the fields only you can answer. Accept answers in "
                    "ApplyPilot (they will be filled for you), complete sensitive/legal items in the browser, then "
                    "press Continue Application.", pending[:30]), ApplicationStatus.APPLICATION_IN_PROGRESS)
                return
            kind, btn = await self._find_nav(fields)
            if kind == "next" and btn:
                before = signature
                self.note(f"Moving to next step via '{btn[1]['text']}'")
                await self._button_locator(btn).click()
                await self.adapter.settle(self.page)
                after_fields = await self._collect_fields()
                if (self.page.url, tuple(sorted(f.display_label for f in after_fields))) == before:
                    errors = await self._validation_errors()
                    if errors:
                        self.pause(Checkpoint("validation", "The site reported validation errors",
                                              "Fix the highlighted fields in the browser (or update your profile and "
                                              "retry), then press Continue Application.", errors),
                                   ApplicationStatus.APPLICATION_IN_PROGRESS)
                        return
                continue
            if kind == "submit" and btn:
                await self._prepare_final_review(fields, btn[1]["text"])
                return
            self.pause(Checkpoint("manual", "Next step not found",
                                  "ApplyPilot could not find a Next/Submit button. Complete this page in the browser, "
                                  "then press Continue Application."), ApplicationStatus.APPLICATION_IN_PROGRESS)
            return
        self.pause(Checkpoint("manual", "Too many steps", "The form has more steps than expected. Please review it in "
                              "the browser."), ApplicationStatus.APPLICATION_IN_PROGRESS)

    async def _prepare_final_review(self, fields: list[Field], submit_text: str) -> None:
        refreshed = await self._collect_fields()
        missing = [f.display_label for f in refreshed if f.required and not f.has_value
                   and f.category not in ("password", "otp")]
        warnings = await self._validation_errors()
        with SessionLocal() as db:
            app = db.get(Application, self.application_id)
            app.review = {
                "generated_at": datetime.now(UTC).isoformat(),
                "platform": self.adapter.display_name,
                "final_url": self.page.url if self.page else "",
                "submit_button": submit_text,
                "resume_uploaded": self.resume_label,
                "filled_fields": [asdict(v) for v in self.filled.values()],
                "left_for_user": list(self.left_for_user.values()),
                "missing_fields": missing,
                "validation_warnings": warnings,
                "pages": self.page_no,
            }
            db.commit()
        self.pause(Checkpoint(
            "final_approval", "Ready for final approval",
            "All supported fields are complete. Review the full application summary. Nothing has been submitted. "
            "Click 'Approve & Submit' to let ApplyPilot press the final submit button, or 'Edit Application' to make "
            "changes in the browser first.", missing), ApplicationStatus.READY_FOR_FINAL_APPROVAL)

    # ------------------------------------------------------------- user actions
    async def resume(self) -> None:
        async with self.lock:
            self.touch()
            if self.state not in ("paused", "error"):
                raise AutomationError("Automation is not waiting for you right now.")
            try:
                if self.checkpoint and self.checkpoint.kind == "post_submit":
                    await self._capture_confirmation(after_human=True)
                    return
                self.error = ""
                await self._run_loop()
            except Exception as exc:
                await self._fail(exc)

    async def approve_and_submit(self) -> None:
        async with self.lock:
            self.touch()
            if not (self.state == "paused" and self.checkpoint and self.checkpoint.kind == "final_approval"):
                raise AutomationError("The application is not at the final approval step.")
            assert self.page is not None
            fields = await self._collect_fields()
            cp = await self._detect_checkpoint(fields)
            if cp:
                self.pause(cp, ApplicationStatus.VERIFICATION_PENDING)
                return
            kind, btn = await self._find_nav(fields)
            if kind != "submit" or not btn:
                self.pause(Checkpoint("manual", "Submit button no longer found",
                                      "The page changed. Review it in the browser and press Continue Application."),
                           ApplicationStatus.APPLICATION_IN_PROGRESS)
                return
            self.state = "running"
            self.note(f"User approved submission. Clicking '{btn[1]['text']}'", "approval", persist=True)
            self._submit_clicked = True
            await self._button_locator(btn).click()
            try:
                await self.page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            await self._capture_confirmation(after_human=False)

    async def _capture_confirmation(self, after_human: bool) -> None:
        assert self.page is not None
        info = await self.page.evaluate(CHECKPOINT_JS)
        text, url = info["bodyText"], info["url"]
        confirmed = bool(CONFIRM_RE.search(text)) or bool(re.search(r"thank|confirm|success|submitted", url, re.I))
        if not confirmed:
            if info["captcha"]:
                self.pause(Checkpoint("post_submit", "CAPTCHA shown at submission",
                                      HUMAN_MSG + " Solve the CAPTCHA. If the site needs it, press its submit button "
                                      "yourself, then press Continue Application.", human_verification=True),
                           ApplicationStatus.VERIFICATION_PENDING)
                return
            errors = await self._validation_errors()
            if errors:
                self.pause(Checkpoint("validation", "The site rejected the submission",
                                      "Fix the issues in the browser, then press Continue Application.", errors),
                           ApplicationStatus.APPLICATION_IN_PROGRESS)
                return
            self.pause(Checkpoint("post_submit", "Submission could not be confirmed automatically",
                                  "Check the browser. If the site shows a confirmation, press Continue Application "
                                  "or use 'Mark as submitted' and enter the reference number."),
                       ApplicationStatus.READY_FOR_FINAL_APPROVAL)
            return
        ref = REFERENCE_RE.search(text)
        shot = await self.page.screenshot(full_page=True, type="png")
        key = storage.save(self.user_id, shot, "png")
        snippet = next((m.group(0) for m in [re.search(r"[^\n]{0,200}" + CONFIRM_RE.pattern + r"[^\n]{0,300}", text, re.I)] if m), text[:500])
        with SessionLocal() as db:
            app = db.get(Application, self.application_id)
            app.status = ApplicationStatus.SUBMITTED.value
            app.submitted_at = datetime.now(UTC)
            app.reference_id = ref.group(1) if ref else app.reference_id
            app.confirmation_text = snippet[:2000]
            app.confirmation_url = url
            app.confirmation_screenshot_key = key
            db.add(ApplicationEvent(application_id=app.id, kind="submitted",
                                    message=f"Application submitted. Reference: {app.reference_id or 'n/a'}"))
            db.commit()
        self.state = "submitted"
        self.checkpoint = Checkpoint("done", "Application submitted",
                                     "Confirmation captured and saved to your application history.",
                                     [f"Reference: {ref.group(1)}" if ref else "No reference number shown"])
        self.note("Application submitted and confirmation captured", "submitted")

    # ------------------------------------------------------- remote control
    async def screenshot(self) -> bytes:
        if not self.page or self.page.is_closed():
            raise AutomationError("Browser is not open")
        self.touch()
        return await self.page.screenshot(type="jpeg", quality=60)

    def _require_interactive(self) -> Page:
        if self.state not in ("paused", "error", "submitted") or not self.page or self.page.is_closed():
            raise AutomationError("Remote control is available while automation is paused for you.")
        self.touch()
        return self.page

    async def remote_click(self, x: float, y: float) -> None:
        page = self._require_interactive()
        await page.mouse.click(max(0, min(1, x)) * VIEWPORT["width"], max(0, min(1, y)) * VIEWPORT["height"])

    async def remote_type(self, text: str) -> None:
        page = self._require_interactive()
        await page.keyboard.type(text[:500], delay=15)  # deliberately not logged (may be OTP/password)

    async def remote_key(self, key: str) -> None:
        if key not in ALLOWED_KEYS:
            raise AutomationError("Key not allowed")
        page = self._require_interactive()
        await page.keyboard.press(" " if key == "Space" else key)

    async def remote_scroll(self, dy: int) -> None:
        page = self._require_interactive()
        await page.mouse.wheel(0, max(-3000, min(3000, dy)))

    async def remote_back(self) -> None:
        page = self._require_interactive()
        await page.go_back()


class SessionManager:
    IDLE_SECONDS = 30 * 60

    def __init__(self) -> None:
        self.sessions: dict[int, AutomationSession] = {}
        self._reaper: asyncio.Task | None = None

    def get(self, application_id: int, user_id: int) -> AutomationSession | None:
        s = self.sessions.get(application_id)
        return s if s and s.user_id == user_id else None

    async def start(self, application_id: int, user_id: int, headless: bool | None = None) -> AutomationSession:
        existing = self.sessions.get(application_id)
        if existing and existing.state != "closed":
            if existing.user_id != user_id:
                raise AutomationError("Not allowed")
            return existing
        active = [s for s in self.sessions.values() if s.state not in ("closed",)]
        if len(active) >= get_settings().automation_max_sessions:
            raise AutomationError("Too many active browser sessions. Close another application session first.")
        session = AutomationSession(application_id, user_id, headless)
        self.sessions[application_id] = session
        session._task = asyncio.create_task(session.start())
        self._ensure_reaper()
        return session

    def run_background(self, coro) -> None:
        asyncio.create_task(coro)

    async def stop(self, application_id: int) -> None:
        s = self.sessions.pop(application_id, None)
        if s:
            await s.close()

    async def stop_user(self, user_id: int) -> None:
        for app_id, s in list(self.sessions.items()):
            if s.user_id == user_id:
                await self.stop(app_id)

    def _ensure_reaper(self) -> None:
        if self._reaper is None or self._reaper.done():
            self._reaper = asyncio.create_task(self._reap())

    async def _reap(self) -> None:
        while self.sessions:
            await asyncio.sleep(60)
            now = time.monotonic()
            for app_id, s in list(self.sessions.items()):
                if s.state != "running" and now - s.last_activity > self.IDLE_SECONDS:
                    await self.stop(app_id)

    async def shutdown(self) -> None:
        for app_id in list(self.sessions):
            await self.stop(app_id)


manager = SessionManager()
