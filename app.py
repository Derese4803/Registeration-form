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
    st.error("⚠️ Missing database files! Ensure models.py, database.py, and auth.py are in GitHub.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
if not os.path.exists(AUDIO_UPLOAD_DIR):
    os.makedirs(AUDIO_UPLOAD_DIR)

create_tables()

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
        st.error(f"❌ GSheet Connection Failed: {e}")
        return None

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    st.title("📍 Manage Woredas & Kebeles")
    db = SessionLocal()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Add New Woreda")
        new_woreda_name = st.text_input("Woreda Name (e.g., Mecha)")
        if st.button("Save Woreda"):
            if new_woreda_name:
                if not db.query(Woreda).filter(Woreda.name == new_woreda_name).first():
                    db.add(Woreda(name=new_woreda_name))
                    db.commit()
                    st.success(f"Woreda '{new_woreda_name}' added!")
                    st.rerun()
                else:
                    st.warning("This Woreda already exists.")

    with col2:
        st.subheader("Add New Kebele")
        woredas = db.query(Woreda).all()
        if woredas:
            target_woreda = st.selectbox("Select Woreda for this Kebele", [w.name for w in woredas])
            new_kebele_name = st.text_input("Kebele Name")
            if st.button("Save Kebele"):
                w_obj = db.query(Woreda).filter(Woreda.name == target_woreda).first()
                if w_obj and new_kebele_name:
                    db.add(Kebele(name=new_kebele_name, woreda_id=w_obj.id))
                    db.commit()
                    st.success(f"Kebele '{new_kebele_name}' added to {target_woreda}!")
        else:
            st.info("Add a Woreda first before adding Kebeles.")
    
    st.divider()
    st.subheader("Current Locations Hierarchy")
    for w in woredas:
        with st.expander(f"📌 {w.name}"):
            for k in w.kebeles:
                st.write(f"  - {k.name}")
    
    db.close()

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        
        # Select Woreda
        w_names = [w.name for w in woredas]
        sel_woreda = st.selectbox("Woreda", w_names if w_names else ["Add Locations First"])
        
        # Dynamic Kebele Selection
        kebeles = []
        if woredas and sel_woreda != "Add Locations First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj:
                kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        
        audio_file = st.file_uploader("🎤 Upload Audio Note", type=["mp3", "wav", "m4a"])
        phone = st.text_input("Phone Number")
        
        if st.form_submit_button("Submit Survey"):
            if not name or not kebeles:
                st.error("Please ensure Farmer Name and Kebele are provided.")
            else:
                audio_path = None
                if audio_file:
                    audio_path = os.path.join(AUDIO_UPLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}")
                    with open(audio_path, "wb") as f:
                        f.write(audio_file.getbuffer())
                
                new_f = Farmer(
                    name=name, woreda=sel_woreda, kebele=sel_kebele,
                    phone=phone, audio_path=audio_path,
                    registered_by=st.session_state["username"]
                )
                db.add(new_f)
                db.commit()
                st.success(f"Registered {name} in {sel_kebele}!")
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    st.title("💾 Download Survey Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{
            "Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, 
            "Phone": f.phone, "Surveyor": f.registered_by
        } for f in farmers])
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", data=csv, file_name="Amhara_Survey.csv", mime="text/csv")
    db.close()

# --- MAIN APP ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        # Logic for login_page() goes here (as defined in previous messages)
        pass 
    else:
        st.sidebar.title(f"User: {st.session_state['username']}")
        menu = {
            "📝 Registration": register_page,
            "📍 Manage Locations": manage_locations,
            "💾 Download Data": download_page
        }
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        menu[choice]()
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
