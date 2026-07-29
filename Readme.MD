# Resume Analyzer & Shortlisting Tool (No API used)

A fully offline, rule-based Streamlit app that:

- Extracts personal details (Name, Email, Phone, LinkedIn, GitHub, Portfolio, Location) into a table
- Finds LinkedIn/GitHub even when they're only clickable **hyperlinks** in the PDF/DOCX with no
  visible URL text (e.g. a "View Profile" link)
- Extracts skills/keywords and highlights them as chips
- Parses work experience with real date ranges, correctly treating "to Present / Current / Till Date" as today
- Computes **stack-wise experience** (e.g. "Python — 11 months", "Django — 4 yrs 6 mos") instead of one
  inflated total, so a skill used in a single 1-year role never looks like the candidate's whole 6-year career
- Computes an accurate **overall total experience** by merging overlapping date ranges (no double-counting)
- Extracts and tabulates Projects with their tech stack (handles labeled blocks, "Skills Used:" narrative
  style, and plain title + paragraph — merged and de-duplicated so nothing is double-counted)
- Extracts Education, Certifications, **Achievements, Languages, Hobbies, and Publications** into their
  own sections — a combined header like "Education & Certifications" no longer causes one section to
  silently swallow the other
- Flags a **"couldn't confidently detect"** warning for any field it wasn't sure about, instead of
  silently leaving it blank
- Supports **candidate shortlisting**: upload multiple resumes, set required skills + minimum experience,
  and get a ranked, scored shortlist you can download as CSV
- Dark / Light theme toggle in the sidebar, with all text colours explicitly set for contrast in both modes
- No external AI/LLM API is used anywhere — all extraction is done with regex, date parsing and a
  built-in keyword database (`parser/skills_database.py`)

## Project structure

```
resume_analyzer/
├── app.py                        # Streamlit UI (main entry point)
├── theme.py                      # Dark/Light CSS theme
├── requirements.txt
├── README.md
└── parser/
    ├── __init__.py
    ├── file_reader.py            # Extracts text from PDF / DOCX / TXT (handles multi-column layouts
    │                              # and pulls hyperlink URLs the visible text doesn't show)
    ├── contact_extractor.py      # Name, email, phone, LinkedIn, GitHub, location
    ├── section_splitter.py       # Splits resume into Summary/Skills/Experience/Projects/etc.
    ├── experience_analyzer.py    # Date-range parsing + stack-wise & total experience logic
    ├── project_extractor.py      # Parses the Projects section into a table
    ├── skills_database.py        # Master keyword list (edit this to add more skills)
    ├── shortlisting.py           # Candidate scoring/ranking engine
    └── resume_parser.py          # Orchestrates all of the above into one result dict
```

## Setup (Windows / PowerShell)

```powershell
# 1. Extract the zip, then open PowerShell in the resume_analyzer folder
cd path\to\resume_analyzer

# 2. (Recommended) create a virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the app
streamlit run app.py
```

The app will open automatically at `http://localhost:8501`.

## Setup (Mac/Linux)

```bash
cd path/to/resume_analyzer
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## How to use it

1. **Single Resume Analysis tab** — upload one resume (PDF/DOCX/TXT) to see:
   - Personal details table
   - A completeness warning for anything that couldn't be confidently detected
   - Skills/keyword chips
   - Overall experience summary (merged, de-duplicated total)
   - Stack-wise / role-wise experience breakdown table
   - Detailed work experience entries
   - Projects table with tech stack
   - Education, Certifications, Achievements, Languages, Publications, Hobbies

2. **Candidate Shortlisting tab** — upload several resumes at once, type the required
   skills (comma separated) and the minimum years of experience, then click
   **Run Shortlisting** to get a ranked, colour-coded table you can export as CSV.

## Notes / limitations (important for your project report)

- All extraction is **rule-based** (regex + `python-dateutil`), not machine-learning based,
  as required (no API usage). This keeps the tool fully offline and free to run.
- Resumes vary a lot in formatting; the section-splitter and project-splitter use heuristics
  (line length, capitalisation, known header words, and — for combined headers like
  "Certifications & Achievements" — connector words) to find boundaries. Extremely unusual
  resume layouts (heavy multi-column PDFs, image-only/scanned resumes) may still need the
  `skills_database.py` keyword list expanded, or minor tweaks to `section_splitter.py`.
- Location detection only recognizes a curated list of Indian + major international cities
  without an explicit "Location:"/"Address:" label; add more to `INDIAN_CITY_HINTS` /
  `GLOBAL_CITY_HINTS` in `contact_extractor.py` if your candidate pool skews elsewhere.
- To add more recognised skills/tools, just add them to the appropriate category list in
  `parser/skills_database.py` — every other module (experience, projects, shortlisting)
  automatically picks up the change.
- The shortlisting score = 70% required-skills match + 30% experience-threshold match.
  You can change these weights in `parser/shortlisting.py` (`score_candidate` function).    