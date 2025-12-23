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

# --- GOOGLE SERVICES HELPERS ---
@st.cache_resource
def get_gcp_creds():
    """Helper to get credentials for both Sheets and Drive."""
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
        spreadsheet = client.open('2025 Amhara Planting Survey')
        return spreadsheet.get_worksheet(0)
    except Exception as e:
        return None

def upload_audio_to_drive(file_buffer, filename):
    """Uploads file to Google Drive and returns a shareable URL."""
    try:
        creds = get_creds() # Using our cached credentials
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {'name': filename}
        media = MediaIoBaseUpload(file_buffer, mimetype='audio/mpeg', resumable=True)
        
        # 1. Upload the file
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')

        # 2. Set permission to 'anyone with link' (Viewer)
        drive_service.permissions().create(
            fileId=file_id, 
            body={'type': 'anyone', 'role': 'viewer'}
        ).execute()
        
        # 3. Generate Shareable URL
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.error(f"Cloud Upload Error: {e}")
        return None

# --- PAGE: HOME (DASHBOARD) ---
def home_page():
    st.title(f"🌾 2025 Amhara Planting Survey")
    st.info(f"Welcome back, **{st.session_state['username']}**")
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"):
            change_page("Registration")
        if st.button("📍 SETUP LOCATIONS", use_container_width=True):
            change_page("Locations")
    with col2:
        if st.button("💾 EXPORT & DOWNLOAD DATA", use_container_width=True):
            change_page("Download")
        if st.button("🛠️ EDIT/DELETE RECORDS", use_container_width=True):
            change_page("EditRecords")

# --- PAGE: REGISTRATION ---
def register_page():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.header("📝 Farmer Registration Form")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Select Woreda", [w.name for w in woredas] if woredas else ["Sync Woredas First"])
        
        kebeles = []
        if woredas and sel_woreda != "Sync Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles] if w_obj else []
        
        sel_kebele = st.selectbox("Select Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Upload Audio Recording", type=["mp3", "wav", "m4a"])
        
        if st.form_submit_button("Save Registration"):
            if not name or not kebeles:
                st.error("Error: Farmer name and locations are required.")
            else:
                final_audio_url = None
                
                # 1. Handle Audio Upload to Drive
                if audio_file:
                    with st.spinner("Uploading audio to Google Drive..."):
                        fname = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                        final_audio_url = upload_audio_to_drive(audio_file, fname)
                
                # 2. Save to Local Database
                new_entry = Farmer(
                    name=name, woreda=sel_woreda, kebele=sel_kebele,
                    phone=phone, audio_path=final_audio_url, # Now saving the URL
                    registered_by=st.session_state["username"]
                )
                db.add(new_entry)
                db.commit()

                # 3. Sync directly to Google Sheet
                sheet = initialize_gsheets()
                if sheet:
                    try:
                        sheet.append_row([
                            datetime.now().strftime("%Y-%m-%d %H:%M"),
                            name, sel_woreda, sel_kebele, phone, 
                            final_audio_url, st.session_state["username"]
                        ])
                        st.success("✅ Saved to Database and Google Sheet!")
                    except:
                        st.warning("⚠️ Saved to Database, but Google Sheet sync failed.")
                else:
                    st.success("✅ Saved locally (GSheet not connected).")
    db.close()

# --- OTHER PAGES (Location, Download, Edit) remain same as your previous version ---
# ... (rest of the code for locations, edit_records_page, download_page, and main)
