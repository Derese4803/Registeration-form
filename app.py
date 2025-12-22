import streamlit as st
import pandas as pd
import os
from datetime import datetime
import io
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- IMPORTS FROM EXTERNAL FILES ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables, User
    from auth import register_user, login_user
except ImportError as e:
    st.error(f"Missing required files (database.py, models.py, or auth.py). Error: {e}")
    st.stop()

# --- CONFIGURATION & DIRECTORIES ---
st.set_page_config(
    page_title="Farmer Registration System",
    page_icon="🌾",
    layout="wide"
)

AUDIO_UPLOAD_DIR = "audio_uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)

# Initialize Database
create_tables()

# --- GOOGLE SHEET CONFIG ---
FARMER_SHEET_NAME = 'FarmerRegistrationLog' 
LOCATION_SHEET_NAME = 'WoredaKebeleList' 

@st.cache_resource
def initialize_gsheets(sheet_name):
    """Initializes and returns the Google Sheet client and the target sheet."""
    try:
        # Expected structure in secrets.toml: [gcp_service_account]
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        sheet = client.open(sheet_name).sheet1
        return sheet
    except Exception as e:
        st.error(f"Connection Error ('{sheet_name}'): {e}")
        return None

def append_to_gsheet(sheet, data_row):
    if sheet is None: return False
    try:
        sheet.append_row(data_row)
        return True
    except Exception as e:
        st.error(f"GSheet Append Error: {e}")
        return False

# --- 1. AUTHENTICATION PAGE ---
def login_page():
    st.title("👤 Login / Register")
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["Login", "Register"])
        with tab1:
            username_login = st.text_input("Username", key="login_username")
            password_login = st.text_input("Password", type="password", key="login_password")
            if st.button("Login"):
                if login_user(username_login, password_login):
                    st.session_state["logged_in"] = True
                    st.session_state["username"] = username_login
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        with tab2:
            username_reg = st.text_input("Username", key="reg_username")
            password_reg = st.text_input("Password", type="password", key="reg_password")
            if st.button("Register"):
                if register_user(username_reg, password_reg):
                    st.success("User registered! You can now login.")
                else:
                    st.error("Registration failed. User might already exist.")

# --- 2. MANAGE WOREDA/KEBELE PAGE ---
def manage_woreda_kebele_page():
    db = SessionLocal()
    st.title("🗂️ Manage Woredas & Kebeles")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Add Woreda")
        w_name = st.text_input("Woreda Name")
        if st.button("Save Woreda"):
            if w_name:
                db.add(Woreda(name=w_name))
                db.commit()
                st.success("Woreda added!")
                st.rerun()

    with col2:
        st.subheader("Add Kebele")
        woredas = db.query(Woreda).all()
        if woredas:
            w_choice = st.selectbox("Select Woreda", [w.name for w in woredas])
            k_names = st.text_area("Kebele Names (one per line)")
            if st.button("Save Kebeles"):
                parent = db.query(Woreda).filter(Woreda.name == w_choice).first()
                for name in k_names.split('\n'):
                    if name.strip():
                        db.add(Kebele(name=name.strip(), woreda_id=parent.id))
                db.commit()
                st.success("Kebeles added!")
                st.rerun()
    db.close()

# --- 3. FARMER REGISTRATION PAGE ---
def register_farmer_page():
    db = SessionLocal()
    st.title("🌾 Farmer Registration")
    gsheet = initialize_gsheets(FARMER_SHEET_NAME)

    with st.form("reg_form"):
        col1, col2 = st.columns(2)
        woredas = db.query(Woreda).all()
        
        with col1:
            woreda_choice = st.selectbox("Woreda", [w.name for w in woredas])
            name = st.text_input("Farmer Name")
        with col2:
            kebeles = []
            if woreda_choice:
                w_obj = db.query(Woreda).filter(Woreda.name == woreda_choice).first()
                kebeles = [k.name for k in w_obj.kebeles]
            kebele_choice = st.selectbox("Kebele", kebeles)
            phone = st.text_input("Phone")
        
        uploaded_file = st.file_uploader("Upload Audio/File", type=['mp3', 'wav', 'pdf', 'jpg', 'png'])
        submitted = st.form_submit_button("Register Farmer")

        if submitted:
            if not (name and phone and woreda_choice and kebele_choice):
                st.error("All fields are required.")
            else:
                path = None
                if uploaded_file:
                    fname = f"{name.replace(' ','_')}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{uploaded_file.name.split('.')[-1]}"
                    path = os.path.join(AUDIO_UPLOAD_DIR, fname)
                    with open(path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                new_farmer = Farmer(
                    name=name, woreda=woreda_choice, kebele=kebele_choice,
                    phone=phone, audio_path=path, registered_by=st.session_state["username"],
                    timestamp=datetime.now()
                )
                db.add(new_farmer)
                db.commit()

                # GSheet Logging
                data = [name, woreda_choice, kebele_choice, phone, datetime.now().strftime("%Y-%m-%d"), st.session_state["username"], path or "N/A"]
                append_to_gsheet(gsheet, data)
                st.success("Farmer Registered Successfully!")
                st.balloons()
    db.close()

# --- 4. IMPORT FROM GSHEET ---
def upload_woreda_kebele_gsheet():
    st.title("📥 Import Data")
    gsheet = initialize_gsheets(LOCATION_SHEET_NAME)
    if st.button("Sync from Google Sheets") and gsheet:
        db = SessionLocal()
        try:
            data = gsheet.get_all_records()
            for row in data:
                w_name = str(row.get("Woreda", "")).strip()
                k_name = str(row.get("Kebele", "")).strip()
                if w_name and k_name:
                    woreda = db.query(Woreda).filter(Woreda.name == w_name).first()
                    if not woreda:
                        woreda = Woreda(name=w_name)
                        db.add(woreda)
                        db.flush() # Get ID without committing yet
                    
                    exists = db.query(Kebele).filter(Kebele.name == k_name, Kebele.woreda_id == woreda.id).first()
                    if not exists:
                        db.add(Kebele(name=k_name, woreda_id=woreda.id))
            db.commit()
            st.success("Sync Complete!")
        except Exception as e:
            st.error(f"Sync failed: {e}")
        finally:
            db.close()

# --- 5. VIEW FARMERS ---
def view_farmers_page():
    st.title("🧑‍🌾 Farmer List")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    
    # Matching header and row count (9 columns)
    cols = st.columns([1, 2, 2, 2, 2, 2, 2, 1, 1])
    headers = ["ID", "Name", "Phone", "Woreda", "Kebele", "File", "By", "Edit", "Del"]
    for col, h in zip(cols, headers): col.write(f"**{h}**")

    for f in farmers:
        row = st.columns([1, 2, 2, 2, 2, 2, 2, 1, 1])
        row[0].write(f.id)
        row[1].write(f.name)
        row[2].write(f.phone)
        row[3].write(f.woreda)
        row[4].write(f.kebele)
        with row[5]:
            if f.audio_path and os.path.exists(f.audio_path):
                st.audio(f.audio_path) if f.audio_path.endswith(('mp3','wav')) else st.write("📄 File")
            else: st.write("-")
        row[6].write(f.registered_by)
        if row[7].button("✏️", key=f"e{f.id}"): pass # Edit logic
        if row[8].button("🗑️", key=f"d{f.id}"):
            db.delete(f)
            db.commit()
            st.rerun()
    db.close()

# --- MAIN ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"Welcome, {st.session_state['username']}")
        menu = {
            "🌾 Register Farmer": register_farmer_page,
            "🧑‍🌾 View Farmers": view_farmers_page,
            "🗂️ Manage Locations": manage_woreda_kebele_page,
            "📥 Sync GSheet": upload_woreda_kebele_gsheet
        }
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        menu[choice]()
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
