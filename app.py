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
    st.error("⚠️ Missing database files! Ensure models.py, database.py, and auth.py are in GitHub.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
create_tables()

# Ensure this matches your Google Sheet Name exactly
SHEET_NAME = '2025 Amhara Planting Survey' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        # Try to open "Order 1" tab, otherwise use the first one
        try:
            return spreadsheet.worksheet("Order 1")
        except:
            return spreadsheet.get_worksheet(0)
    except Exception as e:
        st.error(f"❌ GSheet Connection Failed: {e}")
        return None

# --- PAGE: LOGIN ---
def login_page():
    st.title("🚜 2025 Survey System Login")
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

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form"):
        name = st.text_input("Farmer Full Name")
        w_names = [w.name for w in woredas]
        sel_woreda = st.selectbox("Select Woreda", w_names if w_names else ["No Woredas Found - Sync First"])
        
        kebeles = []
        if woredas and sel_woreda != "No Woredas Found - Sync First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            if w_obj: kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Select Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        file = st.file_uploader("Upload Audio Note/Photo")
        
        if st.form_submit_button("Submit Survey"):
            if not name or not w_names:
                st.error("Missing required information!")
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
                st.success(f"Survey for {name} saved successfully!")
    db.close()

# --- PAGE: MANAGE LOCATIONS ---
def manage_locations():
    st.title("📍 Location Management")
    db = SessionLocal()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Add Woreda")
        nw = st.text_input("New Woreda Name")
        if st.button("Save Woreda"):
            if nw:
                db.add(Woreda(name=nw))
                db.commit()
                st.rerun()
    with c2:
        st.subheader("Add Kebele")
        w_list = [w.name for w in db.query(Woreda).all()]
        target_w = st.selectbox("Woreda", w_list)
        nk = st.text_input("New Kebele Name")
        if st.button("Save Kebele"):
            w_obj = db.query(Woreda).filter(Woreda.name == target_w).first()
            if w_obj and nk:
                db.add(Kebele(name=nk, woreda_id=w_obj.id))
                db.commit()
                st.success("Kebele Added")
    db.close()

# --- PAGE: SYNC ---
def sync_page():
    st.title("📥 Sync from GSheets")
    sheet = initialize_gsheets()
    if st.button("Sync Woredas"):
        if sheet:
            db = SessionLocal()
            data = sheet.get_all_records()
            for row in data:
                # Looks for 'Woreda' column in your sheet
                w_name = str(row.get("Woreda", "General")).strip()
                if not db.query(Woreda).filter(Woreda.name == w_name).first():
                    db.add(Woreda(name=w_name))
            db.commit()
            st.success("Sync Complete!")
            db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    st.title("💾 Download Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{"Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, "Phone": f.phone} for f in farmers])
        st.dataframe(df)
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV File", data=csv, file_name="survey_data.csv", mime="text/csv")
    else:
        st.info("No data to download yet.")
    db.close()

# --- MAIN APP ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"User: {st.session_state['username']}")
        menu = {
            "📝 Registration": register_page,
            "📍 Manage Locations": manage_locations,
            "📥 Sync GSheet": sync_page,
            "💾 Download Data": download_page
        }
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        menu[choice]()
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
