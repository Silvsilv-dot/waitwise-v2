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

st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #0E2A47; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1rem; color: #556B82; margin-bottom: 1.5rem; }
    .clinic-banner { background-color: #E0F2FE; border-left: 5px solid #0284C7; padding: 10px 15px; border-radius: 4px; margin-bottom: 15px; }
    .alert-cancelled { background-color: #FEE2E2; border: 1px solid #EF4444; color: #991B1B; padding: 10px; border-radius: 6px; margin-bottom: 10px; font-weight: 600; }
    .card { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

st.warning("⚠️ **DEMO SYSTEM**: Synthetic data only for Albany Health Center. No real Protected Health Information (PHI).")

st.markdown("""
<div class="clinic-banner">
    <strong>📍 Location:</strong> Waitwise Albany Health Center — 100 Demo Plaza, Albany, NY 12207 | 📞 (518) 555-0101<br>
    <em>All primary care, rheumatology, and nurse practitioner services consolidated at this location.</em>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Database Connection Helper
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
        st.error(f"Failed to connect to database: {e}")
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
# Session & Navigation
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
# LANDING PAGE
# -----------------------------------------------------------------------------
if st.session_state.role is None:
    st.markdown('<div class="main-header">Welcome to Waitwise Albany Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Streamlined appointment scheduling for Albany patients and clinic staff.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.markdown("### Patient Portal")
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
        st.write("Real-time visual monitoring, cancellation alerts, 6-month calendar.")
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
        st.write(f"**MRN:** `{p_row['mrn']}` | **DOB:** {p_row['date_of_birth']} | **Clinic:** Albany Health Center")
    
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
                with st.expander(f"{row['start_et'].strftime('%b %d, %Y at %I:%M %p')} — {row['provider']} ({row['status']})"):
                    st.write(f"**Confirmation:** {row['confirmation_code']}")
                    st.write(f"**Doctor:** {row['provider']} ({row['specialty']})")
                    st.write(f"**Reason:** {row['visit_reason']}")

                    if row['status'] in ['Scheduled', 'Checked In']:
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            if st.button("❌ Cancel Appointment", key=f"pat_cancel_{row['appointment_id']}"):
                                run_query("UPDATE waitwise.appointments SET status = 'Cancelled', cancelled_at = NOW() WHERE appointment_id = %s;", (row['appointment_id'],), fetch=False)
                                st.success("Appointment cancelled.")
                                st.rerun()

                        with col_c2:
                            with st.popover(f"🔄 Reschedule with {row['provider']}"):
                                new_date = st.date_input("Preferred Date", min_value=datetime.today().date(), max_value=datetime.today().date() + timedelta(days=180), key=f"res_date_{row['appointment_id']}")
                                time_pref = st.selectbox("Preferred Time", ["Morning", "Afternoon", "Any"], key=f"res_time_{row['appointment_id']}")
                                reason = st.text_input("Reason", key=f"res_reason_{row['appointment_id']}")
                                
                                if st.button("Submit Request", key=f"sub_res_{row['appointment_id']}"):
                                    run_query("""
                                        INSERT INTO waitwise.reschedule_requests 
                                        (appointment_id, patient_id, provider_id, requested_at, requested_via, reason, preferred_new_date, preferred_time_of_day, status)
                                        VALUES (%s, %s, %s, NOW(), 'Patient Portal', %s, %s, %s, 'Pending');
                                    """, (row['appointment_id'], patient_id, row['provider_id'], reason, new_date, time_pref), fetch=False)
                                    run_query("UPDATE waitwise.appointments SET status = 'Reschedule Requested' WHERE appointment_id = %s;", (row['appointment_id'],), fetch=False)
                                    st.success("Request submitted.")
                                    st.rerun()
        else:
            st.info("No appointments found.")

    with tab2:
        rr_df = run_query("SELECT request_id, preferred_new_date, preferred_time_of_day, reason, status FROM waitwise.reschedule_requests WHERE patient_id = %s ORDER BY requested_at DESC;", (patient_id,))
        if rr_df is not None and not rr_df.empty:
            st.dataframe(rr_df, use_container_width=True)

# -----------------------------------------------------------------------------
# ADMIN PORTAL
# -----------------------------------------------------------------------------
elif st.session_state.role == "admin":
    st.markdown('<div class="main-header">Albany Health Center - Staff Dashboard</div>', unsafe_allow_html=True)
    
    recent_cancels = run_query("""
        SELECT a.appointment_id, a.confirmation_code, p.first_name || ' ' || p.last_name AS patient_name, pr.full_name AS doctor
        FROM waitwise.appointments a
        JOIN waitwise.patients p ON p.patient_id = a.patient_id
        JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
        WHERE a.status = 'Cancelled' AND a.cancelled_at >= NOW() - INTERVAL '24 hours'
        ORDER BY a.cancelled_at DESC LIMIT 5;
    """)

    if recent_cancels is not None and not recent_cancels.empty:
        for _, c_row in recent_cancels.iterrows():
            st.markdown(f'<div class="alert-cancelled">⚠️ <strong>PATIENT CANCELLED:</strong> {c_row["patient_name"]} cancelled visit ({c_row["confirmation_code"]}) with {c_row["doctor"]}.</div>', unsafe_allow_html=True)

    admin_tab1, admin_tab2, admin_tab3, admin_tab4 = st.tabs([
        "⚡ Real-Time Capture", 
        "⏳ Reschedule Queue", 
        "📅 6-Month Calendar",
        "👥 All Appointments"
    ])

    with admin_tab1:
        col_m1, col_m2, col_m3 = st.columns(3)
        checked_in = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Checked In';").iloc[0]['c']
        pending_rr = run_query("SELECT COUNT(*) AS c FROM waitwise.reschedule_requests WHERE status = 'Pending';").iloc[0]['c']
        today_cancels = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Cancelled' AND cancelled_at::date = CURRENT_DATE;").iloc[0]['c']

        col_m1.metric("Checked In", checked_in)
        col_m2.metric("Pending Reschedules", pending_rr)
        col_m3.metric("Cancellations Today", today_cancels)

    with admin_tab2:
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
                with st.expander(f"Request #{r_row['request_id']} — {r_row['patient_name']} ({r_row['doctor_name']})"):
                    st.write(f"**Preferred Date:** {r_row['preferred_new_date']} ({r_row['preferred_time_of_day']})")
                    if st.button("Approve", key=f"app_sd_{r_row['request_id']}"):
                        run_query("UPDATE waitwise.reschedule_requests SET status = 'Approved' WHERE request_id = %s;", (r_row['request_id'],), fetch=False)
                        run_query("UPDATE waitwise.appointments SET status = 'Rescheduled' WHERE appointment_id = %s;", (r_row['appointment_id'],), fetch=False)
                        st.success("Approved!")
                        st.rerun()
        else:
            st.info("No pending requests.")

    with admin_tab3:
        st.subheader("6-Month Provider Calendar")
        providers = run_query("SELECT full_name FROM waitwise.providers;")['full_name'].tolist()
        selected_doc = st.selectbox("Select Provider:", providers)
        start_search = st.date_input("Start Date", datetime.today().date())
        end_search = start_search + timedelta(days=180)
        
        schedule_df = run_query("""
            SELECT (a.start_time AT TIME ZONE 'America/New_York')::date AS visit_date,
                   COUNT(*) AS booked_slots
            FROM waitwise.appointments a
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            WHERE pr.full_name = %s 
              AND a.start_time >= %s 
              AND a.start_time <= %s
            GROUP BY visit_date
            ORDER BY visit_date ASC;
        """, (selected_doc, start_search, end_search))
        st.dataframe(schedule_df, use_container_width=True)

    with admin_tab4:
        all_appts = run_query("""
            SELECT a.appointment_id, a.confirmation_code, p.first_name || ' ' || p.last_name AS patient,
                   pr.full_name AS doctor, a.status
            FROM waitwise.appointments a
            JOIN waitwise.patients p ON p.patient_id = a.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            ORDER BY a.start_time DESC LIMIT 100;
        """)
        st.dataframe(all_appts, use_container_width=True)
