"""CV text extraction (PDF / DOCX) and a heuristic structured parser.

The heuristic parser is used when no AI key is configured, and as a safety net that
pre-fills contact details deterministically.
"""
import io
import re

from docx import Document
from pypdf import PdfReader

from ..schemas import CandidateProfileData, Education, Experience

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class CVParseError(ValueError):
    pass


def detect_type(filename: str, data: bytes) -> str:
    name = filename.lower()
    if data[:5] == b"%PDF-" or name.endswith(".pdf"):
        return "pdf"
    if data[:2] == b"PK" and name.endswith(".docx"):
        return "docx"
    raise CVParseError("Unsupported file type. Please upload a PDF or DOCX file.")


def extract_text(filename: str, data: bytes) -> str:
    kind = detect_type(filename, data)
    try:
        if kind == "pdf":
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            doc = Document(io.BytesIO(data))
            parts = [p.text for p in doc.paragraphs]
            for table in doc.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text for c in row.cells))
            text = "\n".join(parts)
    except Exception as exc:  # corrupt files
        raise CVParseError(f"Could not read the {kind.upper()} file: {exc}") from exc
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 30:
        raise CVParseError(
            "Very little text could be extracted. If this is a scanned PDF, please upload a text-based PDF or DOCX."
        )
    return text


# ------------------------------------------------------------- heuristics
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,5}")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?", re.I)
URL_RE = re.compile(r"https?://[^\s,;]+", re.I)

SKILL_VOCAB = [
    "Python", "SQL", "R", "Excel", "Advanced Excel", "Power BI", "Tableau", "Looker", "Qlik", "SAS", "SPSS",
    "Pandas", "NumPy", "Matplotlib", "Seaborn", "Scikit-learn", "TensorFlow", "PyTorch", "Keras", "Statistics",
    "Machine Learning", "Deep Learning", "NLP", "Data Visualization", "Data Analysis", "Data Cleaning",
    "Data Modeling", "ETL", "Data Warehousing", "Snowflake", "BigQuery", "Redshift", "Databricks", "Spark",
    "PySpark", "Hadoop", "Airflow", "dbt", "MySQL", "PostgreSQL", "Oracle", "SQL Server", "MongoDB", "NoSQL",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Git", "GitHub", "Linux", "Java", "JavaScript", "TypeScript",
    "C++", "C#", "Go", "React", "Node.js", "Django", "Flask", "FastAPI", "REST API", "HTML", "CSS",
    "VBA", "DAX", "Power Query", "SSIS", "SSRS", "Alteryx", "Jira", "Agile", "Scrum", "A/B Testing",
    "Hypothesis Testing", "Regression", "Forecasting", "Time Series", "Google Analytics", "SAP", "Salesforce",
    "Business Intelligence", "Dashboarding", "KPI", "Stakeholder Management", "Communication",
    "Problem Solving", "Project Management", "Financial Analysis", "Risk Analysis", "Audit", "Accounting",
]

SECTION_HEADINGS = {
    "summary": ["summary", "profile", "objective", "about me", "professional summary", "career objective"],
    "experience": ["experience", "work experience", "employment", "professional experience", "work history",
                   "internship", "internships"],
    "education": ["education", "academic", "qualifications", "academics"],
    "skills": ["skills", "technical skills", "key skills", "core competencies", "tools"],
    "projects": ["projects", "academic projects", "key projects"],
    "certifications": ["certifications", "certificates", "courses", "licenses"],
    "achievements": ["achievements", "awards", "accomplishments", "honors"],
}


def find_skills(text: str, vocab: list[str] | None = None) -> list[str]:
    found = []
    for skill in vocab or SKILL_VOCAB:
        pattern = r"(?<![A-Za-z0-9+#])" + re.escape(skill) + r"(?![A-Za-z0-9+#])"
        flags = 0 if len(skill) <= 2 else re.I  # "R", "Go" must match case-sensitively
        if re.search(pattern, text, flags):
            found.append(skill)
    return found


def _split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        key = line.lower().strip(":").strip()
        matched = next((s for s, names in SECTION_HEADINGS.items() if key in names), None)
        if matched and len(line) < 40:
            current = matched
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def heuristic_parse(text: str) -> CandidateProfileData:
    sections = _split_sections(text)
    header = sections.get("header", [])
    email_match = EMAIL_RE.search(text)
    email = email_match.group() if email_match else ""
    linkedin = LINKEDIN_RE.search(text)
    phone = ""
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group())
        if 10 <= len(digits) <= 13:
            phone = m.group().strip()
            break
    name = ""
    for line in header[:5]:
        if not EMAIL_RE.search(line) and not re.search(r"\d", line) and 1 < len(line.split()) <= 5:
            name = line.title() if line.isupper() else line
            break

    bullets = lambda key: [re.sub(r"^[•\-\*▪●◦]\s*", "", l) for l in sections.get(key, [])]  # noqa: E731
    experience = []
    exp_lines = bullets("experience")
    if exp_lines:
        current = Experience(title=exp_lines[0])
        for line in exp_lines[1:]:
            current.responsibilities.append(line)
        experience.append(current)
    education = [Education(degree=l) for l in bullets("education")[:4]]

    return CandidateProfileData(
        full_name=name,
        email=email or "",
        phone=phone,
        linkedin_url=linkedin.group() if linkedin else "",
        professional_summary=" ".join(bullets("summary"))[:1500],
        experience=experience,
        education=education,
        technical_skills=find_skills(text),
        achievements=bullets("achievements")[:10],
    )
