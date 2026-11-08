import json
from datetime import UTC, datetime
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..automation.adapters import list_adapters
from ..automation.engine import manager
from ..config import get_settings
from ..db import get_db
from ..models import Application, ApplicationStatus, Resume, User
from ..security import decrypt_json, get_current_user, verify_password
from ..services import storage
from ..services.profile_service import load_profile

router = APIRouter(prefix="/api", tags=["account"])

COMPANY_PORTALS = [
    {"company": "PwC", "url": "https://www.pwc.in/careers.html"},
    {"company": "Deloitte", "url": "https://www2.deloitte.com/in/en/careers.html"},
    {"company": "EY", "url": "https://careers.ey.com/"},
    {"company": "KPMG", "url": "https://kpmg.com/in/en/careers.html"},
    {"company": "Accenture", "url": "https://www.accenture.com/in-en/careers/jobsearch?jk={q}&jl={loc}"},
    {"company": "TCS", "url": "https://www.tcs.com/careers"},
    {"company": "Infosys", "url": "https://www.infosys.com/careers/"},
    {"company": "Wipro", "url": "https://careers.wipro.com/"},
    {"company": "L&T", "url": "https://www.larsentoubro.com/corporate/careers/"},
    {"company": "Amazon", "url": "https://www.amazon.jobs/en/search?base_query={q}&loc_query={loc}"},
    {"company": "Microsoft", "url": "https://jobs.careers.microsoft.com/global/en/search?q={q}&lc={loc}"},
]
JOB_BOARDS = [
    {"name": "LinkedIn Jobs", "url": "https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}"},
    {"name": "Naukri", "url": "https://www.naukri.com/{slug}-jobs-in-{locslug}"},
    {"name": "Indeed India", "url": "https://in.indeed.com/jobs?q={q}&l={loc}"},
    {"name": "Google Jobs", "url": "https://www.google.com/search?q={q}+jobs+{loc}&ibp=htl;jobs"},
]


@router.get("/meta")
def meta():
    s = get_settings()
    return {"app": s.app_name, "ai_enabled": s.ai_enabled, "ai_model": s.ai_model if s.ai_enabled else None,
            "automation_headless": s.automation_headless, "adapters": list_adapters(),
            "statuses": [x.value for x in ApplicationStatus]}


@router.get("/discovery")
def discovery(role: str = "", location: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Search links on official career portals and job boards built from the saved preferences.
    ApplyPilot does not scrape job boards; open a posting and paste its URL into New Application."""
    p = load_profile(db, user.id)
    roles = [role] if role else (p.preferred_roles or ([p.current_title] if p.current_title else ["Data Analyst"]))
    locs = [location] if location else (p.preferred_locations or ([p.location] if p.location else [""]))
    out = []
    for r in roles[:5]:
        for loc in locs[:3]:
            fmt = dict(q=quote_plus(r), loc=quote_plus(loc), slug=r.lower().replace(" ", "-"),
                       locslug=(loc.lower().replace(" ", "-") or "india"))
            out.append({
                "role": r, "location": loc,
                "boards": [{"name": b["name"], "url": b["url"].format(**fmt)} for b in JOB_BOARDS],
                "companies": [{"company": c["company"], "url": c["url"].format(**fmt)} for c in COMPANY_PORTALS],
            })
    return {"searches": out}


@router.get("/account/export")
def export_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    resumes = db.query(Resume).filter_by(user_id=user.id).all()
    apps = db.query(Application).filter_by(user_id=user.id).all()
    payload = {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {"email": user.email, "full_name": user.full_name, "created_at": user.created_at.isoformat()},
        "profile": load_profile(db, user.id).model_dump(),
        "resumes": [{"id": r.id, "label": r.label, "category": r.category, "kind": r.kind,
                     "created_at": r.created_at.isoformat(), "content": decrypt_json(r.content_enc, {})} for r in resumes],
        "applications": [{
            "id": a.id, "company": a.job.company, "title": a.job.title, "url": a.job.url, "status": a.status,
            "match_score": a.match_score, "reference_id": a.reference_id, "notes": a.notes,
            "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
            "created_at": a.created_at.isoformat(),
            "questions": [{"question": q.question, "answer": q.answer} for q in a.questions],
            "events": [{"kind": e.kind, "message": e.message, "at": e.created_at.isoformat()} for e in a.events],
        } for a in apps],
    }
    return Response(json.dumps(payload, indent=2, default=str), media_type="application/json",
                    headers={"Content-Disposition": "attachment; filename=applypilot-export.json",
                             "Cache-Control": "no-store"})


class DeleteIn(BaseModel):
    password: str


@router.post("/account/delete", status_code=204)
async def delete_account(body: DeleteIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(403, "Password is incorrect")
    await manager.stop_user(user.id)
    storage.delete_user(user.id)
    db.delete(user)
    db.commit()
