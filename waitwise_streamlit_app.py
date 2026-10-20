import os
import streamlit as st
import pandas as pd
import psycopg2
import qrcode
from io import BytesIO
from PIL import Image

# -----------------------------------------------------------------------------
# Page Configuration & Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Waitwise - Healthcare Appointment Portal",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for healthcare dashboard theme
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #0E2A47; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1rem; color: #556B82; margin-bottom: 1.5rem; }
    .card { background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 1.2rem; margin-bottom: 1rem; }
    .badge-scheduled { background-color: #E0F2FE; color: #0369A1; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
    .badge-completed { background-color: #DCFCE7; color: #15803D; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
    .badge-cancelled { background-color: #FEE2E2; color: #B91C1C; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
    .badge-noshow { background-color: #FEF3C7; color: #B45309; padding: 4px 8px; border-radius: 4px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# Privacy & Demo Banner
st.warning("⚠️ **DEMO SYSTEM**: Synthetic data only. No real Protected Health Information (PHI).")

# -----------------------------------------------------------------------------
# Robust Database Connection Management
# -----------------------------------------------------------------------------
def get_db_connection():
    """Returns an active PostgreSQL database connection, automatically reconnecting if closed."""
    if "DATABASE_URL" not in st.secrets:
        st.error("DATABASE_URL secret is missing! Please configure it in Streamlit Secrets.")
        st.stop()
        
    db_url = st.secrets["DATABASE_URL"]
    
    # Check if existing session connection is open and active
    if "db_conn" in st.session_state and st.session_state.db_conn is not None:
        try:
            if st.session_state.db_conn.closed == 0:
                with st.session_state.db_conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                return st.session_state.db_conn
        except Exception:
            st.session_state.db_conn = None

    # Connect/Reconnect
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        st.session_state.db_conn = conn
        return conn
    except Exception as e:
        st.error(f"Failed to connect to Neon PostgreSQL database: {e}")
        st.stop()

def run_query(query, params=None, fetch=True):
    """Executes a SQL query safely and handles connection retries."""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(query, params)
        if fetch and cur.description:
            columns = [desc[0] for desc in cur.description]
            records = cur.fetchall()
            return pd.DataFrame(records, columns=columns)
        return None

# -----------------------------------------------------------------------------
# Navigation & Role Handling
# -----------------------------------------------------------------------------
if "role" not in st.session_state:
    st.session_state.role = None
if "selected_patient_id" not in st.session_state:
    st.session_state.selected_patient_id = 1  # Default demo patient

st.sidebar.title("🏥 Waitwise Portal")

if st.session_state.role:
    st.sidebar.write(f"Logged in as: **{st.session_state.role.capitalize()}**")
    if st.sidebar.button("Log Out"):
        st.session_state.role = None
        st.rerun()

# -----------------------------------------------------------------------------
# LANDING PAGE / ROLE SELECTOR
# -----------------------------------------------------------------------------
if st.session_state.role is None:
    st.markdown('<div class="main-header">Welcome to Waitwise</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Streamlined, accessible appointment management for patients and provider clinics.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.markdown("### Patient Portal")
        st.write("Access your appointments, request reschedules, and cancel visits.")
        patients_df = run_query("SELECT patient_id, first_name, last_name, mrn FROM waitwise.patients ORDER BY patient_id LIMIT 10;")
        if patients_df is not None and not patients_df.empty:
            patient_options = {f"{row['first_name']} {row['last_name']} ({row['mrn']})": row['patient_id'] for _, row in patients_df.iterrows()}
            selected_label = st.selectbox("Select Demo Patient Account:", list(patient_options.keys()))
            if st.button("Log In as Patient", type="primary"):
                st.session_state.role = "patient"
                st.session_state.selected_patient_id = patient_options[selected_label]
                st.rerun()

    with col2:
        st.markdown("### Admin Portal")
        st.write("Access staff management controls, scheduling queue, and clinic metrics.")
        if st.button("Log In as Staff Admin"):
            st.session_state.role = "admin"
            st.rerun()

    with col3:
        st.markdown("### Test on Mobile")
        # QR Code Generator for live URL
        app_url = "https://share.streamlit.io"  # Fallback
        try:
            # Detect public URL if available
            app_url = st.secrets.get("PUBLIC_APP_URL", "https://share.streamlit.io")
        except Exception:
            pass
            
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(app_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="Scan for Mobile View", width=160)

# -----------------------------------------------------------------------------
# PATIENT PORTAL
# -----------------------------------------------------------------------------
elif st.session_state.role == "patient":
    patient_id = st.session_state.selected_patient_id
    patient_info = run_query("SELECT * FROM waitwise.patients WHERE patient_id = %s;", (patient_id,))
    
    if patient_info is not None and not patient_info.empty:
        p_name = f"{patient_info.iloc[0]['first_name']} {patient_info.iloc[0]['last_name']}"
        st.markdown(f'<div class="main-header">Patient Portal - {p_name}</div>', unsafe_allow_html=True)
        st.write(f"**MRN:** {patient_info.iloc[0]['mrn']} | **DOB:** {patient_info.iloc[0]['date_of_birth']}")
    
    tab1, tab2 = st.tabs(["📅 Upcoming Appointments", "🔄 Reschedule Requests"])

    with tab1:
        st.subheader("My Appointments")
        appts_df = run_query("""
            SELECT a.appointment_id, a.confirmation_code, a.status,
                   (a.start_time AT TIME ZONE 'America/New_York') AS start_et,
                   pr.full_name AS provider, pr.specialty, l.name AS location, a.visit_reason
            FROM waitwise.appointments a
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            JOIN waitwise.locations l ON l.location_id = a.location_id
            WHERE a.patient_id = %s
            ORDER BY a.start_time DESC;
        """, (patient_id,))

        if appts_df is not None and not appts_df.empty:
            for idx, row in appts_df.iterrows():
                with st.expander(f"{row['start_et'].strftime('%b %d, %Y at %I:%M %p')} — {row['provider']} ({row['status']})"):
                    st.write(f"**Confirmation Code:** {row['confirmation_code']}")
                    st.write(f"**Specialty:** {row['specialty']}")
                    st.write(f"**Location:** {row['location']}")
                    st.write(f"**Reason for Visit:** {row['visit_reason']}")
                    st.write(f"**Status:** `{row['status']}`")

                    # Patient Action Buttons
                    if row['status'] in ['Scheduled', 'Checked In']:
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            if st.button("Cancel Appointment", key=f"cancel_{row['appointment_id']}"):
                                run_query(
                                    "UPDATE waitwise.appointments SET status = 'Cancelled', cancelled_at = NOW(), cancel_reason = 'Cancelled by patient' WHERE appointment_id = %s;",
                                    (row['appointment_id'],), fetch=False
                                )
                                # Add Audit Log
                                run_query(
                                    "INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id) VALUES (%s, %s, %s, %s, %s);",
                                    ('patient', f"patient:{patient_id}", 'CANCEL_APPOINTMENT', 'appointments', str(row['appointment_id'])),
                                    fetch=False
                                )
                                st.success("Appointment cancelled successfully!")
                                st.rerun()

                        with col_c2:
                            with st.popover("Request Reschedule"):
                                new_date = st.date_input("Preferred Date", key=f"date_{row['appointment_id']}")
                                time_pref = st.selectbox("Preferred Time", ["Morning", "Afternoon", "Any"], key=f"time_{row['appointment_id']}")
                                reason = st.text_input("Reason for Rescheduling", key=f"reason_{row['appointment_id']}")
                                
                                if st.button("Submit Request", key=f"submit_rr_{row['appointment_id']}"):
                                    run_query("""
                                        INSERT INTO waitwise.reschedule_requests 
                                        (appointment_id, patient_id, provider_id, requested_at, requested_via, reason, preferred_new_date, preferred_time_of_day, status)
                                        VALUES (%s, %s, (SELECT provider_id FROM waitwise.appointments WHERE appointment_id = %s), NOW(), 'Patient Portal', %s, %s, %s, 'Pending');
                                    """, (row['appointment_id'], patient_id, row['appointment_id'], reason, new_date, time_pref), fetch=False)
                                    
                                    run_query("UPDATE waitwise.appointments SET status = 'Reschedule Requested' WHERE appointment_id = %s;", (row['appointment_id'],), fetch=False)
                                    
                                    st.success("Reschedule request submitted!")
                                    st.rerun()
        else:
            st.info("No appointments found for this account.")

    with tab2:
        st.subheader("Submitted Reschedule Requests")
        rr_df = run_query("""
            SELECT request_id, preferred_new_date, preferred_time_of_day, reason, status, decline_reason
            FROM waitwise.reschedule_requests
            WHERE patient_id = %s
            ORDER BY requested_at DESC;
        """, (patient_id,))
        
        if rr_df is not None and not rr_df.empty:
            st.dataframe(rr_df, use_container_width=True)
        else:
            st.info("No pending or past reschedule requests.")

# -----------------------------------------------------------------------------
# ADMIN / STAFF PORTAL
# -----------------------------------------------------------------------------
elif st.session_state.role == "admin":
    st.markdown('<div class="main-header">Admin & Staff Portal</div>', unsafe_allow_html=True)
    
    admin_tab1, admin_tab2, admin_tab3 = st.tabs(["📊 Clinic Metrics", "⏳ Reschedule Queue", "📅 All Appointments"])

    with admin_tab1:
        st.subheader("Dashboard Overview")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        total_appts = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments;").iloc[0]['c']
        pending_rr = run_query("SELECT COUNT(*) AS c FROM waitwise.reschedule_requests WHERE status = 'Pending';").iloc[0]['c']
        completed_appts = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Completed';").iloc[0]['c']
        cancelled_appts = run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Cancelled';").iloc[0]['c']
        
        m_col1.metric("Total Appointments", total_appts)
        m_col2.metric("Pending Reschedules", pending_rr)
        m_col3.metric("Completed Visits", completed_appts)
        m_col4.metric("Cancelled Visits", cancelled_appts)

    with admin_tab2:
        st.subheader("Pending Reschedule Requests")
        queue_df = run_query("""
            SELECT rr.request_id, rr.appointment_id, p.first_name || ' ' || p.last_name AS patient_name,
                   pr.full_name AS provider_name, rr.preferred_new_date, rr.preferred_time_of_day, rr.reason
            FROM waitwise.reschedule_requests rr
            JOIN waitwise.patients p ON p.patient_id = rr.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = rr.provider_id
            WHERE rr.status = 'Pending'
            ORDER BY rr.requested_at ASC;
        """)

        if queue_df is not None and not queue_df.empty:
            for idx, row in queue_df.iterrows():
                with st.expander(f"Request #{row['request_id']} — {row['patient_name']} for {row['provider_name']}"):
                    st.write(f"**Preferred Date:** {row['preferred_new_date']} ({row['preferred_time_of_day']})")
                    st.write(f"**Reason:** {row['reason']}")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Approve & Mark Rescheduled", key=f"app_{row['request_id']}"):
                            run_query("UPDATE waitwise.reschedule_requests SET status = 'Approved', resolved_at = NOW(), resolved_by = 'staff_admin' WHERE request_id = %s;", (row['request_id'],), fetch=False)
                            run_query("UPDATE waitwise.appointments SET status = 'Rescheduled' WHERE appointment_id = %s;", (row['appointment_id'],), fetch=False)
                            st.success("Request approved!")
                            st.rerun()
                    with c2:
                        decline_reason = st.text_input("Decline Reason", key=f"dec_reason_{row['request_id']}")
                        if st.button("Decline Request", key=f"dec_{row['request_id']}"):
                            run_query("UPDATE waitwise.reschedule_requests SET status = 'Declined', resolved_at = NOW(), resolved_by = 'staff_admin', decline_reason = %s WHERE request_id = %s;", (decline_reason, row['request_id']), fetch=False)
                            run_query("UPDATE waitwise.appointments SET status = 'Scheduled' WHERE appointment_id = %s;", (row['appointment_id'],), fetch=False)
                            st.warning("Request declined.")
                            st.rerun()
        else:
            st.info("No pending reschedule requests in the queue.")

    with admin_tab3:
        st.subheader("Master Appointment Directory")
        all_appts = run_query("""
            SELECT a.appointment_id, a.confirmation_code, p.first_name || ' ' || p.last_name AS patient,
                   pr.full_name AS provider, a.status, (a.start_time AT TIME ZONE 'America/New_York') AS start_et
            FROM waitwise.appointments a
            JOIN waitwise.patients p ON p.patient_id = a.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            ORDER BY a.start_time DESC
            LIMIT 100;
        """)
        st.dataframe(all_appts, use_container_width=True)
