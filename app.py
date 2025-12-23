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
AUDIO_UPLOAD_DIR = "uploads"
if not os.path.exists(AUDIO_UPLOAD_DIR):
    os.makedirs(AUDIO_UPLOAD_DIR)

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
                else: st.error("Invalid credentials")
        with tab2:
            ru = st.text_input("New Username")
            rp = st.text_input("New Password", type="password")
            if st.button("Register"):
                if register_user(ru, rp): st.success("Account created!")
                else: st.error("User already exists.")

# --- PAGE: BULK LOCATIONS ---
def manage_locations():
    st.title("📍 Location Setup (Template Mode)")
    db = SessionLocal()
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Bulk Add Woredas")
        w_list = st.text_area("Paste Woredas (separated by commas)", placeholder="Mecha, Adet, Bahir Dar")
        if st.button("Save Woredas"):
            names = [n.strip() for n in w_list.split(",") if n.strip()]
            for name in names:
                if not db.query(Woreda).filter(Woreda.name == name).first():
                    db.add(Woreda(name=name))
            db.commit()
            st.success(f"Added {len(names)} Woredas!")
            st.rerun()

    with col2:
        st.subheader("Bulk Add Kebeles")
        woredas = db.query(Woreda).all()
        if woredas:
            target_w = st.selectbox("Assign to Woreda", [w.name for w in woredas])
            k_list = st.text_area(f"Paste Kebeles for {target_w} (comma separated)")
            if st.button("Save Kebeles"):
                w_obj = db.query(Woreda).filter(Woreda.name == target_w).first()
                names = [n.strip() for n in k_list.split(",") if n.strip()]
                for name in names:
                    db.add(Kebele(name=name, woreda_id=w_obj.id))
                db.commit()
                st.success(f"Added {len(names)} Kebeles to {target_w}!")
        else: st.warning("Add a Woreda first.")
    db.close()

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 New Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["No Woredas Available"])
        
        kebeles = []
        if woredas and sel_woreda != "No Woredas Available":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles] if w_obj else []
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Available"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Upload Audio Note", type=["mp3", "wav", "m4a"])
        
        if st.form_submit_button("Submit Survey"):
            if not name or not kebeles: st.error("Missing name or Kebele!")
            else:
                path = None
                if audio_file:
                    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}"
                    path = os.path.join(AUDIO_UPLOAD_DIR, filename)
                    with open(path, "wb") as f: f.write(audio_file.getbuffer())
                
                db.add(Farmer(name=name, woreda=sel_woreda, kebele=sel_kebele, phone=phone, audio_path=path, registered_by=st.session_state["username"]))
                db.commit()
                st.success("✅ Record saved!")
    db.close()

# --- PAGE: EDIT/DELETE RECORDS ---
def manage_records():
    st.title("🛠️ Edit or Delete Records")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    for f in farmers:
        with st.expander(f"👤 {f.name} ({f.woreda} - {f.kebele})"):
            new_name = st.text_input("Name", f.name, key=f"n{f.id}")
            new_phone = st.text_input("Phone", f.phone, key=f"p{f.id}")
            c1, c2, _ = st.columns([1,1,2])
            if c1.button("💾 Save", key=f"s{f.id}"):
                f.name, f.phone = new_name, new_phone
                db.commit()
                st.rerun()
            if c2.button("🗑️ Delete", key=f"d{f.id}"):
                db.delete(f)
                db.commit()
                st.rerun()
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    st.title("💾 Download Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{"Farmer": f.name, "Woreda": f.woreda, "Kebele": f.kebele, "Phone": f.phone, "Surveyor": f.registered_by} for f in farmers])
        st.dataframe(df)
        st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "survey_data.csv", "text/csv")
    db.close()

# --- MAIN APP ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"User: {st.session_state['username']}")
        menu = {
            "📝 Registration": register_page,
            "📍 Setup Locations": manage_locations,
            "🛠️ Edit/Delete Records": manage_records,
            "💾 Download Data": download_page
        }
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        menu[choice]()
        if st.sidebar.button("Logout"):
            st.session_state.clear()
            st.rerun()

if __name__ == "__main__":
    main()
