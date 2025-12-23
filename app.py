import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- EXTERNAL FILE IMPORTS ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
    from auth import register_user, login_user
except ImportError:
    st.error("⚠️ System Files Missing! Ensure models.py, database.py, and auth.py are in your repo.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
create_tables()

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Home"

def change_page(page_name):
    st.session_state["current_page"] = page_name
    st.rerun()

# --- GOOGLE DRIVE & SHEETS HELPERS ---
@st.cache_resource
def get_gcp_creds():
    service_account_info = st.secrets["gcp_service_account"]
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    return ServiceAccountCredentials.from_json(service_account_info, scope)

def initialize_gsheets():
    try:
        creds = get_gcp_creds()
        client = gspread.authorize(creds)
        return client.open('2025 Amhara Planting Survey').get_worksheet(0)
    except:
        return None

def upload_audio_to_drive(file_buffer, filename):
    try:
        creds = get_gcp_creds()
        drive_service = build('drive', 'v3', credentials=creds)
        file_metadata = {'name': filename}
        media = MediaIoBaseUpload(file_buffer, mimetype='audio/mpeg', resumable=True)
        
        # Upload
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')

        # Make Public Link
        drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'viewer'}).execute()
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.error(f"Cloud Upload Failed: {e}")
        return None

# --- PAGE: HOME ---
def home_page():
    st.title(f"🌾 2025 Amhara Survey Dashboard")
    st.write(f"Logged in: **{st.session_state['username']}**")
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"):
            change_page("Registration")
        if st.button("📍 SETUP LOCATIONS", use_container_width=True):
            change_page("Locations")
    with col2:
        if st.button("💾 EXPORT DATA & LINKS", use_container_width=True):
            change_page("Download")
        if st.button("🛠️ EDIT RECORDS", use_container_width=True):
            change_page("EditRecords")

# --- PAGE: REGISTRATION ---
def register_page():
    if st.button("⬅️ Back"): change_page("Home")
    st.header("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Sync Data First"])
        
        kebeles = []
        if woredas and sel_woreda != "Sync Data First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles] if w_obj else []
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Audio Note", type=["mp3", "wav", "m4a"])
        
        if st.form_submit_button("Submit Survey"):
            if not name or not kebeles:
                st.error("Fields required!")
            else:
                final_url = None
                if audio_file:
                    with st.spinner("Uploading audio to Google Drive..."):
                        fname = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                        final_url = upload_audio_to_drive(audio_file, fname)
                
                db.add(Farmer(name=name, woreda=sel_woreda, kebele=sel_kebele, phone=phone, audio_url=final_url, registered_by=st.session_state["username"]))
                db.commit()
                st.success(f"✅ Saved! Audio Link created.")
    db.close()

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    if st.button("⬅️ Back"): change_page("Home")
    st.header("📍 Location Setup")
    db = SessionLocal()
    
    t1, t2 = st.tabs(["📥 Import", "✏️ Edit"])
    with t1:
        if st.button("🔄 Sync from GSheet"):
            sheet = initialize_gsheets()
            if sheet:
                for r in sheet.get_all_records():
                    w_name = str(r.get("Woreda", "")).strip()
                    if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                        db.add(Woreda(name=w_name))
                db.commit(); st.success("Synced!")
        
        st.divider()
        uploaded = st.file_uploader("Upload CSV Template", type="csv")
        if uploaded:
            df = pd.read_csv(uploaded)
            for _, r in df.iterrows():
                w_n, k_n = str(r['Woreda']).strip(), str(r['Kebele']).strip()
                w_obj = db.query(Woreda).filter(Woreda.name == w_n).first()
                if not w_obj:
                    w_obj = Woreda(name=w_n); db.add(w_obj); db.commit()
                if not db.query(Kebele).filter(Kebele.name == k_n, Kebele.woreda_id == w_obj.id).first():
                    db.add(Kebele(name=k_n, woreda_id=w_obj.id))
            db.commit(); st.success("Imported!")
    
    with t2:
        for w in db.query(Woreda).all():
            with st.expander(f"📌 {w.name}"):
                for k in w.kebeles:
                    col1, col2 = st.columns([4, 1])
                    col1.text(k.name)
                    if col2.button("🗑️", key=f"dk{k.id}"):
                        db.delete(k); db.commit(); st.rerun()
                if st.button(f"Delete Woreda {w.name}", key=f"dw{w.id}"):
                    db.delete(w); db.commit(); st.rerun()
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    if st.button("⬅️ Back"): change_page("Home")
    st.header("💾 Export Survey Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        data = []
        for f in farmers:
            data.append({
                "Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, 
                "Phone": f.phone, "Audio Link": f.audio_url, "Surveyor": f.registered_by
            })
        df = pd.DataFrame(data)
        st.dataframe(df)
        st.download_button("📥 Download Excel/CSV", df.to_csv(index=False).encode('utf-8'), "Amhara_Survey_2025.csv")
    db.close()

# --- PAGE: EDIT RECORDS ---
def edit_records_page():
    if st.button("⬅️ Back"): change_page("Home")
    st.header("🛠️ Edit Records")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    for f in farmers:
        with st.expander(f"👤 {f.name} - {f.woreda}"):
            new_n = st.text_input("Name", f.name, key=f"n{f.id}")
            if st.button("Save", key=f"s{f.id}"):
                f.name = new_n; db.commit(); st.rerun()
            if st.button("Delete Entry", key=f"d{f.id}"):
                db.delete(f); db.commit(); st.rerun()
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        st.title("🚜 2025 Amhara Survey Login")
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state.update({"logged_in": True, "username": u})
                st.rerun()
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
