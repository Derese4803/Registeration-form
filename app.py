import streamlit as st
import pandas as pd
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- EXTERNAL FILE IMPORTS ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
    from auth import register_user, login_user
except ImportError:
    st.error("Missing files! Ensure models.py, database.py, and auth.py are in the same folder.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🚜", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
create_tables()

# --- GOOGLE SHEETS CONNECTION ---
# Updated to your new survey name
SHEET_NAME = '2025 Amhara Planting Survey' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        # Assuming the data is in the first tab
        return client.open(SHEET_NAME).sheet1 
    except Exception as e:
        st.error(f"GSheet Connection Failed: {e}")
        return None

# --- PAGE: LOGIN ---
def login_page():
    st.title("👤 Survey System Login")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["Login", "Register"])
        with tab1:
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.button("Login"):
                if login_user(u, p):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = u
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        with tab2:
            ru = st.text_input("New Username")
            rp = st.text_input("New Password", type="password")
            if st.button("Register"):
                if register_user(ru, rp): st.success("Account created!")
                else: st.error("User already exists.")

# --- PAGE: SYNC FROM 2025 SURVEY ---
def sync_page():
    st.title("📥 Sync 2025 Survey Data")
    st.info(f"Connecting to: **{SHEET_NAME}**")
    sheet = initialize_gsheets()
    
    if st.button("Start Import"):
        if sheet:
            db = SessionLocal()
            try:
                data = sheet.get_all_records()
                for row in data:
                    # Logic to import Woredas from the "Woreda" column
                    w_name = str(row.get("Woreda", "General")).strip()
                    if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                        db.add(Woreda(name=w_name))
                db.commit()
                st.success("Woredas/Locations Synced from Survey Sheet!")
            except Exception as e:
                st.error(f"Error reading columns: {e}. Check if 'Woreda' column exists.")
            finally:
                db.close()

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 New Planting Entry")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form"):
        name = st.text_input("Farmer Name")
        
        w_names = [w.name for w in woredas]
        sel_woreda = st.selectbox("Woreda", w_names if w_names else ["Import Woredas First"])
        
        kebeles = []
        if woredas:
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj:
                kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["Add Kebele in Manage Locations"])
        
        phone = st.text_input("Phone Number")
        file = st.file_uploader("Upload Field Audio/Photo")
        
        if st.form_submit_button("Submit Survey"):
            if not w_names:
                st.error("No Woredas available.")
            else:
                path = None
                if file:
                    path = os.path.join(AUDIO_UPLOAD_DIR, file.name)
                    with open(path, "wb") as f: f.write(file.getbuffer())
                
                new_f = Farmer(
                    name=name, woreda=sel_woreda, kebele=sel_kebele,
                    phone=phone, audio_path=path, registered_by=st.session_state["username"]
                )
                db.add(new_f)
                db.commit()
                st.success(f"Survey for {name} saved!")
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"Surveyor: {st.session_state['username']}")
        menu = {
            "📝 New Survey Entry": register_page,
            "📥 Sync GSheet": sync_page,
            "📋 View All Records": lambda: st.table(pd.DataFrame([{"Farmer": f.name, "Woreda": f.woreda, "Kebele": f.kebele} for f in SessionLocal().query(Farmer).all()]))
        }
        choice = st.sidebar.radio("Menu", list(menu.keys()))
        if callable(menu[choice]): menu[choice]()
        
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
