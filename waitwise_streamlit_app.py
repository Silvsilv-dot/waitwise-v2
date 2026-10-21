import os
import streamlit as st
import pandas as pd
import psycopg2
import qrcode
from io import BytesIO
from datetime import datetime, timedelta, time

# -----------------------------------------------------------------------------
# Page Configuration & Visual Theme
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Waitwise - Albany Health Center",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Healthcare Styling
st.markdown("""
<style>
    .main-header { font-size: 2.2rem; font-weight: 700; color: #0E2A47; margin-bottom: 0.2rem; }
    .sub-header { font-size: 1rem; color: #556B82; margin-bottom: 1.5rem; }
    .clinic-banner { background-color: #E0F2FE; border-left: 5px solid #0284C7; padding: 10px 15px; border-radius: 4px; margin-bottom: 15px; }
    .alert-cancelled { background-color: #FEE2E2; border: 1px solid #EF4444; color: #991B1B; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-weight: 600; }
    .alert-rescheduled { background-color: #FEF3C7; border: 1px solid #F59E0B; color: #92400E; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

st.warning("⚠️ **DEMO SYSTEM**: Synthetic data only for Albany Health Center. No real Protected Health Information (PHI).")

st.markdown("""
<div class="clinic-banner">
    <strong>📍 Location:</strong> Waitwise Albany Health Center — 100 Demo Plaza, Albany, NY 12207 | 📞 (518) 555-0101<br>
    <em>Consolidated Albany Clinic: Primary Care (PCP), Rheumatology, and Nurse Practitioners (NP).</em>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Database Connection Helper (Auto-reconnecting)
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
        st.error(f"Failed to connect to Neon PostgreSQL: {e}")
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

# Standard Slot Generation Helper (9:00 AM - 4:30 PM, 30-min intervals)
def generate_daily_time_slots():
    slots = []
    current = datetime.strptime("09:00", "%H:%M")
    end = datetime.strptime("16:30", "%H:%M")
    while current <= end:
        slots.append(current.strftime("%I:%M %p"))
        current += timedelta(minutes=30)
    return slots

# -----------------------------------------------------------------------------
# Navigation & Session Management
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
# LANDING PAGE & MOBILE QR GENERATION
# -----------------------------------------------------------------------------
if st.session_state.role is None:
    st.markdown('<div class="main-header">Welcome to Waitwise Albany Center</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Streamlined, direct appointment management for patients and provider staff.</div>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.markdown("### Patient Portal")
        st.write("Instant booking, same-doctor rescheduling with live open slots, and instant cancellations.")
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
        st.write("Graphical real-time data capture, instant reschedule/cancellation notifications, and 6-month calendar.")
        if st.button("Log In as Staff Admin"):
            st.session_state.role = "admin"
            st.rerun()

    with col3:
        st.markdown("### Test on Mobile")
        # Direct URL generation for smooth mobile scanning
        try:
            public_url = st.secrets.get("PUBLIC_APP_URL", "https://waitwise-v2-pivstljaoah3xufizp8e64.streamlit.app")
        except Exception:
            public_url = "https://waitwise-v2-pivstljaoah3xufizp8e64.streamlit.app"
            
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(public_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        st.image(buf.getvalue(), caption="Scan QR Code to Open Mobile View", width=160)

# -----------------------------------------------------------------------------
# PATIENT PORTAL (Instant Slot Booking & Rescheduling)
# -----------------------------------------------------------------------------
elif st.session_state.role == "patient":
    patient_id = st.session_state.selected_patient_id
    patient_info = run_query("SELECT * FROM waitwise.patients WHERE patient_id = %s;", (patient_id,))
    
    if patient_info is not None and not patient_info.empty:
        p_row = patient_info.iloc[0]
        st.markdown(f'<div class="main-header">Patient Portal — {p_row["first_name"]} {p_row["last_name"]}</div>', unsafe_allow_html=True)
        st.write(f"**MRN:** `{p_row['mrn']}` | **DOB:** {p_row['date_of_birth']} | **Clinic:** Waitwise Albany Health Center")
    
    st.subheader("My Appointments")
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
                st.write(f"**Confirmation Code:** `{row['confirmation_code']}`")
                st.write(f"**Doctor:** {row['provider']}, {row['credentials']} ({row['specialty']})")
                st.write(f"**Reason for Visit:** {row['visit_reason']}")
                st.write(f"**Current Status:** `{row['status']}`")

                if row['status'] in ['Scheduled', 'Checked In', 'Rescheduled']:
                    col_c1, col_c2 = st.columns(2)
                    
                    # 1. Instant Cancellation
                    with col_c1:
                        if st.button("❌ Cancel Visit", key=f"pat_cancel_{row['appointment_id']}"):
                            run_query(
                                "UPDATE waitwise.appointments SET status = 'Cancelled', cancelled_at = NOW(), cancel_reason = 'Cancelled by patient' WHERE appointment_id = %s;",
                                (row['appointment_id'],), fetch=False
                            )
                            st.success("Appointment cancelled instantly. Clinic staff notified.")
                            st.rerun()

                    # 2. Direct Self-Rescheduling (No Staff Approval Queue Required)
                    with col_c2:
                        with st.popover(f"🔄 Reschedule with {row['provider']}"):
                            st.markdown(f"**Select a new date & open slot for {row['provider']}:**")
                            
                            target_date = st.date_input(
                                "Choose Date",
                                min_value=datetime.today().date(),
                                max_value=datetime.today().date() + timedelta(days=180),
                                key=f"sel_date_{row['appointment_id']}"
                            )
                            
                            # Query booked slots on selected date for this doctor to determine availability
                            booked_df = run_query("""
                                SELECT (start_time AT TIME ZONE 'America/New_York')::time AS booked_time
                                FROM waitwise.appointments
                                WHERE provider_id = %s 
                                  AND (start_time AT TIME ZONE 'America/New_York')::date = %s
                                  AND status IN ('Scheduled', 'Checked In', 'Rescheduled');
                            """, (row['provider_id'], target_date))
                            
                            booked_times = []
                            if booked_df is not None and not booked_df.empty:
                                booked_times = [t.strftime("%I:%M %p") for t in booked_df['booked_time']]
                            
                            all_slots = generate_daily_time_slots()
                            available_slots = [slot for slot in all_slots if slot not in booked_times]
                            
                            if available_slots:
                                chosen_slot = st.selectbox("Select Open Time Slot:", available_slots, key=f"slot_{row['appointment_id']}")
                                
                                if st.button("Confirm & Instantly Update Appointment", key=f"btn_resch_{row['appointment_id']}", type="primary"):
                                    # Combine target_date and chosen_slot into timestamp
                                    slot_time_obj = datetime.strptime(chosen_slot, "%I:%M %p").time()
                                    new_start_dt = datetime.combine(target_date, slot_time_obj)
                                    new_end_dt = new_start_dt + timedelta(minutes=30)
                                    
                                    # Update appointment directly in database
                                    run_query("""
                                        UPDATE waitwise.appointments 
                                        SET start_time = %s, end_time = %s, status = 'Rescheduled', updated_at = NOW()
                                        WHERE appointment_id = %s;
                                    """, (new_start_dt, new_end_dt, row['appointment_id']), fetch=False)
                                    
                                    # Insert notification log for staff view
                                    run_query("""
                                        INSERT INTO waitwise.reschedule_requests 
                                        (appointment_id, patient_id, provider_id, requested_at, requested_via, preferred_new_date, preferred_time_of_day, status)
                                        VALUES (%s, %s, %s, NOW(), 'Patient Portal Direct', %s, %s, 'Directly Updated');
                                    """, (row['appointment_id'], patient_id, row['provider_id'], target_date, chosen_slot), fetch=False)
                                    
                                    st.success(f"Appointment successfully rescheduled to {target_date.strftime('%b %d, %Y')} at {chosen_slot}!")
                                    st.rerun()
                            else:
                                st.error("No open slots available for this provider on the selected date. Please pick another date.")
    else:
        st.info("No active or past appointments found for this account.")

# -----------------------------------------------------------------------------
# ADMIN & STAFF PORTAL (Graphical Real-Time Data Capture & Notifications)
# -----------------------------------------------------------------------------
elif st.session_state.role == "admin":
    st.markdown('<div class="main-header">Albany Health Center — Staff Control Dashboard</div>', unsafe_allow_html=True)
    
    # Live Real-Time Cancellation & Patient Reschedule Notification Banner
    st.markdown("### 🔔 Real-Time Patient Activity Notifications (Last 24 Hours)")
    
    notif_col1, notif_col2 = st.columns(2)
    
    with notif_col1:
        st.markdown("#### ❌ Recent Cancellations")
        recent_cancels = run_query("""
            SELECT a.confirmation_code, p.first_name || ' ' || p.last_name AS patient_name, pr.full_name AS doctor
            FROM waitwise.appointments a
            JOIN waitwise.patients p ON p.patient_id = a.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            WHERE a.status = 'Cancelled' AND a.cancelled_at >= NOW() - INTERVAL '24 hours'
            ORDER BY a.cancelled_at DESC LIMIT 4;
        """)
        if recent_cancels is not None and not recent_cancels.empty:
            for _, c_row in recent_cancels.iterrows():
                st.markdown(f'<div class="alert-cancelled">⚠️ <strong>CANCELLED:</strong> {c_row["patient_name"]} ({c_row["confirmation_code"]}) with {c_row["doctor"]}</div>', unsafe_allow_html=True)
        else:
            st.caption("No recent cancellations.")

    with notif_col2:
        st.markdown("#### 🔄 Direct Patient Reschedules")
        recent_reschedules = run_query("""
            SELECT rr.preferred_new_date, rr.preferred_time_of_day, p.first_name || ' ' || p.last_name AS patient_name, pr.full_name AS doctor
            FROM waitwise.reschedule_requests rr
            JOIN waitwise.patients p ON p.patient_id = rr.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = rr.provider_id
            WHERE rr.requested_at >= NOW() - INTERVAL '24 hours'
            ORDER BY rr.requested_at DESC LIMIT 4;
        """)
        if recent_reschedules is not None and not recent_reschedules.empty:
            for _, r_row in recent_reschedules.iterrows():
                st.markdown(f'<div class="alert-rescheduled">🔄 <strong>RESCHEDULED:</strong> {r_row["patient_name"]} moved visit with {r_row["doctor"]} to {r_row["preferred_new_date"]} ({r_row["preferred_time_of_day"]})</div>', unsafe_allow_html=True)
        else:
            st.caption("No recent reschedules.")

    admin_tab1, admin_tab2, admin_tab3 = st.tabs([
        "📊 Graphical Real-Time Data Capture", 
        "📅 6-Month Scheduling Calendar",
        "👥 Albany Appointments Directory"
    ])

    # --- TAB 1: Graphical Real-Time Visual Capture ---
    with admin_tab1:
        st.subheader("Live Operational Analytics & Visual Capture")
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Checked-In Patients", run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Checked In';").iloc[0]['c'])
        m2.metric("Scheduled Today", run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE (start_time AT TIME ZONE 'America/New_York')::date = CURRENT_DATE;").iloc[0]['c'])
        m3.metric("Cancellations Today", run_query("SELECT COUNT(*) AS c FROM waitwise.appointments WHERE status = 'Cancelled' AND cancelled_at::date = CURRENT_DATE;").iloc[0]['c'])
        m4.metric("Direct Reschedules Today", run_query("SELECT COUNT(*) AS c FROM waitwise.reschedule_requests WHERE requested_at::date = CURRENT_DATE;").iloc[0]['c'])

        st.markdown("---")
        g_col1, g_col2 = st.columns(2)

        # Chart 1: Status Distribution Bar Chart
        with g_col1:
            st.markdown("#### Appointment Status Breakdown")
            status_counts = run_query("""
                SELECT status, COUNT(*) AS count 
                FROM waitwise.appointments 
                GROUP BY status;
            """)
            if status_counts is not None and not status_counts.empty:
                st.bar_chart(status_counts.set_index("status"))

        # Chart 2: Provider Visit Load Chart
        with g_col2:
            st.markdown("#### Patient Volume by Albany Doctor")
            provider_load = run_query("""
                SELECT pr.full_name AS doctor, COUNT(a.appointment_id) AS total_visits
                FROM waitwise.providers pr
                LEFT JOIN waitwise.appointments a ON a.provider_id = pr.provider_id
                GROUP BY pr.full_name;
            """)
            if provider_load is not None and not provider_load.empty:
                st.bar_chart(provider_load.set_index("doctor"))

    # --- TAB 2: 6-Month Interactive Calendar ---
    with admin_tab2:
        st.subheader("6-Month Provider Availability Calendar")
        
        providers = run_query("SELECT full_name FROM waitwise.providers;")['full_name'].tolist()
        selected_doc = st.selectbox("Select Albany Doctor:", providers)
        start_search = st.date_input("Start Window", datetime.today().date())
        end_search = start_search + timedelta(days=180)
        
        st.write(f"Displaying scheduling density for **{selected_doc}** from **{start_search}** to **{end_search}** (6 Months)")

        schedule_df = run_query("""
            SELECT (a.start_time AT TIME ZONE 'America/New_York')::date AS visit_date,
                   COUNT(*) AS booked_slots,
                   SUM(CASE WHEN a.status = 'Cancelled' THEN 1 ELSE 0 END) AS cancelled_slots,
                   SUM(CASE WHEN a.status = 'Rescheduled' THEN 1 ELSE 0 END) AS rescheduled_slots
            FROM waitwise.appointments a
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            WHERE pr.full_name = %s 
              AND a.start_time >= %s 
              AND a.start_time <= %s
            GROUP BY visit_date
            ORDER BY visit_date ASC;
        """, (selected_doc, start_search, end_search))
        
        if schedule_df is not None and not schedule_df.empty:
            st.dataframe(schedule_df, use_container_width=True)
            st.line_chart(schedule_df.set_index("visit_date")["booked_slots"])
        else:
            st.info("No booked visits found in this 6-month window.")

    # --- TAB 3: Master Directory ---
    with admin_tab3:
        st.subheader("Master Albany Clinic Appointments")
        all_appts = run_query("""
            SELECT a.appointment_id, a.confirmation_code, p.first_name || ' ' || p.last_name AS patient,
                   pr.full_name AS doctor, a.status, (a.start_time AT TIME ZONE 'America/New_York') AS start_et
            FROM waitwise.appointments a
            JOIN waitwise.patients p ON p.patient_id = a.patient_id
            JOIN waitwise.providers pr ON pr.provider_id = a.provider_id
            ORDER BY a.start_time DESC LIMIT 100;
        """)
        st.dataframe(all_appts, use_container_width=True)
