"""
Supabase auth + DB helpers for Profile Matrix.
Handles: Google OAuth, email/password signup with OTP verification,
resume storage, JD management, shortlisting persistence.
"""

import random
import string
import smtplib
import json
from datetime import datetime, date, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import streamlit as st
from supabase import create_client, Client


# ------------------------------------------------------------------ client
@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["anon_key"]
    return create_client(url, key)


# ------------------------------------------------------------------ JSON-safety helper
def _json_safe(value):
    """
    Recursively convert datetime/date objects (and anything else json.dumps
    can't handle) into JSON-serializable equivalents. Needed because
    parse_resume() embeds datetime/date objects inside experience entries,
    and postgrest-py/httpx will raise 'Object of type datetime is not JSON
    serializable' when the record is sent to Supabase.
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    # Fallback: round-trip through json with a default str() converter,
    # which safely handles Decimal, set, or any other odd type that might
    # sneak in from the parser without us having to special-case it here.
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


# ------------------------------------------------------------------ session helpers
def get_session():
    return st.session_state.get("supabase_session")


def get_user():
    return st.session_state.get("supabase_user")


def get_profile():
    return st.session_state.get("user_profile")


def is_logged_in():
    return get_session() is not None


def get_role():
    p = get_profile()
    return p.get("role") if p else None


def logout():
    sb = get_supabase()
    try:
        sb.auth.sign_out()
    except Exception:
        pass
    for key in ["supabase_session", "supabase_user", "user_profile"]:
        st.session_state.pop(key, None)


# ------------------------------------------------------------------ profile fetch
def fetch_profile(user_id: str) -> dict:
    sb = get_supabase()
    try:
        res = sb.table("profiles").select("*").eq("id", user_id).single().execute()
        return res.data or {}
    except Exception:
        return {}


def load_profile_to_session(user):
    profile = fetch_profile(user.id)
    st.session_state["supabase_user"] = user
    st.session_state["user_profile"] = profile
    return profile


# ------------------------------------------------------------------ Google OAuth
def google_oauth_url(role: str = "candidate") -> str:
    sb = get_supabase()
    redirect = st.secrets["supabase"].get("redirect_url", "http://localhost:8501")
    res = sb.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": redirect,
            "query_params": {"role": role},
        }
    })
    return res.url if res else None


def handle_oauth_callback():
    """Call once at app start to catch ?code= in URL after Google redirect."""
    params = st.query_params
    code = params.get("code")
    if code and not is_logged_in():
        sb = get_supabase()
        try:
            res = sb.auth.exchange_code_for_session({"auth_code": code})
            if res.session:
                st.session_state["supabase_session"] = res.session
                profile = load_profile_to_session(res.session.user)
                st.query_params.clear()
                return profile
        except Exception as e:
            st.error(f"OAuth error: {e}")
    return None


# ------------------------------------------------------------------ Email/password auth
def _generate_otp(length=6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _send_verification_email(to_email: str, otp: str):
    """Send OTP via SMTP. Configure smtp_* in secrets.toml."""
    cfg = st.secrets.get("smtp", {})
    host = cfg.get("host", "smtp.gmail.com")
    port = int(cfg.get("port", 587))
    sender = cfg.get("sender_email", "")
    password = cfg.get("sender_password", "")

    if not sender or not password:
        st.info(f"[DEV] Your OTP is: **{otp}**")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Profile Matrix - Email Verification"
    msg["From"] = sender
    msg["To"] = to_email

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;
                border:1px solid #e2e8f0;border-radius:12px;padding:32px;">
      <h2 style="color:#2563eb">Profile Matrix</h2>
      <p>Your verification code is:</p>
      <div style="font-size:2rem;font-weight:700;letter-spacing:8px;
                  color:#1a1f2b;background:#eef2ff;padding:16px;
                  border-radius:8px;text-align:center;">{otp}</div>
      <p style="color:#6b7280;font-size:0.85rem;margin-top:16px;">
        This code expires in 10 minutes. Do not share it.
      </p>
    </div>
    """
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
    except Exception as e:
        st.warning(f"Could not send email ({e}). OTP: **{otp}**")


def signup_with_email(email: str, password: str, full_name: str, role: str) -> dict:
    sb = get_supabase()
    try:
        res = sb.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {"full_name": full_name, "role": role},
                "email_redirect_to": None,
            }
        })
        if res.user:
            # Update role and name — is_verified set to true by trigger
            sb.table("profiles").update({
                "role": role,
                "full_name": full_name,
                "is_verified": True,
            }).eq("id", res.user.id).execute()
            return {"success": True, "user": res.user}
        return {"success": False, "error": "Signup failed — email may already exist"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def verify_otp(email: str, otp: str) -> dict:
    sb = get_supabase()
    try:
        res = sb.table("profiles").select("*").eq("email", email).single().execute()
        if not res.data:
            return {"success": False, "error": "User not found"}
        profile = res.data
        stored_otp = profile.get("verification_code")
        expires_str = profile.get("verification_expires_at")
        if not stored_otp or stored_otp != otp:
            return {"success": False, "error": "Invalid OTP"}
        if expires_str:
            expires = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
            if datetime.utcnow().replace(tzinfo=expires.tzinfo) > expires:
                return {"success": False, "error": "OTP expired — request a new one"}
        sb.table("profiles").update({
            "is_verified": True,
            "verification_code": None,
        }).eq("email", email).execute()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def resend_otp(email: str) -> dict:
    sb = get_supabase()
    try:
        res = sb.table("profiles").select("id").eq("email", email).single().execute()
        if not res.data:
            return {"success": False, "error": "User not found"}
        otp = _generate_otp()
        expires = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        sb.table("profiles").update({
            "verification_code": otp,
            "verification_expires_at": expires,
        }).eq("email", email).execute()
        _send_verification_email(email, otp)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


def login_with_email(email: str, password: str) -> dict:
    sb = get_supabase()
    try:
        res = sb.auth.sign_in_with_password({"email": email, "password": password})
        if res.session:
            profile = fetch_profile(res.user.id)
            st.session_state["supabase_session"] = res.session
            st.session_state["supabase_user"] = res.user
            st.session_state["user_profile"] = profile
            return {"success": True, "profile": profile}
        return {"success": False, "error": "Login failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ------------------------------------------------------------------ Resume storage
def upload_resume_to_storage(file_bytes: bytes, file_name: str, candidate_id: str) -> str:
    sb = get_supabase()
    path = f"{candidate_id}/{file_name}"
    sb.storage.from_("resumes").upload(
        path, file_bytes,
        {"content-type": "application/octet-stream", "upsert": "true"}
    )
    return path


def save_resume_record(candidate_id: str, file_name: str, file_path: str,
                       file_size: int, parsed: dict) -> dict:
    sb = get_supabase()
    contact = parsed.get("contact", {})
    # parsed can contain datetime/date objects (e.g. inside experience_entries)
    # which the Supabase client can't JSON-serialize directly — sanitize first.
    safe_parsed = _json_safe(parsed)
    record = {
        "candidate_id": candidate_id,
        "file_name": file_name,
        "file_path": file_path,
        "file_size": file_size,
        "parsed_data": safe_parsed,
        "total_experience_months": parsed.get("total_experience_months", 0),
        "total_experience_str": parsed.get("total_experience_str", "0 mo"),
        "all_skills": parsed.get("all_skills", []),
        "candidate_name": contact.get("Name", "Unknown"),
        "candidate_email": contact.get("Email", ""),
        "candidate_phone": contact.get("Phone", ""),
    }
    try:
        existing = sb.table("resumes").select("id").eq(
            "candidate_id", candidate_id
        ).eq("file_name", file_name).execute()
        if existing.data:
            res = sb.table("resumes").update(record).eq(
                "id", existing.data[0]["id"]
            ).execute()
        else:
            res = sb.table("resumes").insert(record).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        st.error(f"Failed to save resume: {e}")
        return {}


def get_candidate_resumes(candidate_id: str) -> list:
    sb = get_supabase()
    try:
        res = sb.table("resumes").select(
            "id,file_name,file_size,total_experience_str,all_skills,candidate_name,uploaded_at"
        ).eq("candidate_id", candidate_id).order("uploaded_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def get_all_resumes_for_recruiter() -> list:
    sb = get_supabase()
    try:
        res = sb.table("resumes").select(
            "id,file_name,candidate_name,candidate_email,candidate_phone,"
            "total_experience_months,total_experience_str,all_skills,parsed_data,uploaded_at"
        ).order("uploaded_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def delete_resume(resume_id: str, file_path: str):
    sb = get_supabase()
    try:
        sb.storage.from_("resumes").remove([file_path])
    except Exception:
        pass
    try:
        sb.table("resumes").delete().eq("id", resume_id).execute()
    except Exception as e:
        st.error(f"Failed to delete resume: {e}")


# ------------------------------------------------------------------ JD + shortlisting
def save_jd(recruiter_id: str, title: str, description: str,
            required_skills: list, min_exp: float) -> dict:
    sb = get_supabase()
    try:
        res = sb.table("job_descriptions").insert({
            "recruiter_id": recruiter_id,
            "title": title,
            "description": description,
            "required_skills": required_skills,
            "min_experience_years": min_exp,
        }).execute()
        return res.data[0] if res.data else {}
    except Exception as e:
        st.error(f"Failed to save JD: {e}")
        return {}


def get_recruiter_jds(recruiter_id: str) -> list:
    sb = get_supabase()
    try:
        res = sb.table("job_descriptions").select("*").eq(
            "recruiter_id", recruiter_id
        ).order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def save_shortlist_results(jd_id: str, results: list):
    sb = get_supabase()
    try:
        sb.table("shortlist_results").delete().eq("jd_id", jd_id).execute()
        rows = []
        for r in results:
            rows.append({
                "jd_id": jd_id,
                "resume_id": r.get("resume_id"),
                "candidate_name": r.get("Name"),
                "candidate_email": r.get("Email"),
                "match_score": r.get("Match Score (%)"),
                "matched_skills": r.get("matched_skills_list", []),
                "missing_skills": r.get("missing_skills_list", []),
                "shortlisted": r.get("Shortlisted") == "Yes",
                "total_experience_str": r.get("Total Experience"),
            })
        if rows:
            sb.table("shortlist_results").insert(rows).execute()
    except Exception as e:
        st.error(f"Failed to save shortlist: {e}")


def get_shortlist_for_jd(jd_id: str) -> list:
    sb = get_supabase()
    try:
        res = sb.table("shortlist_results").select("*").eq(
            "jd_id", jd_id
        ).order("match_score", desc=True).execute()
        return res.data or []
    except Exception:
        return []


# ------------------------------------------------------------------ Admin stats
def get_admin_stats() -> dict:
    sb = get_supabase()
    try:
        candidates = sb.table("profiles").select(
            "id", count="exact").eq("role", "candidate").execute()
        recruiters = sb.table("profiles").select(
            "id", count="exact").eq("role", "recruiter").execute()
        resumes = sb.table("resumes").select("id", count="exact").execute()
        jds = sb.table("job_descriptions").select("id", count="exact").execute()
        shortlisted = sb.table("shortlist_results").select(
            "id", count="exact").eq("shortlisted", True).execute()
        return {
            "candidates": candidates.count or 0,
            "recruiters": recruiters.count or 0,
            "resumes": resumes.count or 0,
            "jds": jds.count or 0,
            "shortlisted": shortlisted.count or 0,
        }
    except Exception:
        return {
            "candidates": 0,
            "recruiters": 0,
            "resumes": 0,
            "jds": 0,
            "shortlisted": 0,
        }


def get_all_profiles_for_admin() -> list:
    sb = get_supabase()
    try:
        res = sb.table("profiles").select(
            "id,email,full_name,role,is_verified,created_at"
        ).order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def get_all_resumes_for_admin() -> list:
    sb = get_supabase()
    try:
        res = sb.table("resumes").select(
            "id,file_name,candidate_name,candidate_email,"
            "total_experience_str,all_skills,uploaded_at"
        ).order("uploaded_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []