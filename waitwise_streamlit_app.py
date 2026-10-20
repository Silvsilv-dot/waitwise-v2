import os
import streamlit as st
import pandas as pd
import psycopg2
import qrcode
from io import BytesIO
from datetime import datetime, timedelta

# -----------------------------------------------------------------------------
# Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Waitwise - Albany Health Center",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Healthcare Theme CSS
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #0E2A47; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1rem; color: #556B82; margin-bottom: 1.5rem; }
    .clinic-banner { background-color: #E0F2FE; border-left: 5px solid #0284C7; padding: 10px 15px; border-radius: 4px; margin-bottom: 15px; }
    .alert-cancelled { background-color: #FEE2E2; border: 1px solid #EF4444; color: #991B1B; padding: 10px; border-radius: 6px; margin-bottom: 10px; font-weight: 600; }
    .card { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
    .badge-scheduled { background-color: #E0F2FE; color: #0369A1; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
    .badge-completed { background-color: #DCFCE7; color: #15803D; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
    .badge-cancelled { background-color: #FEE2E2; color: #B91C1C; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
    .badge-reschedule { background-color: #FEF3C7; color: #B45309; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# Privacy & Demo Banner
st.warning("⚠️ **DEMO SYSTEM**: Synthetic data only for Albany Health Center. No real Protected Health Information (PHI).")

# Single Albany Clinic Information
st.markdown("""
<div class="clinic-banner">
    <strong>📍 Location:</strong> Waitwise Albany Health Center — 100 Demo Plaza, Albany, NY 12207 | 📞 (518) 555-0101<br>
    <em>All primary care, rheumatology, and nurse practitioner services consolidated at this location.</em>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Database Connection Helper (Auto-reconnects on closed connections)
# -----------------------------------------------------------------------------
def get_db_connection():
    if "DATABASE_URL" not in st.secrets:
        st.error("DATABASE_URL secret is missing! Please configure it in Streamlit Secrets.")
        st.stop()
        
    db_url = st.secrets["DATABASE_URL"]
    
    if "db_conn" in st.session_state and st.session_state.db_conn is not None:
        try:
            if st.session_state.db_conn.closed == 0:
                with st.session_state.db_conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                return st.session_state.db_conn
        except Exception:
            st.session_state.db_conn = None

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        st.session_state.db_conn = conn
        return conn
    except Exception as e:
        st.error(f"Failed to connect to Neon PostgreSQL database: {e}")
        st.stop()

def run_query(query, params=None, fetch=True):
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(query, params)
        if fetch and cur.description:
            columns = [desc[0] for desc in cur.description]
            records = cur.fetchall()
            return pd.DataFrame(records, columns=columns)
        return None

# -----------------------------------------------------------------------------
# Session & Role Management
# -----------------------------------------------------------------------------
if "role" not in st.session_state:
    st.session_state.role = None
if "selected_patient_id" not in st.session_state:
    st.session_state.selected_patient_id = 1

st.sidebar.title("🏥 Waitwise Albany")

if st.session_state.role:
    st.sidebar.write(f"Logged in as: **{st.session_state.role.capitalize()}**")
    if st.sidebar.button("Log Out"):
        st.session_state.role = None
        st.rerun()

# -----------------------------------------------------------------------------
# LANDING PAGE / ROLE SELECTOR
# -----------------------------------------------------------------------------
if st.session_state.role is None:
    st.markdown('<div class="main-header">Welcome to Waitwise Albany Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Streamlined appointment scheduling for Albany patients and clinic staff.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.markdown("### Patient Portal")
        st.write("View appointments, request same-doctor reschedules, and cancel visits.")
        patients_df = run_query("SELECT patient_id, first_name, last_name, mrn FROM waitwise.patients ORDER BY patient_id LIMIT 15;")
        if patients_df is not None and not patients_df.empty:
            patient_options = {f"{row['first_name']} {row['last_name']} ({row['mrn']})": row['patient_id'] for _, row in patients_df.iterrows()}
            selected_label = st.selectbox("Select Patient Account:", list(patient_options.keys()))
            if st.button("Log In as Patient", type="primary"):
                st.session_state.role = "patient"
                st.session_state.selected_patient_id = patient_options[selected_label]
                st.rerun()

    with col2:
        st.markdown("### Admin & Staff Portal")
        st.write("Real-time visual monitoring, cancellation alerts, 6-month scheduling calendar.")
        if st.button("Log In as Staff Admin"):
            st.session_state.role = "admin"
            st.rerun()

    with col3:
        st.markdown("### Test on Mobile")
        app_url = st.secrets.get("PUBLIC_APP_URL", "https://share.streamlit.io")
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(app_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="Scan QR for Mobile Version", width=160)

# -----------------------------------------------------------------------------
# PATIENT PORTAL
# -----------------------------------------------------------------------------
elif st.session_state.role == "patient":
    patient_id = st.session_state.selected_patient_id
    patient_info = run_query("SELECT * FROM waitwise.patients WHERE patient_id = %s;", (patient_id,))
    
    if patient_info is not None and not patient_info.empty:
        p_row = patient_info.iloc[0]
        st.markdown(f'<div class="main-header">Patient Portal - {p_row["first_name"]} {p_row["last_name"]}</div>', unsafe_allow_html=True)
        st.write(f"**MRN:** `{p_row['mrn']}` | **DOB:** {p_row['date_of_birth']} | **Clinic:** Waitwise Albany Health Center")
    
    tab1, tab2 = st.tabs(["📅 My Appointments", "🔄 Reschedule History"])

    with tab1:
        st.subheader("Scheduled Appointments")
        appts_df = run_query("""
            SELECT a.appointment_id, a.confirmation_code, a.status, a.provider_id,
                   (a.start_time AT TIME ZONE 'America/New_York') AS start_et,
                   pr.full_name AS provider, pr.credentials, pr.specialty, a.visit_reason
            FROM waitwise.appointments a
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            WHERE a.patient_id = %s
            ORDER BY a.start_time DESC;
        """, (patient_id,))

        if appts_df is not None and not appts_df.empty:
            for idx, row in appts_df.iterrows():
                with st.expander(f"{row['start_et'].strftime('%b %d, %Y at %I:%M %p')} — {row['provider']}, {row['credentials']} ({row['status']})"):
                    st.write(f"**Confirmation Code:** {row['confirmation_code']}")
                    st.write(f"**Doctor / Specialty:** {row['provider']} ({row['specialty']})")
                    st.write(f"**Visit Reason:** {row['visit_reason']}")
                    st.write(f"**Status:** `{row['status']}`")

                    # Cancellation & Reschedule Controls
                    if row['status'] in ['Scheduled', 'Checked In']:
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            if st.button("❌ Cancel Appointment", key=f"pat_cancel_{row['appointment_id']}"):
                                run_query(
                                    "UPDATE waitwise.appointments SET status = 'Cancelled', cancelled_at = NOW(), cancel_reason = 'Cancelled by patient via portal' WHERE appointment_id = %s;",
                                    (row['appointment_id'],), fetch=False
                                )
                                # Explicit Audit Log Entry for Staff View Alert
                                run_query(
                                    "INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id, new_values_json) VALUES (%s, %s, %s, %s, %s, %s);",
                                    ('patient', f"patient:{patient_id}", 'PATIENT_CANCELLED', 'appointments', str(row['appointment_id']), f'{{"patient_id": {patient_id}, "confirmation_code": "{row["confirmation_code"]}"}}'),
                                    fetch=False
                                )
                                st.success("Your appointment has been cancelled. Staff have been notified.")
                                st.rerun()

                        with col_c2:
                            with st.popover(f"🔄 Reschedule with {row['provider']}"):
                                st.markdown(f"**Request a new date with your existing doctor ({row['provider']}):**")
                                new_date = st.date_input("Preferred Date", min_value=datetime.today().date(), max_value=datetime.today().date() + timedelta(days=180), key=f"res_date_{row['appointment_id']}")
                                time_pref = st.selectbox("Preferred Time of Day", ["Morning", "Afternoon", "Any"], key=f"res_time_{row['appointment_id']}")
                                reason = st.text_input("Reason for Reschedule", key=f"res_reason_{row['appointment_id']}")
                                
                                if st.button("Submit Reschedule Request", key=f"sub_res_{row['appointment_id']}"):
                                    # Prevent duplicate active requests for the same visit
                                    existing_req = run_query("SELECT request_id FROM waitwise.reschedule_requests WHERE appointment_id = %s AND status = 'Pending';", (row['appointment_id'],))
                                    if existing_req is not None and not existing_req.empty:
                                        st.warning("You already have a pending reschedule request for this visit.")
                                    else:
                                        run_query("""
                                            INSERT INTO waitwise.reschedule_requests 
                                            (appointment_id, patient_id, provider_id, requested_at, requested_via, reason, preferred_new_date, preferred_time_of_day, status)
                                            VALUES (%s, %s, %s, NOW(), 'Patient Portal', %s, %s, %s, 'Pending');
                                        """, (row['appointment_id'], patient_id, row['provider_id'], reason, new_date, time_pref), fetch=False)
                                        
                                        run_query("UPDATE waitwise.appointments SET status = 'Reschedule Requested' WHERE appointment_id = %s;", (row['appointment_id'],), fetch=False)
                                        st.success(f"Reschedule request submitted for {row['provider']}!")
                                        st.rerun()
        else:
            st.info("No appointment history found.")

    with tab2:
        st.subheader("Reschedule Requests History")
        rr_df = run_query("""
            SELECT rr.request_id, pr.full_name AS doctor, rr.preferred_new_date, rr.preferred_time_of_day, rr.reason, rr.status
            FROM waitwise.reschedule_requests rr
            JOIN waitwise.providers pr ON pr.provider_id = rr.provider_id
            WHERE rr.patient_id = %s
            ORDER BY rr.requested_at DESC;
        """, (patient_id,))
        if rr_df is not None and not rr_df.empty:
            st.dataframe(rr_df, use_container_width=True)
        else:
            st.info("No reschedule requests submitted yet.")

# -----------------------------------------------------------------------------
# ADMIN & STAFF PORTAL (Real-Time Visual Capture)
# -----------------------------------------------------------------------------
elif st.session_state.role == "admin":
    st.markdown('<div class="main-header">Albany Health Center - Staff Control Dashboard</div>', unsafe_allow_html=True)
    
    # Real-Time Live Patient Cancellation Banner Alert
    recent_cancels = run_query("""
        SELECT a.appointment_id, a.confirmation_code, p.first_name || ' ' || p.last_name AS patient_name,
               pr.full_name AS doctor, a.cancelled_at
        FROM waitwise.appointments a
        JOIN waitwise.patients p ON p.patient_id = a.patient_id
        JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
        WHERE a.status = 'Cancelled' AND a.cancelled_at >= NOW() - INTERVAL '24 hours'
        ORDER BY a.cancelled_at DESC LIMIT 5;
    """)

    if recent_cancels is not None and not recent_cancels.empty:
        st.markdown("### 🚨 Live Real-Time Cancellation Alerts (Last 24 Hours)")
        for _, c_row in recent_cancels.iterrows():
            st.markdown(
                f'<div class="alert-cancelled">⚠️ <strong>PATIENT CANCELLED:</strong> {c_row["patient_name"]} cancelled visit ({c_row["confirmation_code"]}) with {c_row["doctor"]}.</div>',
                unsafe_allow_html=True
            )

    admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs([
        "⚡ Visual Real-Time Data Capture", 
        "⏳ Reschedule Queue (Same-Doctor)", 
        "📅 6-Month Scheduling Calendar",
        "👥 All Albany Appointments"
    ])

    # --- TAB 1: Visual Real-Time Data Capture ---
    with admin_tab1:
        st.subheader("Live Clinic Operations & Provider Delays")
        
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        checked_in = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Checked In';").iloc[0]['c']
        pending_rr = run_query("SELECT COUNT(*) AS c FROM waitwise.reschedule_requests WHERE status = 'Pending';").iloc[0]['c']
        today_cancels = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Cancelled' AND cancelled_at::date = CURRENT_DATE;").iloc[0]['c']
        completed_today = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Completed' AND updated_at::date = CURRENT_DATE;").iloc[0]['c']

        col_m1.metric("Current Checked-In / Waiting", checked_in)
        col_m2.metric("Pending Reschedules", pending_rr)
        col_m3.metric("Cancellations Today", today_cancels)
        col_m4.metric("Completed Today", completed_today)

        st.markdown("---")
        st.markdown("### Albany Center Provider Roster & Real-Time Delays")
        
        prov_df = run_query("""
            SELECT pr.provider_id, pr.full_name, pr.credentials, pr.specialty, pd.delay_minutes
            FROM waitwise.providers pr
            LEFT JOIN waitwise.provider_delays pd ON pd.provider_id = pr.provider_id
            ORDER BY pr.provider_id;
        """)
        
        if prov_df is not None and not prov_df.empty:
            p_cols = st.columns(len(prov_df))
            for i, (_, p_row) in enumerate(prov_df.iterrows()):
                with p_cols[i]:
                    st.markdown(f"#### {p_row['full_name']}, {p_row['credentials']}")
                    st.write(f"**Specialty:** {p_row['specialty']}")
                    st.write(f"**Current Delay:** `{p_row['delay_minutes']} mins behind`")
                    new_delay = st.number_input("Update Delay (mins)", min_value=0, max_value=120, value=int(p_row['delay_minutes']), key=f"del_{p_row['provider_id']}")
                    if st.button("Save Delay", key=f"btn_del_{p_row['provider_id']}"):
                        run_query("UPDATE waitwise.provider_delays SET delay_minutes = %s, updated_at = NOW() WHERE provider_id = %s;", (new_delay, p_row['provider_id']), fetch=False)
                        st.success("Delay updated!")
                        st.rerun()

    # --- TAB 2: Same-Doctor Reschedule Queue ---
    with admin_tab2:
        st.subheader("Reschedule Requests (Assigned Same Doctor)")
        rr_queue = run_query("""
            SELECT rr.request_id, rr.appointment_id, p.first_name || ' ' || p.last_name AS patient_name,
                   pr.full_name AS doctor_name, rr.preferred_new_date, rr.preferred_time_of_day, rr.reason
            FROM waitwise.reschedule_requests rr
            JOIN waitwise.patients p ON p.patient_id = rr.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = rr.provider_id
            WHERE rr.status = 'Pending'
            ORDER BY rr.requested_at ASC;
        """)

        if rr_queue is not None and not rr_queue.empty:
            for _, r_row in rr_queue.iterrows():
                with st.expander(f"Request #{r_row['request_id']} — {r_row['patient_name']} (Doctor: {r_row['doctor_name']})"):
                    st.write(f"**Preferred Date:** {r_row['preferred_new_date']} ({r_row['preferred_time_of_day']})")
                    st.write(f"**Reason:** {r_row['reason']}")
                    
                    st.info(f"Approve will schedule this patient with their same doctor: **{r_row['doctor_name']}**")
                    ac1, ac2 = st.columns(2)
                    with ac1:
                        if st.button("Approve Same-Doctor Reschedule", key=f"app_sd_{r_row['request_id']}"):
                            run_query("UPDATE waitwise.reschedule_requests SET status = 'Approved', resolved_at = NOW(), resolved_by = 'staff_admin' WHERE request_id = %s;", (r_row['request_id'],), fetch=False)
                            run_query("UPDATE waitwise.appointments SET status = 'Rescheduled' WHERE appointment_id = %s;", (r_row['appointment_id'],), fetch=False)
                            st.success("Approved and updated!")
                            st.rerun()
                    with ac2:
                        d_reason = st.text_input("Decline Reason", key=f"dec_rsn_{r_row['request_id']}")
                        if st.button("Decline Request", key=f"dec_sd_{r_row['request_id']}"):
                            run_query("UPDATE waitwise.reschedule_requests SET status = 'Declined', resolved_at = NOW(), resolved_by = 'staff_admin', decline_reason = %s WHERE request_id = %s;", (d_reason, r_row['request_id']), fetch=False)
                            run_query("UPDATE waitwise.appointments SET status = 'Scheduled' WHERE appointment_id = %s;", (r_row['appointment_id'],), fetch=False)
                            st.warning("Declined.")
                            st.rerun()
        else:
            st.info("No pending reschedule requests.")

    # --- TAB 3: 6-Month Interactive Scheduling Calendar ---
    with admin_tab3:
        st.subheader("Interactive 6-Month Provider Availability Calendar")
        
        cal_col1, cal_col2 = st.columns([1, 2])
        
        with cal_col1:
            selected_doc = st.selectbox("Filter Doctor:", run_query("SELECT full_name FROM waitwise.providers;")['full_name'].tolist())
            start_search = st.date_input("Calendar Window Start Date", datetime.today().date())
            end_search = start_search + timedelta(days=180)
            st.write(f"Showing schedule window: **{start_search}** to **{end_search}** (6 Months)")

        with cal_col2:
            st.markdown(f"### Appointment Occupancy for {selected_doc}")
            schedule_df = run_query("""
                SELECT (a.start_time AT TIME ZONE 'America/New_York')::date AS visit_date,
                       COUNT(*) AS booked_slots,
                       SUM(CASE WHEN a.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_slots
                FROM waitwise.appointments a
                JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
                WHERE pr.full_name = %s 
                  AND a.start_time >= %