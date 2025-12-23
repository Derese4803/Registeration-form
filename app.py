import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- EXTERNAL FILE IMPORTS ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
    from auth import register_user, login_user
except ImportError:
    st.error("⚠️ Database files missing! Ensure models.py, database.py, and auth.py are in your GitHub.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
create_tables()

# Navigation State
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Home"

def change_page(page_name):
    st.session_state["current_page"] = page_name
    st.rerun()

# Configuration
SHEET_NAME = '2025 Amhara Planting Survey' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        return spreadsheet.get_worksheet(0)
    except Exception as e:
        return None

# --- PAGE: HOME (GRID DASHBOARD) ---
def home_page():
    st.title(f"🌾 2025 Amhara Survey Dashboard")
    st.write(f"Logged in as: **{st.session_state['username']}**")
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 START REGISTRATION", use_container_width=True, type="primary"):
            change_page("Registration")
        if st.button("📍 MANAGE LOCATIONS", use_container_width=True):
            change_page("Locations")
    with col2:
        if st.button("💾 DOWNLOAD DATA", use_container_width=True):
            change_page("Download")
        if st.button("🛠️ EDIT/DELETE RECORDS", use_container_width=True):
            change_page("EditRecords")

# --- PAGE: REGISTRATION ---
def register_page():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("📝 New Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Sync Locations First"])
        
        kebeles = []
        if woredas and sel_woreda != "Sync Locations First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles] if w_obj else []
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Audio Note", type=["mp3", "wav"])
        
        if st.form_submit_button("Submit Survey"):
            if not name or not kebeles:
                st.error("Missing required fields!")
            else:
                path = None
                if audio_file:
                    path = os.path.join(AUDIO_UPLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}")
                    with open(path, "wb") as f: f.write(audio_file.getbuffer())
                db.add(Farmer(name=name, woreda=sel_woreda, kebele=sel_kebele, phone=phone, audio_path=path, registered_by=st.session_state["username"]))
                db.commit()
                st.success("✅ Saved successfully!")
    db.close()

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("📍 Woreda & Kebele Management")
    db = SessionLocal()
    
    t1, t2 = st.tabs(["📥 Sync & Bulk Upload", "✏️ Edit/Delete Locations"])
    
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("GSheet Sync")
            if st.button("🔄 Pull from Google Sheets"):
                sheet = initialize_gsheets()
                if sheet:
                    records = sheet.get_all_records()
                    for r in records:
                        w_name = str(r.get("Woreda", r.get("Dep", ""))).strip()
                        if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                            db.add(Woreda(name=w_name))
                    db.commit(); st.success("Synced!")
                else: st.error("Connection failed.")
        with c2:
            st.subheader("Excel Template")
            template_csv = pd.DataFrame({"Woreda": ["Mecha"], "Kebele": ["Kebele 01"]}).to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Template", template_csv, "template.csv")
            uploaded = st.file_uploader("Upload CSV", type="csv")
            if uploaded:
                df = pd.read_csv(uploaded)
                for _, r in df.iterrows():
                    w_obj = db.query(Woreda).filter(Woreda.name == str(r['Woreda']).strip()).first()
                    if not w_obj:
                        w_obj = Woreda(name=str(r['Woreda']).strip())
                        db.add(w_obj); db.commit()
                    if not db.query(Kebele).filter(Kebele.name == str(r['Kebele']).strip(), Kebele.woreda_id == w_obj.id).first():
                        db.add(Kebele(name=str(r['Kebele']).strip(), woreda_id=w_obj.id))
                db.commit(); st.success("Data Imported!")

    with t2:
        woredas = db.query(Woreda).all()
        for w in woredas:
            with st.expander(f"📌 {w.name}"):
                new_w = st.text_input("Edit Woreda Name", w.name, key=f"w{w.id}")
                if st.button("Update Woreda", key=f"bw{w.id}"):
                    w.name = new_w; db.commit(); st.rerun()
                for k in w.kebeles:
                    colk1, colk2 = st.columns([3, 1])
                    new_k = colk1.text_input("Edit Kebele", k.name, key=f"k{k.id}")
                    if colk2.button("🗑️", key=f"dk{k.id}"):
                        db.delete(k); db.commit(); st.rerun()
                if st.button(f"❌ Delete {w.name}", key=f"dw{w.id}"):
                    db.delete(w); db.commit(); st.rerun()
    db.close()

# --- PAGE: EDIT RECORDS ---
def edit_records_page():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("🛠️ Edit Farmer Records")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    for f in farmers:
        with st.expander(f"👤 {f.name} ({f.woreda})"):
            ename = st.text_input("Name", f.name, key=f"fn{f.id}")
            ephone = st.text_input("Phone", f.phone, key=f"fp{f.id}")
            if st.button("💾 Save Changes", key=f"fs{f.id}"):
                f.name, f.phone = ename, ephone
                db.commit(); st.success("Updated!"); st.rerun()
            if st.button("🗑️ Delete Farmer", key=f"fdel{f.id}"):
                db.delete(f); db.commit(); st.rerun()
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("💾 Download Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{
            "Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, 
            "Phone": f.phone, "Surveyor": f.registered_by
        } for f in farmers])
        st.dataframe(df)
        st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "survey_data.csv")
    else: st.warning("No data found.")
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        st.title("🚜 2025 Amhara Survey Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state["logged_in"] = True
                st.session_state["username"] = u
                st.rerun()
            else: st.error("Access Denied")
    else:
        st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
        
        page = st.session_state["current_page"]
        if page == "Home": home_page()
        elif page == "Registration": register_page()
        elif page == "Locations": manage_locations()
        elif page == "Download": download_page()
        elif page == "EditRecords": edit_records_page()

if __name__ == "__main__":
    main()
