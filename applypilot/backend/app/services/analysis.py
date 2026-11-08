"""Job URL analysis pipeline: fetch -> extract requirements -> match -> pick resume -> recommendations."""
from __future__ import annotations

import asyncio
import logging

from ..db import SessionLocal
from ..models import Application, ApplicationEvent, ApplicationStatus, Job, Resume
from ..schemas import CandidateProfileData, JobRequirements, MatchResult
from .ai import ai_service, profile_corpus
from .job_fetcher import FetchedJob, JobFetchError, detect_platform, fetch_job
from .profile_service import load_profile
from .resume_service import resume_content

log = logging.getLogger("applypilot.analysis")
_running: set[int] = set()


def _event(db, app_id: int, kind: str, message: str) -> None:
    db.add(ApplicationEvent(application_id=app_id, kind=kind, message=message))


def pick_resume(resumes: list[Resume], reqs: JobRequirements, job_title: str) -> tuple[Resume | None, str]:
    """Choose the resume version whose content best covers the job's keywords."""
    if not resumes:
        return None, "No resume uploaded yet."
    keywords = [k.lower() for k in (reqs.required_skills + reqs.preferred_skills + reqs.keywords)]
    best, best_score = None, -1.0
    for r in resumes:
        content = resume_content(r)
        corpus = profile_corpus(content)
        hits = sum(1 for k in set(keywords) if k in corpus)
        score = hits + (0.5 if r.category.lower() in job_title.lower() else 0) + (0.25 if r.is_default else 0)
        if score > best_score:
            best, best_score = r, score
    covered = int(best_score) if best_score > 0 else 0
    return best, f"'{best.label}' covers {covered} of {len(set(keywords))} job keywords - the best of your {len(resumes)} version(s)."


async def run_analysis(app_id: int, url: str, manual_description: str | None = None) -> None:
    if app_id in _running:
        return
    _running.add(app_id)
    try:
        await _run(app_id, url, manual_description)
    except Exception as exc:  # never leave an application stuck in "Analyzing"
        log.exception("Analysis failed")
        with SessionLocal() as db:
            app = db.get(Application, app_id)
            if app:
                app.status = ApplicationStatus.ON_HOLD.value
                app.match = {**(app.match or {}), "error": f"Analysis failed: {exc}"}
                _event(db, app_id, "error", f"Analysis failed: {exc}")
                db.commit()
    finally:
        _running.discard(app_id)


async def _run(app_id: int, url: str, manual_description: str | None) -> None:
    with SessionLocal() as db:
        app = db.get(Application, app_id)
        user_id, job_id = app.user_id, app.job_id
        profile: CandidateProfileData = load_profile(db, user_id)

    # 1. fetch the official job posting
    if manual_description:
        fetched = FetchedJob(url=url, apply_url=url, platform=detect_platform(url), description=manual_description,
                             method="manual")
    else:
        try:
            fetched = await fetch_job(url)
        except JobFetchError as exc:
            with SessionLocal() as db:
                app = db.get(Application, app_id)
                app.status = ApplicationStatus.ON_HOLD.value
                app.match = {"error": str(exc), "needs_manual_description": True}
                _event(db, app_id, "error", str(exc))
                db.commit()
            return

    # 2. analyse JD
    job_ai, mode = await asyncio.to_thread(ai_service.analyze_job, fetched.title, fetched.company, fetched.location,
                                           fetched.description)
    reqs = job_ai.requirements
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.company = job_ai.company or fetched.company
        job.title = job_ai.title or fetched.title
        job.location = job_ai.location or fetched.location
        job.description = fetched.description
        job.apply_url = fetched.apply_url or url
        job.platform = fetched.platform
        job.fetch_method = fetched.method
        job.requirements = {**reqs.model_dump(), "portal_questions": fetched.extra.get("questions", [])}
        _event(db, app_id, "analysis", f"Job extracted via {fetched.method}: {job.title} at {job.company} ({mode})")
        db.commit()
        title, company, description = job.title, job.company, job.description
        resumes = db.query(Resume).filter_by(user_id=user_id).order_by(Resume.created_at.desc()).all()

    # 3. pick resume version, match against it (falls back to the profile)
    chosen, why = pick_resume(resumes, reqs, title)
    candidate = profile
    if chosen is not None:
        content = resume_content(chosen)
        # contact details/compensation come from the profile; experience/skills from the chosen version
        # Profile-only facts always come from the profile; empty resume fields are filled from it.
        update = {k: getattr(profile, k) for k in (
            "notice_period", "current_ctc", "expected_ctc", "preferred_locations", "preferred_roles",
            "work_authorization", "willing_to_relocate")}
        for k, v in profile.model_dump().items():
            if getattr(content, k) in (None, "", []) and v not in (None, "", []):
                update.setdefault(k, getattr(profile, k))
        candidate = content.model_copy(update=update)
    match: MatchResult
    match, mmode = await asyncio.to_thread(ai_service.match, candidate, title, description, reqs)

    # 4. recommendations
    recs, rmode = await asyncio.to_thread(ai_service.recommend, candidate, title, company, description, reqs, match)

    with SessionLocal() as db:
        app = db.get(Application, app_id)
        app.match_score = match.score
        app.match = {**match.model_dump(), "mode": mmode, "recommended_resume_id": chosen.id if chosen else None,
                     "resume_reason": why}
        app.recommendations = [r.model_dump() for r in recs]
        if not match.eligible:
            app.status = ApplicationStatus.ON_HOLD.value
            _event(db, app_id, "analysis", "Not eligible: " + "; ".join(match.ineligibility_reasons))
        elif chosen is None:
            app.status = ApplicationStatus.RESUME_UPDATE_REQUIRED.value
            _event(db, app_id, "analysis", "Upload a resume to continue")
        else:
            app.status = ApplicationStatus.RESUME_UPDATE_REQUIRED.value
            _event(db, app_id, "analysis", f"Match score {match.score}/100. {len(recs)} resume recommendations ready.")
        db.commit()
