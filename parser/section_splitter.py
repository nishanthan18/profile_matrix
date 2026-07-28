"""Splits raw resume text into canonical sections (summary, skills, experience,
projects, education, certifications, achievements, languages, hobbies,
declaration, publications) using header-line detection.

Real resumes use very inconsistent header wording ("PROJECTS HANDLED",
"KEY COMPETENCIES", "Relevant Project Experience", "Domain and Technical Skills",
"Professional Experience" vs a second bare "EXPERIENCE" header used just for
listing projects, "Education & Certifications" as one combined header, etc).
Instead of matching an exact phrase, we match on keyword substrings -- much
more forgiving of real-world variation.

Two things that used to cause real data loss and have been fixed here:

1. COMBINED HEADERS ("Education & Certifications", "Certifications and
   Achievements", "Projects & Internships"...). Previously the FIRST rule in
   a fixed priority list "won" outright, so e.g. "Education & Certifications"
   was classified as *only* certifications and the education content
   (degree, university, year) silently vanished into the certifications
   bucket. Now, when a header line matches more than one canonical section,
   the content that follows is duplicated into *every* matched section until
   the next header. Nothing is dropped, and downstream extractors (which
   each look at a specific section) still find what they need.

2. UNRECOGNISED HEADERS ("Languages Known", "Hobbies & Interests",
   "Declaration", "Publications", "Volunteer Experience", ...). These used
   to fall through and get silently appended to whatever the previous
   section happened to be (e.g. a "Hobbies" block tacked onto the end of
   "Certifications" text), polluting that section. They now have their own
   canonical buckets so they stop contaminating the sections the rest of the
   pipeline actually reads.
"""

import re

# (canonical_section, [substring keywords]) -- a header can match more than one
# canonical section (see module docstring); order here only affects tie-breaks
# when a keyword match starts at the same character position.
_HEADER_RULES = [
    # "experience" is checked before "projects" so that a compound header
    # like "PROJECT EXPERIENCE" (very common for a jobs/work-history
    # section) resolves to "experience", not "projects" -- losing the
    # experience-section boundary breaks date-range parsing, total
    # experience, and the stack-wise breakdown, whereas project data is
    # still independently recoverable from the raw text by
    # project_extractor's labeled/narrative patterns even if it doesn't end
    # up isolated in the "projects" bucket.
    ("experience", ["experience", "employment", "work history", "internship",
                     "career history", "professional background"]),
    ("projects", ["project", "case stud"]),
    ("certifications", ["certificat", "licens"]),
    ("achievements", ["achievement", "award", "accomplishment", "honor", "honour",
                       "accolade"]),
    ("publications", ["publication", "research paper", "patent"]),
    ("education", ["education", "academic background", "academic qualification",
                    "qualification", "scholastic"]),
    ("skills", ["skill", "competenc", "technical", "technolog", "tech stack",
                "tools", "core strength", "areas of expertise", "expertise",
                "proficienc"]),
    ("languages", ["language known", "languages known", "language proficienc",
                    "languages spoken"]),
    ("hobbies", ["hobbies", "hobby", "interest", "extracurricular",
                  "co-curricular", "extra curricular"]),
    ("declaration", ["declaration"]),
    ("references", ["reference"]),
    ("summary", ["summary", "objective", "vision", "profile", "about me",
                  "career goal", "professional summary"]),
]

# "language" alone is deliberately NOT a global keyword above (it's also used
# as a field label inside project blocks, e.g. "Language: Python") -- only the
# more specific "language(s) known/spoken/proficiency" phrasing counts as a
# genuine top-level section header.


# Field-label lines like "Project : Titanium Legal Services" or "Year : 2018 - 2020"
# are structured data, never section headers -- even though they can be short and
# title-cased enough to otherwise look like one.
_FIELD_LABEL_RE = re.compile(
    r"^\s*(project(?:\s*title)?|year|role|client|technolog(?:y|ies)|techniques?|"
    r"library\s*used|environment|description|responsibilities|duration|"
    r"team\s*size|language|microcontroller|robots?|operating\s*platform|"
    r"tech(?:nical)?\s*stack|skills?\s*used|tools?\s*used|"
    r"grade|percentage|cgpa|gpa|score)\s*[-:]",
    re.IGNORECASE,
)


_CONNECTOR_ONLY_RE = re.compile(r"^(&|/|,|and|\+|plus)$")


def _match_headers(line: str):
    """
    Returns an ORDERED list of every canonical section a header line matches.

    Most headers describe exactly one section even when they contain a word
    that happens to also be another section's keyword -- e.g. "Relevant
    Project Experience" is a *single* projects-flavoured experience header,
    not "projects" + "experience" duplicated. For these, the ORIGINAL
    priority order (projects before experience, etc, as listed in
    _HEADER_RULES) picks the single winner, same as before.

    Only when two keyword hits are separated by an explicit connector
    ("&", "/", ",", "and", ...) -- e.g. "Education & Certifications",
    "Certifications and Achievements" -- do we treat it as a genuinely
    combined header and duplicate the following text into every matched
    section, so a truly combined header never loses content.

    Returns [] if the line isn't a recognised header at all.
    """
    if _FIELD_LABEL_RE.match(line.strip()):
        return []
    clean = line.strip().strip(":").strip().lower()
    clean = re.sub(r"[^a-z& ]", " ", clean).strip()
    clean = re.sub(r"\s+", " ", clean)
    if not clean:
        return []

    hits = []  # (start_idx, end_idx, canon)
    for canon, keywords in _HEADER_RULES:
        best = None  # (start, end)
        for kw in keywords:
            idx = clean.find(kw)
            if idx != -1 and (best is None or idx < best[0]):
                # extend to the end of the enclosing word -- keywords like
                # "certificat" are deliberately partial (to catch certificate/
                # certification/certifications), so without this the leftover
                # letters ("...ions") would pollute the connector-gap check
                # between this hit and the next one
                end = idx + len(kw)
                while end < len(clean) and clean[end].isalpha():
                    end += 1
                best = (idx, end)
        if best is not None:
            hits.append((best[0], best[1], canon))

    if not hits:
        return []

    # de-dupe: keep only the earliest hit per canon
    earliest_per_canon = {}
    for start, end, canon in hits:
        if canon not in earliest_per_canon or start < earliest_per_canon[canon][0]:
            earliest_per_canon[canon] = (start, end)
    hits = sorted(((s, e, c) for c, (s, e) in earliest_per_canon.items()), key=lambda x: x[0])

    if len(hits) == 1:
        return [hits[0][2]]

    # check every consecutive gap is a genuine connector -- if any gap is NOT,
    # this is a compound phrase describing one section, not a combined header
    all_connected = True
    for (_, prev_end, _c1), (start, _, _c2) in zip(hits, hits[1:]):
        gap = clean[prev_end:start].strip()
        if not _CONNECTOR_ONLY_RE.match(gap):
            all_connected = False
            break

    if all_connected:
        return [canon for _, _, canon in hits]

    # fall back to the single winner using _HEADER_RULES priority order
    hit_canons = {canon for _, _, canon in hits}
    for canon, _ in _HEADER_RULES:
        if canon in hit_canons:
            return [canon]
    return [hits[0][2]]


def _looks_like_header(stripped: str) -> bool:
    if not stripped:
        return False
    word_count = len(stripped.split())
    if word_count > 6:
        return False
    return bool(stripped.isupper() or stripped.istitle() or stripped.endswith(":"))


def split_sections(text: str) -> dict:
    """
    Returns a dict: {canonical_section_name: joined_text}.
    Any text before the first recognised header goes under 'header' (contact block).

    When a header line matches multiple canonical sections at once (a
    "combined" header such as "Education & Certifications"), the text that
    follows is duplicated into every matched section so nothing is lost --
    each downstream extractor only reads the section(s) it cares about, so
    the duplication is harmless there.
    """
    lines = text.split("\n")
    sections = {"header": []}
    current = ["header"]

    for line in lines:
        stripped = line.strip()
        is_header_line = _looks_like_header(stripped)
        matched = _match_headers(stripped) if is_header_line else []
        # also try matching even if not "header-looking" line, for messy PDFs
        if not matched and len(stripped.split()) <= 4:
            matched = _match_headers(stripped)

        if matched:
            current = matched
            for c in current:
                sections.setdefault(c, [])
            continue

        for c in current:
            sections.setdefault(c, [])
            sections[c].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}