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

# --- INITIALIZATION & ROBUST REPAIR ---
st.set_page_config(page_title="2025 Amhara Survey", layout="wide", page_icon="🌾")

# Ensure tables exist
create_tables()

def repair_database():
    """Ensures the schema is up to date without crashing."""
    db = SessionLocal()
    try:
        # Check if f_type exists by trying to select it
        db.execute(text("SELECT f_type FROM farmers LIMIT 1"))
    except Exception:
        db.rollback()
        try:
            # If selection fails, the column is missing -> Add it
            db.execute(text("ALTER TABLE farmers ADD COLUMN f_type TEXT"))
            db.commit()
            st.toast("Database schema updated!", icon="🛠️")
        except Exception as e:
            st.error(f"Migration failed: {e}")
    finally:
        db.close()

repair_database()

# Navigation State
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
    st.write(f"Welcome, **{st.session_state.get('user', 'Surveyor')}**")
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
        f_type = st.selectbox("Farmer Type", ["Smallholder", "Commercial", "Large Scale", "Subsistence"])
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Add Woredas First"])
        
        kebeles = []
        if woredas and sel_woreda != "Add Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj:
                kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio = st.file_uploader("🎤 Audio Note", type=['mp3', 'wav', 'm4a'])
        
        if st.form_submit_button("Save Record"):
            if not name or not kebeles or sel_kebele == "No Kebeles Found":
                st.error("Please fill in the name and ensure a Kebele is selected.")
            else:
                with st.spinner("Uploading to Google Drive..."):
                    url = upload_to_drive(audio, name) if audio else None
                
                new_entry = Farmer(
                    name=name, 
                    f_type=f_type, 
                    woreda=sel_woreda, 
                    kebele=sel_kebele, 
                    phone=phone, 
                    audio_url=url,
                    registered_by=st.session_state.get("user")
                )
                db.add(new_entry)
                try:
                    db.commit()
                    st.success(f"✅ Record for {name} saved!")
                except Exception as e:
                    db.rollback()
                    st.error(f"Database Error: {e}")
    db.close()

# --- PAGE: LOCATIONS ---
def location_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    st.header("📍 Manage Locations")
    
    with st.expander("➕ Add New Woreda"):
        nw = st.text_input("Woreda Name")
        if st.button("Save Woreda"):
            if nw: 
                db.add(Woreda(name=nw.strip()))
                db.commit()
                st.rerun()

    for w in db.query(Woreda).all():
        with st.expander(f"📌 {w.name}"):
            c1, c2 = st.columns([4, 1])
            if c2.button(f"🗑️ Woreda", key=f"dw{w.id}"):
                db.delete(w); db.commit(); st.rerun()
            
            for k in w.kebeles:
                colk1, colk2 = st.columns([5,1])
                colk1.text(f"• {k.name}")
                if colk2.button("🗑️", key=f"dk{k.id}"):
                    db.delete(k); db.commit(); st.rerun()
            
            nk = st.text_input("New Kebele Name", key=f"ik{w.id}")
            if st.button("Add Kebele", key=f"bk{w.id}"):
                if nk:
                    db.add(Kebele(name=nk.strip(), woreda_id=w.id))
                    db.commit(); st.rerun()
    db.close()

# --- PAGE: DATA & DOWNLOAD ---
def data_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📊 Data Management")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    
    if farmers:
        df = pd.DataFrame([{
            "ID": f.id, "Name": f.name, "Type": f.f_type, 
            "Woreda": f.woreda, "Kebele": f.kebele, 
            "Phone": f.phone, "Audio Link": f.audio_url
        } for f in farmers])

        # --- Search Bar ---
        search = st.text_input("🔍 Search by Name or Woreda", "").lower()
        if search:
            df = df[df['Name'].str.lower().contains(search) | df['Woreda'].str.lower().contains(search)]

        st.download_button("📥 Download Filtered CSV", df.to_csv(index=False).encode('utf-8'), "Survey_Data.csv", "text/csv")
        st.dataframe(df, use_container_width=True)

        st.subheader("🛠️ Edit/Delete Entries")
        for f in farmers:
            with st.expander(f"👤 {f.name} ({f.woreda})"):
                c1, c2 = st.columns(2)
                if c1.button(f"🗑️ Delete Record", key=f"df{f.id}"):
                    db.delete(f); db.commit(); st.rerun()
                if f.audio_url:
                    st.markdown(f"[🔗 Open Audio Recording]({f.audio_url})")
    else:
        st.info("No records found.")
    db.close()

# --- MAIN ---
def main():
    if "user" not in st.session_state:
        st.title("🚜 2025 Survey Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if u and p: # Use your auth.py login_user(u, p) here
                st.session_state["user"] = u
                st.rerun()
    else:
        st.sidebar.title(f"👤 {st.session_state['user']}")
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()
            
        p = st.session_state["page"]
        if p == "Home": home_page()
        elif p == "Reg": registration_page()
        elif p == "Loc": location_page()
        elif p == "Data": data_page()

if __name__ == "__main__": 
    main()
