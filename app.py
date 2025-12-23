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
    st.error("⚠️ Missing files in GitHub! Ensure models.py, database.py, and auth.py are present.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")

# Folder for audio storage
AUDIO_UPLOAD_DIR = "uploads"
if not os.path.exists(AUDIO_UPLOAD_DIR):
    os.makedirs(AUDIO_UPLOAD_DIR)

# Initialize Database Tables
create_tables()

# Google Sheet Name
SHEET_NAME = '2025 Amhara Planting Survey' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
        # Try "Order 1" tab, otherwise use first tab
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

# --- PAGE: REGISTRATION (With Audio Upload) ---
def register_page():
    st.title("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        
        w_names = [w.name for w in woredas]
        sel_woreda = st.selectbox("Select Woreda", w_names if w_names else ["No Woredas Found - Sync First"])
        
        # Audio Upload
        audio_file = st.file_uploader("🎤 Upload Audio Note (MP3/WAV)", type=["mp3", "wav", "m4a"])
        
        phone = st.text_input("Phone Number")
        
        if st.form_submit_button("Submit Survey"):
            if not name or not w_names:
                st.error("Please provide Farmer Name and ensure Woredas are synced.")
            else:
                path = None
                if audio_file:
                    # Save file with timestamp to prevent overwriting
                    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}"
                    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
                    with open(path, "wb") as f:
                        f.write(audio_file.getbuffer())
                
                new_f = Farmer(
                    name=name, woreda=sel_woreda, 
                    phone=phone, audio_path=path,
                    registered_by=st.session_state["username"]
                )
                db.add(new_f)
                db.commit()
                st.success(f"Survey for {name} saved! (Surveyor: {st.session_state['username']})")
    db.close()

# --- PAGE: SYNC ---
def sync_page():
    st.title("📥 Sync Woredas from Google Sheets")
    st.info(f"Looking for Woredas in: {SHEET_NAME}")
    sheet = initialize_gsheets()
    
    if st.button("Start Sync"):
        if sheet:
            db = SessionLocal()
            try:
                data = sheet.get_all_records()
                new_count = 0
                for row in data:
                    w_name = str(row.get("Woreda", row.get("Dep", "General"))).strip()
                    if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                        db.add(Woreda(name=w_name))
                        new_count += 1
                db.commit()
                st.success(f"Sync finished! Added {new_count} new Woredas.")
            except Exception as e:
                st.error(f"Error reading sheet: {e}")
            finally:
                db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    st.title("💾 Download Data & Export to CSV")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    
    if farmers:
        # Create a list for the Pandas DataFrame
        export_data = []
        for f in farmers:
            export_data.append({
                "Farmer Name": f.name,
                "Woreda": f.woreda,
                "Phone": f.phone,
                "Registered By": f.registered_by,
                "Audio File": f.audio_path if f.audio_path else "No Audio"
            })
        
        df = pd.DataFrame(export_data)
        st.write("### Data Preview")
        st.dataframe(df)
        
        # CSV Download Button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download as Excel (CSV)",
            data=csv,
            file_name=f"Planting_Survey_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("No records found in the database.")
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"Surveyor: {st.session_state['username']}")
        menu = {
            "📝 Registration": register_page,
            "📥 Sync GSheet": sync_page,
            "💾 Download Data": download_page
        }
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        
        if choice == "📝 Registration": register_page()
        elif choice == "📥 Sync GSheet": sync_page()
        elif choice == "💾 Download Data": download_page()
        
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
