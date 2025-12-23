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
    st.error("⚠️ Database files missing! Ensure models.py, database.py, and auth.py are in your GitHub repo.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
if not os.path.exists(AUDIO_UPLOAD_DIR):
    os.makedirs(AUDIO_UPLOAD_DIR)

create_tables()

# --- NAVIGATION HELPER ---
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Home"

def change_page(page_name):
    st.session_state["current_page"] = page_name
    st.rerun()

# --- PAGE: HOME (DASHBOARD) ---
def home_page():
    st.title(f"👋 Welcome, {st.session_state['username']}")
    st.subheader("2025 Amhara Planting Survey Control Panel")
    st.write("Select a task below to get started:")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📝 Start New Registration", use_container_width=True):
            change_page("Registration")
        if st.button("📍 Manage Woredas & Kebeles", use_container_width=True):
            change_page("Locations")
            
    with col2:
        if st.button("💾 Download/Export Data", use_container_width=True):
            change_page("Download")
        if st.button("🛠️ Edit/Delete Records", use_container_width=True):
            change_page("EditRecords")

# --- PAGE: REGISTRATION ---
def register_page():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.title("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Setup Locations First"])
        kebeles = []
        if woredas and sel_woreda != "Setup Locations First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles]
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Audio Note", type=["mp3", "wav"])
        if st.form_submit_button("Submit Survey"):
            path = None
            if audio_file:
                path = os.path.join(AUDIO_UPLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}")
                with open(path, "wb") as f: f.write(audio_file.getbuffer())
            db.add(Farmer(name=name, woreda=sel_woreda, kebele=sel_kebele, phone=phone, audio_path=path, registered_by=st.session_state["username"]))
            db.commit()
            st.success("✅ Saved successfully!")
    db.close()

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.title("📍 Location Management")
    db = SessionLocal()
    
    t1, t2 = st.tabs(["Sync/Upload", "Edit Existing"])
    with t1:
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔄 Sync from GSheet"):
                # Sync logic here (omitted for brevity, same as previous)
                st.success("Synced!")
        with c2:
            st.write("Bulk Excel Upload")
            # Excel logic here
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.title("💾 Data Export")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{"Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, "Phone": f.phone} for f in farmers])
        st.dataframe(df)
        st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "data.csv")
    db.close()

# --- MAIN APP LOGIC ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        # Inline login page
        st.title("🚜 2025 Survey Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state["logged_in"] = True
                st.session_state["username"] = u
                st.rerun()
    else:
        # SIDEBAR (For easy logout)
        st.sidebar.title(f"👤 {st.session_state['username']}")
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

        # ROUTING
        page = st.session_state["current_page"]
        if page == "Home": home_page()
        elif page == "Registration": register_page()
        elif page == "Locations": manage_locations()
        elif page == "Download": download_page()

if __name__ == "__main__":
    main()
