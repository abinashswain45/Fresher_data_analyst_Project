"""Database models.

Sensitive candidate data (profile, resume content, resume text) is stored encrypted
with Fernet (see security.py). Passwords/OTPs for recruitment portals are NEVER stored.
"""
from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class ApplicationStatus(StrEnum):
    NEW = "New"
    ANALYZING = "Analyzing"
    RESUME_UPDATE_REQUIRED = "Resume Update Required"
    READY_FOR_APPLICATION = "Ready for Application"
    ACCOUNT_CREATION_REQUIRED = "Account Creation Required"
    VERIFICATION_PENDING = "Verification Pending"
    APPLICATION_IN_PROGRESS = "Application In Progress"
    READY_FOR_FINAL_APPROVAL = "Ready for Final Approval"
    SUBMITTED = "Submitted"
    INTERVIEW = "Interview"
    REJECTED = "Rejected"
    ON_HOLD = "On Hold"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    full_name: Mapped[str] = mapped_column(String(200), default="")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    profile: Mapped["CandidateProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    resumes: Mapped[list["Resume"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    applications: Mapped[list["Application"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class CandidateProfile(Base):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    data_enc: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    user: Mapped[User] = relationship(back_populates="profile")


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(120), default="General")
    kind: Mapped[str] = mapped_column(String(20), default="uploaded")  # uploaded | tailored
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(300), default="")
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    file_key: Mapped[str] = mapped_column(String(300), default="")  # encrypted original upload
    content_enc: Mapped[str] = mapped_column(Text, default="")  # structured resume JSON
    text_enc: Mapped[str] = mapped_column(Text, default="")  # raw extracted text
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship(back_populates="resumes")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("user_id", "normalized_url", name="uq_job_user_url"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(String(1000))
    apply_url: Mapped[str] = mapped_column(Text, default="")
    platform: Mapped[str] = mapped_column(String(50), default="generic")
    company: Mapped[str] = mapped_column(String(300), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    location: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[dict] = mapped_column(JSON, default=dict)
    fetch_method: Mapped[str] = mapped_column(String(40), default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship(back_populates="jobs")


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default=ApplicationStatus.NEW.value, index=True)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    review: Mapped[dict] = mapped_column(JSON, default=dict)  # snapshot of filled fields for final review
    reference_id: Mapped[str] = mapped_column(String(200), default="")
    confirmation_text: Mapped[str] = mapped_column(Text, default="")
    confirmation_url: Mapped[str] = mapped_column(Text, default="")
    confirmation_screenshot_key: Mapped[str] = mapped_column(String(300), default="")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    interview_status: Mapped[str] = mapped_column(String(120), default="")
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="applications")
    job: Mapped[Job] = relationship()
    resume: Mapped[Resume | None] = relationship()
    questions: Mapped[list["ApplicationQuestion"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationQuestion.id"
    )
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", order_by="ApplicationEvent.id"
    )


class ApplicationQuestion(Base):
    __tablename__ = "application_questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested | accepted | filled
    field_ref: Mapped[str] = mapped_column(String(100), default="")  # automation element reference
    field_type: Mapped[str] = mapped_column(String(30), default="textarea")
    options: Mapped[list] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(default=False)
    needs_user_input: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    application: Mapped[Application] = relationship(back_populates="questions")


class ApplicationEvent(Base):
    """Audit timeline. Never contains passwords, OTPs or other secrets."""

    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    application: Mapped[Application] = relationship(back_populates="events")
