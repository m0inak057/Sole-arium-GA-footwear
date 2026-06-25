"""Streamlit MVP viewer for the Sole-Arium Gait Analysis pipeline.

Launch with:
    streamlit run src/gait/app/viewer.py

Requires the API server to be running:
    uvicorn src.gait.api.main:app --host 0.0.0.0 --port 8000

Configure the API URL via the GAIT_API_URL environment variable.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests

try:
    import streamlit as st
except ImportError:
    raise ImportError(
        "Streamlit is not installed. Install it with: pip install streamlit"
    )

API_BASE = os.getenv("GAIT_API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Sole-Arium Gait Analyser",
    page_icon="👟",
    layout="wide",
)

st.title("Sole-Arium Gait Analysis Viewer")
st.caption(f"API: `{API_BASE}`")

# ── Sidebar — session management ──────────────────────────────────────────────

st.sidebar.header("Session")

mode = st.sidebar.radio("Mode", ["Create new session", "Track existing session"])

# ── Create new session ────────────────────────────────────────────────────────

if mode == "Create new session":
    st.header("1. Create Session")

    with st.form("create_session_form"):
        patient_id = st.text_input("Patient ID", placeholder="P0042")
        col1, col2 = st.columns(2)
        height_cm = col1.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=172.0)
        mass_kg = col2.number_input("Weight (kg)", min_value=10.0, max_value=300.0, value=68.0)

        col3, col4 = st.columns(2)
        foot_len_l = col3.number_input("Foot length L (mm)", value=258.0)
        foot_len_r = col4.number_input("Foot length R (mm)", value=260.0)

        col5, col6 = st.columns(2)
        foot_w_l = col5.number_input("Foot width L (mm)", value=98.0)
        foot_w_r = col6.number_input("Foot width R (mm)", value=99.0)

        submitted = st.form_submit_button("Create Session")

    if submitted:
        if not patient_id:
            st.error("Patient ID is required.")
        else:
            payload = {
                "patient_id": patient_id,
                "anthropometrics": {
                    "height_cm": height_cm,
                    "mass_kg": mass_kg,
                    "foot_length_mm": {"L": foot_len_l, "R": foot_len_r},
                    "foot_width_mm": {"L": foot_w_l, "R": foot_w_r},
                },
            }
            try:
                r = requests.post(f"{API_BASE}/api/v1/sessions", json=payload, timeout=10)
                r.raise_for_status()
                data = r.json()
                session_id = data["session_id"]
                st.success(f"Session created: `{session_id}`")
                st.session_state["session_id"] = session_id
            except requests.RequestException as exc:
                st.error(f"Failed to create session: {exc}")

    # Upload section (only after session created)
    if "session_id" in st.session_state:
        session_id = st.session_state["session_id"]
        st.header("2. Upload Videos")
        st.info(f"Session ID: `{session_id}`")

        uploaded_file = st.file_uploader(
            "Select a video file (MP4)", type=["mp4", "avi", "mov"]
        )
        camera_view = st.selectbox(
            "Camera view", ["anterior", "sagittal", "posterior"]
        )

        if st.button("Upload") and uploaded_file:
            try:
                r = requests.post(
                    f"{API_BASE}/api/v1/sessions/{session_id}/uploads",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue(), "video/mp4")},
                    params={"camera_view": camera_view},
                    timeout=60,
                )
                r.raise_for_status()
                st.success(f"Uploaded `{uploaded_file.name}` ({r.json()['size_bytes']} bytes)")
            except requests.RequestException as exc:
                st.error(f"Upload failed: {exc}")

        st.header("3. Run Analysis")
        if st.button("Start Processing"):
            try:
                r = requests.post(
                    f"{API_BASE}/api/v1/sessions/{session_id}/process",
                    json={},
                    timeout=10,
                )
                r.raise_for_status()
                st.success("Processing started. See status below.")
            except requests.RequestException as exc:
                st.error(f"Failed to start processing: {exc}")

# ── Track existing session ────────────────────────────────────────────────────

else:
    st.header("Track Session")
    session_id_input = st.text_input(
        "Session ID",
        value=st.session_state.get("session_id", ""),
        placeholder="Paste session UUID here",
    )
    auto_refresh = st.checkbox("Auto-refresh every 5 seconds", value=False)

    if session_id_input:
        try:
            r = requests.get(
                f"{API_BASE}/api/v1/sessions/{session_id_input}/status",
                timeout=10,
            )
            r.raise_for_status()
            status_data = r.json()

            status_val = status_data.get("status", "UNKNOWN")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Status", status_val)
            col_b.metric("Patient ID", status_data.get("patient_id", "—"))
            col_c.metric("Progress", f"{status_data.get('progress_pct', 0) or 0:.0f}%")

            if status_data.get("error_message"):
                st.error(f"Error: {status_data['error_message']}")

            if status_val == "COMPLETED":
                st.success("Analysis complete!")
                prof_r = requests.get(
                    f"{API_BASE}/api/v1/sessions/{session_id_input}/profile",
                    timeout=10,
                )
                prof_r.raise_for_status()
                profile_data: Optional[Dict[str, Any]] = prof_r.json().get("profile")

                if profile_data:
                    _render_profile(profile_data)

        except requests.RequestException as exc:
            st.error(f"Could not reach API: {exc}")

        if auto_refresh and status_val not in ("COMPLETED", "FAILED"):
            time.sleep(5)
            st.rerun()


# ── Profile rendering ─────────────────────────────────────────────────────────


def _render_profile(profile: Dict[str, Any]) -> None:
    """Render the profile dict as a Streamlit dashboard."""
    st.header("Gait Profile")

    # Health assessment card
    assessment = profile.get("health_assessment", {})
    if assessment:
        st.subheader("Health Assessment")

        # What went right
        positives = assessment.get("what_went_right", [])
        if positives:
            st.success("✓ Strengths")
            for item in positives:
                st.write(f"• {item}")

        # Defects found
        defects = assessment.get("defects_found", [])
        if defects:
            st.warning("⚠ Areas for Improvement")
            for defect in defects:
                with st.expander(f"{defect.get('name', 'Unknown')} ({defect.get('severity', '?')})", expanded=False):
                    st.write(f"**Affected side:** {defect.get('affected_side', '?')}")
                    st.write(f"**Cause:** {defect.get('biomechanical_cause', '?')}")
                    st.write(f"**Phase:** {defect.get('gait_cycle_phase', '?')}")

        # Improvement plan
        improvements = assessment.get("improvement_plan", [])
        if improvements:
            st.info("💡 Recommended Exercises")
            for action in improvements:
                with st.expander(f"{action.get('exercise_name', 'Unknown')}", expanded=False):
                    st.write(f"**Target:** {action.get('target_area', '?')}")
                    st.write(f"**Frequency:** {action.get('frequency', '?')}")
                    st.write(f"**Instructions:** {action.get('instructions', '?')}")
                    st.write(f"*Addresses: {action.get('addresses_defect', '?')}*")

    # Pronation
    pronation = profile.get("pronation", {})
    if pronation:
        st.subheader("Pronation Analysis")
        classification = pronation.get("classification", {})
        rfa = pronation.get("rearfoot_angle_at_midstance_deg", {})
        p_cols = st.columns(2)
        p_cols[0].metric("L Classification", classification.get("L", "—"))
        p_cols[1].metric("R Classification", classification.get("R", "—"))
        p_cols[0].metric("L Rearfoot Angle (°)", f"{rfa.get('L', 0):.1f}")
        p_cols[1].metric("R Rearfoot Angle (°)", f"{rfa.get('R', 0):.1f}")

    # Symmetry flags
    flags = profile.get("symmetry_flags", [])
    if flags:
        st.warning(f"Symmetry flags: {', '.join(flags)}")

    if profile.get("needs_human_review"):
        st.error("This profile requires clinician/orthotist review.")

    # Raw JSON expander
    with st.expander("Full Profile JSON"):
        st.json(profile)
