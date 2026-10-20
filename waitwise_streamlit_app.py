import streamlit as st
import pandas as pd
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, time
import qrcode
from io import BytesIO
import os

# ==========================================
# PAGE CONFIGURATION & CUSTOM STYLING
# ==========================================
st.set_page_config(
    page_title="Waitwise Healthcare",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Mobile-First Healthcare UI & Badges
st.markdown("""
<style>
    /* Base App Styling */
    .block-container { padding-top: 1rem; padding-bottom: 5rem; max-width: 1200px; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Synthetic Banner */
    .synthetic-banner {
        background-color: #fef3c7;
        color: #92400e;
        padding: 10px 16px;
        border-radius: 8px;
        border: 1px solid #fde68a;
        text-align: center;
        font-weight: 500;
        margin-bottom: 20px;
        font-size: 0.875rem;
    }
    
    /* Status Badges */
    .badge {
        display: inline-block;
        padding: 0.25em 0.65em;
        font-size: 0.8rem;
        font-weight: 600;
        border-radius: 9999px;
        text-align: center;
    }
    .badge-scheduled { background-color: #e0f2fe; color: #0369a1; }
    .badge-checkedin { background-color: #fef9c3; color: #854d0e; }
    .badge-completed { background-color: #dcfce7; color: #15803d; }
    .badge-cancelled { background-color: #fee2e2; color: #b91c1c; }
    .badge-noshow { background-color: #f3f4f6; color: #374151; }
    .badge-resched-req { background-color: #ffedd5; color: #c2410c; }
    .badge-rescheduled { background-color: #fce7f3; color: #9d174d; }
    
    /* Appointment Cards */
    .appt-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 12px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# DATABASE CONNECTION & HELPER FUNCTIONS
# ==========================================
@st.cache_resource
def get_db_connection():
    """Establish connection to PostgreSQL/Neon DB using secrets or env vars."""
    try:
        db_url = st.secrets.get("DATABASE_URL", os.environ.get("DATABASE_URL", None))
        if not db_url:
            st.error("DATABASE_URL secret is missing. Please configure secrets in Streamlit Cloud.")
            return None
        return psycopg2.connect(db_url)
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None

def fetch_query(query, params=None, single=False):
    """Execute a SELECT query and return results as dictionary/list."""
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if single:
                return cur.fetchone()
            return cur.fetchall()
    except Exception as e:
        st.error(f"Database Query Error: {e}")
        return None

def execute_query(query, params=None):
    """Execute INSERT/UPDATE/DELETE query and commit changes."""
    conn = get_db_connection()
    if not conn: return False
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
            return True
    except Exception as e:
        conn.rollback()
        st.error(f"Database Execution Error: {e}")
        return False

def format_status(status):
    """Render color-coded HTML status badge."""
    classes = {
        'Scheduled': 'badge-scheduled',
        'Checked In': 'badge-checkedin',
        'Completed': 'badge-completed',
        'Cancelled': 'badge-cancelled',
        'No Show': 'badge-noshow',
        'Reschedule Requested': 'badge-resched-req',
        'Rescheduled': 'badge-rescheduled'
    }
    cls = classes.get(status, 'badge-scheduled')
    return f'<span class="badge {cls}">{status}</span>'

# ==========================================
# SESSION STATE INITIALIZATION
# ==========================================
if 'role' not in st.session_state:
    st.session_state.role = None
if 'user_data' not in st.session_state:
    st.session_state.user_data = None

# ==========================================
# AUTH & ACTIONS LOGIC
# ==========================================
def login_patient(patient_id=None):
    if patient_id:
        patient = fetch_query("SELECT * FROM waitwise.patients WHERE patient_id = %s", (patient_id,), single=True)
    else:
        patient = fetch_query("SELECT * FROM waitwise.patients ORDER BY patient_id LIMIT 1", single=True)
        
    if patient:
        st.session_state.role = 'patient'
        st.session_state.user_data = patient

def login_admin():
    st.session_state.role = 'admin'
    st.session_state.user_data = {'name': 'Clinic Admin', 'id': 'admin-01'}

def logout():
    st.session_state.role = None
    st.session_state.user_data = None

# Patient Actions
def submit_reschedule_request(appt_id, patient_id, provider_id, reason, pref_date, pref_time):
    query = """
        INSERT INTO waitwise.reschedule_requests 
        (appointment_id, patient_id, provider_id, requested_at, requested_via, reason, preferred_new_date, preferred_time_of_day, status)
        VALUES (%s, %s, %s, now(), 'Patient Portal', %s, %s, %s, 'Pending');
        
        UPDATE waitwise.appointments SET status = 'Reschedule Requested', updated_at = now() WHERE appointment_id = %s;
        
        INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id)
        VALUES ('patient', %s, 'RESCHEDULE_REQUESTED', 'reschedule_requests', %s);
    """
    if execute_query(query, (appt_id, patient_id, provider_id, reason, pref_date, pref_time, appt_id, f"patient:{patient_id}", appt_id)):
        st.toast("Reschedule request submitted successfully!", icon="✅")

def cancel_appointment(appt_id, patient_id, reason):
    query = """
        UPDATE waitwise.appointments SET status = 'Cancelled', cancel_reason = %s, updated_at = now(), cancelled_at = now() WHERE appointment_id = %s;
        
        INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id)
        VALUES ('patient', %s, 'APPT_CANCELLED', 'appointments', %s);
    """
    if execute_query(query, (reason, appt_id, f"patient:{patient_id}", appt_id)):
        st.toast("Appointment cancelled successfully.", icon="✅")

def cancel_reschedule_request(appt_id, patient_id):
    query = """
        UPDATE waitwise.reschedule_requests SET status = 'Declined', decline_reason = 'Cancelled by patient', resolved_at = now() WHERE appointment_id = %s AND status = 'Pending';
        
        UPDATE waitwise.appointments SET status = 'Scheduled', updated_at = now() WHERE appointment_id = %s;
        
        INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id)
        VALUES ('patient', %s, 'RESCHEDULE_REQ_CANCELLED', 'reschedule_requests', %s);
    """
    if execute_query(query, (appt_id, appt_id, f"patient:{patient_id}", appt_id)):
        st.toast("Reschedule request withdrawn. Appointment restored to Scheduled.", icon="ℹ️")

# Admin Actions
def approve_reschedule(req_id, appt_id):
    query = """
        UPDATE waitwise.reschedule_requests SET status = 'Approved', resolved_at = now(), resolved_by = 'admin-demo' WHERE request_id = %s;
        UPDATE waitwise.appointments SET status = 'Cancelled', updated_at = now(), cancel_reason = 'Rescheduled' WHERE appointment_id = %s;
        INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id)
        VALUES ('staff', 'admin-demo', 'RESCHEDULE_APPROVED', 'reschedule_requests', %s);
    """
    if execute_query(query, (req_id, appt_id, req_id)):
        st.toast("Request approved. Original appointment updated.", icon="✅")

def deny_reschedule(req_id, appt_id, decline_reason):
    query = """
        UPDATE waitwise.reschedule_requests SET status = 'Declined', resolved_at = now(), resolved_by = 'admin-demo', decline_reason = %s WHERE request_id = %s;
        UPDATE waitwise.appointments SET status = 'Scheduled', updated_at = now() WHERE appointment_id = %s;
        INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id)
        VALUES ('staff', 'admin-demo', 'RESCHEDULE_DECLINED', 'reschedule_requests', %s);
    """
    if execute_query(query, (decline_reason, req_id, appt_id, req_id)):
        st.toast("Reschedule request declined.", icon="❌")

def manual_reschedule(appt_id, new_date, new_time):
    start_dt = datetime.combine(new_date, new_time)
    end_dt = start_dt + timedelta(minutes=30)
    query = """
        UPDATE waitwise.appointments SET start_time = %s, end_time = %s, status = 'Scheduled', updated_at = now() WHERE appointment_id = %s;
        INSERT INTO waitwise.audit_log (user_role, user_id, action_type, table_affected, record_id)
        VALUES ('staff', 'admin-demo', 'MANUAL_RESCHEDULE', 'appointments', %s);
    """
    if execute_query(query, (start_dt, end_dt, appt_id, appt_id)):
        st.toast("Appointment time updated successfully.", icon="✅")

def add_synthetic_appointment(patient_id, provider_id, loc_id, type_id, date, t):
    start_dt = datetime.combine(date, t)
    end_dt = start_dt + timedelta(minutes=30)
    query = """
        INSERT INTO waitwise.appointments (patient_id, provider_id, location_id, type_id, start_time, end_time, status, visit_reason, booked_via)
        VALUES (%s, %s, %s, %s, %s, %s, 'Scheduled', 'Admin Scheduled Visit', 'Front Desk');
    """
    if execute_query(query, (patient_id, provider_id, loc_id, type_id, start_dt, end_dt)):
        st.toast("New appointment added!", icon="✅")

# ==========================================
# VIEWS & LAYOUT
# ==========================================
def render_qr_code():
    url = "https://share.streamlit.io"
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    st.image(buf.getvalue(), caption="Scan for Mobile View", width=140)

def login_view():
    st.markdown('<div class="synthetic-banner">🏥 <b>Waitwise Healthcare Portal</b> — 100% Synthetic Demo Data. No real PHI is stored or displayed.</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    with col1:
        st.title("Welcome to Waitwise")
        st.write("Streamlined, accessible appointment management for patients and provider clinics.")
        
        st.markdown("### Select a Demo Role")
        
        # Patient selector list
        patients = fetch_query("SELECT patient_id, first_name, last_name, mrn FROM waitwise.patients ORDER BY patient_id LIMIT 5")
        
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Patient Portal")
            if patients:
                pat_options = {f"{p['first_name']} {p['last_name']} ({p['mrn']})": p['patient_id'] for p in patients}
                selected_patient = st.selectbox("Choose Demo Patient", list(pat_options.keys()))
                if st.button("Log In as Patient", type="primary", use_container_width=True):
                    login_patient(pat_options[selected_patient])
                    st.rerun()
            else:
                if st.button("Log In as Patient", type="primary", use_container_width=True):
                    login_patient()
                    st.rerun()
                    
        with c2:
            st.subheader("Admin Portal")
            st.caption("Access staff management controls, scheduling queue, and clinic metrics.")
            st.write("") # spacing
            if st.button("Log In as Staff Admin", use_container_width=True):
                login_admin()
                st.rerun()
                
    with col2:
        st.markdown("### Test on Mobile")
        render_qr_code()

def patient_view():
    user = st.session_state.user_data
    st.markdown('<div class="synthetic-banner">⚠️ SYNTHETIC DEMO MODE — Logged in as Patient: <b>' + f"{user['first_name']} {user['last_name']}" + '</b></div>', unsafe_allow_html=True)
    
    head_col, btn_col = st.columns([4, 1])
    head_col.title(f"Hello, {user['first_name']}")
    head_col.caption(f"MRN: {user['mrn']} | Phone: {user['phone']}")
    btn_col.button("Log Out", on_click=logout, use_container_width=True)
    
    st.divider()
    
    query = """
        SELECT a.*, p.full_name as provider_name, l.name as location_name, t.name as type_name 
        FROM waitwise.appointments a
        JOIN waitwise.providers p ON a.provider_id = p.provider_id
        JOIN waitwise.locations l ON a.location_id = l.location_id
        JOIN waitwise.appointment_types t ON a.type_id = t.type_id
        WHERE a.patient_id = %s
        ORDER BY a.start_time DESC LIMIT 15
    """
    appts = fetch_query(query, (user['patient_id'],))
    st.subheader("Your Appointments")
    
    if not appts:
        st.info("No appointments currently found on record.")
    else:
        for appt in appts:
            with st.container():
                st.markdown(f"""
                <div class="appt-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h4 style="margin:0; font-size:1.1rem;">{appt['type_name']}</h4>
                        {format_status(appt['status'])}
                    </div>
                    <p style="margin: 8px 0 0 0; color: #374151; font-size:0.95rem;">
                        📅 <b>Date & Time:</b> {appt['start_time'].strftime('%b %d, %Y at %I:%M %p')}<br>
                        👨‍⚕️ <b>Provider:</b> {appt['provider_name']}<br>
                        📍 <b>Location:</b> {appt['location_name']}
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                if appt['status'] == 'Scheduled':
                    with st.expander("Reschedule or Cancel"):
                        t1, t2 = st.tabs(["Request Reschedule", "Cancel Appointment"])
                        with t1:
                            with st.form(key=f"resched_form_{appt['appointment_id']}"):
                                reason = st.selectbox("Reason for Reschedule", 
                                                      ["Work conflict", "Transportation issue", "Illness", "Family emergency", "Other"],
                                                      key=f"r_reason_{appt['appointment_id']}")
                                pref_date = st.date_input("Preferred New Date", 
                                                          min_value=datetime.today() + timedelta(days=1),
                                                          key=f"r_date_{appt['appointment_id']}")
                                pref_time = st.selectbox("Preferred Time of Day", ["Morning", "Afternoon", "Any"],
                                                         key=f"r_time_{appt['appointment_id']}")
                                
                                if st.form_submit_button("Submit Reschedule Request", type="primary"):
                                    submit_reschedule_request(appt['appointment_id'], user['patient_id'], appt['provider_id'], reason, pref_date, pref_time)
                                    st.rerun()
                        with t2:
                            with st.form(key=f"cancel_form_{appt['appointment_id']}"):
                                reason = st.text_input("Reason for Cancellation", key=f"c_reason_{appt['appointment_id']}")
                                if st.form_submit_button("Confirm Cancellation"):
                                    cancel_appointment(appt['appointment_id'], user['patient_id'], reason)
                                    st.rerun()
                                    
                elif appt['status'] == 'Reschedule Requested':
                    if st.button("Withdraw Reschedule Request", key=f"withdraw_{appt['appointment_id']}"):
                        cancel_reschedule_request(appt['appointment_id'], user['patient_id'])
                        st.rerun()

def admin_view():
    st.markdown('<div class="synthetic-banner">⚙️ ADMIN CONTROL PANEL — Synthetic Data Portal</div>', unsafe_allow_html=True)
    
    with st.sidebar:
        st.title("Clinic Admin")
        view_mode = st.radio("Navigation", ["Dashboard Metrics", "Master Schedule", "Reschedule Queue", "Audit Log"])
        st.divider()
        st.button("Log Out Staff", on_click=logout, use_container_width=True)
        
    if view_mode == "Dashboard Metrics":
        st.header("Clinic Operational Metrics")
        
        metrics = fetch_query("""
            SELECT 
                (SELECT count(*) FROM waitwise.patients) as total_patients,
                (SELECT count(*) FROM waitwise.appointments WHERE start_time >= current_date) as upcoming_appts,
                (SELECT count(*) FROM waitwise.reschedule_requests WHERE status = 'Pending') as pending_requests
        """, single=True)
        
        if metrics:
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Active Patients", metrics['total_patients'])
            m2.metric("Upcoming Appointments", metrics['upcoming_appts'])
            m3.metric("Pending Reschedules", metrics['pending_requests'])
            
        st.subheader("Appointment Status Distribution")
        stats = fetch_query("SELECT * FROM waitwise.v_daily_status_counts WHERE appt_date >= current_date - interval '5 days' AND appt_date <= current_date + interval '10 days'")
        if stats:
            df = pd.DataFrame(stats)
            pivot_df = df.pivot(index='appt_date', columns='status', values='appointments').fillna(0)
            st.bar_chart(pivot_df)
            
    elif view_mode == "Master Schedule":
        st.header("Master Schedule & Management")
        
        with st.expander("➕ Schedule New Synthetic Appointment"):
            with st.form("add_appt_form"):
                pats = fetch_query("SELECT patient_id, first_name, last_name FROM waitwise.patients ORDER BY last_name LIMIT 50")
                provs = fetch_query("SELECT provider_id, full_name FROM waitwise.providers WHERE is_active=true")
                locs = fetch_query("SELECT location_id, name FROM waitwise.locations")
                types = fetch_query("SELECT type_id, name FROM waitwise.appointment_types")
                
                pat_opts = {f"{p['last_name']}, {p['first_name']}": p['patient_id'] for p in pats} if pats else {}
                prov_opts = {p['full_name']: p['provider_id'] for p in provs} if provs else {}
                loc_opts = {l['name']: l['location_id'] for l in locs} if locs else {}
                type_opts = {t['name']: t['type_id'] for t in types} if types else {}
                
                sel_pat = st.selectbox("Select Patient", list(pat_opts.keys()))
                sel_prov = st.selectbox("Select Provider", list(prov_opts.keys()))
                sel_loc = st.selectbox("Select Location", list(loc_opts.keys()))
                sel_type = st.selectbox("Visit Type", list(type_opts.keys()))
                
                c_d, c_t = st.columns(2)
                d = c_d.date_input("Date", min_value=datetime.today())
                t = c_t.time_input("Time", value=time(9, 0))
                
                if st.form_submit_button("Book Appointment", type="primary"):
                    add_synthetic_appointment(pat_opts[sel_pat], prov_opts[sel_prov], loc_opts[sel_loc], type_opts[sel_type], d, t)
                    st.rerun()

        st.subheader("Filter Appointments")
        c1, c2 = st.columns(2)
        search = c1.text_input("Search Patient Last Name or MRN", "")
        status_f = c2.selectbox("Status Filter", ["All", "Scheduled", "Checked In", "Completed", "Cancelled", "No Show", "Reschedule Requested", "Rescheduled"])
        
        q = "SELECT * FROM waitwise.v_appointment_details WHERE 1=1 "
        params = []
        if search:
            q += "AND (last_name ILIKE %s OR mrn ILIKE %s) "
            params.extend([f"%{search}%", f"%{search}%"])
        if status_f != "All":
            q += "AND status = %s "
            params.append(status_f)
            
        q += "ORDER BY start_et DESC LIMIT 30"
        
        records = fetch_query(q, tuple(params) if params else None)
        if records:
            for rec in records:
                with st.container():
                    st.markdown(f"""
                    <div class="appt-card">
                        <div style="display:flex; justify-content:space-between;">
                            <b>{rec['start_et'].strftime('%b %d, %Y - %I:%M %p')}</b>
                            {format_status(rec['status'])}
                        </div>
                        <div><b>Patient:</b> {rec['first_name']} {rec['last_name']} ({rec['mrn']})</div>
                        <div><b>Provider:</b> {rec['provider']} | <b>Type:</b> {rec['appointment_type']}</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if rec['status'] == 'Scheduled':
                        with st.expander(f"Admin Reschedule Code: {rec['confirmation_code']}"):
                            ca, cb = st.columns(2)
                            new_d = ca.date_input("New Date", key=f"ad_d_{rec['appointment_id']}")
                            new_t = cb.time_input("New Time", key=f"ad_t_{rec['appointment_id']}")
                            if st.button("Update Appointment Time", key=f"ad_btn_{rec['appointment_id']}", type="primary"):
                                manual_reschedule(rec['appointment_id'], new_d, new_t)
                                st.rerun()
        else:
            st.info("No matching appointments found.")

    elif view_mode == "Reschedule Queue":
        st.header("Pending Reschedule Requests Queue")
        reqs = fetch_query("SELECT * FROM waitwise.v_reschedule_queue WHERE request_status = 'Pending' ORDER BY requested_et ASC")
        
        if not reqs:
            st.success("🎉 All clear! No pending reschedule requests in queue.")
        else:
            for req in reqs:
                with st.container():
                    st.markdown(f"""
                    <div class="appt-card">
                        <h4>Patient: {req['first_name']} {req['last_name']} (MRN: {req['mrn']})</h4>
                        <p><b>Original Appt:</b> {req['original_start_et'].strftime('%b %d, %Y %I:%M %p')} with {req['provider']}</p>
                        <p><b>Reason:</b> {req['reason']}</p>
                        <p><b>Preferred Window:</b> {req['preferred_new_date']} ({req['preferred_time_of_day']})</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Approve Request", key=f"app_{req['request_id']}", type="primary", use_container_width=True):
                            approve_reschedule(req['request_id'], req.get('appointment_id'))
                            st.rerun()
                    with c2:
                        with st.expander("Deny Request"):
                            decline_reason = st.text_input("Decline Reason", value="No availability", key=f"d_reason_{req['request_id']}")
                            if st.button("Confirm Denial", key=f"den_{req['request_id']}", use_container_width=True):
                                deny_reschedule(req['request_id'], req.get('appointment_id'), decline_reason)
                                st.rerun()

    elif view_mode == "Audit Log":
        st.header("System Activity & Audit Log")
        logs = fetch_query("SELECT * FROM waitwise.audit_log ORDER BY timestamp_est DESC LIMIT 50")
        if logs:
            st.dataframe(pd.DataFrame(logs), use_container_width=True)

# ==========================================
# APP ENTRY POINT
# ==========================================
def main():
    if st.session_state.role is None:
        login_view()
    elif st.session_state.role == 'patient':
        patient_view()
    elif st.session_state.role == 'admin':
        admin_view()

if __name__ == "__main__":
    main()