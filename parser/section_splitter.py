"""Splits raw resume text into canonical sections (summary, skills, experience,
projects, education, certifications, achievements, languages, hobbies,
declaration, publications) using header-line detection.

Real resumes use very inconsistent header wording ("PROJECTS HANDLED",
"KEY COMPETENCIES", "Relevant Project Experience", "Domain and Technical Skills",
"Professional Experience" vs a second bare "EXPERIENCE" header used just for
listing projects, "Education & Certifications" as one combined header, etc).
Instead of matching an exact phrase, we match on keyword substrings -- much
more forgiving of real-world variation.

Three things that used to cause real data loss and have been fixed here:

1. COMBINED HEADERS ("Education & Certifications", "Certifications and
   Achievements", "Projects & Internships"...). When a header line matches
   more than one canonical section, the content that follows is duplicated
   into *every* matched section until the next header, so nothing is lost.

2. UNRECOGNISED HEADERS ("Languages Known", "Hobbies & Interests",
   "Declaration", "Publications", ...) have their own canonical buckets so
   they stop contaminating whatever section came before them.

3. FALSE-POSITIVE HEADERS (the big one). Two separate patterns were
   silently reclassifying ordinary content as a brand-new section header,
   which reset "current section" mid-way through the real experience/
   projects section and caused most entries to vanish or land in the
   wrong bucket:

   a) In-entry field labels like "Project Name: SSCOM-298", "Technology &
      Tools: .Net Core, ..." were not recognised as structured data (the
      old field-label regex only matched bare "Project:", not "Project
      Name:" or "Technology & Tools:"), so they were read as new section
      headers -- e.g. hitting "Project Name:" inside a work-history entry
      would flip the whole rest of that entry (and every entry after it,
      until the next real header) into the "projects" bucket instead of
      "experience". Fixed with a general `_is_field_label_line()` check:
      any "Label(s): value" line whose label words are all known
      field-label words (project, name, client, team, size, technology,
      tools, ...) is treated as data, never a header, regardless of the
      exact wording combination.

   b) Ordinary sentences that merely *contain* a header keyword as a
      substring -- e.g. "...transform them into functional applications
      in line with business objectives." -- were being matched because
      "objectives" contains "objective" (a "summary" keyword), and any
      line with 8 or fewer words was eligible for keyword-based header
      detection. That's what was truncating the experience section down
      to a single entry. Fixed by only trusting a keyword match on a line
      that doesn't already look header-styled (no ':', not ALLCAPS, not
      Title Case) when the line is essentially JUST the header phrase --
      at most one extra filler word beyond the matched keyword(s). Lines
      that already look header-styled (e.g. "Education & Certifications")
      keep the original, more permissive combined-header matching.
"""

import re

# (canonical_section, [substring keywords]) -- a header can match more than one
# canonical section (see module docstring); order here only affects tie-breaks
# when a keyword match starts at the same character position.
_HEADER_RULES = [

    ("education", [
        "educational experience",
        "education",
        "educational",
        "academic background",
        "academic qualification",
        "qualification",
        "scholastic",
        "degree",
        "university",
        "college"
    ]),

    ("experience", [
        "experience",
        "employment",
        "work history",
        "internship",
        "career history",
        "professional background"
    ]),

    ("projects", [
        "project",
        "case stud"
    ]),

    ("certifications", [
        "certification",
        "certified",
        "license",
        "licence"
    ]),

    ("achievements", [
        "achievement",
        "award",
        "accomplishment",
        "honor",
        "honour",
        "accolade"
    ]),

    ("publications", [
        "publication",
        "research paper",
        "patent"
    ]),

    ("skills", [
        "skill",
        "competenc",
        "technical",
        "technolog",
        "tech stack",
        "tools",
        "core strength",
        "areas of expertise",
        "expertise",
        "proficienc"
    ]),

    ("languages", [
        "language known",
        "languages known",
        "language proficienc",
        "languages spoken"
    ]),

    ("hobbies", [
        "hobbies",
        "hobby",
        "interest",
        "extracurricular",
        "co-curricular",
        "extra curricular"
    ]),

    ("declaration", [
        "declaration"
    ]),

    ("references", [
        "reference"
    ]),

    ("summary", [
        "summary",
        "objective",
        "vision",
        "profile",
        "about me",
        "career goal",
        "professional summary"
    ]),
]

# "language" alone is deliberately NOT a global keyword above (it's also used
# as a field label inside project blocks, e.g. "Language: Python") -- only the
# more specific "language(s) known/spoken/proficiency" phrasing counts as a
# genuine top-level section header.


# General "Label: value" / "Label1 & Label2: value" detector. Covers every
# in-entry field line (Project Name:, Technology & Tools:, Team Size: ...)
# without hard-coding each exact wording combination -- previously only
# exact phrasings like bare "Project:" were recognised, so "Project Name:"
# and "Technology & Tools:" fell through and were misread as new section
# headers, silently truncating the experience/projects sections.
_FIELD_LABEL_KEYWORDS = {
    "project", "projects", "title", "year", "role", "client", "technology",
    "technologies", "technique", "techniques", "library", "libraries",
    "environment", "description", "responsibilities", "responsibility",
    "duration", "team", "size", "language", "languages", "microcontroller",
    "robot", "robots", "platform", "stack", "tool", "tools", "skill",
    "skills", "grade", "percentage", "cgpa", "gpa", "score", "name", "used",
    "domain", "framework", "frameworks", "database", "databases", "type",
    "operating",
}
_CONNECTORS = {"and", "used", "of", "&"}

# Filler words ignored when deciding whether a short, non-header-styled line
# is "mostly just the header phrase" vs. an ordinary sentence that happens
# to contain a header keyword as a substring.
_FILLER_WORDS = {"and", "the", "of", "for", "in", "on", "a", "an", "&"}


def _is_field_label_line(stripped: str) -> bool:
    """True for 'Label: value' / 'Label1 & Label2: value' lines such as
    'Project Name: X', 'Technology & Tools: Y', 'Team Size: 8'. These are
    structured data inside an experience/project block and must never be
    treated as section headers, even though they can be short/title-cased
    enough to otherwise look like one."""
    if not stripped or (":" not in stripped and "-" not in stripped):
        return False
    parts = re.split(r"\s*[-:]\s*", stripped, maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return False
    label_part = parts[0].strip().lower()
    words = re.findall(r"[a-z]+", label_part)
    if not words or len(words) > 5:
        return False
    return all(w in _FIELD_LABEL_KEYWORDS or w in _CONNECTORS for w in words)


_CONNECTOR_ONLY_RE = re.compile(r"^(&|/|,|and|\+|plus)$")


def _match_headers(line: str, strict: bool = False):
    """Returns the list of canonical sections this line's header matches.

    strict=True is used for lines that don't already look header-styled on
    their own (no trailing ':', not ALLCAPS, not Title Case) -- i.e. plain
    sentences from a messy PDF. For those, a keyword match is only accepted
    if the line is essentially JUST the header phrase (at most one extra
    filler word), so an ordinary sentence that happens to contain a header
    keyword as a substring (e.g. "...business objectives.") isn't misread
    as a new section header.
    """
    if _is_field_label_line(line.strip()):
        return []

    clean = line.strip().strip(":").strip().lower()
    clean = re.sub(r"[^a-z& ]", " ", clean).strip()
    clean = re.sub(r"\s+", " ", clean)

    # Fix common resume heading
    if "educational experience" in clean:
        return ["education"]

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

    if strict:
        # Reject if there's more than one real "extra" word beyond the
        # matched header keyword(s) -- i.e. this is prose, not a header.
        words_with_span = []
        pos = 0
        for w in clean.split(" "):
            start = clean.find(w, pos)
            end = start + len(w)
            words_with_span.append((start, end, w))
            pos = end
        leftover = 0
        for wstart, wend, w in words_with_span:
            if w in _FILLER_WORDS:
                continue
            covered = any(not (wend <= hs or wstart >= he) for hs, he, _ in hits)
            if not covered:
                leftover += 1
        if leftover > 1:
            return []

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


def _looks_like_header(stripped: str):
    if not stripped:
        return False

    # Ignore long sentences
    if len(stripped.split()) > 8:
        return False

    # Headers ending with :
    if stripped.endswith(":"):
        return True

    # ALL CAPS
    if stripped.isupper():
        return True

    # Title Case
    if stripped.istitle():
        return True

    return False


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

        # Lines that already look header-styled (colon/ALLCAPS/Title Case)
        # get the normal (looser) combined-header matching -- this is what
        # correctly catches "PROJECTS HANDLED", "KEY COMPETENCIES",
        # "Education & Certifications", etc.
        #
        # Lines that DON'T look header-styled -- short, plain sentences from
        # a messy PDF -- get the strict check instead, so an ordinary
        # sentence that happens to contain a header keyword as a substring
        # (e.g. "...business objectives.") is never misread as a new
        # section header and doesn't truncate the section it's actually
        # part of.
        if is_header_line:
            matched = _match_headers(stripped, strict=False)
        elif len(stripped.split()) <= 4:
            matched = _match_headers(stripped, strict=True)
        else:
            matched = []

        if matched:
            current = matched

            for c in current:
                sections.setdefault(c, [])

            continue

        for c in current:
            sections.setdefault(c, [])
            sections[c].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}