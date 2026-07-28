"""
Extracts personal / contact details from raw resume text using regex heuristics:
name, email, phone, LinkedIn, GitHub, portfolio link, location.

No external API / ML model is used -- everything is rule based.
"""

import re

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{7,15}\d")

LINKEDIN_RE = re.compile(r"(https?://)?(www\.)?linkedin\.com/[A-Za-z0-9\-_/%]+", re.I)
GITHUB_RE = re.compile(r"(https?://)?(www\.)?github\.com/[A-Za-z0-9\-_/%]+", re.I)
PORTFOLIO_RE = re.compile(
    r"(https?://)?(www\.)?[A-Za-z0-9\-]+\.(dev|me|io|com|in|tech)(/[A-Za-z0-9\-_/%]*)?", re.I
)

# Common non-name header words that should never be mistaken for a person's name
NAME_STOPWORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "objective", "summary",
    "contact", "details", "personal", "information", "career", "vision",
    "professional", "address", "education", "experience", "skills", "projects",
    "declaration", "about", "mobile", "phone", "email", "linkedin",
    "github", "portfolio", "achievements", "certifications", "languages",
    "references", "competencies", "domain", "technical"
}

# Words that mark the end of a "name segment" if they appear on the same line
# (e.g. "SANKARALINGAM.R Mobile : +91 7395844185")
NAME_LINE_SPLIT_RE = re.compile(
    r"\b(mobile|phone|ph|cell|contact|email|e-mail|mail)\b\s*[:.]?", re.I
)

INDIAN_CITY_HINTS = [
    "coimbatore", "chennai", "bangalore", "bengaluru", "hyderabad", "mumbai",
    "delhi", "new delhi", "pune", "kolkata", "ahmedabad", "trichy",
    "tiruchirappalli", "tirupur", "madurai", "salem", "erode", "kochi",
    "cochin", "noida", "gurgaon", "gurugram", "chandigarh", "jaipur",
    "lucknow", "indore", "nagpur", "bhopal", "surat", "vadodara", "visakhapatnam",
    "vizag", "thiruvananthapuram", "trivandrum", "mysore", "mysuru", "mangalore",
    "vellore", "nashik", "ranchi", "patna", "guwahati", "raipur", "amritsar",
    "ludhiana", "jodhpur", "kanpur", "faridabad", "ghaziabad", "thane",
    "navi mumbai", "pondicherry", "puducherry", "hosur", "karur", "dindigul",
    "thanjavur", "tirunelveli", "nagercoil"
]

# A modest set of common international hiring hubs, useful as a fallback when
# a resume isn't India-based (kept short deliberately -- exhaustive world city
# lists cause far more false positives, e.g. matching a company or skill name).
GLOBAL_CITY_HINTS = [
    "new york", "san francisco", "seattle", "austin", "chicago", "boston",
    "los angeles", "toronto", "vancouver", "london", "manchester", "dublin",
    "berlin", "munich", "amsterdam", "paris", "madrid", "barcelona", "zurich",
    "singapore", "dubai", "abu dhabi", "sydney", "melbourne", "auckland",
    "tokyo", "hong kong", "shanghai", "beijing"
]

_LOCATION_LABEL_RE = re.compile(
    r"^\s*(current\s+)?(location|address|based\s*(in|at)|residing\s*(in|at)|"
    r"city)\s*:\s*(?P<value>.+)$",
    re.IGNORECASE,
)

_PIN_CITY_RE = re.compile(
    r"([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\s*[-,]?\s*\d{6}\b"
)


def _clean(s):
    return s.strip().strip(",").strip() if s else s


def extract_email(text: str):
    m = EMAIL_RE.search(text)
    return m.group(0) if m else None


def extract_phone(text: str):
    # Prefer numbers near the top of the resume, and with at least 10 digits
    for line in text.split("\n")[:15]:
        for m in PHONE_RE.finditer(line):
            digits = re.sub(r"\D", "", m.group(0))
            if 10 <= len(digits) <= 13:
                return m.group(0).strip()
    # fallback: search whole doc
    for m in PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13:
            return m.group(0).strip()
    return None


def extract_linkedin(text: str):
    m = LINKEDIN_RE.search(text)
    if not m:
        return None
    url = m.group(0)
    if not url.startswith("http"):
        url = "https://" + url
    return url


def extract_github(text: str):
    m = GITHUB_RE.search(text)
    if not m:
        return None
    url = m.group(0)
    if not url.startswith("http"):
        url = "https://" + url
    return url


def extract_portfolio(text: str, exclude_urls=None):
    exclude_urls = exclude_urls or []
    email = extract_email(text)
    email_domain = email.split("@")[1].lower() if email else None

    for m in PORTFOLIO_RE.finditer(text):
        url = m.group(0)
        low = url.lower()
        if "linkedin.com" in low or "github.com" in low:
            continue
        if "@" in url:
            continue
        # skip a preceding '@' right before the match (part of an email address)
        if m.start() > 0 and text[m.start() - 1] == "@":
            continue
        if email_domain and email_domain in low:
            continue
        if any(url in ex for ex in exclude_urls if ex):
            continue
        if not url.startswith("http"):
            url = "https://" + url
        return url
    return None


def _looks_like_name(words) -> bool:
    if not (0 < len(words) <= 4):
        return False
    joined = "".join(words)
    if len(joined) < 3:
        return False
    if not all(re.match(r"^[A-Za-z.'\-]+$", w) for w in words):
        return False
    if any(w.strip(".").lower() in NAME_STOPWORDS for w in words):
        return False
    return True


def extract_name(text: str):
    """
    Heuristic: the name is almost always the very first non-empty line (or very
    close to it). Many resumes put the phone/email on the SAME line as the name
    (e.g. "SANKARALINGAM.R  Mobile : +91 7395844185") -- so instead of rejecting
    any line containing a digit outright, we first strip out email/phone/label
    fragments and check what's left.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    for line in lines[:8]:
        candidate = line
        # cut the line off at the first contact-label word (Mobile/Phone/Email/etc.)
        split_match = NAME_LINE_SPLIT_RE.search(candidate)
        if split_match:
            candidate = candidate[: split_match.start()]
        # cut off at an email address or the first digit run (phone number)
        candidate = EMAIL_RE.sub("", candidate)
        digit_match = re.search(r"\d", candidate)
        if digit_match:
            candidate = candidate[: digit_match.start()]
        candidate = candidate.strip(" -|,:")

        if not candidate:
            continue

        words = candidate.replace(".", ". ").split()
        words = [w.strip(".") if len(w) > 2 else w for w in words]  # keep initials like "R"/"K."
        words = [w for w in candidate.split() if w]

        if _looks_like_name(words):
            name = re.sub(r"\s+", " ", candidate).strip()
            return name.title() if name.isupper() else name

    return None


def _reject_if_skill_words(candidate: str, skill_words: set) -> bool:
    words_low = [w.strip(",").lower() for w in candidate.split()]
    return any(w in skill_words for w in words_low)


def extract_location(text: str):
    """
    Tries several strategies, most reliable first. Everything here operates
    strictly WITHIN a single line -- never on a raw character-offset window
    that can straddle two unrelated lines (that used to produce garbage like
    "karr\\nCoimbatore, Tamil" when a city name happened to sit right after
    an unrelated line such as a GitHub URL).

    1. An explicit "Location:" / "Address:" / "Based in:" label line.
    2. A known city name appearing in its own line, refined to "City, State"
       if that pattern is present on the SAME line.
    3. A generic "City, State" pattern within a single line.
    4. A "City ... 6-digit PIN code" pattern (common in Indian resumes).
    """
    from .skills_database import ALL_SKILLS_FLAT
    skill_words = {kw for kw, _ in ALL_SKILLS_FLAT}

    top_lines = [l.strip() for l in text.split("\n")[:25] if l.strip()]
    city_hints = INDIAN_CITY_HINTS + GLOBAL_CITY_HINTS

    # 1. explicit label
    for line in top_lines:
        m = _LOCATION_LABEL_RE.match(line)
        if m:
            value = _clean(m.group("value"))
            # strip a trailing pincode if present, keep it readable
            value = re.sub(r"\s*[-,]?\s*\d{6}\s*$", "", value).strip(" ,-")
            if value and not EMAIL_RE.search(value):
                return value

    # 2. known city name, refined to "City, State" on that same line if possible
    _CITY_STATE_RE = re.compile(
        r"([A-Za-z][a-zA-Z]+(?:\s[A-Za-z]+)?,\s*[A-Za-z][a-zA-Z]+(?:\s[A-Za-z]+)?)"
    )
    for line in top_lines:
        low = line.lower()
        for city in city_hints:
            if city in low:
                m = _CITY_STATE_RE.search(line)
                if m and not _reject_if_skill_words(m.group(1), skill_words):
                    return _clean(m.group(1))
                return city.title()

    # 3. generic "City, State" pattern, single line only
    for line in top_lines:
        for m in re.finditer(r"\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?,\s*[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)?)\b", line):
            candidate = _clean(m.group(1))
            if _reject_if_skill_words(candidate, skill_words):
                continue
            return candidate

    # 4. "City ... 123456" (Indian PIN code) pattern, single line only
    for line in top_lines:
        m = _PIN_CITY_RE.search(line)
        if m:
            candidate = _clean(m.group(1))
            if not _reject_if_skill_words(candidate, skill_words):
                return candidate

    return None


def extract_contact_details(text: str) -> dict:
    email = extract_email(text)
    phone = extract_phone(text)
    linkedin = extract_linkedin(text)
    github = extract_github(text)
    portfolio = extract_portfolio(text, exclude_urls=[linkedin, github])
    name = extract_name(text)
    location = extract_location(text)

    return {
        "Name": name or "Not found",
        "Email": email or "Not found",
        "Phone": phone or "Not found",
        "LinkedIn": linkedin or "Not found",
        "GitHub": github or "Not found",
        "Portfolio": portfolio or "Not found",
        "Location": location or "Not found",
    }