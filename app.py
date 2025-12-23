import streamlit as st
import pandas as pd
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from sqlalchemy import text
import os

# --- 1. DATABASE PATH FIX ---
# This ensures Streamlit has write permissions for the database file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'survey.db')

try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
except ImportError:
    st.error("⚠️ models.py or database.py missing in your repository!")
    st.stop()

# --- 2. INITIALIZATION & MIGRATION ---
st.set_page_config(page_title="2025 Amhara Survey", layout="wide", page_icon="🌾")

# Create tables if they don't exist
try:
    create_tables()
except Exception as e:
    st.error(f"Database Initialization Error: {e}")

def run_migrations():
    """Adds new columns to an existing database to prevent OperationalErrors."""
    db = SessionLocal()
    # List of columns we've added over time
    migrations = [
        "ALTER TABLE farmers ADD COLUMN f_type TEXT",
        "ALTER TABLE farmers ADD COLUMN audio_url TEXT",
        "ALTER TABLE farmers ADD COLUMN phone TEXT",
        "ALTER TABLE farmers ADD COLUMN registered_by TEXT"
    ]
    for sql in migrations:
        try:
            db.execute(text(sql))
            db.commit()
        except Exception:
            db.rollback() # Column likely already exists
    db.close()

run_migrations()

# --- 3. GOOGLE DRIVE UPLOAD ---
def upload_to_drive(file, farmer_name):
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json(creds_info, ['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        
        file_name = f"Audio_{farmer_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3"
        media = MediaIoBaseUpload(file, mimetype='audio/mpeg', resumable=True)
        
        g_file = service.files().create(
            body={'name': file_name}, 
            media_body=media, 
            fields='id'
        ).execute()
        
        fid = g_file.get('id')
        # Set permission so links work in the CSV export
        service.permissions().create(fileId=fid, body={'type': 'anyone', 'role': 'viewer'}).execute()
        return f"https://drive.google.com/uc?id={fid}"
    except Exception as e:
        st.error(f"Cloud Upload Failed: {e}")
        return None

# --- 4. NAVIGATION LOGIC ---
if "page" not in st.session_state: st.session_state["page"] = "Home"

def nav(p):
    st.session_state["page"] = p
    st.rerun()

# --- 5. PAGE: HOME ---
def home_page():
    st.title("🌾 2025 Amhara Planting Survey")
    st.subheader(f"User: {st.session_state.get('user', 'Surveyor')}")
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"): nav("Reg")
    with col2:
        if st.button("📍 MANAGE LOCATIONS", use_container_width=True): nav("Loc")
    with col3:
        if st.button("📊 DATA & DOWNLOAD", use_container_width=True): nav("Data")

# --- 6. PAGE: REGISTRATION ---
def registration_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        f_type = st.selectbox("Farmer Type", ["Smallholder", "Commercial", "Large Scale", "Subsistence"])
        
        w_list = [w.name for w in woredas] if woredas else ["Add Woredas First"]
        sel_woreda = st.selectbox("Woreda", w_list)
        
        kebeles = []
        if woredas and sel_woreda != "Add Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio = st.file_uploader("🎤 Audio Note", type=['mp3', 'wav', 'm4a'])
        
        if st.form_submit_button("Save Registration"):
            if not name or not kebeles:
                st.error("Missing Name or Location!")
            else:
                with st.spinner("Uploading audio..."):
                    url = upload_to_drive(audio, name) if audio else None
                
                new_farmer = Farmer(
                    name=name, f_type=f_type, woreda=sel_woreda, 
                    kebele=sel_kebele, phone=phone, audio_url=url,
                    registered_by=st.session_state.get('user')
                )
                db.add(new_farmer)
                db.commit()
                st.success(f"✅ Saved record for {name}")
    db.close()

# --- 7. PAGE: LOCATIONS ---
def location_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    st.header("📍 Location Management")
    
    with st.expander("➕ Add Woreda"):
        nw = st.text_input("Woreda Name")
        if st.button("Save Woreda"):
            if nw: db.add(Woreda(name=nw)); db.commit(); st.rerun()

    for w in db.query(Woreda).all():
        with st.expander(f"📌 {w.name}"):
            c1, c2 = st.columns([4, 1])
            if c2.button(f"🗑️ Woreda", key=f"dw{w.id}"):
                db.delete(w); db.commit(); st.rerun()
            
            for k in w.kebeles:
                col1, col2 = st.columns([5, 1])
                col1.text(f"• {k.name}")
                if col2.button("🗑️", key=f"dk{k.id}"):
                    db.delete(k); db.commit(); st.rerun()
            
            nk = st.text_input("New Kebele", key=f"ik{w.id}")
            if st.button("Add Kebele", key=f"bk{w.id}"):
                db.add(Kebele(name=nk, woreda_id=w.id)); db.commit(); st.rerun()
    db.close()

# --- 8. PAGE: DATA & DOWNLOAD ---
def data_page():
    if st.button("⬅️ Home"): nav("Home")
    st.header("📊 Survey Records")
    db = SessionLocal()
    
    try:
        farmers = db.query(Farmer).all()
        if farmers:
            # 1. Create DataFrame
            data_dict = [{
                "Name": f.name, "Type": f.f_type, "Woreda": f.woreda,
                "Kebele": f.kebele, "Phone": f.phone, "Audio Link": f.audio_url
            } for f in farmers]
            df = pd.DataFrame(data_dict)
            
            # 2. Download Button
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Data as CSV",
                data=csv,
                file_name=f"Amhara_Survey_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
            
            st.divider()
            
            # 3. Display Data
            st.dataframe(df, use_container_width=True)
            
            # 4. Individual Actions
            for f in farmers:
                with st.expander(f"👤 {f.name} ({f.woreda})"):
                    if st.button(f"🗑️ Delete {f.id}", key=f"df{f.id}"):
                        db.delete(f); db.commit(); st.rerun()
        else:
            st.info("No records found.")
    except Exception as e:
        st.error(f"Error loading data: {e}")
    finally:
        db.close()

# --- 9. MAIN AUTH & ROUTING ---
def main():
    if "user" not in st.session_state:
        st.title("🚜 Survey Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Enter System"):
            if u and p: # Simplified Auth
                st.session_state["user"] = u
                st.rerun()
    else:
        st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
        pg = st.session_state["page"]
        if pg == "Home": home_page()
        elif pg == "Reg": registration_page()
        elif pg == "Loc": location_page()
        elif pg == "Data": data_page()

if __name__ == "__main__":
    main()
