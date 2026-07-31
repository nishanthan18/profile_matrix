"""
Parses the 'experience' section text into individual entries (role/company + duration),
handles 'to Present / Current / Till Date' as today's date, computes:

  1. Duration of EACH entry separately (in months/years).
  2. Skills/technologies used in each entry (regex keyword match).
  3. Stack-wise / role-wise total experience (sum of the entries that used that skill).
  4. TOTAL overall experience using a merged (union) of all date ranges.
"""

import re
from datetime import datetime
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

from .skills_database import find_skills_in_text

TODAY = datetime.today()

PRESENT_WORDS = r"(?:presently|present|currently|current|till\s*date|till|ongoing|continuing|now)"

# IMPORTANT: use horizontal whitespace only ( [ \t] ) instead of \s here.
# \s also matches newlines, which let the old regex's \s* separator jump
# across several lines/bullets to grab the nearest-looking "end" token
# (e.g. a bare year or "Present") several entries below the real one.
# That produced one giant, wrong match per scan, and since finditer()
# never looks inside an already-consumed match, every real entry sitting
# inside that swallowed span was silently skipped -- collapsing 14 years
# of work history down to a single tiny (mis-paired) duration.
_HSPACE = r"[ \t]"

DATE_RANGE_RE = re.compile(
    rf"""
    (?P<start>
        \d{{4}}[-/]\d{{1,2}}
        |\d{{1,2}}[-/]\d{{4}}
        |[A-Za-z]{{3,9}}{_HSPACE}+\d{{4}}
        |\d{{4}}
    )
    {_HSPACE}*
    (?:-|\u2013|\u2014|to|until|through)
    {_HSPACE}*
    (?P<end>
        \d{{4}}[-/]\d{{1,2}}
        |\d{{1,2}}[-/]\d{{4}}
        |[A-Za-z]{{3,9}}{_HSPACE}+\d{{4}}
        |\d{{4}}
        |{PRESENT_WORDS}
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _parse_date(token: str):
    token = token.strip()
    if re.match(PRESENT_WORDS, token, re.IGNORECASE):
        return TODAY
    # Handle YYYY-MM or YYYY/MM explicitly
    ym = re.match(r'^(\d{4})[-/](\d{1,2})$', token)
    if ym:
        try:
            return datetime(int(ym.group(1)), int(ym.group(2)), 1)
        except ValueError:
            pass
    # Handle bare YYYY
    if re.fullmatch(r"\d{4}", token):
        return datetime(int(token), 1, 1)
    token = token.replace(".", " ").strip()
    try:
        return dateparser.parse(token, default=datetime(TODAY.year, 1, 1))
    except Exception:
        return None


def _months_between(start, end):
    if not start or not end:
        return 0
    if end < start:
        return 0
    months = (
        (end.year - start.year) * 12
        + end.month
        - start.month
    )
    if end.day >= start.day:
        months += 1
    return max(months, 1)


def _merge_intervals(intervals):
    """Merge overlapping or consecutive (within 1 month) intervals."""
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        next_month = last_end + relativedelta(months=1)
        if start <= next_month:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def format_duration(months: int) -> str:
    years, rem_months = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr{'s' if years != 1 else ''}")
    if rem_months:
        parts.append(f"{rem_months} mo{'s' if rem_months != 1 else ''}")
    return " ".join(parts) if parts else "0 mo"


def parse_experience_entries(experience_text: str):
    if not experience_text:
        return []

    full_text = experience_text
    matches = list(DATE_RANGE_RE.finditer(full_text))
    entries = []

    for i, m in enumerate(matches):
        start_dt = _parse_date(m.group("start"))
        end_dt = _parse_date(m.group("end"))
        if not start_dt or not end_dt:
            continue

        # Extract role from SAME line as the date
        current_line_start = full_text.rfind("\n", 0, m.start()) + 1
        current_line_end = full_text.find("\n", m.end())
        if current_line_end == -1:
            current_line_end = len(full_text)

        current_line = full_text[current_line_start:current_line_end].strip()

        # Remove date from the line to get role title
        title_line = DATE_RANGE_RE.sub("", current_line).strip()
        if not title_line:
            pre_lines = [
                l.strip()
                for l in full_text[:m.start()].splitlines()
                if l.strip()
            ]
            title_line = pre_lines[-1] if pre_lines else "Role"

        # Company: usually next non-empty line after role
        remaining_lines = full_text[current_line_end:].splitlines()
        company = ""
        for line in remaining_lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("•"):
                break
            if line.lower().startswith("project"):
                break
            if line.lower().startswith("client"):
                break
            company = line
            break

        # Descriptive text window
        window_start = current_line_end
        window_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        desc_text = full_text[window_start:window_end]

        # Strip next date range from desc to avoid skill pollution
        desc_text = re.sub(DATE_RANGE_RE, "", desc_text)
        desc_text = desc_text.strip()

        months = _months_between(start_dt, end_dt)

        skill_text = "\n".join([title_line, company, desc_text])
        skills_found = find_skills_in_text(skill_text)

        entries.append({
            "title": title_line,
            "company": company,
            "start": start_dt,
            "end": end_dt,
            "start_str": m.group("start"),
            "end_str": (
                "Present"
                if re.match(PRESENT_WORDS, m.group("end"), re.I)
                else m.group("end")
            ),
            "months": months,
            "duration": format_duration(months),
            "skills": skills_found,
            "description": desc_text,
        })

    return entries


def compute_total_experience(entries) -> dict:
    """Total career span using merged (non-overlapping) intervals."""
    intervals = [(e["start"], e["end"]) for e in entries if e["start"] and e["end"]]
    merged = _merge_intervals(intervals)
    total_months = sum(_months_between(s, e) for s, e in merged)
    return {
        "months": total_months,
        "formatted": format_duration(total_months),
    }


def compute_stackwise_experience(entries) -> list:
    """Uses merged intervals per skill to avoid double-counting overlapping roles."""
    from .skills_database import skill_category

    skill_map = {}
    for e in entries:
        for skill in e["skills"]:
            skill_map.setdefault(skill, {"intervals": [], "roles": []})
            if e["start"] and e["end"]:
                skill_map[skill]["intervals"].append((e["start"], e["end"]))
            skill_map[skill]["roles"].append(e["title"])

    result = []
    for skill, info in skill_map.items():
        merged = _merge_intervals(info["intervals"])
        months = sum(_months_between(s, e) for s, e in merged)
        result.append({
            "Skill / Stack": skill.title(),
            "Category": skill_category(skill),
            "Experience": format_duration(months),
            "Months": months,
            "Used In (Role/Company)": ", ".join(sorted(set(info["roles"]))),
        })

    result.sort(key=lambda x: x["Months"], reverse=True)
    return result