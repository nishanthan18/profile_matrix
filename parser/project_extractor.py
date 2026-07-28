"""
Parses resume text into a structured list of project entries.

Real resumes describe projects in wildly different ways, so this module tries
THREE independent patterns and merges/de-duplicates the results:

  1. LABELED BLOCKS   e.g. "Project : CLS AI Brain" / "Project Title-1 : ..."
                       followed by "Year :", "Role :", "Client :",
                       "Technologies :", "Description :" style fields.
                       (Common in experienced/senior resumes; may appear
                       inside an "Experience" section rather than "Projects".)

  2. NARRATIVE + "Skills Used:" anchor
                       A short title line, a paragraph/bullets, then a line
                       like "Skills Used: Python, Django, MySQL". Very common
                       when projects are described inside a job's bullet list.

  3. PLAIN TITLE + PARAGRAPH (fallback)
                       Used only on text already identified as a "Projects"
                       section: a short title line followed by a description
                       paragraph, optionally with a "Tech Stack:" line.

All three are searched, then merged so nothing is double-counted.
"""

import re
from .skills_database import find_skills_in_text

BULLET_RE = re.compile(r"^\s*[\u2022\-\*•▪➢●]\s*")

# ---------------------------------------------------------------- Pattern 1
LABELED_PROJECT_ANCHOR_RE = re.compile(
    r"(?im)^\s*project\s*(?:title)?\s*[-:–]?\s*\d*\s*:\s*(.+)$"
)
FIELD_RE = re.compile(
    r"(?im)^\s*(year|role|client|technolog(?:y|ies)|techniques?|"
    r"library\s*used|environment|description|responsibilities)\s*:\s*(.*)$"
)


def _parse_labeled_projects(full_text: str):
    anchors = list(LABELED_PROJECT_ANCHOR_RE.finditer(full_text))
    results = []
    for i, m in enumerate(anchors):
        title = m.group(1).strip()
        if not title:
            continue
        block_start = m.end()
        block_end = anchors[i + 1].start() if i + 1 < len(anchors) else len(full_text)
        block = full_text[block_start:block_end]

        fields = {}
        for fm in FIELD_RE.finditer(block):
            key = fm.group(1).lower().replace(" ", "")
            fields.setdefault(key, fm.group(2).strip())

        description = fields.get("description", "").strip()
        if not description:
            desc_lines = []
            for line in block.split("\n"):
                stripped = line.strip()
                if not stripped or FIELD_RE.match(stripped):
                    continue
                desc_lines.append(BULLET_RE.sub("", stripped))
            description = " ".join(desc_lines).strip()

        tech_source = fields.get("technology") or fields.get("technologies") or \
            fields.get("libraryused") or fields.get("techniques") or ""
        combined_for_skills = title + " " + tech_source + " " + description
        tech_stack = find_skills_in_text(combined_for_skills)

        results.append({
            "Project Title": title,
            "Description": description if description else "-",
            "Tech Stack": ", ".join(t.title() for t in tech_stack) if tech_stack
                          else (tech_source if tech_source else "Not specified"),
        })
    return results


# ---------------------------------------------------------------- Pattern 2
SKILLS_USED_RE = re.compile(r"(?im)^\s*skills?\s*used\s*:\s*(.+)$")


def _looks_like_project_title(line: str) -> bool:
    stripped = line.strip()
    if not stripped or BULLET_RE.match(stripped):
        return False
    if FIELD_RE.match(stripped) or SKILLS_USED_RE.match(stripped):
        return False
    words = stripped.split()
    if not (0 < len(words) <= 10):
        return False
    if not stripped[0].isupper():
        return False
    if stripped.isupper() and len(words) <= 2:
        return False
    return True


def _parse_skills_used_projects(full_text: str):
    lines = full_text.split("\n")
    results = []
    used_line_indices = set()

    for idx, line in enumerate(lines):
        m = SKILLS_USED_RE.match(line.strip())
        if not m:
            continue
        skills_text = m.group(1).strip()

        desc_lines = []
        title = None
        for back in range(idx - 1, max(idx - 15, -1), -1):
            if back in used_line_indices:
                break
            candidate = lines[back].strip()
            if not candidate:
                if desc_lines:
                    break
                continue
            if SKILLS_USED_RE.match(candidate) or FIELD_RE.match(candidate):
                break
            if _looks_like_project_title(candidate) and not BULLET_RE.match(candidate):
                title = candidate
                break
            desc_lines.append(BULLET_RE.sub("", candidate))

        if not title:
            continue

        used_line_indices.add(idx)
        description = " ".join(reversed(desc_lines)).strip()
        tech_stack = [s.strip() for s in re.split(r",|;", skills_text) if s.strip()]

        results.append({
            "Project Title": title,
            "Description": description if description else "-",
            "Tech Stack": ", ".join(tech_stack) if tech_stack else "Not specified",
        })
    return results


# ---------------------------------------------------------------- Pattern 3
TECH_LABEL_RE = re.compile(
    r"(?:tech(?:nologies|nology)?\s*stack|tools?\s*(?:used|&\s*technologies)?|"
    r"technologies\s*used)\s*[:\-]\s*(.+)", re.IGNORECASE
)


def _parse_plain_section_projects(projects_text: str):
    if not projects_text:
        return []

    lines = [l for l in projects_text.split("\n") if l.strip()]
    projects = []
    current = None

    for line in lines:
        stripped = line.strip()

        # a structured "Label : value" row (Project:, Technologies:, Role:,
        # Description:, ...) or a "Skills Used:" anchor is never itself a
        # project title/description -- it belongs to pattern 1 / pattern 2
        # above, and letting it fall through here used to spawn a bogus
        # "project" out of the raw label line (e.g. "Technologies : Python,
        # Django, MySQL" showing up as its own Project Title).
        if FIELD_RE.match(stripped) or LABELED_PROJECT_ANCHOR_RE.match(stripped) \
                or SKILLS_USED_RE.match(stripped):
            continue

        is_bullet = bool(BULLET_RE.match(stripped))
        clean_line = BULLET_RE.sub("", stripped)

        looks_like_title = (
            not is_bullet
            and len(clean_line.split()) <= 12
            and clean_line[0:1].isupper()
            and not clean_line.rstrip().endswith((".", ";"))
        )
        tech_match = TECH_LABEL_RE.search(clean_line)

        if looks_like_title and current is not None and not tech_match:
            projects.append(current)
            current = {"title": clean_line, "description": [], "tech_line": ""}
        elif looks_like_title and current is None:
            current = {"title": clean_line, "description": [], "tech_line": ""}
        else:
            if current is None:
                current = {"title": "Project", "description": [], "tech_line": ""}
            if tech_match:
                current["tech_line"] += " " + tech_match.group(1)
            else:
                current["description"].append(clean_line)

    if current is not None:
        projects.append(current)

    results = []
    for p in projects:
        desc = " ".join(p["description"]).strip()
        combined_text = p["title"] + " " + desc + " " + p["tech_line"]
        tech_stack = find_skills_in_text(combined_text)
        results.append({
            "Project Title": p["title"],
            "Description": desc if desc else "-",
            "Tech Stack": ", ".join(t.title() for t in tech_stack) if tech_stack else "Not specified",
        })
    return results


# ---------------------------------------------------------------- Merge
def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]", "", title.lower())[:30]


_JUNK_TITLES = {"project", "description", "responsibilities", "role", "client",
                "technologies", "environment", "year", "duration"}


def _is_valid_title(title: str) -> bool:
    title = title.strip()
    if len(title) < 3:
        return False
    if title.rstrip().endswith(("&", "-", ",", ":")):
        return False
    if title.lower().strip(":") in _JUNK_TITLES:
        return False
    if not re.search(r"[A-Za-z]{3,}", title):
        return False
    return True


def parse_projects_full(raw_text: str, projects_section_text: str = ""):
    """
    Runs all three extraction patterns and merges results, de-duplicating by
    normalized title so the same project isn't listed twice.
    """
    labeled = _parse_labeled_projects(raw_text)
    narrative = _parse_skills_used_projects(raw_text)
    plain = _parse_plain_section_projects(projects_section_text)

    merged = []
    seen = {}
    for group in (labeled, narrative, plain):
        for proj in group:
            if not _is_valid_title(proj["Project Title"]):
                continue
            key = _normalize_title(proj["Project Title"])
            if not key:
                continue
            if key in seen:
                existing = merged[seen[key]]
                if len(proj.get("Description", "")) > len(existing.get("Description", "")):
                    merged[seen[key]] = proj
                continue
            seen[key] = len(merged)
            merged.append(proj)

    return merged


def parse_projects(projects_text: str):
    """Backwards-compatible plain-section parser (pattern 3 only)."""
    return _parse_plain_section_projects(projects_text)