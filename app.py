"""
WebUntis Absence Analyzer
=====================

A Streamlit web app that connects to WebUntis API and analyzes teacher
absence patterns (cancelled lessons) across different school years.

Authentication methods:
- Username/Password: Standard WebUntis credentials
- QR/Key: Scan QR code or paste data to login with TOTP key

Data filtering:
- School year selector
- Minimum scheduled lessons filter (filters out cover teachers)
- Filters out TA_, U , and Unknown teachers

Usage:
    streamlit run app.py
    
Or set credentials in .env file for auto-login:
    UNTIS_SERVER=yourchool.webuntis.com
    UNTIS_SCHOOL=yourschool
    UNTIS_USER=yourusername
    UNTIS_PASSWORD=yourpassword
"""

# ============================================================================
# IMPORTS
# ============================================================================

import streamlit as st          # Web UI framework
import pandas as pd            # Data handling
import webuntis               # WebUntis API client
import datetime              # Date handling
import pyotp                 # TOTP for QR/Key login
import requests             # HTTP requests
from collections import defaultdict
from dotenv import load_dotenv
import os

# Load credentials from .env file
load_dotenv()

# Image processing for QR code scanning
import cv2
import numpy as np
from PIL import Image

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="WebUntis Absence Analyzer",
    page_icon="🏫",
    layout="centered"
)

# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================
# Streamlit persists state during the session but not across refreshes

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'credentials' not in st.session_state:
    st.session_state.credentials = {}
if 'login_method' not in st.session_state:
    st.session_state.login_method = ''

# Load saved credentials from .env (auto-fill login form)
if 'saved_server' not in st.session_state:
    st.session_state.saved_server = os.getenv('UNTIS_SERVER', '')
if 'saved_school' not in st.session_state:
    st.session_state.saved_school = os.getenv('UNTIS_SCHOOL', '')
if 'saved_username' not in st.session_state:
    st.session_state.saved_username = os.getenv('UNTIS_USER', '')
if 'saved_password' not in st.session_state:
    st.session_state.saved_password = os.getenv('UNTIS_PASSWORD', '')
if 'qr_scanned' not in st.session_state:
    st.session_state.qr_scanned = None

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_teacher_name(t_obj):
    """Extract display name from teacher object.
    
    Teacher objects can be either webuntis objects or dictionaries
    (from mobile API). Returns 'LongName (ShortName)' format.
    """
    if isinstance(t_obj, dict):
        long_name = t_obj.get('longName') or t_obj.get('long_name', '')
        name = t_obj.get('name', '')
        if long_name:
            return f"{long_name} ({name})"
        return name
    if hasattr(t_obj, 'long_name') and t_obj.long_name:
        return f"{t_obj.long_name} ({t_obj.name})"
    return t_obj.name


def parse_untis_date(date_str):
    """Parse Untis date string to Python date.
    
    Untis uses format YYYYMMDD, but mobile API may return YYYY-MM-DD.
    Handles both formats.
    """
    if not date_str:
        return datetime.date.today()
    try:
        return datetime.datetime.strptime(date_str, "%Y%m%d").date()
    except ValueError:
        try:
            return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return datetime.date.today()


def _create_stats():
    """Create empty stats dictionary for a teacher.
    
    Returns a defaultdict that auto-initializes missing keys.
    Used to track cancelled lessons per teacher.
    """
    return {
        'absent': 0,    # Total cancelled lessons
        'total': 0,     # Total scheduled lessons
        'by_day': defaultdict(lambda: {'absent': 0, 'total': 0}),
        'by_year': defaultdict(lambda: {'absent': 0, 'total': 0})
    }

# ============================================================================
# ANALYZE FUNCTION (Username/Password Login)
# ============================================================================

def analyze(session):
    """Analyze teacher absences using standard WebUntis API.
    
    Gets the logged-in user's timetable and calculates cancelled lessons
    for each assigned teacher. Uses my_timetable() which returns all
    periods the user is scheduled to teach.
    """
    today = datetime.date.today()
    all_years = sorted(list(session.schoolyears()), key=lambda x: x.start)
    years = [sy for sy in all_years if sy.start.date() <= today]
    
    # Get all teachers for name lookup
    teacher_map = {t.id: t for t in session.teachers()}
    stats = defaultdict(_create_stats)
    
    for sy in years:
        try:
            # Get timetable for this school year
            for p in session.my_timetable(start=sy.start, end=sy.end):
                # Skip irregular lessons (substitutions)
                if p.code == 'irregular':
                    continue
                
                # Extract teachers from period
                teachers = []
                try:
                    teachers = [get_teacher_name(t) for t in p.teachers]
                except IndexError:
                    # Fallback: get from raw data
                    for te in p._data.get('te', []):
                        t = teacher_map.get(te.get('id'))
                        teachers.append(get_teacher_name(t) if t else "Unknown")
                
                is_cancelled = p.code == 'cancelled'
                day = p.start.weekday()
                
                for t in teachers:
                    if not t:
                        continue
                    s = stats[t]
                    s['total'] += 1
                    s['by_day'][day]['total'] += 1
                    s['by_year'][sy.name]['total'] += 1
                    
                    if is_cancelled:
                        s['absent'] += 1
                        s['by_day'][day]['absent'] += 1
                        s['by_year'][sy.name]['absent'] += 1
        except Exception as e:
            st.warning(f"Error: {e}")
    
    return {t: s for t, s in stats.items() if s['total'] >= 10}


# ============================================================================
# ANALYZE MOBILE FUNCTION (QR/Key Login)
# ============================================================================

def analyze_mobile(server, school, username, secret):
    """Analyze teacher absences using mobile API.
    
    This function is used when logging in via QR code / TOTP key.
    The mobile API has different method names and data structures.
    """
    totp = pyotp.TOTP(secret)
    client_time = int(datetime.datetime.now().timestamp() * 1000)
    url = f"https://{server}/WebUntis/jsonrpc_intern.do"
    
    # First get user data (includes master data with teachers/school years)
    user_data_req = requests.post(
        url,
        params={'m': 'getUserData2017', 'school': school, 'v': 'i2.2'},
        json={
            "id": "Awesome",
            "method": "getUserData2017",
            "params": [{"auth": {"user": username, "otp": totp.now(), "clientTime": client_time}}],
            "jsonrpc": "2.0"
        }
    )
    
    user_data_resp = user_data_req.json()
    if 'error' in user_data_resp:
        return {}
    
    user_data = user_data_resp.get('result', {})
    master_data = user_data.get('masterData', {})
    teacher_map = {t['id']: t for t in master_data.get('teachers', [])}
    schoolyears_list = master_data.get('schoolyears', [])
    
    today = datetime.date.today()
    valid_years = [y for y in schoolyears_list if parse_untis_date(y['startDate']) <= today]
    
    stats = defaultdict(_create_stats)
    
    # Try getTimetable2017 first (type=3 is TEACHER), then fallback
    for sy in valid_years[:3]:
        # Try method 1: getTimetable2017 with type
        timetable_req = requests.post(
            url,
            params={'m': 'getTimetable2017', 'school': school, 'v': 'i2.2'},
            json={
                "id": 1,
                "method": "getTimetable2017",
                "params": [{
                    "auth": {"user": username, "otp": totp.now(), "clientTime": client_time},
                    "startDate": sy['startDate'],
                    "endDate": sy['endDate'],
                    "type": 3,  # TEACHER
                    "id": 0    # Current user
                }],
                "jsonrpc": "2.0"
            }
        )
        
        timetable_data = timetable_req.json()
        
        # Fallback: getOwnTimetable2017
        if 'error' in timetable_data:
            timetable_req2 = requests.post(
                url,
                params={'m': 'getOwnTimetable2017', 'school': school, 'v': 'i2.2'},
                json={
                    "id": 1,
                    "method": "getOwnTimetable2017",
                    "params": [{
                        "auth": {"user": username, "otp": totp.now(), "clientTime": client_time},
                        "startDate": sy['startDate'],
                        "endDate": sy['endDate']
                    }],
                    "jsonrpc": "2.0"
                }
            )
            timetable_data = timetable_req2.json()
        
        if 'error' in timetable_data:
            continue
        
        result = timetable_data.get('result', {})
        periods = result.get('periods', [])
        
        # Process each period
        for p in periods:
            if p.get('code') == 'irregular':
                continue
            
            is_cancelled = p.get('code') == 'cancelled'
            day = parse_untis_date(p.get('date', '')).weekday()
            
            teachers = []
            for te in p.get('teachers', []):
                t = teacher_map.get(te.get('id'))
                teachers.append(get_teacher_name(t) if t else "Unknown")
            
            for t in teachers:
                if not t:
                    continue
                s = stats[t]
                s['total'] += 1
                s['by_day'][day]['total'] += 1
                s['by_year'][sy['name']]['total'] += 1
                
                if is_cancelled:
                    s['absent'] += 1
                    s['by_day'][day]['absent'] += 1
                    s['by_year'][sy['name']]['absent'] += 1
    
    return {t: s for t, s in stats.items() if s['total'] >= 10}


# ============================================================================
# MAIN APP UI
# ============================================================================

st.title("🏫 WebUntis Absence Analyzer")

# -------------------------------------------------------------------------
# LOGIN SECTION
# -------------------------------------------------------------------------

if not st.session_state.logged_in:
    st.markdown("### Login")
    
    # Choose login method
    method = st.radio("Login Method", ["Username/Password", "QR/Key"])
    
    server = school = username = password = qr = ""
    
    # Username/Password form
    if method == "Username/Password":
        c1, c2 = st.columns(2)
        with c1:
            server = st.text_input(
                "Server",
                placeholder="yourschool.webuntis.com",
                value=st.session_state.saved_server
            )
        with c2:
            school = st.text_input(
                "School",
                placeholder="NAME",
                value=st.session_state.saved_school
            )
        username = st.text_input(
            "Username",
            value=st.session_state.saved_username
        )
        # Password field (dots hidden, can still edit)
        password = st.text_input(
            "Password",
            type="password",
            value=st.session_state.saved_password
        )
    
    # QR/Key login form
    elif method == "QR/Key":
        # Upload QR code image
        uploaded = st.file_uploader(
            "Upload QR image",
            type=['png', 'jpg', 'jpeg'],
            label_visibility="collapsed"
        )
        
        detector = cv2.QRCodeDetector()
        
        # Try to decode QR code
        if uploaded:
            try:
                img = Image.open(uploaded)
                img_array = np.array(img)
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
                for try_img in [img_array, gray]:
                    qr_data, _, _ = detector.detectAndDecode(try_img)
                    if qr_data and "untis://" in qr_data:
                        st.session_state.qr_scanned = qr_data
                        st.success("✅ QR Code detected!")
                        break
                else:
                    st.info("No QR code found")
            except Exception as e:
                st.info(f"Error: {e}")
        
        # QR data text area (can paste or edit)
        qr = st.text_area(
            "QR Data",
            value=st.session_state.qr_scanned or "",
            placeholder="untis://setschool?url=...&school=...&user=...&key=..."
        )
    
    # Login button
    if st.button("🔓 Login", type="primary", width='stretch'):
        with st.spinner("Logging in..."):
            try:
                # -----------------------------------------------------------------
                # USERNAME/PASSWORD LOGIN
                # -----------------------------------------------------------------
                if method == "Username/Password":
                    if not (server and school and username and password):
                        st.error("Fill all fields!")
                    else:
                        # Clean server URL
                        s = server.replace("https://", "").replace("http://", "").split("/")[0]
                        
                        # Login via standard WebUntis API
                        with webuntis.Session(
                            username=username,
                            password=password,
                            server=s,
                            school=school,
                            useragent='WebUntis'
                        ) as sess:
                            sess.login()
                            st.session_state.credentials = {
                                'server': s,
                                'school': school,
                                'username': username,
                                'password': password
                            }
                            st.session_state.logged_in = True
                            st.session_state.login_method = method
                            st.rerun()
                
                # -----------------------------------------------------------------
                # QR/KEY LOGIN  
                # -----------------------------------------------------------------
                elif method == "QR/Key":
                    if not qr:
                        st.error("Enter QR data!")
                    else:
                        # Parse QR data: untis://setschool?url=...&school=...&user=...&key=...
                        qr_str = qr.replace("untis://setschool?", "").replace("untis://", "")
                        params = dict(p.split("=") for p in qr_str.split("&") if "=" in p)
                        
                        srv = params.get("url", "").replace("https://", "").replace("http://", "").split("/")[0]
                        sch = params.get("school", "")
                        user = params.get("user", "")
                        key = params.get("key", "")
                        
                        if key:
                            # Generate TOTP from key
                            totp = pyotp.TOTP(key)
                            otp = totp.now()
                            
                            # Login via mobile API
                            url = f"https://{srv}/WebUntis/jsonrpc_intern.do"
                            resp = requests.post(
                                url,
                                params={
                                    'm': 'getUserData2017',
                                    'school': ch,
                                    'v': 'i2.2'
                                },
                                json={
                                    "id": "Awesome",
                                    "method": "getUserData2017",
                                    "params": [{
                                        "auth": {
                                            "user": user,
                                            "otp": otp,
                                            "clientTime": int(datetime.datetime.now().timestamp() * 1000)
                                        }
                                    }],
                                    "jsonrpc": "2.0"
                                }
                            )
                            
                            if resp.status_code == 200:
                                data = resp.json()
                                if 'result' in data:
                                    st.session_state.credentials = {
                                        'server': srv,
                                        'school': ch,
                                        'username': user,
                                        'password': key
                                    }
                                    st.session_state.logged_in = True
                                    st.session_state.login_method = method
                                    st.rerun()
                                else:
                                    st.error(f"Login failed")
                            else:
                                st.error(f"Login failed: {resp.status_code}")
                        else:
                            st.error("QR code missing key")
            
            except Exception as e:
                st.error(f"Login failed: {e}")

# -------------------------------------------------------------------------
# DASHBOARD SECTION (after login)
# -------------------------------------------------------------------------

else:
    # Sidebar with user info and logout
    with st.sidebar:
        st.markdown(f"**{st.session_state.credentials['username']}**")
        st.caption(f"@ {st.session_state.credentials['school']}")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.credentials = {}
            st.session_state.qr_scanned = None
            st.rerun()
    
    # Analyze button
    if st.button("🔄 Analyze Data", type="primary"):
        with st.spinner("Analyzing..."):
            creds = st.session_state.credentials
            login_method = st.session_state.get('login_method', '')
            try:
                pwd = creds.get('password', '')
                
                if login_method == "QR/Key":
                    st.warning("QR login data - using mobile API...")
                    st.session_state.stats = analyze_mobile(
                        creds['server'],
                        creds['school'],
                        creds['username'],
                        pwd
                    )
                else:
                    # Standard API login
                    with webuntis.Session(
                        username=creds['username'],
                        password=pwd,
                        server=creds['server'],
                        school=creds['school'],
                        useragent='WebUntis'
                    ) as sess:
                        sess.login()
                        st.session_state.stats = analyze(sess)
            except Exception as e:
                st.error(f"Error: {e}")
    
    # Display results
    if 'stats' in st.session_state:
        stats = st.session_state.stats
        
        # Get all years from stats
        all_years = set()
        for s in stats.values():
            all_years.update(s['by_year'].keys())
        year_options = ["All Years"] + sorted(all_years, reverse=True)
        
        # Filters
        selected_year = st.selectbox("School Year", year_options)
        min_lessons = st.slider(
            "Minimum Scheduled Lessons",
            min_value=10,
            max_value=200,
            value=26,
            help="Filter out teachers with fewer scheduled lessons"
        )
        anonymous = st.checkbox("Anonymous Mode", value=False, help="Hide teacher names (show as Teacher 1, 2, etc.)")
        
        # Filter stats by year
        if selected_year == "All Years":
            filtered_stats = stats
        else:
            filtered_stats = {
                t: s for t, s in stats.items()
                if selected_year in s['by_year']
            }
        
        if not filtered_stats:
            st.warning("No data for selected year.")
            st.stop()
        
        # Build leaderboard
        leaderboard = []
        for t, s in filtered_stats.items():
            # Skip cover teachers and unknowns
            if "TA_" in t or t.startswith("U ") or t == "Unknown":
                continue
            
            # Get data for selected year
            if selected_year == "All Years":
                total = s['total']
                cancelled = s['absent']
            else:
                y_data = s['by_year'].get(
                    selected_year,
                    {'total': s['total'], 'absent': s['absent']}
                )
                total = y_data['total']
                cancelled = y_data['absent']
            
            # Skip if below minimum lessons
            if total < min_lessons:
                continue
            
            pct = ((total - cancelled) / total) * 100 if total else 0
            worst = max(range(5), key=lambda d: s['by_day'][d]['absent'])
            worst_name = ["Mon", "Tue", "Wed", "Thu", "Fri"][worst] if s['by_day'][worst]['absent'] else "N/A"
            
            # Anonymize teacher name if checked
            display_name = t
            if anonymous:
                display_name = f"Teacher {len(leaderboard) + 1}"
            
            leaderboard.append({
                "Teacher": display_name,
                "Cancelled": cancelled,
                "Scheduled": total,
                "Attendance %": round(pct, 1),
                "Worst Day": f"{worst_name} ({s['by_day'][worst]['absent']})" if s['by_day'][worst]['absent'] else "N/A"
            })
        
        df = pd.DataFrame(leaderboard)
        df = df.sort_values("Cancelled", ascending=False)
        
        # Metrics
        c1, c2 = st.columns(2)
        c1.metric("Total Cancelled", df["Cancelled"].sum())
        c2.metric(
            "Avg Attendance",
            f"{df['Attendance %'].mean():.1f}%" if len(df) > 0 else "N/A"
        )
        
        # Tabs for different views
        tab1, tab2 = st.tabs(["Leaderboard", "Charts"])
        
        with tab1:
            # Data table
            st.dataframe(
                df,
                width='stretch',
                hide_index=True,
                column_config={
                    "Attendance %": st.column_config.ProgressColumn(
                        "Attendance %",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%"
                    )
                }
            )
        
        with tab2:
            if len(df) > 0:
                # Chart: Cancelled by teacher
                st.subheader("Cancelled by Teacher")
                chart_df = df.head(15)
                if anonymous:
                    chart_df = chart_df.copy()
                    chart_df['Teacher'] = [f"Teacher {i+1}" for i in range(len(chart_df))]
                st.bar_chart(chart_df.set_index("Teacher")["Cancelled"])
                
                # Chart: Cancelled by day
                day_stats = []
                for d in range(5):
                    day_cancelled = sum(s['by_day'][d]['absent'] for s in filtered_stats.values())
                    day_stats.append({
                        "Day": ["Mon", "Tue", "Wed", "Thu", "Fri"][d],
                        "Cancelled": day_cancelled
                    })
                day_df = pd.DataFrame(day_stats)
                st.subheader("Cancelled by Day")
                st.bar_chart(day_df.set_index("Day")["Cancelled"])

# Footer
st.markdown("---")
st.caption("**Disclaimer:** Educational use only. Not affiliated with Untis GmbH.")