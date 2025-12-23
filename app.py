import streamlit as st
import pandas as pd
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from sqlalchemy import text
import os

# --- SYSTEM IMPORTS ---
try:
    from database import SessionLocal, engine
    from models import Farmer, Woreda, Kebele, create_tables
except ImportError:
    st.error("⚠️ models.py or database.py missing!")
    st.stop()

# --- INITIALIZATION ---
st.set_page_config(page_title="2025 Amhara Survey", layout="wide")
create_tables()

# Auto-migrate database for new audio_url column
def migrate():
    db = SessionLocal()
    try:
        db.execute(text("ALTER TABLE farmers ADD COLUMN audio_url TEXT"))
        db.commit()
    except:
        db.rollback()
    db.close()

migrate()

# --- GOOGLE DRIVE UPLOAD LOGIC ---
def upload_audio_to_drive(file, farmer_name):
    """Uploads file to Drive and returns a public URL."""
    try:
        # Load credentials from Streamlit Secrets
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json(creds_info, ['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        
        file_name = f"Audio_{farmer_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3"
        media = MediaIoBaseUpload(file, mimetype='audio/mpeg', resumable=True)
        
        # Create file in Drive
        g_file = service.files().create(
            body={'name': file_name}, 
            media_body=media, 
            fields='id'
        ).execute()
        
        file_id = g_file.get('id')
        
        # Make file viewable by anyone with the link
        service.permissions().create(
            fileId=file_id, 
            body={'type': 'anyone', 'role': 'viewer'}
        ).execute()
        
        # Return the direct stream link
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.error(f"Cloud Upload Failed: {e}")
        return None

# --- NAVIGATION ---
if "page" not in st.session_state: st.session_state["page"] = "Home"
def nav(p):
    st.session_state["page"] = p
    st.rerun()

# --- PAGE: REGISTRATION (With Audio) ---
def registration_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📝 New Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        f_type = st.selectbox("Type", ["Smallholder", "Commercial", "Large Scale"])
        w_name = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["No Woredas"])
        
        # Audio Input
        st.write("🎤 **Record or Upload Audio Note**")
        audio_file = st.file_uploader("Upload .mp3 or .wav", type=['mp3', 'wav', 'm4a'])
        
        if st.form_submit_button("Submit Survey"):
            if name and audio_file:
                with st.spinner("Uploading audio to Cloud..."):
                    audio_url = upload_audio_to_drive(audio_file, name)
                
                new_farmer = Farmer(
                    name=name, 
                    f_type=f_type, 
                    woreda=w_name, 
                    audio_url=audio_url
                )
                db.add(new_farmer)
                db.commit()
                st.success("✅ Registration and Audio Saved!")
            else:
                st.warning("Name and Audio are required.")
    db.close()

# --- PAGE: DATA MANAGEMENT (With Audio Player) ---
def data_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📊 Survey Records")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    
    if farmers:
        for f in farmers:
            with st.expander(f"👤 {f.name} ({f.woreda})"):
                st.write(f"Type: {f.f_type}")
                if f.audio_url:
                    st.audio(f.audio_url) # Plays directly in app
                    st.markdown(f"[🔗 Direct Link]({f.audio_url})")
                else:
                    st.info("No audio recorded.")
                
                if st.button(f"🗑️ Delete Record {f.id}", key=f"del{f.id}"):
                    db.delete(f); db.commit(); st.rerun()
    db.close()

# --- MAIN ROUTING ---
def main():
    if "user" not in st.session_state:
        st.title("🚜 2025 Amhara Survey")
        if st.button("Start Session"):
            st.session_state["user"] = "Surveyor_1"
            st.rerun()
    else:
        p = st.session_state["page"]
        if p == "Home":
            st.title("Dashboard")
            if st.button("📝 NEW REGISTRATION"): nav("Reg")
            if st.button("📊 VIEW DATA"): nav("Data")
        elif p == "Reg": registration_page()
        elif p == "Data": data_page()

if __name__ == "__main__": main()
