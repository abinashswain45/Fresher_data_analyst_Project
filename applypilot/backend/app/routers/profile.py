from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CandidateProfile, Resume, User
from ..schemas import CandidateProfileData, ProfileOut
from ..security import get_current_user
from ..services.profile_service import completeness, load_profile, merge_profile, save_profile
from ..services.resume_service import resume_content

router = APIRouter(prefix="/api/profile", tags=["profile"])


def _out(db: Session, user: User) -> ProfileOut:
    data = load_profile(db, user.id)
    pct, missing = completeness(data)
    row = db.query(CandidateProfile).filter_by(user_id=user.id).first()
    return ProfileOut(data=data, completeness=pct, missing_fields=missing, updated_at=row.updated_at if row else None)


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(db, user)


@router.put("", response_model=ProfileOut)
def update_profile(body: CandidateProfileData, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    save_profile(db, user.id, body)
    if body.full_name and body.full_name != user.full_name:
        user.full_name = body.full_name
        db.commit()
    return _out(db, user)


@router.post("/import/{resume_id}", response_model=ProfileOut)
def import_from_resume(resume_id: int, overwrite: bool = False, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    resume = db.get(Resume, resume_id)
    if not resume or resume.user_id != user.id:
        raise HTTPException(404, "Resume not found")
    parsed = resume_content(resume)
    current = load_profile(db, user.id)
    data = parsed.model_copy(update={k: getattr(current, k) for k in (
        "notice_period", "current_ctc", "expected_ctc", "preferred_locations", "preferred_roles",
        "work_authorization", "willing_to_relocate")}) if overwrite else merge_profile(current, parsed)
    save_profile(db, user.id, data)
    return _out(db, user)
