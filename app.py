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
    st.error("⚠️ System Files Missing! Please ensure models.py, database.py, and auth.py are in your GitHub repository.")
    st.stop()

# --- INITIAL SETUP ---
st.set_page_config(page_title="2025 Amhara Planting Survey", page_icon="🌾", layout="wide")
AUDIO_UPLOAD_DIR = "uploads"
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
create_tables()

# Initialize Navigation State
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Home"

def change_page(page_name):
    st.session_state["current_page"] = page_name
    st.rerun()

# --- GOOGLE SHEETS CONNECTION (SECRETS) ---
@st.cache_resource
def initialize_gsheets():
    try:
        # Pulls the secret JSON from Streamlit App Settings -> Secrets
        service_account_info = st.secrets["gcp_service_account"]
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json(service_account_info, scope)
        client = gspread.authorize(creds)
        
        # Name of your Google Sheet
        SHEET_NAME = '2025 Amhara Planting Survey' 
        spreadsheet = client.open(SHEET_NAME)
        return spreadsheet.get_worksheet(0)
    except Exception as e:
        return None

# --- PAGE: HOME (DASHBOARD) ---
def home_page():
    st.title(f"🌾 2025 Amhara Planting Survey")
    st.info(f"Welcome back, **{st.session_state['username']}**")
    st.divider()
    
    # Large Button Navigation
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"):
            change_page("Registration")
        if st.button("📍 SETUP LOCATIONS (Woreda/Kebele)", use_container_width=True):
            change_page("Locations")
    with col2:
        if st.button("💾 EXPORT & DOWNLOAD DATA", use_container_width=True):
            change_page("Download")
        if st.button("🛠️ EDIT/DELETE RECORDS", use_container_width=True):
            change_page("EditRecords")

# --- PAGE: REGISTRATION ---
def register_page():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.header("📝 Farmer Registration Form")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("reg_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        sel_woreda = st.selectbox("Select Woreda", [w.name for w in woredas] if woredas else ["Sync Woredas First"])
        
        kebeles = []
        if woredas and sel_woreda != "Sync Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles] if w_obj else []
        
        sel_kebele = st.selectbox("Select Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio_file = st.file_uploader("🎤 Upload Audio Recording", type=["mp3", "wav", "m4a"])
        
        if st.form_submit_button("Save Registration"):
            if not name or not kebeles:
                st.error("Error: Please provide a name and ensure Woreda/Kebele are selected.")
            else:
                path = None
                if audio_file:
                    path = os.path.join(AUDIO_UPLOAD_DIR, f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{audio_file.name}")
                    with open(path, "wb") as f: f.write(audio_file.getbuffer())
                
                new_entry = Farmer(
                    name=name, woreda=sel_woreda, kebele=sel_kebele,
                    phone=phone, audio_path=path,
                    registered_by=st.session_state["username"]
                )
                db.add(new_entry)
                db.commit()
                st.success("✅ Registration saved to database!")
    db.close()

# --- PAGE: SETUP LOCATIONS ---
def manage_locations():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.header("📍 Manage Woredas & Kebeles")
    db = SessionLocal()
    
    t1, t2 = st.tabs(["📥 Import & Sync", "✏️ Edit/Delete List"])
    
    with t1:
        st.subheader("🔗 Google Sheet Sync")
        if st.button("🔄 Pull Woredas from GSheet"):
            sheet = initialize_gsheets()
            if sheet:
                records = sheet.get_all_records()
                for r in records:
                    w_name = str(r.get("Woreda", r.get("Dep", ""))).strip()
                    if w_name and not db.query(Woreda).filter(Woreda.name == w_name).first():
                        db.add(Woreda(name=w_name))
                db.commit(); st.success("Woredas Imported Successfully!")
            else: st.error("Sync Failed! Please check your Secrets and GSheet Name.")
        
        st.divider()
        st.subheader("📄 Excel/CSV Bulk Upload")
        temp_df = pd.DataFrame({"Woreda": ["Example Woreda"], "Kebele": ["Example Kebele"]})
        st.download_button("📥 Download Excel Template", temp_df.to_csv(index=False).encode('utf-8'), "template.csv")
        
        uploaded = st.file_uploader("Upload filled CSV Template", type="csv")
        if uploaded:
            df = pd.read_csv(uploaded)
            for _, r in df.iterrows():
                w_n, k_n = str(r['Woreda']).strip(), str(r['Kebele']).strip()
                w_obj = db.query(Woreda).filter(Woreda.name == w_n).first()
                if not w_obj:
                    w_obj = Woreda(name=w_n); db.add(w_obj); db.commit()
                if not db.query(Kebele).filter(Kebele.name == k_n, Kebele.woreda_id == w_obj.id).first():
                    db.add(Kebele(name=k_n, woreda_id=w_obj.id))
            db.commit(); st.success("Locations Uploaded!")

    with t2:
        woredas = db.query(Woreda).all()
        for w in woredas:
            with st.expander(f"📌 {w.name}"):
                c1, c2 = st.columns([3, 1])
                new_w = c1.text_input("Rename Woreda", w.name, key=f"w{w.id}")
                if c2.button("Save", key=f"sb{w.id}"):
                    w.name = new_w; db.commit(); st.rerun()
                for k in w.kebeles:
                    ck1, ck2 = st.columns([3, 1])
                    new_k = ck1.text_input("Edit Kebele", k.name, key=f"k{k.id}")
                    if ck2.button("🗑️", key=f"dk{k.id}"):
                        db.delete(k); db.commit(); st.rerun()
                if st.button(f"❌ Delete {w.name}", key=f"dw{w.id}"):
                    db.delete(w); db.commit(); st.rerun()
    db.close()

# --- PAGE: EDIT RECORDS ---
def edit_records_page():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.header("🛠️ Edit Farmer Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    for f in farmers:
        with st.expander(f"👤 {f.name} - {f.woreda}"):
            n_name = st.text_input("Edit Name", f.name, key=f"fn{f.id}")
            n_phone = st.text_input("Edit Phone", f.phone, key=f"fp{f.id}")
            if st.button("Save Changes", key=f"fs{f.id}"):
                f.name, f.phone = n_name, n_phone
                db.commit(); st.success("Updated!"); st.rerun()
            if st.button("🗑️ Delete Record", key=f"fdel{f.id}"):
                db.delete(f); db.commit(); st.rerun()
    db.close()

# --- PAGE: DOWNLOAD ---
def download_page():
    if st.button("⬅️ Back to Home"): change_page("Home")
    st.header("💾 Export Survey Data")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    if farmers:
        df = pd.DataFrame([{
            "Farmer": f.name, "Woreda": f.woreda, "Kebele": f.kebele, 
            "Phone": f.phone, "Surveyor": f.registered_by
        } for f in farmers])
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Download as CSV (Excel)", df.to_csv(index=False).encode('utf-8'), "Amhara_Survey_2025.csv")
    else: st.info("No records found to download.")
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state or not st.session_state["logged_in"]:
        st.title("🚜 2025 Amhara Survey Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Enter System"):
            if login_user(u, p):
                st.session_state["logged_in"] = True
                st.session_state["username"] = u
                st.rerun()
            else: st.error("Login Failed")
    else:
        st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
        page = st.session_state["current_page"]
        if page == "Home": home_page()
        elif page == "Registration": register_page()
        elif page == "Locations": manage_locations()
        elif page == "Download": download_page()
        elif page == "EditRecords": edit_records_page()

if __name__ == "__main__":
    main()
