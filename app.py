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

# This creates tables if they don't exist
create_tables()

def force_migrate():
    """Manually add all possible missing columns."""
    db = SessionLocal()
    columns = ["f_type", "registered_by", "audio_url"]
    for col in columns:
        try:
            db.execute(text(f"ALTER TABLE farmers ADD COLUMN {col} TEXT"))
            db.commit()
        except Exception:
            db.rollback()
    db.close()

# Run migration attempt on every load
force_migrate()

# --- SIDEBAR TOOLS ---
with st.sidebar:
    st.title("⚙️ Admin Tools")
    if st.button("🚨 Emergency Fix Database"):
        if os.path.exists("survey.db"):
            os.remove("survey.db")
            st.success("Old database deleted! Re-running...")
            create_tables()
            st.rerun()

# --- NAVIGATION ---
if "page" not in st.session_state: st.session_state["page"] = "Home"
def nav(p):
    st.session_state["page"] = p
    st.rerun()

# --- GOOGLE DRIVE UPLOAD ---
def upload_to_drive(file, farmer_name):
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json(creds_info, ['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        file_name = f"{farmer_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3"
        media = MediaIoBaseUpload(file, mimetype='audio/mpeg', resumable=True)
        g_file = service.files().create(body={'name': file_name}, media_body=media, fields='id').execute()
        fid = g_file.get('id')
        service.permissions().create(fileId=fid, body={'type': 'anyone', 'role': 'viewer'}).execute()
        return f"https://drive.google.com/uc?id={fid}"
    except Exception as e:
        st.error(f"Upload Error: {e}")
        return None

# --- PAGE: HOME ---
def home_page():
    st.title("🌾 2025 Amhara Survey Dashboard")
    st.divider()
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"): nav("Reg")
    with c2:
        if st.button("📍 MANAGE LOCATIONS", use_container_width=True): nav("Loc")
    with c3:
        if st.button("📊 DATA & DOWNLOAD", use_container_width=True): nav("Data")

# --- PAGE: REGISTRATION ---
def registration_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    with st.form("reg_form"):
        name = st.text_input("Farmer Full Name")
        f_type = st.selectbox("Type", ["Smallholder", "Commercial", "Large Scale", "Subsistence"])
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Add Woredas First"])
        
        kebeles = []
        if woredas and sel_woreda != "Add Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj: kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio = st.file_uploader("🎤 Audio Note", type=['mp3', 'wav'])
        if st.form_submit_button("Save Record"):
            url = upload_to_drive(audio, name) if audio else None
            db.add(Farmer(name=name, f_type=f_type, woreda=sel_woreda, kebele=sel_kebele, phone=phone, audio_url=url, registered_by=st.session_state.get('user')))
            db.commit(); st.success("✅ Saved!")
    db.close()

# --- PAGE: LOCATIONS ---
def location_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    st.header("📍 Manage Locations")
    nw = st.text_input("New Woreda")
    if st.button("Add"):
        if nw: db.add(Woreda(name=nw)); db.commit(); st.rerun()
    for w in db.query(Woreda).all():
        with st.expander(f"📌 {w.name}"):
            if st.button(f"Delete Woreda {w.id}", key=f"dw{w.id}"):
                db.delete(w); db.commit(); st.rerun()
            nk = st.text_input("New Kebele", key=f"ik{w.id}")
            if st.button("Add Kebele", key=f"bk{w.id}"):
                db.add(Kebele(name=nk, woreda_id=w.id)); db.commit(); st.rerun()
    db.close()

# --- PAGE: DATA & DOWNLOAD ---
def data_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📊 Survey Data")
    db = SessionLocal()
    try:
        farmers = db.query(Farmer).all()
        if farmers:
            df = pd.DataFrame([{
                "Name": f.name, "Type": f.f_type, "Woreda": f.woreda, 
                "Kebele": f.kebele, "Phone": f.phone, "Audio": f.audio_url
            } for f in farmers])
            st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "Survey_Data.csv")
            st.dataframe(df)
            for f in farmers:
                with st.expander(f"Delete {f.name}"):
                    if st.button(f"Confirm Delete {f.id}", key=f"df{f.id}"):
                        db.delete(f); db.commit(); st.rerun()
        else: st.info("No records.")
    except Exception as e:
        st.error(f"Database Error: {e}")
        st.warning("Try clicking 'Emergency Fix Database' in the sidebar.")
    finally:
        db.close()

# --- MAIN ---
def main():
    if "user" not in st.session_state:
        st.title("🚜 Login")
        u = st.text_input("User")
        p = st.text_input("Pass", type="password")
        if st.button("Enter"):
            st.session_state["user"] = u
            st.rerun()
    else:
        p = st.session_state["page"]
        if p == "Home": home_page()
        elif p == "Reg": registration_page()
        elif p == "Loc": location_page()
        elif p == "Data": data_page()

if __name__ == "__main__": main()
