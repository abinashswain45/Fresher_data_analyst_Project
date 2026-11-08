"""Pydantic schemas shared by the API and the AI layer."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ----------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    created_at: datetime


# ----------------------------------------------------------- candidate profile
class Experience(BaseModel):
    company: str = ""
    title: str = ""
    location: str = ""
    start_date: str = ""  # free text as written in the CV, e.g. "Jan 2022"
    end_date: str = ""  # "Present" for current role
    is_current: bool = False
    responsibilities: list[str] = Field(default_factory=list)


class Education(BaseModel):
    institution: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    link: str = ""


class Certification(BaseModel):
    name: str = ""
    issuer: str = ""
    date: str = ""


class CandidateProfileData(BaseModel):
    """The reusable candidate profile. Entered once, reused for every application."""

    full_name: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    linkedin_url: str = ""
    portfolio_url: str = ""
    professional_summary: str = ""
    total_experience_years: float | None = None
    current_company: str = ""
    current_title: str = ""
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    soft_skills: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    notice_period: str = ""
    current_ctc: str = ""
    expected_ctc: str = ""
    preferred_locations: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    work_authorization: str = ""
    willing_to_relocate: bool | None = None


class ProfileOut(BaseModel):
    data: CandidateProfileData
    completeness: int
    missing_fields: list[str]
    updated_at: datetime | None = None


# ----------------------------------------------------------------- resumes
class ResumeOut(BaseModel):
    id: int
    label: str
    category: str
    kind: str
    parent_id: int | None
    job_id: int | None
    original_filename: str
    is_default: bool
    created_at: datetime


class ResumeDetail(ResumeOut):
    content: CandidateProfileData
    text_preview: str


class ResumeUpdate(BaseModel):
    label: str | None = None
    category: str | None = None
    is_default: bool | None = None
    content: CandidateProfileData | None = None


# ------------------------------------------------------------------- jobs
class JobRequirements(BaseModel):
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    min_experience_years: float | None = None
    max_experience_years: float | None = None
    education_requirements: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    employment_type: str = ""
    seniority: str = ""
    hard_requirements: list[str] = Field(default_factory=list)  # e.g. work authorization, location constraints


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    url: str
    apply_url: str
    platform: str
    company: str
    title: str
    location: str
    description: str
    requirements: dict
    fetch_method: str
    fetched_at: datetime


class AnalyzeUrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    force: bool = False  # create a new application even if one exists for this URL
    manual_description: str | None = None  # paste JD when the site blocks fetching


# ---------------------------------------------------------- matching / tailoring
class MatchResult(BaseModel):
    score: int = Field(ge=0, le=100)
    eligible: bool
    summary: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    ineligibility_reasons: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    id: str = ""
    section: str  # summary | experience | skills | projects | formatting
    target_index: int | None = None  # index into experience/projects when relevant
    original: str = ""
    suggested: str
    reason: str
    keywords_added: list[str] = Field(default_factory=list)
    evidence: str = ""  # which part of the candidate's own data supports this change
    status: str = "pending"  # pending | approved | rejected
    flagged: bool = False  # true if the guardrail found unsupported claims


class RecommendationDecision(BaseModel):
    id: str
    status: str  # approved | rejected
    suggested: str | None = None  # user may edit the text before approving


class TailorIn(BaseModel):
    mode: str = "review"  # review (approve individually) | auto (apply all safe suggestions)
    decisions: list[RecommendationDecision] = Field(default_factory=list)
    label: str | None = None


# ---------------------------------------------------------------- applications
class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    question: str
    answer: str
    status: str
    field_type: str
    options: list
    required: bool
    needs_user_input: bool


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


class AnswerUpdate(BaseModel):
    answer: str = Field(max_length=10000)
    status: str = "accepted"


class RegenerateIn(BaseModel):
    style: str = "default"  # default | shorter | more_professional | more_detailed


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    message: str
    created_at: datetime


class ApplicationSummary(BaseModel):
    id: int
    job_id: int
    company: str
    title: str
    job_url: str
    platform: str
    status: str
    match_score: float | None
    resume_id: int | None
    resume_label: str
    reference_id: str
    interview_status: str
    follow_up_date: date | None
    notes: str
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApplicationDetail(ApplicationSummary):
    job: JobOut
    match: dict
    recommendations: list
    review: dict
    confirmation_text: str
    confirmation_url: str
    has_confirmation_screenshot: bool
    questions: list[QuestionOut]
    events: list[EventOut]


class ApplicationUpdate(BaseModel):
    status: str | None = None
    resume_id: int | None = None
    interview_status: str | None = None
    follow_up_date: date | None = None
    notes: str | None = None
    reference_id: str | None = None


class ManualSubmitIn(BaseModel):
    reference_id: str = ""
    confirmation_text: str = ""
    confirmation_url: str = ""


TokenOut.model_rebuild()
