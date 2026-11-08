"""Resume versions: tailoring (applying approved recommendations) and file generation."""
from __future__ import annotations

import re

from ..models import Resume
from ..schemas import CandidateProfileData, Recommendation
from ..security import decrypt_json
from . import storage
from .cv_parser import DOCX_MIME, PDF_MIME
from .resume_render import render_docx, render_pdf


def resume_content(resume: Resume) -> CandidateProfileData:
    return CandidateProfileData(**decrypt_json(resume.content_enc, {}))


def _safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")[:60] or "Resume"


def resume_file(resume: Resume, fmt: str) -> tuple[str, bytes, str]:
    """Return (filename, bytes, mime) for download. fmt: pdf | docx | original."""
    content = resume_content(resume)
    base = _safe_name(f"{content.full_name or 'Resume'}_{resume.label}")
    if fmt == "original":
        if not resume.file_key:
            raise ValueError("This version has no original upload")
        return resume.original_filename or f"{base}.bin", storage.load(resume.file_key), resume.mime_type
    if fmt == "docx":
        return f"{base}.docx", render_docx(content), DOCX_MIME
    if fmt == "pdf":
        return f"{base}.pdf", render_pdf(content), PDF_MIME
    raise ValueError("Unsupported format")


def resume_file_for_upload(resume: Resume) -> tuple[str, bytes]:
    """The file the automation uploads: the user's original CV if untouched, else the tailored PDF."""
    if resume.kind == "uploaded" and resume.file_key:
        name, data, _ = resume_file(resume, "original")
        return _safe_name(name.rsplit(".", 1)[0]) + "." + (name.rsplit(".", 1)[-1] if "." in name else "pdf"), data
    name, data, _ = resume_file(resume, "pdf")
    return name, data


def apply_recommendations(base: CandidateProfileData, recs: list[Recommendation]) -> tuple[CandidateProfileData, list[str]]:
    """Apply approved recommendations to a copy of the resume content. Returns (content, applied_ids)."""
    data = base.model_copy(deep=True)
    applied: list[str] = []
    corpus_skills = {s.lower(): s for s in base.technical_skills + base.soft_skills}
    for r in recs:
        if r.status != "approved" or r.section == "formatting":
            continue
        if r.section == "summary":
            data.professional_summary = r.suggested.strip()
            applied.append(r.id)
        elif r.section == "skills":
            proposed = [s.strip() for s in re.split(r"[,;\n]", r.suggested) if s.strip()]
            # Guardrail: only skills the candidate already has can be kept
            ordered = [corpus_skills[s.lower()] for s in proposed if s.lower() in corpus_skills]
            if ordered:
                rest = [s for s in base.technical_skills if s not in ordered]
                data.technical_skills = list(dict.fromkeys([s for s in ordered if s in base.technical_skills] + rest))
                applied.append(r.id)
        elif r.section == "experience" and data.experience:
            idx = r.target_index if r.target_index is not None and 0 <= r.target_index < len(data.experience) else None
            targets = [idx] if idx is not None else range(len(data.experience))
            done = False
            for i in targets:
                bullets = data.experience[i].responsibilities
                for j, b in enumerate(bullets):
                    if r.original and (b.strip() == r.original.strip() or r.original.strip() in b):
                        bullets[j] = r.suggested.strip()
                        done = True
                        break
                if done:
                    break
            if not done and idx is not None:
                data.experience[idx].responsibilities.append(r.suggested.strip())
                done = True
            if done:
                applied.append(r.id)
        elif r.section == "projects" and data.projects:
            idx = r.target_index if r.target_index is not None and 0 <= r.target_index < len(data.projects) else None
            if idx is None and r.original:
                idx = next((i for i, p in enumerate(data.projects) if r.original in p.description), None)
            if idx is not None:
                data.projects[idx].description = r.suggested.strip()
                applied.append(r.id)
    return data, applied
