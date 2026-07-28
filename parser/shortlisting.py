"""
Candidate shortlisting: given a list of parsed resumes (dicts produced by
resume_parser.parse_resume) plus HR-defined required skills and a minimum
total-experience threshold, computes a match score and ranks candidates.

Scoring (no external API / ML model -- fully transparent, rule based):
  - 70% weight: fraction of required skills present anywhere in the resume
  - 30% weight: whether total experience meets/exceeds the minimum required
                (partial credit if close)
"""


def score_candidate(parsed_resume: dict, required_skills: list, min_experience_years: float):
    required_skills = [s.strip().lower() for s in required_skills if s.strip()]
    resume_skills = set(s.lower() for s in parsed_resume.get("all_skills", []))

    if required_skills:
        matched = [s for s in required_skills if s in resume_skills]
        missing = [s for s in required_skills if s not in resume_skills]
        skill_ratio = len(matched) / len(required_skills)
    else:
        matched, missing, skill_ratio = [], [], 1.0

    total_months = parsed_resume.get("total_experience_months", 0)
    total_years = total_months / 12

    if min_experience_years <= 0:
        exp_ratio = 1.0
    else:
        exp_ratio = min(total_years / min_experience_years, 1.0)

    score = round((skill_ratio * 0.7 + exp_ratio * 0.3) * 100, 1)

    return {
        "Name": parsed_resume["contact"].get("Name", "Unknown"),
        "Email": parsed_resume["contact"].get("Email", "-"),
        "Total Experience": parsed_resume.get("total_experience_str", "0 mo"),
        "Matched Skills": ", ".join(m.title() for m in matched) if matched else "-",
        "Missing Skills": ", ".join(m.title() for m in missing) if missing else "-",
        "Match Score (%)": score,
        "Shortlisted": "Yes" if score >= 60 else "No",
    }


def shortlist_candidates(parsed_resumes: list, required_skills: list, min_experience_years: float):
    rows = [score_candidate(r, required_skills, min_experience_years) for r in parsed_resumes]
    rows.sort(key=lambda r: r["Match Score (%)"], reverse=True)
    return rows