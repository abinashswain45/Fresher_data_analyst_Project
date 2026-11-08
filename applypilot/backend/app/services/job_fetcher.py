"""Fetch and extract a job posting from its official URL.

Strategy (first success wins):
  1. Platform public APIs: Greenhouse job board API, Lever postings API, Workday CXS endpoint.
  2. Static HTML: schema.org JobPosting JSON-LD, then OpenGraph/title + main content text.
  3. Rendered HTML via Playwright for JavaScript-heavy career sites.
Only the single public posting page the user supplied is fetched (no crawling).
"""
from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings

log = logging.getLogger("applypilot.jobs")


class JobFetchError(RuntimeError):
    pass


@dataclass
class FetchedJob:
    url: str
    apply_url: str = ""
    platform: str = "generic"
    company: str = ""
    title: str = ""
    location: str = ""
    description: str = ""
    method: str = ""
    extra: dict = field(default_factory=dict)


# ------------------------------------------------------------- URL helpers
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid",
                   "src", "source", "ref", "referrer", "trk", "lipi", "refid"}


def normalize_url(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    p = urlparse(url)
    query = "&".join(
        f"{k}={v[0]}" for k, v in sorted(parse_qs(p.query).items()) if k.lower() not in TRACKING_PARAMS
    )
    path = p.path.rstrip("/") or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", query, ""))


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    q = parse_qs(urlparse(url).query)
    if "greenhouse.io" in host or "gh_jid" in q:
        return "greenhouse"
    if "lever.co" in host:
        return "lever"
    if "myworkdayjobs.com" in host or "myworkdaysite.com" in host or "workday" in host:
        return "workday"
    if "successfactors" in host or "sapsf" in host or "jobs.sap.com" in host:
        return "successfactors"
    if "oraclecloud.com" in host or "taleo.net" in host:
        return "oracle"
    return "generic"


def assert_public_url(url: str) -> None:
    """SSRF protection: refuse URLs resolving to private/loopback addresses (except in tests)."""
    s = get_settings()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise JobFetchError("Please provide a valid http(s) job URL.")
    if s.environment == "test" or s.allow_private_urls:
        return
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror as exc:
        raise JobFetchError(f"Could not resolve host {p.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise JobFetchError("This URL points to a private network address and cannot be fetched.")


def html_to_text(markup: str) -> str:
    soup = BeautifulSoup(markup, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form", "iframe"]):
        tag.decompose()
    for br in soup.find_all(["br"]):
        br.replace_with("\n")
    for li in soup.find_all("li"):
        li.insert_before("\n• ")
    for blk in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "section", "ul", "ol", "tr"]):
        blk.insert_after("\n")
    text = soup.get_text()
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def _client() -> httpx.Client:
    s = get_settings()
    return httpx.Client(
        timeout=20, follow_redirects=True,
        headers={"User-Agent": s.http_user_agent, "Accept-Language": "en-US,en;q=0.9"},
    )


# --------------------------------------------------------- platform APIs
def _greenhouse(url: str, client: httpx.Client) -> FetchedJob | None:
    p = urlparse(url)
    m = re.search(r"/([^/]+)/jobs/(\d+)", p.path)
    board, job_id = (m.group(1), m.group(2)) if m else (None, None)
    q = parse_qs(p.query)
    if not job_id and "gh_jid" in q:
        job_id = q["gh_jid"][0]
        board = q.get("for", [None])[0] or q.get("board", [None])[0]
    if not (board and job_id):
        return None
    r = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}", params={"questions": "true"})
    if r.status_code != 200:
        return None
    d = r.json()
    company = board
    rb = client.get(f"https://boards-api.greenhouse.io/v1/boards/{board}")
    if rb.status_code == 200:
        company = rb.json().get("name") or board
    return FetchedJob(
        url=url, apply_url=d.get("absolute_url") or url, platform="greenhouse", company=company,
        title=d.get("title", ""), location=(d.get("location") or {}).get("name", ""),
        description=html_to_text(html.unescape(d.get("content", ""))), method="greenhouse_api",
        extra={"questions": [qq.get("label") for qq in d.get("questions", []) if qq.get("label")]},
    )


def _lever(url: str, client: httpx.Client) -> FetchedJob | None:
    m = re.search(r"lever\.co/([^/]+)/([0-9a-f-]{36})", url)
    if not m:
        return None
    company, pid = m.groups()
    eu = ".eu." in url
    r = client.get(f"https://api{'.eu' if eu else ''}.lever.co/v0/postings/{company}/{pid}")
    if r.status_code != 200:
        return None
    d = r.json()
    parts = [d.get("descriptionPlain", "")]
    for lst in d.get("lists", []):
        parts.append(lst.get("text", ""))
        parts.append(html_to_text(lst.get("content", "")))
    parts.append(d.get("additionalPlain", ""))
    return FetchedJob(
        url=url, apply_url=d.get("applyUrl") or url, platform="lever", company=company.replace("-", " ").title(),
        title=d.get("text", ""), location=(d.get("categories") or {}).get("location", ""),
        description="\n\n".join(p for p in parts if p), method="lever_api",
    )


def _workday(url: str, client: httpx.Client) -> FetchedJob | None:
    p = urlparse(url)
    host = p.netloc
    tenant = host.split(".")[0]
    segs = [s for s in p.path.split("/") if s]
    if segs and re.fullmatch(r"[a-z]{2}-[A-Z]{2}", segs[0]):
        segs = segs[1:]  # locale prefix e.g. en-US
    if "job" not in segs:
        return None
    site = segs[0]
    job_path = "/".join(segs[segs.index("job"):])
    r = client.get(f"https://{host}/wday/cxs/{tenant}/{site}/{job_path}", headers={"Accept": "application/json"})
    if r.status_code != 200:
        return None
    d = r.json()
    info = d.get("jobPostingInfo", {})
    org = (d.get("hiringOrganization") or {}).get("name", "") or tenant.title()
    return FetchedJob(
        url=url, apply_url=info.get("externalUrl") or url, platform="workday", company=org,
        title=info.get("title", ""), location=info.get("location", ""),
        description=html_to_text(info.get("jobDescription", "")), method="workday_cxs",
    )


# ------------------------------------------------------------- HTML parsing
def _find_jobposting(obj):
    if isinstance(obj, list):
        for o in obj:
            r = _find_jobposting(o)
            if r:
                return r
    elif isinstance(obj, dict):
        t = obj.get("@type")
        if t == "JobPosting" or (isinstance(t, list) and "JobPosting" in t):
            return obj
        for k in ("@graph", "mainEntity", "itemListElement"):
            if k in obj:
                r = _find_jobposting(obj[k])
                if r:
                    return r
    return None


def _location_from_ld(jp: dict) -> str:
    loc = jp.get("jobLocation")
    locs = loc if isinstance(loc, list) else [loc] if loc else []
    out = []
    for l in locs:
        addr = (l or {}).get("address", {}) if isinstance(l, dict) else {}
        if isinstance(addr, dict):
            out.append(", ".join(v for v in (addr.get("addressLocality"), addr.get("addressRegion"),
                                              addr.get("addressCountry") if isinstance(addr.get("addressCountry"), str) else None) if v))
    if jp.get("jobLocationType") == "TELECOMMUTE":
        out.append("Remote")
    return "; ".join(o for o in out if o)


def parse_html(url: str, markup: str, method: str) -> FetchedJob:
    soup = BeautifulSoup(markup, "lxml")
    job = FetchedJob(url=url, platform=detect_platform(url), method=method)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        jp = _find_jobposting(data)
        if jp:
            org = jp.get("hiringOrganization") or {}
            job.title = jp.get("title", "") or ""
            job.company = (org.get("name") if isinstance(org, dict) else str(org)) or ""
            job.location = _location_from_ld(jp)
            job.description = html_to_text(html.unescape(jp.get("description", "") or ""))
            job.method = method + "+jsonld"
            break
    if not job.title:
        og = soup.find("meta", property="og:title")
        h1 = soup.find("h1")
        job.title = (h1.get_text(strip=True) if h1 else "") or (og.get("content", "") if og else "") or (
            soup.title.get_text(strip=True) if soup.title else "")
    if not job.company:
        site = soup.find("meta", property="og:site_name")
        job.company = site.get("content", "") if site else urlparse(url).netloc.replace("www.", "").split(".")[0].title()
    if len(job.description) < 200:
        main = soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find("article") or soup.body
        if main:
            job.description = html_to_text(str(main))
    # apply link
    for a in soup.find_all("a", href=True):
        if re.search(r"\bapply\b", a.get_text(" ", strip=True), re.I):
            href = a["href"]
            if href.startswith("/"):
                pu = urlparse(url)
                href = f"{pu.scheme}://{pu.netloc}{href}"
            if href.startswith("http"):
                job.apply_url = href
                break
    job.apply_url = job.apply_url or url
    return job


async def _render_with_playwright(url: str) -> str:
    from ..automation.browser import launch_browser

    pw, browser = await launch_browser(headless=True)
    try:
        page = await browser.new_page(user_agent=get_settings().http_user_agent)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        return await page.content()
    finally:
        await browser.close()
        await pw.stop()


def _fetch_static(url: str, platform: str) -> FetchedJob | None:
    job: FetchedJob | None = None
    with _client() as client:
        try:
            if platform == "greenhouse":
                job = _greenhouse(url, client)
            elif platform == "lever":
                job = _lever(url, client)
            elif platform == "workday":
                job = _workday(url, client)
        except (httpx.HTTPError, ValueError) as exc:
            log.info("Platform API fetch failed for %s: %s", platform, exc)
        if job is None:
            try:
                r = client.get(url)
                if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
                    job = parse_html(str(r.url), r.text, "http")
                    job.url = url
            except httpx.HTTPError as exc:
                log.info("Static fetch failed: %s", exc)
    return job


async def fetch_job(url: str) -> FetchedJob:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    await asyncio.to_thread(assert_public_url, url)
    platform = detect_platform(url)
    job = await asyncio.to_thread(_fetch_static, url, platform)
    if job is None or len(job.description) < 300:
        try:
            rendered = await _render_with_playwright(url)
            rjob = parse_html(url, rendered, "browser")
            if job is None or len(rjob.description) > len(job.description):
                job = rjob
        except Exception as exc:  # browser unavailable / blocked
            log.info("Rendered fetch failed: %s", exc)
    if job is None or len(job.description) < 80:
        raise JobFetchError(
            "Could not extract the job description from this page (it may require login or block automated "
            "access). Paste the job description manually to continue."
        )
    job.platform = platform if platform != "generic" else detect_platform(job.apply_url or url)
    job.description = job.description[:100000]
    return job
