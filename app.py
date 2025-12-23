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
    st.error("⚠️ Database files missing! Ensure models.py, database.py, and auth.py are in your GitHub repo.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")

# Setup directory for Audio recordings
AUDIO_UPLOAD_DIR = "uploads"
if not os.path.exists(AUDIO_UPLOAD_DIR):
    os.makedirs(AUDIO_UPLOAD_DIR)

# Initialize SQL Database
create_tables()

# Configuration
SHEET_NAME = '2025 Amhara Planting Survey' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        # Try to open "Order 1" tab; fallback to first sheet
        try:
            return spreadsheet.worksheet("Order 1")
        except:
            return spreadsheet.get_worksheet(0)
    except Exception as e:
        st.error(f"❌ GSheet Connection Failed: {e}")
        return None

# --- PAGE: LOGIN/REGISTER ---
def login_page():
    st.title("🚜 2025 Amhara Planting Survey Login")
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

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    st.title("📍 Location Setup (Woreda & Kebele)")
    db = SessionLocal()
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Add Woreda")
        new_woreda = st.text_input("Enter Woreda Name")
        if st.button("Save Woreda"):
            if new_woreda:
                db.add(Woreda(name=new_woreda))
                db.commit()
                st.success(f"Added {new_woreda}")
                st.rerun()

    with col2:
        st.subheader("Add Kebele")
        woredas = db.query(Woreda).all()
        if woredas:
            target_w = st.selectbox("Assign to Woreda", [w.name for w in woredas])
            new_k = st.text_input("Enter Kebele Name")
            if st.button("Save Kebele"):
                w_obj = db.query(Woreda).filter(Woreda.name == target_w).first()
                if w_obj and new_k:
                    db.add(Kebele(name=new_k, woreda_id=w_obj.id))
                    db.commit()
                    st.success(f"Added {new_k} to {target_w}")
        else:
            st.warning("Add a Woreda first.")
    db.close()

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 New Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        
        # Woreda Selection
        w_names = [w.name for w in woredas]
        sel_woreda = st.selectbox("Woreda", w_names if w_names else ["No Woredas Available"])
        
        # Filter Kebeles based on Woreda
        kebeles = []
        if woredas and sel_woreda != "No Woredas Available":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj: kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Available"])
        
        phone = st.text_input("Phone Number
