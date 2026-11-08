import asyncio
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Resume, User
from ..schemas import ResumeDetail, ResumeOut, ResumeUpdate
from ..security import decrypt_json, encrypt_json, get_current_user
from ..services import storage
from ..services.ai import ai_service
from ..services.cv_parser import DOCX_MIME, PDF_MIME, CVParseError, detect_type, extract_text
from ..services.profile_service import load_profile, merge_profile, save_profile
from ..services.resume_service import resume_content, resume_file

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _out(r: Resume) -> ResumeOut:
    return ResumeOut(id=r.id, label=r.label, category=r.category, kind=r.kind, parent_id=r.parent_id, job_id=r.job_id,
                     original_filename=r.original_filename, is_default=r.is_default, created_at=r.created_at)


def _owned(db: Session, user: User, resume_id: int) -> Resume:
    r = db.get(Resume, resume_id)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "Resume not found")
    return r


def _set_default(db: Session, user: User, resume: Resume) -> None:
    for other in db.query(Resume).filter_by(user_id=user.id, is_default=True):
        other.is_default = False
    resume.is_default = True


@router.post("", response_model=ResumeDetail, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    label: str = Form(""),
    category: str = Form("General"),
    update_profile: bool = Form(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File too large (max {s.max_upload_mb} MB)")
    filename = (file.filename or "resume").replace("/", "_").replace("\\", "_")[:200]
    try:
        kind = detect_type(filename, data)
        text = await asyncio.to_thread(extract_text, filename, data)
    except CVParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    parsed, mode = await asyncio.to_thread(ai_service.parse_cv, text)
    key = storage.save(user.id, data, kind)
    is_first = db.query(Resume).filter_by(user_id=user.id).count() == 0
    resume = Resume(
        user_id=user.id, label=label.strip() or filename.rsplit(".", 1)[0], category=category.strip() or "General",
        kind="uploaded", original_filename=filename, mime_type=PDF_MIME if kind == "pdf" else DOCX_MIME,
        file_key=key, content_enc=encrypt_json(parsed.model_dump()), text_enc=encrypt_json(text),
    )
    db.add(resume)
    if is_first:
        _set_default(db, user, resume)
    db.commit()
    db.refresh(resume)
    if update_profile:
        save_profile(db, user.id, merge_profile(load_profile(db, user.id), parsed))
    return ResumeDetail(**_out(resume).model_dump(), content=parsed, text_preview=text[:3000] + f"\n\n[parsed: {mode}]")


@router.get("", response_model=list[ResumeOut])
def list_resumes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_out(r) for r in db.query(Resume).filter_by(user_id=user.id).order_by(Resume.created_at.desc())]


@router.get("/{resume_id}", response_model=ResumeDetail)
def get_resume(resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _owned(db, user, resume_id)
    text = decrypt_json(r.text_enc, "") or ""
    return ResumeDetail(**_out(r).model_dump(), content=resume_content(r), text_preview=text[:3000])


@router.patch("/{resume_id}", response_model=ResumeDetail)
def update_resume(resume_id: int, body: ResumeUpdate, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    r = _owned(db, user, resume_id)
    if body.label is not None:
        r.label = body.label.strip()[:200] or r.label
    if body.category is not None:
        r.category = body.category.strip()[:120] or "General"
    if body.content is not None:
        r.content_enc = encrypt_json(body.content.model_dump())
    if body.is_default:
        _set_default(db, user, r)
    db.commit()
    return get_resume(resume_id, user, db)


@router.delete("/{resume_id}", status_code=204)
def delete_resume(resume_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = _owned(db, user, resume_id)
    storage.delete(r.file_key)
    db.delete(r)
    db.commit()


@router.get("/{resume_id}/download")
def download_resume(resume_id: int, format: str = "pdf", user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    r = _owned(db, user, resume_id)
    try:
        name, data, mime = resume_file(r, format)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(data, media_type=mime, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}", "Cache-Control": "no-store"})
