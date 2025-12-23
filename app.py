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
        
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Upload Audio Note (MP3/WAV)", type=["mp3", "wav", "m4a"])
        
        if st.form_submit_button("Submit Survey"):
            if not name or not w_names or not kebeles:
                st.error("Missing required information! Ensure Woredas and Kebeles are set up.")
            else:
                audio_path = None
                if audio_file:
                    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}"
                    audio_path = os.path.join(AUDIO_UPLOAD_DIR, filename)
                    with open(audio_path, "wb") as f:
                        f.write(audio_file.getbuffer())
                
                # Save to Database
                new_farmer = Farmer(
                    name=name, woreda=sel_woreda, kebele=sel_kebele,
                    phone=phone, audio_path=audio_path,
                    registered_by=st.session_state["username"]
                )
                db.add(new_farmer)
                db.commit()
                st.success(f"✅ Record saved! Surveyor: {st.session_state['username']}")
    db.close()

# --- PAGE: SYNC FROM GSHEET ---
def sync_page():
    st.title("📥 Sync Woredas from Google Sheets")
    sheet = initialize_gsheets()
    if st.button("Start Import"):
        if sheet:
            db = SessionLocal()
            try:
                data = sheet.get_all_records()
                for row in data:
                    w_name = str(row.get("Woreda", row.get("Dep", "General"))).strip()
                    if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                        db.add(Woreda(name=w_name))
                db.commit()
                st.success("Woredas synced successfully!")
            except Exception as e:
                st.error(f"Sync error: {e}")
            finally:
                db.close()

# --- PAGE: DOWNLOAD & VIEW ---
def download_page():
    st.title("💾 Data Export & Download")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    
    if farmers:
        # Convert DB to List of Dicts for Pandas
        data = []
        for f in farmers:
            data.append({
                "Farmer Name": f.name,
                "Woreda": f.woreda,
                "Kebele": f.kebele,
                "Phone": f.phone,
                "Registered By": f.registered_by
            })
        df = pd.DataFrame(data)
        st.dataframe(df)
        
        # Download Button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download Survey CSV",
            data=csv,
            file_name=f"Planting_Survey_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.info("No data available yet.")
    db.close()

# --- MAIN NAVIGATION ---
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
