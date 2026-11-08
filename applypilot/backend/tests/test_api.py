import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/api/auth/register", json={"email": "priya@example.com", "password": "s3cure-pass!", "full_name": "Priya"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_auth_required(client):
    assert client.get("/api/profile").status_code == 401


def test_login_and_duplicate_register(client, auth):
    assert client.post("/api/auth/register", json={"email": "priya@example.com", "password": "another-pass"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "priya@example.com", "password": "wrong-pass"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "PRIYA@example.com", "password": "s3cure-pass!"})
    assert r.status_code == 200 and r.json()["access_token"]


def test_upload_resume_builds_profile(client, auth, cv_docx):
    r = client.post("/api/resumes", headers=auth, data={"label": "Data Analyst CV", "category": "Data Analyst"},
                    files={"file": ("priya_cv.docx", cv_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    assert r.status_code == 201, r.text
    content = r.json()["content"]
    assert content["email"] == "priya.sharma@example.com"
    assert "SQL" in content["technical_skills"] and "Power BI" in content["technical_skills"]
    prof = client.get("/api/profile", headers=auth).json()
    assert prof["data"]["email"] == "priya.sharma@example.com"
    assert 0 < prof["completeness"] < 100 and "Notice period" in prof["missing_fields"]


def test_reject_non_cv(client, auth):
    r = client.post("/api/resumes", headers=auth, files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 422


def test_profile_update(client, auth):
    data = client.get("/api/profile", headers=auth).json()["data"]
    data.update({"full_name": "Priya Sharma", "notice_period": "Immediate", "expected_ctc": "6 LPA",
                 "total_experience_years": 0.5, "preferred_roles": ["Data Analyst"], "preferred_locations": ["Bengaluru"],
                 "location": "Bengaluru, India",
                 "experience": [{"company": "Contoso Retail", "title": "Data Analyst Intern", "is_current": True,
                                 "responsibilities": ["Built Power BI dashboards tracking weekly sales KPIs for 12 stores",
                                                      "Wrote SQL queries to analyse customer purchase data"]}],
                 "education": [{"institution": "Christ University", "degree": "Bachelor of Science",
                                "field_of_study": "Statistics", "end_date": "2024"}]})
    r = client.put("/api/profile", headers=auth, json=data)
    assert r.status_code == 200
    assert r.json()["data"]["notice_period"] == "Immediate"


def _wait_status(client, auth, app_id, not_in=("Analyzing",), timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        d = client.get(f"/api/applications/{app_id}", headers=auth).json()
        if d["status"] not in not_in:
            return d
        time.sleep(0.5)
    raise AssertionError("analysis did not finish")


def test_analyze_job_url_and_tailor(client, auth, portal_url):
    r = client.post("/api/applications/analyze", headers=auth, json={"url": f"{portal_url}/job.html?utm_source=x"})
    assert r.status_code == 202, r.text
    app_id = r.json()["id"]
    d = _wait_status(client, auth, app_id)
    assert d["job"]["company"] == "Acme Analytics"
    assert d["job"]["title"] == "Data Analyst"
    assert "SQL" in d["job"]["requirements"]["required_skills"]
    assert d["status"] == "Resume Update Required"
    assert d["match_score"] >= 50 and d["match"]["eligible"] is True
    assert d["match"]["recommended_resume_id"]
    assert d["recommendations"]

    # duplicate prevention (tracking params ignored)
    dup = client.post("/api/applications/analyze", headers=auth, json={"url": f"{portal_url}/job.html"})
    assert dup.status_code == 409 and dup.json()["detail"]["application_id"] == app_id

    # approve individual recommendations -> tailored version
    decisions = [{"id": rec["id"], "status": "approved"} for rec in d["recommendations"] if rec["section"] == "skills"]
    t = client.post(f"/api/applications/{app_id}/tailor", headers=auth, json={"mode": "review", "decisions": decisions})
    assert t.status_code == 200, t.text
    resume_id = t.json()["resume_id"]
    tailored = client.get(f"/api/resumes/{resume_id}", headers=auth).json()
    assert tailored["kind"] == "tailored"
    assert tailored["content"]["technical_skills"][0] in ("SQL", "Python", "Excel", "Power BI", "Pandas")
    # guardrail: no skill the candidate lacks (Snowflake/Tableau) is ever added
    assert "Snowflake" not in tailored["content"]["technical_skills"]

    for fmt, magic in (("pdf", b"%PDF"), ("docx", b"PK")):
        dl = client.get(f"/api/resumes/{resume_id}/download?format={fmt}", headers=auth)
        assert dl.status_code == 200 and dl.content[:len(magic)] == magic

    ok = client.post(f"/api/applications/{app_id}/approve-resume?resume_id={resume_id}", headers=auth)
    assert ok.json()["status"] == "Ready for Application"


def test_questions_assistant(client, auth):
    app_id = client.get("/api/applications", headers=auth).json()[0]["id"]
    q = client.post(f"/api/applications/{app_id}/questions", headers=auth, json={"question": "What is your expected salary?"})
    assert q.status_code == 201 and q.json()["answer"] == "6 LPA"
    q2 = client.post(f"/api/applications/{app_id}/questions", headers=auth,
                     json={"question": "Describe your experience with SQL and Python."}).json()
    assert "SQL" in q2["answer"]
    r = client.post(f"/api/applications/{app_id}/questions/{q2['id']}/regenerate", headers=auth, json={"style": "shorter"})
    assert r.status_code == 200
    e = client.put(f"/api/applications/{app_id}/questions/{q2['id']}", headers=auth, json={"answer": "My edited answer", "status": "accepted"})
    assert e.json()["status"] == "accepted" and e.json()["answer"] == "My edited answer"


def test_tracking_filters_stats_and_manual_submit(client, auth):
    apps = client.get("/api/applications?q=Acme", headers=auth).json()
    assert len(apps) == 1
    app_id = apps[0]["id"]
    assert client.patch(f"/api/applications/{app_id}", headers=auth, json={"status": "Submitted"}).status_code == 400
    client.patch(f"/api/applications/{app_id}", headers=auth, json={"notes": "Referred by alumni", "follow_up_date": "2026-11-20"})
    r = client.post(f"/api/applications/{app_id}/manual-submit", headers=auth, json={"reference_id": "REF-1"})
    assert r.json()["status"] == "Submitted" and r.json()["reference_id"] == "REF-1"
    stats = client.get("/api/applications/stats", headers=auth).json()
    assert stats["total"] == 1 and stats["submitted"] == 1
    assert client.get("/api/applications?status=Interview", headers=auth).json() == []
    guide = client.get(f"/api/applications/{app_id}/manual-guide", headers=auth).json()
    assert any(f["key"] == "email" and f["value"] for f in guide["fields"])


def test_manual_description_when_site_blocks(client, auth):
    r = client.post("/api/applications/analyze", headers=auth, json={
        "url": "https://careers.example.com/job/data-analyst-blocked",
        "manual_description": "We need a Data Analyst with 5+ years of experience in SQL, Python and Tableau."})
    d = _wait_status(client, auth, r.json()["id"])
    assert d["match"]["eligible"] is False  # 5+ years vs 0.5 years -> honest ineligibility
    assert d["status"] == "On Hold" and d["match"]["ineligibility_reasons"]


def test_isolation_between_users(client, auth):
    other = client.post("/api/auth/register", json={"email": "other@example.com", "password": "password-123"}).json()
    h = {"Authorization": f"Bearer {other['access_token']}"}
    app_id = client.get("/api/applications", headers=auth).json()[0]["id"]
    assert client.get(f"/api/applications/{app_id}", headers=h).status_code == 404
    assert client.get("/api/resumes", headers=h).json() == []


def test_export_and_delete(client, auth):
    exp = client.get("/api/account/export", headers=auth)
    assert exp.status_code == 200 and exp.json()["profile"]["email"] == "priya.sharma@example.com"
    tmp = client.post("/api/auth/register", json={"email": "gone@example.com", "password": "password-123"}).json()
    h = {"Authorization": f"Bearer {tmp['access_token']}"}
    assert client.post("/api/account/delete", headers=h, json={"password": "nope-nope"}).status_code == 403
    assert client.post("/api/account/delete", headers=h, json={"password": "password-123"}).status_code == 204
    assert client.get("/api/profile", headers=h).status_code == 401


def test_continue_endpoint_resumes_session(client, auth, portal_url):
    """Regression: POST /continue must actually resume a paused session (not just flip its state)."""
    r = client.post("/api/applications/analyze", headers=auth, json={"url": f"{portal_url}/captcha.html", "force": True})
    app_id = r.json()["id"]
    _wait_status(client, auth, app_id)
    resume_id = client.get("/api/resumes", headers=auth).json()[0]["id"]
    client.post(f"/api/applications/{app_id}/approve-resume?resume_id={resume_id}", headers=auth)
    assert client.post(f"/api/automation/{app_id}/start", headers=auth, json={}).status_code == 200
    end = time.time() + 60
    while time.time() < end and client.get(f"/api/automation/{app_id}/state", headers=auth).json()["state"] != "paused":
        time.sleep(0.5)
    st = client.get(f"/api/automation/{app_id}/state", headers=auth).json()
    assert st["checkpoint"]["kind"] == "captcha"
    n_before = len(st["log"])
    assert client.post(f"/api/automation/{app_id}/continue", headers=auth).status_code == 200
    end = time.time() + 30
    while time.time() < end:
        st = client.get(f"/api/automation/{app_id}/state", headers=auth).json()
        if st["state"] == "paused" and len(st["log"]) > n_before:
            break
        time.sleep(0.5)
    # the engine re-ran detection and paused again because the CAPTCHA is still there
    assert st["state"] == "paused" and st["checkpoint"]["kind"] == "captcha" and len(st["log"]) > n_before
    assert client.post(f"/api/automation/{app_id}/approve-submit", headers=auth).status_code == 409
    client.post(f"/api/automation/{app_id}/stop", headers=auth)
