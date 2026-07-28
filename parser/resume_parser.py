"""Top-level orchestrator: raw resume text -> fully structured dict used by the app."""

from .section_splitter import split_sections
from .contact_extractor import extract_contact_details
from .experience_analyzer import (
    parse_experience_entries, compute_total_experience, compute_stackwise_experience
)
from .project_extractor import parse_projects_full
from .skills_database import find_skills_in_text


def parse_resume(raw_text: str) -> dict:
    sections = split_sections(raw_text)

    header_block = sections.get("header", "")
    contact = extract_contact_details(raw_text)

    experience_entries = parse_experience_entries(sections.get("experience", ""))
    total_exp = compute_total_experience(experience_entries)
    stackwise = compute_stackwise_experience(experience_entries)

    projects = parse_projects_full(raw_text, sections.get("projects", ""))

    skills_section_text = sections.get("skills", "")
    listed_skills = find_skills_in_text(skills_section_text)
    all_skills = sorted(set(listed_skills) | {s.lower() for e in experience_entries for s in e["skills"]}
                         | {s.lower() for p in projects for s in p["Tech Stack"].split(", ") if s and s != "Not specified"})

    result = {
        "raw_text": raw_text,
        "sections": sections,
        "contact": contact,
        "experience_entries": experience_entries,
        "total_experience_months": total_exp["months"],
        "total_experience_str": total_exp["formatted"],
        "stackwise_experience": stackwise,
        "projects": projects,
        "listed_skills": listed_skills,
        "all_skills": sorted(all_skills),
        "summary": sections.get("summary", "").strip() or "Not found",
        "education": sections.get("education", "").strip() or "Not found",
        "certifications": sections.get("certifications", "").strip() or "Not found",
        "achievements": sections.get("achievements", "").strip() or "Not found",
        "languages": sections.get("languages", "").strip() or "Not found",
        "hobbies": sections.get("hobbies", "").strip() or "Not found",
        "publications": sections.get("publications", "").strip() or "Not found",
    }

    # ---- completeness check: surface what couldn't be found instead of
    # letting it disappear silently, so HR knows to double-check the source
    # file rather than assuming the candidate simply has nothing there.
    missing = []
    for field in ("Name", "Email", "Phone"):
        if contact.get(field, "Not found") == "Not found":
            missing.append(field)
    if not experience_entries:
        missing.append("Work Experience (no date ranges detected)")
    if not projects:
        missing.append("Projects")
    if not all_skills:
        missing.append("Skills")
    if result["education"] == "Not found":
        missing.append("Education")
    result["missing_fields"] = missing

    return result