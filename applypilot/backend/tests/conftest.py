import functools
import http.server
import os
import socketserver
import tempfile
import threading
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="applypilot-test-")
os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "STORAGE_DIR": f"{_tmp}/storage",
    "ANTHROPIC_API_KEY": "",
    "JWT_SECRET": "test-secret-key-that-is-long-enough-for-hs256",
    "AUTOMATION_HEADLESS": "true",
})

import io  # noqa: E402

import pytest  # noqa: E402
from docx import Document  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def portal_url():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(FIXTURES / "portal"))
    handler.log_message = lambda *a, **k: None
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def make_cv_docx() -> bytes:
    doc = Document()
    for line in [
        "PRIYA SHARMA", "priya.sharma@example.com | +91 98765 43210 | Bengaluru",
        "linkedin.com/in/priya-sharma-data", "",
        "Professional Summary",
        "Data analyst with hands-on experience building dashboards and analysing sales data.",
        "Experience",
        "Data Analyst Intern - Contoso Retail",
        "• Built Power BI dashboards tracking weekly sales KPIs for 12 stores",
        "• Wrote SQL queries to analyse customer purchase data",
        "• Cleaned datasets using Python and Pandas",
        "Education",
        "Bachelor of Science in Statistics, Christ University, 2024",
        "Skills",
        "SQL, Python, Pandas, Excel, Power BI, Statistics",
    ]:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture(scope="session")
def cv_docx() -> bytes:
    return make_cv_docx()
