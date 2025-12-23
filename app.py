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
st.set_page_config(page_title="Farmer Registration System", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
create_tables()

# --- GOOGLE SHEETS CONNECTION ---
SHEET_NAME = '2025 Amhara Planting Surivey ' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).worksheet("Order 1")
    except Exception as e:
        st.error(f"GSheet Connection Failed: {e}")
        return None

# --- PAGE: LOGIN ---
def login_page():
    st.title("👤 System Login")
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

# --- PAGE: MANAGE LOCATIONS (Woreda & Kebele) ---
def manage_locations():
    st.title("📍 Manage Woredas & Kebeles")
    db = SessionLocal()
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add Woreda")
        new_woreda = st.text_input("Woreda Name")
        if st.button("Save Woreda"):
            if new_woreda:
                w = Woreda(name=new_woreda)
                db.add(w)
                db.commit()
                st.success(f"Woreda '{new_woreda}' added!")
                st.rerun()

    with col2:
        st.subheader("Add Kebele")
        woredas = db.query(Woreda).all()
        target_woreda = st.selectbox("Select Woreda for Kebele", [w.name for w in woredas])
        new_kebele = st.text_input("Kebele Name")
        if st.button("Save Kebele"):
            w_obj = db.query(Woreda).filter(Woreda.name == target_woreda).first()
            if w_obj and new_kebele:
                k = Kebele(name=new_kebele, woreda_id=w_obj.id)
                db.add(k)
                db.commit()
                st.success(f"Kebele '{new_kebele}' added to {target_woreda}!")
    db.close()

# --- PAGE: SYNC FROM GSHEET ---
def sync_page():
    st.title("📥 Sync from Google Sheets")
    st.write(f"Connecting to: **{SHEET_NAME}**")
    sheet = initialize_gsheets()
    
    if st.button("Start Import"):
        if sheet:
            db = SessionLocal()
            data = sheet.get_all_records()
            for row in data:
                # We map 'Dep' to Woreda and 'Staff Name' to Farmer
                w_name = str(row.get("Dep", "General")).strip()
                if not db.query(Woreda).filter(Woreda.name == w_name).first():
                    db.add(Woreda(name=w_name))
            db.commit()
            st.success("Woredas/Departments Synced!")
            db.close()

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form"):
        name = st.text_input("Farmer/Staff Name")
        
        # Woreda Selection
        w_names = [w.name for w in woredas]
        sel_woreda = st.selectbox("Select Woreda", w_names if w_names else ["No Woredas Available"])
        
        # Kebele Selection (Filtered by Woreda)
        kebeles = []
        if woredas:
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj:
                kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Select Kebele", kebeles if kebeles else ["No Kebeles Available"])
        
        phone = st.text_input("Phone Number")
        file = st.file_uploader("Upload Audio Note")
        
        if st.form_submit_button("Register"):
            if not w_names or not kebeles:
                st.error("Please add Woredas and Kebeles first!")
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
                st.success(f"Registered {name} successfully!")
    db.close()

# --- MAIN APP LOGIC ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"Welcome, {st.session_state['username']}")
        menu = {
            "📝 Registration": register_page,
            "📍 Manage Locations": manage_locations,
            "📥 Sync GSheet": sync_page,
            "📋 View Records": lambda: st.table(pd.DataFrame([{"Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele} for f in SessionLocal().query(Farmer).all()]))
        }
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        if callable(menu[choice]): menu[choice]()
        
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
