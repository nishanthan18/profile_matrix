"""
Parses the 'experience' section text into individual entries (role/company + duration),
handles 'to Present / Current / Till Date' as today's date, computes:

  1. Duration of EACH entry separately (in months/years).
  2. Skills/technologies used in each entry (regex keyword match).
  3. Stack-wise / role-wise total experience (sum of the entries that used that skill) --
     this stops a candidate's resume from showing an inflated single number when in
     reality each stack was only used for part of the overall timeline.
  4. TOTAL overall experience using a merged (union) of all date ranges, so overlapping
     roles are not double counted.
"""

import re
from datetime import datetime
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

from .skills_database import find_skills_in_text

TODAY = datetime.today()

PRESENT_WORDS = r"(?:presently|present|currently|current|till\s*date|till|ongoing|continuing|now)"

DATE_RANGE_RE = re.compile(
    r"(?P<start>[A-Za-z]{3,9}\.?\s*\d{4}|\d{1,2}[/\-]\d{4}|\d{4})"
    r"\s*(?:-|–|—|to)\s*"
    r"(?P<end>[A-Za-z]{3,9}\.?\s*\d{4}|\d{1,2}[/\-]\d{4}|\d{4}|" + PRESENT_WORDS + ")",
    re.IGNORECASE,
)


def _parse_date(token: str):
    token = token.strip()
    if re.match(PRESENT_WORDS, token, re.IGNORECASE):
        return TODAY
    try:
        return dateparser.parse(token, default=datetime(TODAY.year, 1, 1))
    except Exception:
        return None


def _months_between(start: datetime, end: datetime) -> int:
    if not start or not end or end < start:
        return 0
    delta = relativedelta(end, start)
    months = delta.years * 12 + delta.months
    return max(months, 1)  # count part-month entries as at least 1 month


def _merge_intervals(intervals):
    """intervals: list of (start_datetime, end_datetime) -> merged non-overlapping list"""
    if not intervals:
        return []
    intervals = sorted(intervals, key=lambda x: x[0])
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
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
    """
    Splits the experience section into entries anchored on each date-range match,
    and pulls the surrounding lines (title/company above, bullet points below) as
    that entry's descriptive text for skill detection.
    Returns a list of dicts: {title_line, start, end, start_str, end_str, months, skills}
    """
    if not experience_text:
        return []

    lines = experience_text.split("\n")
    full_text = experience_text

    matches = list(DATE_RANGE_RE.finditer(full_text))
    entries = []

    for i, m in enumerate(matches):
        start_dt = _parse_date(m.group("start"))
        end_dt = _parse_date(m.group("end"))
        if not start_dt or not end_dt:
            continue

        # descriptive text window: from this match to the next match (or end of section)
        window_start = m.end()
        window_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        desc_text = full_text[window_start:window_end]

        # title/company: the line(s) just before this match, on the same or previous line
        pre_text = full_text[:m.start()]
        pre_lines = [l.strip() for l in pre_text.split("\n") if l.strip()]
        title_line = pre_lines[-1] if pre_lines else "Role"
        # the date match is usually cut off the end of this same line (e.g.
        # "Senior Backend Developer, Infosys, Mar 2020 - Present"), leaving a
        # trailing separator behind once the date portion is removed
        title_line = title_line.rstrip(" ,-|·:").strip()
        if not title_line:
            title_line = "Role"

        months = _months_between(start_dt, end_dt)
        skills_found = find_skills_in_text(title_line + " " + desc_text)

        entries.append({
            "title": title_line,
            "start": start_dt,
            "end": end_dt,
            "start_str": m.group("start").strip(),
            "end_str": m.group("end").strip() if not re.match(PRESENT_WORDS, m.group("end"), re.I) else "Present",
            "months": months,
            "duration": format_duration(months),
            "skills": skills_found,
            "description": desc_text.strip(),
        })

    return entries


def compute_total_experience(entries) -> dict:
    """Total career span using merged (non-overlapping) intervals -- avoids inflated totals."""
    intervals = [(e["start"], e["end"]) for e in entries if e["start"] and e["end"]]
    merged = _merge_intervals(intervals)
    total_months = sum(_months_between(s, e) for s, e in merged)
    return {
        "months": total_months,
        "formatted": format_duration(total_months),
    }


def compute_stackwise_experience(entries) -> list:
    """
    Returns a list of {skill, category, months, duration, roles} sorted by months desc.
    Each skill's duration is the SUM of the entries in which it appeared -- so a skill
    used in only one 1-year role never shows up as if it were the whole 6-year career.
    """
    from .skills_database import skill_category

    skill_map = {}
    for e in entries:
        for s in e["skills"]:
            skill_map.setdefault(s, {"months": 0, "roles": []})
            skill_map[s]["months"] += e["months"]
            skill_map[s]["roles"].append(e["title"])

    result = []
    for skill, data in skill_map.items():
        result.append({
            "Skill / Stack": skill.title(),
            "Category": skill_category(skill),
            "Experience": format_duration(data["months"]),
            "Months": data["months"],
            "Used In (Role/Company)": ", ".join(sorted(set(data["roles"]))),
        })
    result.sort(key=lambda x: x["Months"], reverse=True)
    return result