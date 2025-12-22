import streamlit as st
import pandas as pd
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- IMPORTS FROM EXTERNAL FILES ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
    from auth import register_user, login_user
except ImportError:
    st.error("Error: database.py, models.py, and auth.py must be in the same folder.")
    st.stop()

# --- CONFIGURATION ---
st.set_page_config(page_title="Staff & Farmer System", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
create_tables()

# --- GOOGLE SHEET SETTINGS ---
# Use the exact name of your Google Sheet file
SHEET_NAME = 'Bahir Dar staff lunch order' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        # Open the sheet and specifically the "Order 1" tab
        return client.open(SHEET_NAME).worksheet("Order 1")
    except Exception as e:
        st.error(f"GSheet Error: {e}")
        return None

# --- 1. LOGIN PAGE ---
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
                else: st.error("User exists.")

# --- 2. IMPORT FROM YOUR SHARED SHEET ---
def import_from_gsheet():
    st.title("📥 Sync Staff Data")
    st.info(f"Reading from: {SHEET_NAME} -> Order 1")
    sheet = initialize_gsheets()
    
    if st.button("Start Sync") and sheet:
        db = SessionLocal()
        try:
            data = sheet.get_all_records()
            count = 0
            for row in data:
                # We map 'Dep' from your sheet to 'Woreda' in our DB
                dep_name = str(row.get("Dep", "General")).strip()
                staff_name = str(row.get("Staff Name", "")).strip()
                
                if staff_name:
                    # 1. Ensure Department exists
                    woreda = db.query(Woreda).filter(Woreda.name == dep_name).first()
                    if not woreda:
                        woreda = Woreda(name=dep_name)
                        db.add(woreda)
                        db.flush()
                    
                    # 2. Add as Farmer/Staff if not exists
                    exists = db.query(Farmer).filter(Farmer.name == staff_name).first()
                    if not exists:
                        new_f = Farmer(
                            name=staff_name,
                            woreda=dep_name,
                            kebele="N/A",
                            phone="0000",
                            registered_by="GSheet Import"
                        )
                        db.add(new_f)
                        count += 1
            db.commit()
            st.success(f"Successfully imported {count} staff members!")
        except Exception as e:
            st.error(f"Sync error: {e}")
        finally:
            db.close()

# --- 3. REGISTRATION PAGE ---
def register_page():
    st.title("🌾 Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form"):
        name = st.text_input("Staff/Farmer Name")
        dep_choice = st.selectbox("Department (Woreda)", [w.name for w in woredas]) if woredas else st.warning("Import data first.")
        phone = st.text_input("Phone Number")
        file = st.file_uploader("Upload Audio/File")
        
        if st.form_submit_button("Register"):
            path = None
            if file:
                path = os.path.join(AUDIO_UPLOAD_DIR, file.name)
                with open(path, "wb") as f: f.write(file.getbuffer())
            
            new_farmer = Farmer(
                name=name, woreda=dep_choice, kebele="N/A",
                phone=phone, audio_path=path, registered_by=st.session_state["username"]
            )
            db.add(new_farmer)
            db.commit()
            st.success("Registration Complete!")

# --- 4. VIEW DATA ---
def view_page():
    st.title("📋 Database View")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{
            "Name": f.name, "Dept": f.woreda, "Phone": f.phone, "By": f.registered_by
        } for f in farmers])
        st.table(df)
    else:
        st.info("No records yet.")

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"User: {st.session_state['username']}")
        menu = {
            "🌾 Registration": register_page,
            "📥 Sync GSheet": import_from_gsheet,
            "📋 View Database": view_page
        }
        choice = st.sidebar.radio("Go to", list(menu.keys()))
        menu[choice]()
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
