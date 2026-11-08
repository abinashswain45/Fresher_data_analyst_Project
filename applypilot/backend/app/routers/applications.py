import asyncio
from collections import Counter
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Application, ApplicationEvent, ApplicationQuestion, ApplicationStatus, Job, Resume, User
from ..schemas import (
    AnalyzeUrlIn,
    AnswerUpdate,
    ApplicationDetail,
    ApplicationSummary,
    ApplicationUpdate,
    EventOut,
    JobOut,
    ManualSubmitIn,
    QuestionIn,
    QuestionOut,
    Recommendation,
    RegenerateIn,
    TailorIn,
)
from ..security import encrypt_json, get_current_user
from ..services import storage
from ..services.ai import ai_service
from ..services.analysis import run_analysis
from ..services.job_fetcher import detect_platform, normalize_url
from ..services.profile_service import load_profile
from ..services.resume_service import apply_recommendations, resume_content

router = APIRouter(prefix="/api/applications", tags=["applications"])
VALID_STATUSES = {s.value for s in ApplicationStatus}


def owned_app(db: Session, user: User, app_id: int) -> Application:
    app = db.get(Application, app_id)
    if not app or app.user_id != user.id:
        raise HTTPException(404, "Application not found")
    return app


def summary(app: Application) -> ApplicationSummary:
    return ApplicationSummary(
        id=app.id, job_id=app.job_id, company=app.job.company, title=app.job.title, job_url=app.job.url,
        platform=app.job.platform, status=app.status, match_score=app.match_score, resume_id=app.resume_id,
        resume_label=app.resume.label if app.resume else "", reference_id=app.reference_id,
        interview_status=app.interview_status, follow_up_date=app.follow_up_date, notes=app.notes,
        submitted_at=app.submitted_at, created_at=app.created_at, updated_at=app.updated_at,
    )


def detail(app: Application) -> ApplicationDetail:
    return ApplicationDetail(
        **summary(app).model_dump(), job=JobOut.model_validate(app.job), match=app.match or {},
        recommendations=app.recommendations or [], review=app.review or {},
        confirmation_text=app.confirmation_text, confirmation_url=app.confirmation_url,
        has_confirmation_screenshot=bool(app.confirmation_screenshot_key),
        questions=[QuestionOut.model_validate(q) for q in app.questions],
        events=[EventOut.model_validate(e) for e in app.events][-50:],
    )


def _event(db: Session, app: Application, kind: str, msg: str) -> None:
    db.add(ApplicationEvent(application_id=app.id, kind=kind, message=msg))


# --------------------------------------------------------------- analyse URL
@router.post("/analyze", response_model=ApplicationDetail, status_code=202)
async def analyze_url(body: AnalyzeUrlIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    url = body.url.strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    norm = normalize_url(url)
    job = db.query(Job).filter_by(user_id=user.id, normalized_url=norm).first()
    if job:
        existing = db.query(Application).filter_by(user_id=user.id, job_id=job.id).order_by(Application.id.desc()).first()
        if existing and not body.force:
            raise HTTPException(409, {
                "message": f"You already have an application for this job (status: {existing.status}).",
                "application_id": existing.id, "status": existing.status})
    else:
        job = Job(user_id=user.id, url=url, normalized_url=norm, platform=detect_platform(url), apply_url=url)
        db.add(job)
        db.flush()
    app = Application(user_id=user.id, job_id=job.id, status=ApplicationStatus.ANALYZING.value)
    db.add(app)
    db.flush()
    _event(db, app, "created", f"Analysing {url}")
    db.commit()
    db.refresh(app)
    asyncio.create_task(run_analysis(app.id, url, body.manual_description))
    return detail(app)


@router.post("/{app_id}/reanalyze", response_model=ApplicationDetail, status_code=202)
async def reanalyze(app_id: int, body: AnalyzeUrlIn | None = None, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    if app.status == ApplicationStatus.SUBMITTED.value:
        raise HTTPException(400, "This application was already submitted")
    app.status = ApplicationStatus.ANALYZING.value
    app.match = {}
    _event(db, app, "analysis", "Re-analysis requested")
    db.commit()
    asyncio.create_task(run_analysis(app.id, app.job.url, body.manual_description if body else None))
    return detail(app)


# ----------------------------------------------------------------- tracking
@router.get("", response_model=list[ApplicationSummary])
def list_applications(
    status: str | None = None, q: str | None = None, platform: str | None = None,
    sort: str = Query("updated", pattern="^(updated|created|score|company)$"),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    query = db.query(Application).join(Job).filter(Application.user_id == user.id)
    if status:
        query = query.filter(Application.status.in_(status.split(",")))
    if platform:
        query = query.filter(Job.platform == platform)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Job.company.ilike(like), Job.title.ilike(like), Application.notes.ilike(like),
                                 Application.reference_id.ilike(like)))
    order = {"updated": Application.updated_at.desc(), "created": Application.created_at.desc(),
             "score": Application.match_score.desc(), "company": Job.company.asc()}[sort]
    return [summary(a) for a in query.order_by(order).limit(500)]


@router.get("/stats")
def stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apps = db.query(Application).filter_by(user_id=user.id).all()
    by_status = Counter(a.status for a in apps)
    scores = [a.match_score for a in apps if a.match_score is not None]
    today = datetime.now(UTC).date()
    return {
        "total": len(apps),
        "by_status": {s.value: by_status.get(s.value, 0) for s in ApplicationStatus},
        "submitted": by_status.get("Submitted", 0) + by_status.get("Interview", 0) + by_status.get("Rejected", 0),
        "interviews": by_status.get("Interview", 0),
        "in_progress": sum(by_status.get(s, 0) for s in (
            "Analyzing", "Resume Update Required", "Ready for Application", "Account Creation Required",
            "Verification Pending", "Application In Progress", "Ready for Final Approval")),
        "average_match": round(sum(scores) / len(scores)) if scores else None,
        "follow_ups_due": sum(1 for a in apps if a.follow_up_date and a.follow_up_date <= today
                              and a.status not in ("Rejected",)),
    }


@router.get("/{app_id}", response_model=ApplicationDetail)
def get_application(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return detail(owned_app(db, user, app_id))


@router.patch("/{app_id}", response_model=ApplicationDetail)
def update_application(app_id: int, body: ApplicationUpdate, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(400, "Invalid status")
        if body.status == ApplicationStatus.SUBMITTED.value and app.status != body.status:
            raise HTTPException(400, "Use the final approval or manual-submit workflow to mark as submitted")
        _event(db, app, "status", f"Status changed to {body.status}")
        app.status = body.status
    if body.resume_id is not None:
        r = db.get(Resume, body.resume_id)
        if not r or r.user_id != user.id:
            raise HTTPException(404, "Resume not found")
        app.resume_id = r.id
    for f in ("interview_status", "follow_up_date", "notes", "reference_id"):
        v = getattr(body, f)
        if v is not None:
            setattr(app, f, v)
    db.commit()
    return detail(app)


@router.delete("/{app_id}", status_code=204)
def delete_application(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    storage.delete(app.confirmation_screenshot_key)
    db.delete(app)
    db.commit()


# ------------------------------------------------------------ resume tailoring
@router.post("/{app_id}/tailor", response_model=ApplicationDetail)
def tailor_resume(app_id: int, body: TailorIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create a tailored resume version from approved recommendations (mode=review) or all
    guardrail-clean recommendations (mode=auto). The user still reviews/approves the result."""
    app = owned_app(db, user, app_id)
    base_id = (app.match or {}).get("recommended_resume_id") or app.resume_id
    base = db.get(Resume, base_id) if base_id else None
    if not base or base.user_id != user.id:
        raise HTTPException(400, "Upload a resume first")
    recs = [Recommendation(**r) for r in (app.recommendations or [])]
    decisions = {d.id: d for d in body.decisions}
    for r in recs:
        if body.mode == "auto":
            r.status = "approved" if not r.flagged else "rejected"
        elif r.id in decisions:
            d = decisions[r.id]
            r.status = d.status if d.status in ("approved", "rejected") else "pending"
            if d.suggested is not None and d.suggested.strip():
                r.suggested = d.suggested.strip()
    content, applied = apply_recommendations(resume_content(base), recs)
    label = body.label or f"{app.job.company or 'Job'} – {app.job.title or 'Tailored'}"[:200]
    tailored = Resume(user_id=user.id, label=label, category=base.category, kind="tailored", parent_id=base.id,
                      job_id=app.job_id, content_enc=encrypt_json(content.model_dump()), text_enc=base.text_enc)
    db.add(tailored)
    db.flush()
    app.recommendations = [r.model_dump() for r in recs]
    app.resume_id = tailored.id
    _event(db, app, "resume", f"Tailored resume '{label}' created with {len(applied)} approved change(s). Review it before applying.")
    db.commit()
    return detail(app)


@router.post("/{app_id}/approve-resume", response_model=ApplicationDetail)
def approve_resume(app_id: int, resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    r = db.get(Resume, resume_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Resume not found")
    app.resume_id = r.id
    if app.status in (ApplicationStatus.NEW.value, ApplicationStatus.RESUME_UPDATE_REQUIRED.value,
                      ApplicationStatus.ON_HOLD.value, ApplicationStatus.ANALYZING.value):
        app.status = ApplicationStatus.READY_FOR_APPLICATION.value
    _event(db, app, "approval", f"User approved resume version '{r.label}' for this application")
    db.commit()
    return detail(app)


@router.post("/{app_id}/recommendations/regenerate", response_model=ApplicationDetail)
async def regenerate_recommendations(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..schemas import JobRequirements, MatchResult

    app = owned_app(db, user, app_id)
    base_id = (app.match or {}).get("recommended_resume_id") or app.resume_id
    base = db.get(Resume, base_id) if base_id else None
    candidate = resume_content(base) if base else load_profile(db, user.id)
    reqs = JobRequirements(**{k: v for k, v in (app.job.requirements or {}).items() if k in JobRequirements.model_fields})
    m = app.match or {}
    match = MatchResult(**{k: m[k] for k in MatchResult.model_fields if k in m}) if "score" in m else MatchResult(
        score=0, eligible=True, summary="")
    recs, _ = await asyncio.to_thread(ai_service.recommend, candidate, app.job.title, app.job.company,
                                      app.job.description, reqs, match)
    app.recommendations = [r.model_dump() for r in recs]
    db.commit()
    return detail(app)


# ------------------------------------------------------------ questions
def _owned_question(db: Session, app: Application, qid: int) -> ApplicationQuestion:
    q = db.get(ApplicationQuestion, qid)
    if not q or q.application_id != app.id:
        raise HTTPException(404, "Question not found")
    return q


@router.post("/{app_id}/questions", response_model=QuestionOut, status_code=201)
async def add_question(app_id: int, body: QuestionIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    profile = load_profile(db, user.id)
    res = await asyncio.to_thread(ai_service.answer_question, body.question, profile, app.job.company,
                                  app.job.title, app.job.description)
    q = ApplicationQuestion(application_id=app.id, question=body.question.strip(), answer=res["answer"],
                            needs_user_input=bool(res.get("needs_user_input")), field_type="textarea")
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


@router.put("/{app_id}/questions/{qid}", response_model=QuestionOut)
def update_answer(app_id: int, qid: int, body: AnswerUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    q = _owned_question(db, app, qid)
    if q.options and body.answer and body.answer not in q.options:
        raise HTTPException(400, "Choose one of the available options")
    q.answer = body.answer
    q.status = body.status if body.status in ("suggested", "accepted") else "accepted"
    if q.status == "accepted":
        q.needs_user_input = False
    db.commit()
    return q


@router.post("/{app_id}/questions/accept-all", response_model=list[QuestionOut])
def accept_all(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    for q in app.questions:
        if q.status == "suggested" and q.answer and not q.needs_user_input:
            q.status = "accepted"
    db.commit()
    return [QuestionOut.model_validate(q) for q in app.questions]


@router.post("/{app_id}/questions/{qid}/regenerate", response_model=QuestionOut)
async def regenerate_answer(app_id: int, qid: int, body: RegenerateIn, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    q = _owned_question(db, app, qid)
    profile = load_profile(db, user.id)
    if q.options:
        q.answer = await asyncio.to_thread(ai_service.choose_option, q.question, q.options, profile)
        q.needs_user_input = not q.answer
    else:
        res = await asyncio.to_thread(ai_service.answer_question, q.question, profile, app.job.company, app.job.title,
                                      app.job.description, body.style, q.answer)
        q.answer, q.needs_user_input = res["answer"], bool(res.get("needs_user_input"))
    if q.status != "filled":
        q.status = "suggested"
    db.commit()
    return q


@router.delete("/{app_id}/questions/{qid}", status_code=204)
def delete_question(app_id: int, qid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    db.delete(_owned_question(db, app, qid))
    db.commit()


# ------------------------------------------------------- manual workflow
@router.get("/{app_id}/manual-guide")
def manual_guide(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Copy-ready values for sites that do not permit automation."""
    from ..automation.fields import profile_value

    app = owned_app(db, user, app_id)
    p = load_profile(db, user.id)
    keys = ["first_name", "last_name", "email", "phone", "location", "linkedin_url", "portfolio_url",
            "current_company", "current_title", "total_experience_years", "notice_period", "current_ctc",
            "expected_ctc", "institution", "degree", "field_of_study", "graduation_year", "technical_skills"]
    return {
        "job_url": app.job.apply_url or app.job.url,
        "resume_download": f"/api/resumes/{app.resume_id}/download?format=pdf" if app.resume_id else None,
        "fields": [{"key": k, "label": k.replace("_", " ").title(), "value": profile_value(k, p)} for k in keys],
        "experience": [e.model_dump() for e in p.experience],
        "education": [e.model_dump() for e in p.education],
        "answers": [{"question": q.question, "answer": q.answer} for q in app.questions],
        "steps": [
            "Open the official job page using the link above and click Apply.",
            "Sign in or create your account on the portal (you choose the password).",
            "Complete any OTP / CAPTCHA verification yourself.",
            "Upload the approved resume (download it above).",
            "Copy each value below into the matching field.",
            "Answer voluntary disclosures and legal declarations yourself.",
            "Review everything and submit on the portal.",
            "Come back and click 'Mark as submitted' with the reference number.",
        ],
    }


@router.post("/{app_id}/manual-submit", response_model=ApplicationDetail)
def manual_submit(app_id: int, body: ManualSubmitIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    app.status = ApplicationStatus.SUBMITTED.value
    app.submitted_at = app.submitted_at or datetime.now(UTC)
    app.reference_id = body.reference_id or app.reference_id
    app.confirmation_text = body.confirmation_text or app.confirmation_text
    app.confirmation_url = body.confirmation_url or app.confirmation_url
    _event(db, app, "submitted", f"Marked as submitted by user. Reference: {app.reference_id or 'n/a'}")
    db.commit()
    return detail(app)


@router.get("/{app_id}/confirmation-screenshot")
def confirmation_screenshot(app_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = owned_app(db, user, app_id)
    if not app.confirmation_screenshot_key:
        raise HTTPException(404, "No confirmation screenshot")
    return Response(storage.load(app.confirmation_screenshot_key), media_type="image/png",
                    headers={"Cache-Control": "no-store"})
