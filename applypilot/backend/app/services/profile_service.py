from sqlalchemy.orm import Session

from ..models import CandidateProfile
from ..schemas import CandidateProfileData
from ..security import decrypt_json, encrypt_json

REQUIRED_FIELDS = {
    "full_name": "Full name",
    "email": "Email address",
    "phone": "Mobile number",
    "location": "Current location",
    "linkedin_url": "LinkedIn profile",
    "professional_summary": "Professional summary",
    "total_experience_years": "Total work experience",
    "experience": "Employment history",
    "technical_skills": "Technical skills",
    "education": "Education",
    "notice_period": "Notice period",
    "expected_ctc": "Expected CTC",
    "preferred_locations": "Preferred locations",
    "preferred_roles": "Preferred job roles",
}


def load_profile(db: Session, user_id: int) -> CandidateProfileData:
    row = db.query(CandidateProfile).filter_by(user_id=user_id).first()
    if not row or not row.data_enc:
        return CandidateProfileData()
    return CandidateProfileData(**decrypt_json(row.data_enc, {}))


def save_profile(db: Session, user_id: int, data: CandidateProfileData) -> CandidateProfile:
    row = db.query(CandidateProfile).filter_by(user_id=user_id).first()
    if row is None:
        row = CandidateProfile(user_id=user_id)
        db.add(row)
    row.data_enc = encrypt_json(data.model_dump())
    db.commit()
    db.refresh(row)
    return row


def merge_profile(existing: CandidateProfileData, parsed: CandidateProfileData) -> CandidateProfileData:
    """Fill empty profile fields from a parsed CV without overwriting what the user entered."""
    merged = existing.model_dump()
    for key, value in parsed.model_dump().items():
        current = merged.get(key)
        if current in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    return CandidateProfileData(**merged)


def completeness(data: CandidateProfileData) -> tuple[int, list[str]]:
    d = data.model_dump()
    missing = [label for key, label in REQUIRED_FIELDS.items() if d.get(key) in (None, "", [], {})]
    pct = round(100 * (len(REQUIRED_FIELDS) - len(missing)) / len(REQUIRED_FIELDS))
    return pct, missing
