"""
Profile Matrix — app.py
Keeps the original working resume analyzer intact.
Adds login layer on top: candidate / recruiter, plus a hidden admin entry point.
"""

import pandas as pd
import streamlit as st

from theme import inject_theme
from auth_supabase import (
    handle_oauth_callback, google_oauth_url,
    signup_with_email, login_with_email, verify_otp, resend_otp,
    logout, get_role, is_logged_in, get_profile, get_user,
    upload_resume_to_storage, save_resume_record,
    get_candidate_resumes, get_all_resumes_for_recruiter, delete_resume,
    save_jd, get_recruiter_jds, save_shortlist_results, get_shortlist_for_jd,
    get_admin_stats, get_all_profiles_for_admin, get_all_resumes_for_admin,
)
from parser.file_reader import extract_text
from parser.resume_parser import parse_resume
from parser.shortlisting import shortlist_candidates, score_candidate

st.set_page_config(
    page_title="Profile Matrix",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------ theme
if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "Dark"

inject_theme(st.session_state.theme_mode)

# ------------------------------------------------------------------ OAuth callback
handle_oauth_callback()

if "parsed_resumes" not in st.session_state:
    st.session_state.parsed_resumes = {}


# ==================================================================
# AUTH PAGES
# ==================================================================

def page_login():
    st.markdown("## 🧾 Profile Matrix")
    st.markdown("##### AI-Free Resume Analyzer & Shortlisting Platform")
    st.markdown("---")

    # ------------------------------------------------------------
    # Hidden admin entry point — no "Admin" option is shown anywhere
    # in the public signup/login UI. Admin accounts are provisioned
    # manually (Supabase dashboard / SQL), never via public self-signup.
    # Reach this form only via ?admin=1 in the URL.
    # ------------------------------------------------------------
    is_admin_mode = st.query_params.get("admin") == "1"

    if is_admin_mode:
        st.markdown("### 🛡️ Admin Sign In")
        email = st.text_input("Admin Email", key="admin_email")
        password = st.text_input("Password", type="password", key="admin_pass")
        if st.button("Sign In", type="primary", use_container_width=True):
            if not email or not password:
                st.warning("Fill in all fields.")
            else:
                with st.spinner("Signing in..."):
                    result = login_with_email(email, password)
                if result["success"]:
                    if result["profile"].get("role") != "admin":
                        st.error("This account does not have admin access.")
                        logout()
                    else:
                        st.success("Logged in!")
                        st.rerun()
                else:
                    st.error(result.get("error", "Login failed"))
        return

    col_l, col_r = st.columns([1, 1], gap="large")

    with col_l:
        st.markdown("### Sign In")
        tab_email, tab_google = st.tabs(["📧 Email", "🔵 Google"])

        with tab_email:
            role = st.radio(
                "I am a", ["Candidate", "Recruiter"],
                horizontal=True, key="login_role"
            ).lower()
            email = st.text_input("Email", key="li_email")
            password = st.text_input("Password", type="password", key="li_pass")
            if st.button("Sign In", type="primary", use_container_width=True):
                if not email or not password:
                    st.warning("Fill in all fields.")
                else:
                    with st.spinner("Signing in..."):
                        result = login_with_email(email, password)
                    if result["success"]:
                        st.success("Logged in!")
                        st.rerun()
                    elif result.get("error") == "unverified":
                        st.warning("Email not verified. Check your inbox for the OTP.")
                        st.session_state["pending_verify_email"] = email
                        st.session_state["page"] = "verify"
                        st.rerun()
                    else:
                        st.error(result.get("error", "Login failed"))

        with tab_google:
            role_g = st.radio(
                "I am a", ["Candidate", "Recruiter"],
                horizontal=True, key="login_role_g"
            ).lower()
            st.markdown("")
            url = google_oauth_url(role_g)
            if url:
                st.markdown(
                    f'<a href="{url}" target="_self">'
                    f'<button style="width:100%;padding:10px;background:#4285F4;'
                    f'color:white;border:none;border-radius:8px;font-size:1rem;'
                    f'cursor:pointer;">🔵 Continue with Google</button></a>',
                    unsafe_allow_html=True,
                )

    with col_r:
        st.markdown("### Create Account")
        role_s = st.radio(
            "I am a", ["Candidate", "Recruiter"],
            horizontal=True, key="signup_role"
        ).lower()
        name = st.text_input("Full Name", key="su_name")
        email_s = st.text_input("Email", key="su_email")
        pass_s = st.text_input("Password (min 6 chars)", type="password", key="su_pass")
        pass_c = st.text_input("Confirm Password", type="password", key="su_pass2")

        if st.button("Create Account", type="primary", use_container_width=True):
            if not all([name, email_s, pass_s, pass_c]):
                st.warning("Fill in all fields.")
            elif pass_s != pass_c:
                st.error("Passwords do not match.")
            elif len(pass_s) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                with st.spinner("Creating account..."):
                    res = signup_with_email(email_s, pass_s, name, role_s)
                if res["success"]:
                    st.success("Account created! You can now sign in.")
                    st.session_state["page"] = "login"
                    st.rerun()
                else:
                    st.error(res.get("error", "Signup failed"))


def page_verify():
    email = st.session_state.get("pending_verify_email", "")
    st.markdown("## 📧 Verify Your Email")
    st.info(f"A 6-digit OTP was sent to **{email}**. Enter it below.")

    otp = st.text_input("Verification Code", max_chars=6, key="otp_input")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("✅ Verify", type="primary", use_container_width=True):
            res = verify_otp(email, otp)
            if res["success"]:
                st.success("Email verified! You can now sign in.")
                st.session_state.pop("pending_verify_email", None)
                st.session_state["page"] = "login"
                st.rerun()
            else:
                st.error(res.get("error", "Verification failed"))
    with col2:
        if st.button("🔁 Resend OTP", use_container_width=True):
            resend_otp(email)
            st.success("OTP resent!")
    if st.button("← Back to Login"):
        st.session_state["page"] = "login"
        st.rerun()


# ==================================================================
# SIDEBAR (shown when logged in)
# ==================================================================

def render_sidebar():
    profile = get_profile()
    name = profile.get("full_name") or profile.get("email", "User")
    role = get_role()
    icons = {"candidate": "👤", "recruiter": "🏢", "admin": "🛡️"}

    with st.sidebar:
        st.markdown(f"### {icons.get(role, '👤')} {name}")
        st.caption(f"Role: {role.title()}")
        st.markdown("---")
        st.session_state.theme_mode = st.radio(
            "Appearance", ["Light", "Dark"],
            index=0 if st.session_state.theme_mode == "Light" else 1,
            horizontal=True,
        )
        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()


# ==================================================================
# CANDIDATE — original working app preserved exactly
# ==================================================================

def page_candidate():
    render_sidebar()
    user = get_user()

    st.markdown("## 🧾 AI-Free Resume Analyzer & Shortlisting Tool")
    st.markdown(
        '<p class="subtle">Upload resumes to extract structured details, '
        "stack-wise experience, projects and keywords — then shortlist candidates "
        "against a job requirement.</p>",
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3 = st.tabs([
        "📄 Single Resume Analysis",
        "🎯 Candidate Shortlisting",
        "📁 My Saved Resumes",
    ])

    # ============================================================ TAB 1 — original
    with tab1:
        uploaded = st.file_uploader(
            "Upload a resume (PDF, DOCX or TXT)",
            type=["pdf", "docx", "txt"], key="single_upload"
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
                if parsed.get("missing_fields"):
                    st.warning(
                        "⚠️ Couldn't confidently detect: " + ", ".join(parsed["missing_fields"]) +
                        ". This can happen with unusual formatting — worth a quick manual check."
                    )

                # Personal details
                st.markdown('<div class="section-title">👤 Personal Details</div>', unsafe_allow_html=True)
                contact_df = pd.DataFrame(list(parsed["contact"].items()), columns=["Field", "Value"])
                st.table(contact_df)

                # Summary
                with st.expander("📝 Professional Summary / Objective (if found)"):
                    st.write(parsed["summary"])

                # Skills
                st.markdown('<div class="section-title">🛠️ Skills & Keywords Found</div>', unsafe_allow_html=True)
                if parsed["all_skills"]:
                    chips = "".join(f'<span class="chip">{s.title()}</span>' for s in parsed["all_skills"])
                    st.markdown(f'<div class="card">{chips}</div>', unsafe_allow_html=True)
                else:
                    st.info("No known keywords detected in this resume.")

                # Experience metrics
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

                # Stack-wise
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

                # Detailed entries
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

                # Projects
                st.markdown('<div class="section-title">🚀 Projects</div>', unsafe_allow_html=True)
                if parsed["projects"]:
                    proj_df = pd.DataFrame(parsed["projects"])
                    st.dataframe(proj_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No projects section detected.")

                # Education / Certifications
                colA, colB = st.columns(2)
                with colA:
                    st.markdown('<div class="section-title">🎓 Education</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="card">{parsed["education"]}</div>', unsafe_allow_html=True)
                with colB:
                    st.markdown('<div class="section-title">📜 Certifications</div>', unsafe_allow_html=True)
                    st.markdown(f'<div class="card">{parsed["certifications"]}</div>', unsafe_allow_html=True)

                # Extra sections
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

                # ==================================================
                # 🎯 NEW: Check Your Match Score Against a Job Description
                # Candidate-only self-check — paste a JD, see how this
                # exact resume scores against it. Reuses the same
                # score_candidate() function the recruiter dashboard
                # uses, so the number always matches recruiter-side logic.
                # ==================================================
                st.markdown("---")
                st.markdown(
                    '<div class="section-title">🎯 Check Your Match Score Against a Job Description</div>',
                    unsafe_allow_html=True,
                )
                st.caption(
                    "Paste a job description below to see how well this resume matches — "
                    "skills are auto-detected from the JD text, the same way they're detected "
                    "from resumes."
                )

                jd_text = st.text_area(
                    "Paste the Job Description here",
                    height=160,
                    key="candidate_jd_paste",
                    placeholder="Paste the full job description text here...",
                )
                jd_min_exp = st.number_input(
                    "Minimum experience required (years) — optional, from the JD",
                    min_value=0.0, step=0.5, value=0.0, key="candidate_jd_min_exp"
                )

                if st.button("🔍 Check My Score", type="primary", key="candidate_check_score"):
                    if not jd_text.strip():
                        st.warning("Paste a job description first.")
                    else:
                        with st.spinner("Analysing job description and scoring your resume..."):
                            jd_parsed = parse_resume(jd_text)
                            jd_required_skills = jd_parsed.get("all_skills", [])
                            score_row = score_candidate(parsed, jd_required_skills, jd_min_exp)

                        if not jd_required_skills:
                            st.info(
                                "No recognisable skills were detected in the pasted job "
                                "description, so scoring may be less accurate. Try pasting "
                                "the full JD including the requirements section."
                            )

                        sc1, sc2, sc3 = st.columns(3)
                        sc1.metric("Match Score", f"{score_row.get('Match Score (%)', 0)}%")
                        sc2.metric("Shortlisted?", score_row.get("Shortlisted", "No"))
                        sc3.metric("Your Experience", score_row.get("Total Experience", "0 mo"))

                        matched = score_row.get("Matched Skills", "-")
                        missing = score_row.get("Missing Skills", "-")

                        st.markdown("**✅ Matched Skills**")
                        if matched and matched != "-":
                            chips = "".join(f'<span class="chip">{s.strip().title()}</span>' for s in matched.split(","))
                            st.markdown(f'<div class="card">{chips}</div>', unsafe_allow_html=True)
                        else:
                            st.caption("No overlapping skills found.")

                        st.markdown("**❌ Missing Skills**")
                        if missing and missing != "-":
                            chips = "".join(f'<span class="chip">{s.strip().title()}</span>' for s in missing.split(","))
                            st.markdown(f'<div class="card">{chips}</div>', unsafe_allow_html=True)
                        else:
                            st.caption("No missing skills — great match!")

                # Save to Supabase
                st.markdown("---")
                if st.button("💾 Save Resume to My Profile", type="primary"):
                    with st.spinner("Uploading to Supabase..."):
                        file_bytes = uploaded.getvalue()
                        path = upload_resume_to_storage(file_bytes, uploaded.name, user.id)
                        save_resume_record(user.id, uploaded.name, path, len(file_bytes), parsed)
                    st.success("Resume saved to your profile!")
        else:
            st.info("👆 Upload a resume to see the full structured breakdown.")

    # ============================================================ TAB 2 — original shortlisting
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
                            p = parse_resume(text)
                            parsed_list.append(p)
                            st.session_state.parsed_resumes[f.name] = p
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
                    st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
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

    # ============================================================ TAB 3 — saved resumes
    with tab3:
        st.markdown("### Your Saved Resumes")
        resumes = get_candidate_resumes(user.id)
        if not resumes:
            st.info("No resumes saved yet. Upload one in the first tab and click Save.")
        else:
            for r in resumes:
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.markdown(f"**{r['file_name']}**")
                c2.caption(f"Exp: {r['total_experience_str']} | {r['uploaded_at'][:10]}")
                if c3.button("🗑️ Delete", key=f"del_{r['id']}"):
                    delete_resume(r["id"], f"{user.id}/{r['file_name']}")
                    st.success("Deleted.")
                    st.rerun()
                if r.get("all_skills"):
                    chips = "".join(
                        f'<span class="chip">{s.title()}</span>'
                        for s in (r["all_skills"] or [])[:10]
                    )
                    st.markdown(f'<div class="card">{chips}</div>', unsafe_allow_html=True)
                st.markdown("---")


# ==================================================================
# RECRUITER DASHBOARD
# ==================================================================

def page_recruiter():
    render_sidebar()
    user = get_user()

    st.markdown("## 🎯 Recruiter Dashboard")
    tab1, tab2, tab3 = st.tabs(["📋 Post JD & Shortlist", "📊 My JDs & Results", "👥 All Candidates"])

    with tab1:
        st.markdown("### Post a Job Description")
        jd_title = st.text_input("Job Title", placeholder="e.g. Senior Python Developer")
        jd_desc = st.text_area("Job Description (optional)", height=100)
        skills_raw = st.text_input(
            "Required Skills (comma separated)",
            placeholder="e.g. python, django, aws, docker"
        )
        min_exp = st.number_input("Minimum Experience (years)", min_value=0.0, step=0.5, value=2.0)

        if st.button("🔍 Shortlist from Candidate Pool", type="primary"):
            if not jd_title:
                st.warning("Enter a job title.")
            else:
                required_skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
                with st.spinner("Fetching resumes and scoring..."):
                    all_resumes = get_all_resumes_for_recruiter()

                if not all_resumes:
                    st.info("No candidate resumes in the system yet.")
                else:
                    jd = save_jd(user.id, jd_title, jd_desc, required_skills, min_exp)
                    jd_id = jd.get("id")
                    results = []
                    for r in all_resumes:
                        parsed = r.get("parsed_data", {})
                        if not parsed:
                            continue
                        row = score_candidate(parsed, required_skills, min_exp)
                        row["resume_id"] = r["id"]
                        row["matched_skills_list"] = [
                            s.strip() for s in row.get("Matched Skills", "").split(",")
                            if s.strip() and s.strip() != "-"
                        ]
                        row["missing_skills_list"] = [
                            s.strip() for s in row.get("Missing Skills", "").split(",")
                            if s.strip() and s.strip() != "-"
                        ]
                        results.append(row)

                    results.sort(key=lambda x: x["Match Score (%)"], reverse=True)
                    if jd_id:
                        save_shortlist_results(jd_id, results)

                    st.success(f"✅ Scored {len(results)} candidates!")

                    def badge(v):
                        cls = "badge-yes" if v == "Yes" else "badge-no"
                        return f'<span class="{cls}">{v}</span>'

                    df = pd.DataFrame(results)[[
                        "Name", "Email", "Total Experience",
                        "Matched Skills", "Missing Skills", "Match Score (%)", "Shortlisted"
                    ]]
                    df_display = df.copy()
                    df_display["Shortlisted"] = df_display["Shortlisted"].apply(badge)
                    st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
                    st.download_button(
                        "⬇️ Download CSV",
                        df.to_csv(index=False).encode("utf-8"),
                        file_name=f"shortlist_{jd_title}.csv",
                        mime="text/csv"
                    )

    with tab2:
        st.markdown("### Your Past JDs & Shortlist Results")
        jds = get_recruiter_jds(user.id)
        if not jds:
            st.info("No JDs posted yet.")
        else:
            for jd in jds:
                with st.expander(f"📋 {jd['title']} — {jd['created_at'][:10]}"):
                    st.write(f"**Required Skills:** {', '.join(jd['required_skills'] or [])}")
                    st.write(f"**Min Experience:** {jd['min_experience_years']} yrs")
                    results = get_shortlist_for_jd(jd["id"])
                    if results:
                        df = pd.DataFrame(results)[[
                            "candidate_name", "candidate_email",
                            "match_score", "shortlisted", "total_experience_str"
                        ]]
                        df.columns = ["Name", "Email", "Score (%)", "Shortlisted", "Experience"]
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        st.download_button(
                            "⬇️ Export CSV",
                            df.to_csv(index=False).encode("utf-8"),
                            file_name=f"shortlist_{jd['title']}.csv",
                            mime="text/csv",
                            key=f"dl_{jd['id']}"
                        )
                    else:
                        st.info("No results saved for this JD.")

    with tab3:
        st.markdown("### All Candidate Resumes in System")
        all_res = get_all_resumes_for_recruiter()
        if not all_res:
            st.info("No resumes uploaded by candidates yet.")
        else:
            fc1, fc2 = st.columns(2)
            skill_filter = fc1.text_input("Filter by skill", placeholder="e.g. python")
            exp_filter = fc2.number_input("Min experience (months)", min_value=0, step=6, value=0)

            filtered = all_res
            if skill_filter:
                sf = skill_filter.lower()
                filtered = [r for r in filtered if any(sf in s for s in (r.get("all_skills") or []))]
            if exp_filter > 0:
                filtered = [r for r in filtered if (r.get("total_experience_months") or 0) >= exp_filter]

            st.caption(f"Showing {len(filtered)} of {len(all_res)} resumes")
            rows = [{
                "Name": r.get("candidate_name", ""),
                "Email": r.get("candidate_email", ""),
                "Phone": r.get("candidate_phone", ""),
                "Experience": r.get("total_experience_str", ""),
                "Skills": ", ".join((r.get("all_skills") or [])[:8]),
                "Uploaded": (r.get("uploaded_at") or "")[:10],
            } for r in filtered]

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Export All Candidates CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name="all_candidates.csv",
                mime="text/csv"
            )


# ==================================================================
# ADMIN DASHBOARD
# ==================================================================

def page_admin():
    render_sidebar()
    st.markdown("## 🛡️ Admin Dashboard")

    with st.spinner("Loading stats..."):
        stats = get_admin_stats()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("👤 Candidates", stats["candidates"])
    c2.metric("🏢 Recruiters", stats["recruiters"])
    c3.metric("📄 Resumes", stats["resumes"])
    c4.metric("📋 JDs Posted", stats["jds"])
    c5.metric("✅ Shortlisted", stats["shortlisted"])

    st.markdown("---")
    tab1, tab2 = st.tabs(["👥 All Users", "📄 All Resumes"])

    with tab1:
        st.markdown("### All Registered Users")
        users = get_all_profiles_for_admin()
        if users:
            df = pd.DataFrame(users)[["full_name", "email", "role", "is_verified", "created_at"]]
            df.columns = ["Name", "Email", "Role", "Verified", "Joined"]
            df["Joined"] = df["Joined"].str[:10]
            role_f = st.selectbox("Filter by role", ["All", "candidate", "recruiter", "admin"])
            if role_f != "All":
                df = df[df["Role"] == role_f]
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Export Users CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name="all_users.csv", mime="text/csv"
            )
        else:
            st.info("No users found.")

    with tab2:
        st.markdown("### All Resumes")
        resumes = get_all_resumes_for_admin()
        if resumes:
            rows = [{
                "Candidate": r.get("candidate_name", ""),
                "Email": r.get("candidate_email", ""),
                "File": r.get("file_name", ""),
                "Experience": r.get("total_experience_str", ""),
                "Skills": ", ".join((r.get("all_skills") or [])[:6]),
                "Uploaded": (r.get("uploaded_at") or "")[:10],
            } for r in resumes]
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Export Resumes CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name="all_resumes.csv", mime="text/csv"
            )
        else:
            st.info("No resumes found.")


# ==================================================================
# ROUTER
# ==================================================================

def main():
    inject_theme(st.session_state.get("theme_mode", "Dark"))

    if is_logged_in():
        role = get_role()
        if role == "candidate":
            page_candidate()
        elif role == "recruiter":
            page_recruiter()
        elif role == "admin":
            page_admin()
        else:
            st.error("Unknown role. Please contact admin.")
            if st.button("Logout"):
                logout()
                st.rerun()
    else:
        page = st.session_state.get("page", "login")
        if page == "verify":
            page_verify()
        else:
            page_login()


if __name__ == "__main__":
    main()