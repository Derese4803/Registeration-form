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
    st.error("⚠️ Database files missing! Ensure models.py, database.py, and auth.py are in your GitHub.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
create_tables()

# Navigation State
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Home"

def change_page(page_name):
    st.session_state["current_page"] = page_name
    st.rerun()

# --- GOOGLE API HELPERS ---
@st.cache_resource
def get_gcp_credentials():
    """Returns credentials for both Sheets and Drive."""
    service_account_info = st.secrets["gcp_service_account"]
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    return ServiceAccountCredentials.from_json(service_account_info, scope)

def upload_to_drive(file_buffer, filename):
    """Uploads file to Google Drive and returns a shareable URL."""
    try:
        creds = get_gcp_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {'name': filename}
        media = MediaIoBaseUpload(file_buffer, mimetype='audio/mpeg', resumable=True)
        
        # Upload
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = file.get('id')

        # Make Publicly Viewable (Anyone with the link)
        drive_service.permissions().create(
            fileId=file_id, 
            body={'type': 'anyone', 'role': 'viewer'}
        ).execute()
        
        # Create direct link
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.error(f"Cloud Upload Error: {e}")
        return None

def initialize_gsheets():
    try:
        creds = get_gcp_credentials()
        client = gspread.authorize(creds)
        spreadsheet = client.open('2025 Amhara Planting Survey')
        return spreadsheet.get_worksheet(0)
    except Exception as e:
        return None

# --- PAGE: HOME ---
def home_page():
    st.title(f"🌾 2025 Amhara Survey Dashboard")
    st.info(f"Logged in as: **{st.session_state['username']}**")
    st.divider()
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 START REGISTRATION", use_container_width=True, type="primary"): change_page("Registration")
        if st.button("📍 MANAGE LOCATIONS", use_container_width=True): change_page("Locations")
    with col2:
        if st.button("💾 DOWNLOAD DATA", use_container_width=True): change_page("Download")
        if st.button("🛠️ EDIT/DELETE RECORDS", use_container_width=True): change_page("EditRecords")

# --- PAGE: REGISTRATION ---
def register_page():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("📝 New Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        f_type = st.selectbox("Farmer Type", ["Smallholder", "Commercial", "Large Scale", "Subsistence"])
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
                final_url = None
                if audio_file:
                    with st.spinner("Uploading audio to Cloud..."):
                        filename = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
                        final_url = upload_to_drive(audio_file, filename)
                
                # Save to Local Database
                new_farmer = Farmer(
                    name=name, woreda=sel_woreda, kebele=sel_kebele, 
                    phone=phone, audio_path=final_url, # Storing the URL
                    registered_by=st.session_state["username"]
                )
                db.add(new_farmer)
                db.commit()

                # Save to Google Sheet
                sheet = initialize_gsheets()
                if sheet:
                    try:
                        sheet.append_row([
                            datetime.now().strftime("%Y-%m-%d %H:%M"),
                            name, f_type, sel_woreda, sel_kebele, phone, final_url, st.session_state["username"]
                        ])
                        st.success("✅ Saved to Database and Google Sheet!")
                    except:
                        st.warning("⚠️ Saved locally, but Google Sheet sync failed.")
                else:
                    st.success("✅ Saved to Local Database!")
    db.close()

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("📍 Location Management")
    db = SessionLocal()
    
    t1, t2 = st.tabs(["📥 Add / Sync", "✏️ Edit / Delete"])
    
    with t1:
        new_w = st.text_input("Add New Woreda")
        if st.button("Save Woreda"):
            if new_w and not db.query(Woreda).filter(Woreda.name == new_w).first():
                db.add(Woreda(name=new_w)); db.commit(); st.rerun()
        
        st.divider()
        if st.button("🔄 Sync Woredas from GSheet"):
            sheet = initialize_gsheets()
            if sheet:
                records = sheet.get_all_records()
                for r in records:
                    w_name = str(r.get("Woreda", "")).strip()
                    if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                        db.add(Woreda(name=w_name))
                db.commit(); st.success("Synced!")

    with t2:
        for w in db.query(Woreda).all():
            with st.expander(f"📌 {w.name}"):
                c1, c2 = st.columns([4, 1])
                if c2.button("🗑️ Woreda", key=f"dw{w.id}"):
                    db.delete(w); db.commit(); st.rerun()
                
                for k in w.kebeles:
                    kc1, kc2 = st.columns([4, 1])
                    kc1.text(f"• {k.name}")
                    if kc2.button("🗑️", key=f"dk{k.id}"):
                        db.delete(k); db.commit(); st.rerun()
                
                nk = st.text_input(f"New Kebele for {w.name}", key=f"ink{w.id}")
                if st.button(f"Add Kebele", key=f"bnk{w.id}"):
                    db.add(Kebele(name=nk, woreda_id=w.id)); db.commit(); st.rerun()
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("💾 Data Export")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{
            "Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, 
            "Phone": f.phone, "Audio Link": f.audio_path, "Surveyor": f.registered_by
        } for f in farmers])
        st.dataframe(df)
        st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "survey_export.csv")
    db.close()

# --- PAGE: EDIT RECORDS ---
def edit_records_page():
    if st.button("⬅️ Back to Dashboard"): change_page("Home")
    st.header("🛠️ Edit Records")
    db = SessionLocal()
    for f in db.query(Farmer).all():
        with st.expander(f"👤 {f.name}"):
            if st.button("🗑️ Delete Record", key=f"df{f.id}"):
                db.delete(f); db.commit(); st.rerun()
    db.close()

# --- MAIN ---
def main():
    if "logged_in" not in st.session_state:
        st.title("🚜 2025 Survey Login")
        u, p = st.text_input("User"), st.text_input("Pass", type="password")
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
    
