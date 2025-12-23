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

SHEET_NAME = '2025 Amhara Planting Survey' 

@st.cache_resource
def initialize_gsheets():
    try:
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        spreadsheet = client.open(SHEET_NAME)
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

# --- PAGE: SETUP & EDIT LOCATIONS ---
def manage_locations():
    st.title("📍 Manage Woredas & Kebeles")
    db = SessionLocal()
    
    tab_sync, tab_edit = st.tabs(["📥 Sync/Upload", "✏️ Edit/Delete Locations"])
    
    with tab_sync:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("🔗 Google Sheet Sync")
            if st.button("🔄 Sync from GSheet"):
                sheet = initialize_gsheets()
                if sheet:
                    records = sheet.get_all_records()
                    for row in records:
                        w_name = str(row.get("Woreda", row.get("Dep", ""))).strip()
                        if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                            db.add(Woreda(name=w_name))
                    db.commit()
                    st.success("Woredas Synced!")
        with col2:
            st.subheader("📄 Excel Template")
            template_csv = pd.DataFrame({"Woreda": ["Mecha"], "Kebele": ["Kebele 01"]}).to_csv(index=False).encode('utf-8')
            st.download_button("📥 Get Template", template_csv, "template.csv")
            uploaded = st.file_uploader("Upload CSV", type="csv")
            if uploaded:
                df = pd.read_csv(uploaded)
                for _, r in df.iterrows():
                    w_obj = db.query(Woreda).filter(Woreda.name == str(r['Woreda']).strip()).first()
                    if not w_obj:
                        w_obj = Woreda(name=str(r['Woreda']).strip())
                        db.add(w_obj); db.commit()
                    if not db.query(Kebele).filter(Kebele.name == str(r['Kebele']).strip(), Kebele.woreda_id == w_obj.id).first():
                        db.add(Kebele(name=str(r['Kebele']).strip(), woreda_id=w_obj.id))
                db.commit(); st.success("Uploaded!")

    with tab_edit:
        st.subheader("Modify Existing Locations")
        woredas = db.query(Woreda).all()
        for w in woredas:
            with st.expander(f"📌 Woreda: {w.name}"):
                c1, c2 = st.columns([3, 1])
                new_w_name = c1.text_input("Edit Woreda Name", value=w.name, key=f"edit_w_{w.id}")
                if c2.button("Update", key=f"btn_w_{w.id}"):
                    w.name = new_w_name
                    db.commit(); st.rerun()
                
                st.write("---")
                for k in w.kebeles:
                    col_k1, col_k2, col_k3 = st.columns([3, 1, 1])
                    new_k_name = col_k1.text_input("Edit Kebele", value=k.name, key=f"edit_k_{k.id}")
                    if col_k2.button("💾", key=f"save_k_{k.id}"):
                        k.name = new_k_name
                        db.commit(); st.rerun()
                    if col_k3.button("🗑️", key=f"del_k_{k.id}"):
                        db.delete(k); db.commit(); st.rerun()
                
                if st.button(f"❌ Delete Woreda: {w.name}", key=f"del_w_{w.id}"):
                    db.delete(w); db.commit(); st.rerun()
    db.close()

# --- PAGE: REGISTRATION ---
def register_page():
    st.title("📝 Farmer Registration")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Sync Locations First"])
        kebeles = []
        if woredas and sel_woreda != "Sync Locations First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles]
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Audio Note", type=["mp3", "wav"])
        if st.form_submit_button("Submit"):
            path = None
            if audio_file:
                path = os.path.join(AUDIO_UPLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}")
                with open(path, "wb") as f: f.write(audio_file.getbuffer())
            db.add(Farmer(name=name, woreda=sel_woreda, kebele=sel_kebele, phone=phone, audio_path=path, registered_by=st.session_state["username"]))
            db.commit(); st.success("Saved!")
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    st.title("💾 Data Export")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{"Name": f.name, "Woreda": f.woreda, "Kebele": f.kebele, "Phone": f.phone, "Surveyor": f.registered_by} for f in farmers])
        st.dataframe(df)
        st.download_button("📥 Download CSV", df.to_csv(index=False).encode('utf-8'), "data.csv", "text/csv")
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        login_page()
    else:
        st.sidebar.title(f"Hi, {st.session_state['username']}")
        menu = {"📝 Registration": register_page, "📍 Manage Locations": manage_locations, "💾 Download Data": download_page}
        choice = st.sidebar.radio("Navigation", list(menu.keys()))
        menu[choice]()
        if st.sidebar.button("Logout"):
            st.session_state.clear(); st.rerun()

if __name__ == "__main__":
    main()
