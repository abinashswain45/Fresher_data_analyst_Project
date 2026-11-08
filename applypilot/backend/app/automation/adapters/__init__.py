"""Recruitment platform adapters.

Each adapter customises how the generic engine opens the application form, which ATS-specific
attributes map to profile fields, and which buttons mean "next" vs "submit". Adding support for a
new recruitment system means adding one adapter class and registering it in ADAPTERS.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from playwright.async_api import Page

from ..fields import APPLY_LINK_RE


class BaseAdapter:
    name = "generic"
    display_name = "Company career portal"
    # automation-id / name attribute -> profile key, checked before label heuristics
    attribute_map: dict[str, str] = {}
    next_button_ids: tuple[str, ...] = ()
    submit_button_ids: tuple[str, ...] = ()
    apply_texts: tuple[str, ...] = ()
    requires_account = False
    notes = "Fields are detected dynamically from the page."

    @classmethod
    def matches(cls, url: str) -> bool:
        return False

    def application_url(self, job_url: str, apply_url: str) -> str:
        return apply_url or job_url

    async def open(self, page: Page, url: str, timeout: int) -> None:
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await self.settle(page)

    async def settle(self, page: Page) -> None:
        try:
            await page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

    async def click_apply_entry(self, page: Page) -> bool:
        """On a job description page, click the 'Apply' entry point (never a final submit)."""
        candidates = [t for t in self.apply_texts] + ["Apply now", "Apply for this job", "Apply", "Apply online",
                                                      "Start application", "Apply to job"]
        for text in candidates:
            loc = page.get_by_role("link", name=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I))
            if await loc.count() == 0:
                loc = page.get_by_role("button", name=re.compile(rf"^\s*{re.escape(text)}\s*$", re.I))
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click()
                await self.settle(page)
                return True
        return False

    def is_apply_entry(self, text: str) -> bool:
        return bool(APPLY_LINK_RE.match(text.strip()))


class GreenhouseAdapter(BaseAdapter):
    name = "greenhouse"
    display_name = "Greenhouse"
    attribute_map = {"first_name": "first_name", "last_name": "last_name", "email": "email", "phone": "phone",
                     "job_application[first_name]": "first_name", "job_application[last_name]": "last_name",
                     "job_application[email]": "email", "job_application[phone]": "phone"}
    notes = "Single-page form; resume upload + custom questions. reCAPTCHA may appear on submit."

    @classmethod
    def matches(cls, url: str) -> bool:
        return "greenhouse.io" in url or "gh_jid=" in url


class LeverAdapter(BaseAdapter):
    name = "lever"
    display_name = "Lever"
    attribute_map = {"name": "full_name", "email": "email", "phone": "phone", "org": "current_company",
                     "location": "location", "urls[LinkedIn]": "linkedin_url", "urls[GitHub]": "portfolio_url",
                     "urls[Portfolio]": "portfolio_url", "urls[Other]": "portfolio_url"}
    notes = "Apply form at /apply. hCaptcha may be required at submission."

    @classmethod
    def matches(cls, url: str) -> bool:
        return "lever.co" in url

    def application_url(self, job_url: str, apply_url: str) -> str:
        url = apply_url or job_url
        path = urlparse(url).path.rstrip("/")
        return url if path.endswith("/apply") else url.split("?")[0].rstrip("/") + "/apply"


class WorkdayAdapter(BaseAdapter):
    name = "workday"
    display_name = "Workday"
    requires_account = True
    attribute_map = {
        "legalNameSection_firstName": "first_name", "legalNameSection_lastName": "last_name",
        "email": "email", "phone-number": "phone", "addressSection_city": "location",
        "addressSection_addressLine1": "", "jobTitle": "current_title", "company": "current_company",
        "school": "institution", "degree": "degree", "fieldOfStudy": "field_of_study",
        "linkedinQuestion": "linkedin_url",
    }
    next_button_ids = ("bottom-navigation-next-button", "pageFooterNextButton")
    submit_button_ids = ("bottom-navigation-submit-button",)
    apply_texts = ("Apply", "Apply Manually")
    notes = ("Multi-step wizard; requires a candidate account per company (sign-in/OTP handled by you). "
             "Prefers 'Apply Manually' so all fields come from your verified profile.")

    @classmethod
    def matches(cls, url: str) -> bool:
        return "myworkdayjobs.com" in url or "myworkdaysite.com" in url or ".workday.com" in url

    async def click_apply_entry(self, page: Page) -> bool:
        clicked = await super().click_apply_entry(page)
        manual = page.get_by_role("button", name=re.compile(r"apply manually", re.I))
        if await manual.count() == 0:
            manual = page.get_by_role("link", name=re.compile(r"apply manually", re.I))
        if await manual.count() > 0:
            await manual.first.click()
            await self.settle(page)
            return True
        return clicked


class SuccessFactorsAdapter(BaseAdapter):
    name = "successfactors"
    display_name = "SAP SuccessFactors"
    requires_account = True
    apply_texts = ("Apply now", "Apply")
    notes = "Usually requires a candidate profile/login per company; multi-section form."

    @classmethod
    def matches(cls, url: str) -> bool:
        return any(k in url for k in ("successfactors", "sapsf", "jobs.sap.com"))


class OracleAdapter(BaseAdapter):
    name = "oracle"
    display_name = "Oracle Recruiting Cloud / Taleo"
    requires_account = False
    apply_texts = ("Apply Now", "Apply")
    notes = "Email verification (OTP) is common before the form; multi-step wizard with Next/Submit."

    @classmethod
    def matches(cls, url: str) -> bool:
        return "oraclecloud.com" in url or "taleo.net" in url


ADAPTERS: list[type[BaseAdapter]] = [GreenhouseAdapter, LeverAdapter, WorkdayAdapter, SuccessFactorsAdapter,
                                     OracleAdapter]


def get_adapter(url: str, platform: str = "") -> BaseAdapter:
    for cls in ADAPTERS:
        if cls.name == platform or cls.matches(url):
            return cls()
    return BaseAdapter()


def list_adapters() -> list[dict]:
    return [{"name": c.name, "display_name": c.display_name, "requires_account": c.requires_account, "notes": c.notes}
            for c in [BaseAdapter, *ADAPTERS]]
