"""Dynamic form-field discovery and classification.

Fields are discovered from the live DOM (labels, aria attributes, placeholders, names, ATS automation
ids, surrounding text) instead of relying on fixed selectors, then classified into:
  profile:<key>  - safe to fill from the verified candidate profile
  resume         - resume/CV upload
  question       - free-text question -> AI-drafted answer for user review
  choice         - non-sensitive select/radio -> option picked from the profile when supported
  password/otp   - human verification checkpoint (never filled by the agent)
  sensitive      - demographic / voluntary disclosure / identity numbers -> user only
  legal          - terms, declarations, consents, work authorisation -> user only
  skip           - irrelevant/hidden
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

COLLECT_JS = r"""
() => {
  const visible = (el) => {
    if (el.type === 'file') return true;           // file inputs are often visually hidden
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const text = (el) => (el ? (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim() : '');
  const labelFor = (el) => {
    const parts = [];
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) parts.push(text(l));
    }
    const wrap = el.closest('label');
    if (wrap) parts.push(text(wrap));
    if (el.getAttribute('aria-label')) parts.push(el.getAttribute('aria-label'));
    const lb = el.getAttribute('aria-labelledby');
    if (lb) lb.split(/\s+/).forEach(id => { const n = document.getElementById(id); if (n) parts.push(text(n)); });
    if (!parts.length) {
      const fs = el.closest('fieldset');
      if (fs && fs.querySelector('legend')) parts.push(text(fs.querySelector('legend')));
    }
    if (!parts.length) {
      let p = el.parentElement;
      for (let i = 0; i < 3 && p && !parts.length; i++, p = p.parentElement) {
        const t = text(p);
        if (t && t.length < 250) parts.push(t);
      }
    }
    return parts.filter(Boolean).join(' | ').slice(0, 400);
  };
  let counter = window.__apCounter || 0;
  const out = [];
  const radios = {};
  document.querySelectorAll('input, textarea, select').forEach(el => {
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'image', 'reset', 'search'].includes(type)) return;
    if (el.disabled || !visible(el)) return;
    if (!el.dataset.apId) el.dataset.apId = 'ap' + (++counter);
    const base = {
      ref: el.dataset.apId, tag: el.tagName.toLowerCase(), type,
      name: el.name || '', id: el.id || '',
      autocomplete: el.getAttribute('autocomplete') || '',
      automation_id: el.getAttribute('data-automation-id') || el.getAttribute('data-qa') || el.getAttribute('data-testid') || '',
      placeholder: el.getAttribute('placeholder') || '',
      required: el.required || el.getAttribute('aria-required') === 'true',
      label: labelFor(el),
      has_value: type === 'checkbox' ? el.checked : !!(el.value && el.value.trim()),
      options: [],
    };
    if (el.tagName === 'SELECT') {
      base.options = Array.from(el.options).map(o => o.text.trim()).filter(t => t && !/^(select|choose|--)/i.test(t));
      base.has_value = el.selectedIndex > 0;
    }
    if (type === 'radio') {
      const key = el.name || base.ref;
      const fs = el.closest('fieldset');
      const groupLabel = fs && fs.querySelector('legend') ? text(fs.querySelector('legend')) : '';
      if (!radios[key]) {
        radios[key] = { ...base, label: groupLabel || base.label, options: [], option_refs: [], has_value: false };
        out.push(radios[key]);
      }
      radios[key].options.push(labelFor(el) || el.value);
      radios[key].option_refs.push(base.ref);
      radios[key].has_value = radios[key].has_value || el.checked;
      return;
    }
    out.push(base);
  });
  window.__apCounter = counter;
  return out;
}
"""

BUTTONS_JS = r"""
() => {
  const out = [];
  let counter = window.__apBtnCounter || 0;
  document.querySelectorAll('button, input[type=submit], input[type=button], a[role=button], a').forEach(el => {
    const r = el.getBoundingClientRect();
    if (!(r.width > 0 && r.height > 0) || el.disabled) return;
    const t = (el.innerText || el.value || el.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    if (!t || t.length > 60) return;
    if (!el.dataset.apBtn) el.dataset.apBtn = 'b' + (++counter);
    out.push({ ref: el.dataset.apBtn, text: t, tag: el.tagName.toLowerCase(),
               type: (el.getAttribute('type') || '').toLowerCase(),
               automation_id: el.getAttribute('data-automation-id') || '',
               in_form: !!el.closest('form'), href: el.getAttribute('href') || '' });
  });
  window.__apBtnCounter = counter;
  return out;
}
"""

CHECKPOINT_JS = r"""
() => {
  const sel = 'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], iframe[src*="captcha"], '
            + '.g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey], #captcha, [id*="captcha" i], [class*="captcha" i]';
  const captcha = Array.from(document.querySelectorAll(sel)).some(el => {
    const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0;
  });
  const bodyText = (document.body ? document.body.innerText : '').slice(0, 20000);
  return { captcha, bodyText, title: document.title, url: location.href };
}
"""


@dataclass
class Field:
    ref: str
    tag: str
    type: str
    label: str
    name: str = ""
    id: str = ""
    autocomplete: str = ""
    automation_id: str = ""
    placeholder: str = ""
    required: bool = False
    has_value: bool = False
    options: list[str] = field(default_factory=list)
    option_refs: list[str] = field(default_factory=list)
    frame_index: int = 0
    category: str = ""
    profile_key: str = ""

    @property
    def haystack(self) -> str:
        return " ".join([self.label, self.name, self.id, self.placeholder, self.automation_id,
                         self.autocomplete]).lower()

    @property
    def display_label(self) -> str:
        lbl = self.label.split(" | ")[0].strip() if self.label else ""
        return (lbl or self.placeholder or self.name or self.automation_id or self.id or "Field")[:200]


SENSITIVE_RE = re.compile(
    r"gender|\bsex\b|pronoun|\brace\b|ethnic|veteran|disab|sexual orientation|religio|caste|marital|"
    r"date of birth|birth ?date|\bdob\b|\bage\b|social security|\bssn\b|aadha?ar|\bpan\b|passport|"
    r"national id|tax id|criminal|conviction|hispanic|latino|transgender|military|medical|health condition",
    re.I,
)
LEGAL_RE = re.compile(
    r"terms|privacy|consent|i agree|agree to|declar|certify|acknowledg|attest|authori[sz]ed to work|"
    r"work authori|sponsor|visa|right to work|background check|non-?compete|gdpr|data processing|"
    r"signature|e-?sign|truthful|accurate and complete",
    re.I,
)
OTP_RE = re.compile(r"\botp\b|one[- ]time|verification code|verify code|passcode|security code|6-digit|"
                    r"enter (the )?code|confirmation code|\bpin\b", re.I)

PROFILE_RULES: list[tuple[str, str]] = [
    ("first_name", r"first.?name|given.?name|\bfname\b|legalnamesection_firstname|forename"),
    ("last_name", r"last.?name|surname|family.?name|\blname\b|legalnamesection_lastname"),
    ("email", r"e-?mail"),
    ("phone", r"phone|mobile|cell|contact.?number|\btel\b|telephone"),
    ("linkedin_url", r"linkedin"),
    ("portfolio_url", r"website|portfolio|github|personal.?site|blog|url"),
    ("current_company", r"current.?(company|employer|organi[sz]ation)|present employer|\bemployer\b|\borg\b|^company|company.?name"),
    ("current_title", r"current.?(title|role|designation|position)|job.?title|designation"),
    ("total_experience_years", r"years? of (relevant |total |work )?experience|total.?experience|experience.?\(?years|work experience in years"),
    ("notice_period", r"notice.?period"),
    ("current_ctc", r"current.?(ctc|salary|compensation|package)"),
    ("expected_ctc", r"expected.?(ctc|salary|compensation|package)|salary expectation|desired salary"),
    ("preferred_locations", r"preferred.?location"),
    ("location", r"current.?location|\bcity\b|location|addresssection_city|town"),
    ("institution", r"school|university|college|institut"),
    ("degree", r"\bdegree\b|qualification"),
    ("field_of_study", r"discipline|field of study|major|speciali[sz]ation|branch"),
    ("graduation_year", r"graduation (year|date)|year of (passing|graduation)|passing year"),
    ("full_name", r"full.?name|^name\b|your name|\bname\b|candidate.?name"),
    ("technical_skills", r"\bskills?\b|technolog"),
    ("professional_summary", r"summary|about (you|yourself)|profile summary|headline"),
    ("willing_to_relocate", r"relocat"),
]


def classify(f: Field) -> Field:
    hay = f.haystack
    label = f.display_label.lower()
    if f.type == "password":
        f.category = "password"
    elif OTP_RE.search(hay) and f.type not in ("checkbox", "radio", "file", "select"):
        f.category = "otp"
    elif f.type == "file":
        f.category = "cover_letter" if re.search(r"cover", hay) else "resume"
    elif SENSITIVE_RE.search(hay):
        f.category = "sensitive"
    elif LEGAL_RE.search(hay) or (f.type == "checkbox" and re.search(r"agree|accept|confirm", hay)):
        f.category = "legal"
    else:
        for key, pattern in PROFILE_RULES:
            # Long free-text labels ("Describe your experience with SQL...") are questions, not profile fields
            if re.search(pattern, hay) and not (f.tag == "textarea" and len(label) > 60):
                f.category, f.profile_key = "profile", key
                break
        else:
            if f.tag == "textarea" or (f.type == "text" and ("?" in label or len(label) > 35)):
                f.category = "question"
            elif f.tag == "select" or f.type == "radio":
                f.category = "choice"
            elif f.type == "checkbox":
                f.category = "legal"  # unknown checkboxes are left to the user
            else:
                f.category = "unknown"
    # Cover letter / motivation textareas behave like questions
    if f.category == "profile" and f.profile_key == "professional_summary" and f.tag == "textarea" and "cover" in hay:
        f.category, f.profile_key = "question", ""
    return f


def _year(text: str) -> str:
    m = re.search(r"(?:19|20)\d{2}", text or "")
    return m.group() if m else ""


def profile_value(key: str, profile) -> str:
    """Resolve a profile key into the string to type into a form field."""
    p = profile
    names = (p.full_name or "").split()
    edu = p.education[0] if p.education else None
    values = {
        "first_name": names[0] if names else "",
        "last_name": " ".join(names[1:]) if len(names) > 1 else "",
        "full_name": p.full_name,
        "email": p.email,
        "phone": p.phone,
        "linkedin_url": p.linkedin_url,
        "portfolio_url": p.portfolio_url,
        "current_company": p.current_company or next((e.company for e in p.experience if e.is_current), ""),
        "current_title": p.current_title or next((e.title for e in p.experience if e.is_current), ""),
        "total_experience_years": "" if p.total_experience_years is None else f"{p.total_experience_years:g}",
        "notice_period": p.notice_period,
        "current_ctc": p.current_ctc,
        "expected_ctc": p.expected_ctc,
        "preferred_locations": ", ".join(p.preferred_locations),
        "location": p.location,
        "institution": edu.institution if edu else "",
        "degree": edu.degree if edu else "",
        "field_of_study": edu.field_of_study if edu else "",
        "graduation_year": _year(edu.end_date) if edu else "",
        "technical_skills": ", ".join(p.technical_skills),
        "professional_summary": p.professional_summary,
        "willing_to_relocate": "" if p.willing_to_relocate is None else ("Yes" if p.willing_to_relocate else "No"),
    }
    return values.get(key, "") or ""


def best_option(value: str, options: list[str]) -> str | None:
    """Fuzzy-match a value to one of the options (exact > startswith > contains > token overlap)."""
    if not value or not options:
        return None
    v = value.strip().lower()
    for o in options:
        if o.strip().lower() == v:
            return o
    for o in options:
        if o.lower().startswith(v) or v.startswith(o.lower()):
            return o
    for o in options:
        if v in o.lower() or o.lower() in v:
            return o
    vt = set(re.findall(r"\w+", v))
    scored = sorted(((len(vt & set(re.findall(r"\w+", o.lower()))), o) for o in options), reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return None


SUBMIT_RE = re.compile(r"^(submit|send)( (my|your))?( application| now)?$|submit application|send application|"
                       r"finish|complete application|^apply$|^apply now$|^submit$", re.I)
NEXT_RE = re.compile(r"^(next|continue|save (and|&) continue|save (and|&) next|proceed|review|next step|"
                     r"continue to next step|go to next|save and proceed)\b", re.I)
APPLY_LINK_RE = re.compile(r"^(apply|apply now|apply for (this )?job|apply online|start (your )?application|"
                           r"apply manually|i'?m interested|apply to job)$", re.I)
CONFIRM_RE = re.compile(r"thank you for (applying|your application)|application (has been )?(received|submitted)|"
                        r"successfully (applied|submitted)|we have received your application|"
                        r"application complete|your application was sent", re.I)
REFERENCE_RE = re.compile(r"(?:application|reference|confirmation|tracking|candidate)\s*(?:id|no\.?|number|#|code)"
                          r"\s*[:#-]?\s*([A-Z0-9][A-Z0-9-]{3,30})", re.I)
LOGIN_TEXT_RE = re.compile(r"sign in|log ?in|create (an )?account|register|forgot password", re.I)
