import streamlit as st
import pandas as pd

from theme import inject_theme
from parser.file_reader import extract_text
from parser.resume_parser import parse_resume
from parser.shortlisting import shortlist_candidates

st.set_page_config(
    page_title="Resume Analyzer for HR",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------- theme setup
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Light"

with st.sidebar:
    st.markdown("### ⚙️ Settings")
    st.session_state.theme_mode = st.radio(
        "Appearance", ["Light", "Dark"],
        index=0 if st.session_state.theme_mode == "Light" else 1,
        horizontal=True,
    )
    st.markdown("---")
    st.markdown(
        "**Resume Analyzer**\n\n"
        "Extracts structured candidate data from resumes and helps HR shortlist "
    
    )

inject_theme(st.session_state.theme_mode)

st.markdown("## 🧾 AI-Free Resume Analyzer & Shortlisting Tool")
st.markdown(
    '<p class="subtle">Upload resumes to extract structured details, '
    "stack-wise experience, projects and keywords — then shortlist candidates "
    "against a job requirement.</p>",
    unsafe_allow_html=True,
)

if "parsed_resumes" not in st.session_state:
    st.session_state.parsed_resumes = {}  # filename -> parsed dict

tab1, tab2 = st.tabs(["📄 Single Resume Analysis", "🎯 Candidate Shortlisting"])

# ============================================================== TAB 1
with tab1:
    uploaded = st.file_uploader(
        "Upload a resume (PDF, DOCX or TXT)", type=["pdf", "docx", "txt"], key="single_upload"
    )

    if uploaded:
        with st.spinner("Extracting and analysing resume..."):
            try:
                raw_text = extract_text(uploaded)
                parsed = parse_resume(raw_text)
                st.session_state.parsed_resumes[uploaded.name] = parsed
            except Exception as e:
                st.error(f"Could not process this file: {e}")
                parsed = None

        if parsed:
            # ---------------- Completeness warning (advanced feature)
            if parsed.get("missing_fields"):
                st.warning(
                    "⚠️ Couldn't confidently detect: " + ", ".join(parsed["missing_fields"]) +
                    ". This can happen with unusual formatting — worth a quick manual check."
                )

            # ---------------- Personal details
            st.markdown('<div class="section-title">👤 Personal Details</div>', unsafe_allow_html=True)
            contact_df = pd.DataFrame(list(parsed["contact"].items()), columns=["Field", "Value"])
            st.table(contact_df)

            # ---------------- Summary
            with st.expander("📝 Professional Summary / Objective (if found)"):
                st.write(parsed["summary"])

            # ---------------- Skills / keywords
            st.markdown('<div class="section-title">🛠️ Skills & Keywords Found</div>', unsafe_allow_html=True)
            if parsed["all_skills"]:
                chips = "".join(f'<span class="chip">{s.title()}</span>' for s in parsed["all_skills"])
                st.markdown(f'<div class="card">{chips}</div>', unsafe_allow_html=True)
            else:
                st.info("No known keywords detected in this resume.")

            # ---------------- Total experience metric
            st.markdown('<div class="section-title">📊 Overall Experience Summary</div>', unsafe_allow_html=True)
            col1, col2, col3 = st.columns(3)
            col1.metric("Total Experience (merged, no double-count)", parsed["total_experience_str"])
            col2.metric("Work Entries Detected", len(parsed["experience_entries"]))
            col3.metric("Projects Detected", len(parsed["projects"]))
            st.caption(
                "Total experience is calculated by merging overlapping date ranges, "
                "so it reflects the real career span rather than simply adding up every "
                "role's duration."
            )

            # ---------------- Stack-wise experience (the key requested feature)
            st.markdown(
                '<div class="section-title">🧩 Stack-wise / Role-wise Experience Breakdown</div>',
                unsafe_allow_html=True,
            )
            if parsed["stackwise_experience"]:
                stack_df = pd.DataFrame(parsed["stackwise_experience"])[
                    ["Skill / Stack", "Category", "Experience", "Used In (Role/Company)"]
                ]
                st.dataframe(stack_df, use_container_width=True, hide_index=True)
                st.caption(
                    "Each skill's experience is the sum of only the roles/entries where it "
                    "was actually mentioned — so a skill used in one 1-year role will never "
                    "be shown as if it were the candidate's full 6-year career."
                )
            else:
                st.info("No date-ranged experience entries were detected in this resume.")

            # ---------------- Raw experience entries
            with st.expander("📁 Detailed Work Experience Entries"):
                if parsed["experience_entries"]:
                    for e in parsed["experience_entries"]:
                        st.markdown(
                            f"**{e['title']}** &nbsp;·&nbsp; {e['start_str']} → {e['end_str']} "
                            f"&nbsp;·&nbsp; **{e['duration']}**"
                        )
                        if e["skills"]:
                            st.markdown(", ".join(f"`{s}`" for s in e["skills"]))
                        st.markdown("---")
                else:
                    st.write("No detailed entries found.")

            # ---------------- Projects
            st.markdown('<div class="section-title">🚀 Projects</div>', unsafe_allow_html=True)
            if parsed["projects"]:
                proj_df = pd.DataFrame(parsed["projects"])
                st.dataframe(proj_df, use_container_width=True, hide_index=True)
            else:
                st.info("No projects section detected.")

            # ---------------- Education / Certifications
            colA, colB = st.columns(2)
            with colA:
                st.markdown('<div class="section-title">🎓 Education</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card">{parsed["education"]}</div>', unsafe_allow_html=True)
            with colB:
                st.markdown('<div class="section-title">📜 Certifications</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="card">{parsed["certifications"]}</div>', unsafe_allow_html=True)

            # ---------------- Achievements / Languages / Publications / Hobbies
            extra_sections = [
                ("🏆 Achievements", parsed.get("achievements", "Not found")),
                ("🗣️ Languages", parsed.get("languages", "Not found")),
                ("📚 Publications", parsed.get("publications", "Not found")),
                ("🎯 Hobbies / Interests", parsed.get("hobbies", "Not found")),
            ]
            extra_sections = [(label, text) for label, text in extra_sections if text != "Not found"]
            if extra_sections:
                cols = st.columns(len(extra_sections))
                for col, (label, text) in zip(cols, extra_sections):
                    with col:
                        st.markdown(f'<div class="section-title">{label}</div>', unsafe_allow_html=True)
                        st.markdown(f'<div class="card">{text}</div>', unsafe_allow_html=True)

    else:
        st.info("👆 Upload a resume to see the full structured breakdown.")

# ============================================================== TAB 2
with tab2:
    st.markdown("Upload **multiple resumes** and define the job requirement to auto-shortlist candidates.")

    uploaded_multi = st.file_uploader(
        "Upload resumes (PDF, DOCX or TXT) — multiple allowed",
        type=["pdf", "docx", "txt"], accept_multiple_files=True, key="multi_upload"
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        required_skills_raw = st.text_input(
            "Required skills (comma separated)",
            placeholder="e.g. python, react, aws, docker"
        )
    with col2:
        min_exp = st.number_input("Minimum experience (years)", min_value=0.0, step=0.5, value=1.0)

    run = st.button("🔍 Run Shortlisting", type="primary")

    if run:
        if not uploaded_multi:
            st.warning("Please upload at least one resume first.")
        else:
            parsed_list = []
            with st.spinner("Parsing resumes..."):
                for f in uploaded_multi:
                    try:
                        text = extract_text(f)
                        parsed = parse_resume(text)
                        parsed_list.append(parsed)
                        st.session_state.parsed_resumes[f.name] = parsed
                    except Exception as e:
                        st.error(f"Skipped {f.name}: {e}")

            required_skills = [s.strip() for s in required_skills_raw.split(",")] if required_skills_raw else []
            results = shortlist_candidates(parsed_list, required_skills, min_exp)

            st.markdown('<div class="section-title">🏆 Shortlisting Results</div>', unsafe_allow_html=True)
            if results:
                df = pd.DataFrame(results)

                def badge(v):
                    cls = "badge-yes" if v == "Yes" else "badge-no"
                    return f'<span class="{cls}">{v}</span>'

                df_display = df.copy()
                df_display["Shortlisted"] = df_display["Shortlisted"].apply(badge)
                st.write(
                    df_display.to_html(escape=False, index=False),
                    unsafe_allow_html=True,
                )
                st.download_button(
                    "⬇️ Download results as CSV",
                    df.to_csv(index=False).encode("utf-8"),
                    file_name="shortlisted_candidates.csv",
                    mime="text/csv",
                )
            else:
                st.info("No candidates parsed.")
    else:
        st.caption("Upload resumes, set requirements above, then click **Run Shortlisting**.")