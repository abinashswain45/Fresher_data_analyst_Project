"""Full-stack UI end-to-end test (frontend + backend + fake recruitment portal).

Drives the real web app the way a user would, on an emulated Android phone (Pixel 7, Chrome) and on a
Windows Chrome desktop viewport:

  register -> upload CV -> complete profile -> paste job URL -> analysis -> approve CV ->
  start automation -> sign in on the portal via the remote browser view (human step) ->
  accept AI answers -> tick terms via the remote view (human step) -> continue ->
  final review -> Approve & Submit -> confirmation saved in history.

Prerequisites (see README "End-to-end UI test"):
  portal:   python -m http.server 8765 --bind 127.0.0.1   (in backend/tests/fixtures/portal)
  backend:  ALLOW_PRIVATE_URLS=true uvicorn app.main:app --port 8000
  frontend: npm run build && npm start   (port 3000)

Usage: python e2e/ui_flow.py [android|desktop] [--shots DIR]
"""
import argparse
import asyncio
import io
import re
import sys
import time
from pathlib import Path

from docx import Document
from playwright.async_api import async_playwright, expect

APP = "http://localhost:3000"
PORTAL = "http://127.0.0.1:8765"
WIN_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/130.0.0.0 Safari/537.36")


def cv_bytes() -> bytes:
    doc = Document()
    for line in ["PRIYA SHARMA", "priya.sharma@example.com | +91 98765 43210 | Bengaluru",
                 "linkedin.com/in/priya-sharma-data", "Professional Summary",
                 "Data analyst with hands-on experience building dashboards and analysing sales data.",
                 "Experience", "Data Analyst Intern - Contoso Retail",
                 "• Built Power BI dashboards tracking weekly sales KPIs for 12 stores",
                 "• Wrote SQL queries to analyse customer purchase data", "• Cleaned datasets using Python and Pandas",
                 "Education", "Bachelor of Science in Statistics, Christ University, 2024",
                 "Skills", "SQL, Python, Pandas, Excel, Power BI, Statistics"]:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


async def remote_click_at(page, fx: float, fy: float):
    img = page.get_by_alt_text(re.compile("Live view"))
    await img.evaluate("e => e.scrollIntoView({block: 'center'})")
    await page.wait_for_timeout(300)
    box = await img.bounding_box()
    await page.mouse.click(box["x"] + fx * box["width"], box["y"] + fy * box["height"])


async def wait_checkpoint(page, title_re: str, timeout=60):
    await expect(page.get_by_text(re.compile(title_re)).first).to_be_visible(timeout=timeout * 1000)


async def run(device: str, shots: Path | None):
    email = f"{device}-{int(time.time())}@example.com"
    cv = Path("/tmp") / f"applypilot_cv_{device}.docx"
    cv.write_bytes(cv_bytes())

    async def shot(page, name):
        if shots:
            shots.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(shots / f"{device}-{name}.png"), full_page=False)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except Exception:
            browser = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium")
        if device == "android":
            ctx = await browser.new_context(**p.devices["Pixel 7"])
        else:
            ctx = await browser.new_context(viewport={"width": 1366, "height": 768}, user_agent=WIN_UA)
        page = await ctx.new_page()
        page.set_default_timeout(30000)
        page.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        try:
            await _flow(p, browser, page, shot, email, cv, device)
        except Exception:
            if shots:
                await page.screenshot(path=str(shots / f"{device}-FAILED.png"), full_page=True)
            raise
        finally:
            await browser.close()


async def _flow(p, browser, page, shot, email, cv, device):
    if True:

        # Layout of the portal form at the automation browser's viewport, to know where the user taps.
        helper = await browser.new_page(viewport={"width": 1280, "height": 860})
        await helper.goto(f"{PORTAL}/form.html")
        tb = await helper.locator("#terms").bounding_box()
        terms_frac = ((tb["x"] + tb["width"] / 2) / 1280, (tb["y"] + tb["height"] / 2) / 860)
        await helper.close()

        # 1. Register
        await page.goto(f"{APP}/register")
        await page.get_by_label("Full name").fill("Priya Sharma")
        await page.get_by_label("Email").fill(email)
        await page.get_by_label("Password").fill("s3cure-pass!")
        await page.get_by_role("button", name="Create account").click()
        await page.wait_for_url("**/resumes**")
        await shot(page, "01-resumes")

        # 2. Upload CV
        await page.locator("input[type=file]").set_input_files(str(cv))
        await expect(page.get_by_text("CV processed")).to_be_visible(timeout=60000)
        await expect(page.get_by_text(re.compile("General · Uploaded"))).to_be_visible()
        print("✓ CV uploaded and parsed")

        # 3. Complete profile
        await page.goto(f"{APP}/profile")
        await expect(page.get_by_label("Email address")).to_have_value("priya.sharma@example.com")
        await page.get_by_label("Total experience (years)").fill("0.5")
        await page.get_by_label("Notice period").fill("Immediate")
        await page.get_by_label("Expected CTC").fill("6 LPA")
        await page.get_by_role("button", name="Save profile").first.click()
        await expect(page.get_by_text("Profile saved")).to_be_visible()
        await shot(page, "02-profile")
        print("✓ Profile saved")

        # 4. Paste job URL
        await page.goto(f"{APP}/apply")
        await page.get_by_label("Paste Job Application URL").fill(f"{PORTAL}/job.html")
        await page.get_by_role("button", name="Analyse job").click()
        await page.wait_for_url(re.compile(r"/applications/\d+"))
        await expect(page.get_by_text("You appear eligible")).to_be_visible(timeout=90000)
        await expect(page.get_by_role("heading", name="Data Analyst")).to_be_visible()
        await shot(page, "03-analysis")
        print("✓ Job analysed:", await page.locator("text=/match/i").first.inner_text())

        # 5. Approve recommendations -> tailored CV -> approve
        approve_btns = page.get_by_role("button", name="Approve", exact=True)
        if await approve_btns.count():
            await approve_btns.first.click()
            await page.get_by_role("button", name="Create CV from approved changes").click()
            await expect(page.locator("option", has_text="(tailored)")).to_have_count(1)
        await page.get_by_role("button", name=re.compile("Approve this CV")).click()
        await expect(page.get_by_text(re.compile("Approved:"))).to_be_visible()
        print("✓ Resume approved")

        # 6. Start automation -> sign-in checkpoint
        await page.get_by_role("button", name="Start automated application").click()
        await wait_checkpoint(page, "Sign-in required")
        await expect(page.get_by_text("Human verification required").first).to_be_visible()
        await expect(page.get_by_alt_text(re.compile("Live view"))).to_be_visible(timeout=20000)
        await shot(page, "04-login-checkpoint")
        print("✓ Paused for human sign-in")

        # 7. The user signs in through the remote browser view (tap page, Tab to email, type, Tab, type, Enter)
        typer = page.get_by_placeholder(re.compile("Text to type"))
        await remote_click_at(page, 0.6, 0.9)
        await page.get_by_role("button", name="Tab").click()
        await typer.fill("priya.sharma@example.com")
        await page.get_by_role("button", name="Type", exact=True).click()
        await page.get_by_role("button", name="Tab").click()
        await typer.fill("portal-secret-1")
        await page.get_by_role("button", name="Type", exact=True).click()
        await shot(page, "04b-typed")
        await page.get_by_role("button", name="Enter").click()
        await page.wait_for_timeout(1500)
        await shot(page, "04c-entered")
        await page.get_by_role("button", name="Continue Application").click()

        # 8. Page 1 filled; review drafted answers
        await wait_checkpoint(page, "Your input needed on page")
        await page.reload()
        await page.get_by_role("button", name="Accept all ready answers").or_(page.get_by_role("button", name="Accept").first).first.click()
        await page.wait_for_timeout(800)
        for btn in await page.get_by_role("button", name=re.compile("^(Accept|Save & accept)$")).all():
            if await btn.is_enabled():
                await btn.click()
                await page.wait_for_timeout(400)
        await shot(page, "05-questions")
        # The user ticks the terms checkbox themselves in the remote view
        await page.locator("#automation").scroll_into_view_if_needed()
        await page.get_by_role("button", name="Scroll").first.click()  # scroll up
        for _ in range(4):
            await page.get_by_role("button", name="Scroll").first.click()
        await page.wait_for_timeout(2500)
        await remote_click_at(page, *terms_frac)
        await page.wait_for_timeout(500)
        await page.get_by_role("button", name="Continue Application").click()
        print("✓ Answers approved, terms ticked by user")

        # 9. Page 2 question -> accept -> continue
        await expect(page.get_by_text("Describe your experience with SQL and Python *").first).to_be_visible(timeout=60000)
        await page.reload()
        await expect(page.get_by_text("Describe your experience with SQL and Python").first).to_be_visible()
        for btn in await page.get_by_role("button", name=re.compile("^(Accept|Save & accept)$")).all():
            if await btn.is_enabled():
                await btn.click()
                await page.wait_for_timeout(400)
        await page.get_by_role("button", name="Continue Application").click()

        # 10. Final review -> approve & submit
        await wait_checkpoint(page, "Final review & submission")
        await expect(page.get_by_text("Nothing has been submitted yet")).to_be_visible()
        await expect(page.get_by_text("Gender (voluntary)")).to_be_visible()
        await shot(page, "06-final-review")
        await page.get_by_label(re.compile("I have reviewed this application")).check()
        await page.get_by_role("button", name="Approve & Submit").click()
        await expect(page.get_by_text("Application submitted").first).to_be_visible(timeout=60000)
        await expect(page.get_by_text("APP-48213").first).to_be_visible()
        await shot(page, "07-submitted")
        print("✓ Submitted with reference APP-48213")

        # 11. History
        await page.goto(f"{APP}/history")
        await expect(page.locator("text=/APP-48213/ >> visible=true").first).to_be_visible()
        await shot(page, "08-history")
        print(f"✓ [{device}] full flow passed")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("device", nargs="?", default="desktop", choices=["android", "desktop"])
    ap.add_argument("--shots", type=Path, default=None)
    a = ap.parse_args()
    try:
        asyncio.run(run(a.device, a.shots))
    except Exception as exc:
        print("✗ FAILED:", exc)
        sys.exit(1)
