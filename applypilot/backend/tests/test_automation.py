"""End-to-end browser automation against a local fake recruitment portal.

Covers: apply-entry navigation, login checkpoint (user signs in), dynamic field detection and filling,
resume upload, AI-drafted answers awaiting approval, legal checkbox left to the user, multi-step
navigation, final-approval gate (nothing submitted before approval), submission + confirmation capture,
and CAPTCHA detection.
"""
import asyncio

from app.automation.engine import AutomationSession
from app.automation.fields import Field, classify
from app.db import SessionLocal, init_db
from app.models import Application, ApplicationQuestion, ApplicationStatus, Job, Resume, User
from app.schemas import CandidateProfileData, Education, Experience
from app.security import encrypt_json, hash_password
from app.services import storage
from app.services.profile_service import save_profile
from tests.conftest import make_cv_docx


def _setup(url: str, email: str) -> tuple[int, int]:
    init_db()
    with SessionLocal() as db:
        user = User(email=email, password_hash=hash_password("x" * 10), full_name="Priya Sharma")
        db.add(user)
        db.commit()
        profile = CandidateProfileData(
            full_name="Priya Sharma", email="priya.sharma@example.com", phone="+91 98765 43210",
            location="Bengaluru", linkedin_url="https://linkedin.com/in/priya-sharma-data",
            technical_skills=["SQL", "Python", "Pandas", "Power BI"], notice_period="Immediate",
            experience=[Experience(company="Contoso Retail", title="Data Analyst Intern", is_current=True,
                                   responsibilities=["Wrote SQL queries to analyse customer purchase data",
                                                     "Cleaned datasets using Python and Pandas"])],
            education=[Education(institution="Christ University", degree="Bachelor of Science",
                                 field_of_study="Statistics", end_date="2024")],
        )
        save_profile(db, user.id, profile)
        key = storage.save(user.id, make_cv_docx(), "docx")
        resume = Resume(user_id=user.id, label="Data Analyst CV", kind="uploaded", original_filename="priya_cv.docx",
                        file_key=key, content_enc=encrypt_json(profile.model_dump()))
        job = Job(user_id=user.id, url=url, normalized_url=url, apply_url=url, company="Acme Analytics",
                  title="Data Analyst", description="Data Analyst role using SQL and Python.")
        db.add_all([resume, job])
        db.commit()
        app = Application(user_id=user.id, job_id=job.id, resume_id=resume.id,
                          status=ApplicationStatus.READY_FOR_APPLICATION.value)
        db.add(app)
        db.commit()
        return user.id, app.id


def _accept_all(app_id: int) -> list[str]:
    with SessionLocal() as db:
        qs = db.query(ApplicationQuestion).filter_by(application_id=app_id).all()
        for q in qs:
            if q.status == "suggested":
                q.status = "accepted"
        db.commit()
        return [q.question for q in qs]


def _status(app_id: int) -> Application:
    with SessionLocal() as db:
        return db.get(Application, app_id)


def test_full_application_flow(portal_url):
    user_id, app_id = _setup(f"{portal_url}/job.html", "flow@example.com")

    async def run():
        s = AutomationSession(app_id, user_id, headless=True)
        try:
            await s.start()
            # 1) Opened job page, clicked "Apply now", hit the sign-in wall -> human checkpoint
            assert s.state == "paused", s.to_dict()
            assert s.checkpoint.kind == "login" and s.checkpoint.human_verification
            assert "Human verification required" in s.checkpoint.message
            assert _status(app_id).status == "Account Creation Required"

            # 2) The USER signs in (the agent never touches the password)
            await s.page.fill("#em", "priya.sharma@example.com")
            await s.page.fill("#pw", "my-own-secret")
            await s.page.click("button[type=submit]")
            await s.page.wait_for_url("**/form.html")
            await s.resume()

            # 3) Page 1 filled from profile; question drafted; legal checkbox left for the user
            assert s.state == "paused" and s.checkpoint.kind == "review_page", s.to_dict()
            assert await s.page.input_value("#fn") == "Priya"
            assert await s.page.input_value("#ln") == "Sharma"
            assert await s.page.input_value("#em") == "priya.sharma@example.com"
            assert await s.page.input_value("#ph") == "+91 98765 43210"
            assert "linkedin.com/in/priya" in await s.page.input_value("#li")
            assert await s.page.evaluate("document.getElementById('cv').files.length") == 1
            assert await s.page.evaluate("document.getElementById('deg').value") == "Bachelor of Science"
            assert await s.page.evaluate("document.getElementById('gen').selectedIndex") == 0  # sensitive: untouched
            assert not await s.page.is_checked("#terms")  # legal: untouched
            assert await s.page.input_value("#why") == ""  # draft awaits approval
            pending = " ".join(s.checkpoint.details)
            assert "Why do you want to join" in pending and "terms" in pending.lower()

            # 4) User approves the drafted answer and ticks the terms themselves
            assert any("Why do you want to join" in q for q in _accept_all(app_id))
            await s.page.check("#terms")
            await s.resume()

            # 5) Page 2: new question drafted -> approve -> continue
            assert s.state == "paused" and s.checkpoint.kind == "review_page", s.to_dict()
            assert await s.page.is_visible("#sql")
            _accept_all(app_id)
            await s.resume()

            # 6) Final approval gate: nothing submitted yet
            assert s.state == "paused" and s.checkpoint.kind == "final_approval", s.to_dict()
            assert await s.page.evaluate("window.__submitted === true") is False
            app = _status(app_id)
            assert app.status == "Ready for Final Approval"
            labels = [f["label"] for f in app.review["filled_fields"]]
            assert any("First Name" in l for l in labels) and app.review["resume_uploaded"] == "Data Analyst CV"
            assert any("Gender" in x["label"] for x in app.review["left_for_user"])
            assert "SQL" in await s.page.input_value("#sql")

            # 7) Explicit approval -> submit -> confirmation captured
            await s.approve_and_submit()
            assert s.state == "submitted", s.to_dict()
            app = _status(app_id)
            assert app.status == "Submitted"
            assert app.reference_id == "APP-48213"
            assert app.confirmation_url.endswith("thanks.html")
            assert app.confirmation_screenshot_key and app.submitted_at
        finally:
            await s.close()

    asyncio.run(run())


def test_captcha_pauses_for_human(portal_url):
    user_id, app_id = _setup(f"{portal_url}/captcha.html", "captcha@example.com")

    async def run():
        s = AutomationSession(app_id, user_id, headless=True)
        try:
            await s.start()
            assert s.state == "paused" and s.checkpoint.kind == "captcha"
            assert _status(app_id).status == "Verification Pending"
            # Approve & submit is refused unless at the final approval step
            try:
                await s.approve_and_submit()
                raise AssertionError("submit should be refused")
            except Exception as exc:
                assert "final approval" in str(exc)
        finally:
            await s.close()

    asyncio.run(run())


def test_field_classification():
    def c(label, type_="text", tag="input", name=""):
        return classify(Field(ref="x", tag=tag, type=type_, label=label, name=name))

    assert c("Password", "password").category == "password"
    assert c("Enter the 6-digit verification code").category == "otp"
    assert c("Gender", "select", "select").category == "sensitive"
    assert c("Are you a protected veteran?", "select", "select").category == "sensitive"
    assert c("I agree to the Terms of Service", "checkbox").category == "legal"
    assert c("Will you now or in the future require visa sponsorship?", "select", "select").category == "legal"
    assert (f := c("First name")).category == "profile" and f.profile_key == "first_name"
    assert c("Company name").profile_key == "current_company"
    assert c("Notice period").profile_key == "notice_period"
    assert c("Expected CTC").profile_key == "expected_ctc"
    assert c("Describe a challenging project you worked on and what you learned from it", "textarea", "textarea").category == "question"
    assert c("Resume", "file").category == "resume"
