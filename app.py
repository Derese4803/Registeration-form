import streamlit as st
import pandas as pd
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

# --- SYSTEM IMPORTS ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
except ImportError:
    st.error("⚠️ Critical Error: models.py or database.py not found!")
    st.stop()

# --- INITIALIZATION ---
st.set_page_config(page_title="2025 Amhara Survey", page_icon="🌾", layout="wide")
create_tables()

# Navigation Logic
if "page" not in st.session_state:
    st.session_state["page"] = "Home"

def nav(page_name):
    st.session_state["page"] = page_name
    st.rerun()

# --- GOOGLE DRIVE UPLOAD UTILITY ---
def upload_to_drive(file, farmer_name):
    try:
        # Pulls from Streamlit Secrets
        creds_info = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json(creds_info, 
                ['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        
        file_name = f"{farmer_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3"
        file_metadata = {'name': file_name}
        media = MediaIoBaseUpload(file, mimetype='audio/mpeg', resumable=True)
        
        # Upload file
        g_file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        file_id = g_file.get('id')
        
        # Set Permissions to Public
        service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'viewer'}).execute()
        
        # Return direct streamable link
        return f"https://drive.google.com/uc?id={file_id}"
    except Exception as e:
        st.error(f"Google Drive Error: {e}")
        return None

# --- PAGE: HOME (DASHBOARD) ---
def home_page():
    st.title("🌾 2025 Amhara Planting Survey")
    st.write(f"Logged in as: **{st.session_state.get('user', 'Surveyor')}**")
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"):
            nav("Reg")
    with col2:
        if st.button("📍 MANAGE LOCATIONS", use_container_width=True):
            nav("Loc")
    with col3:
        if st.button("📊 DATA & DOWNLOAD", use_container_width=True):
            nav("Data")

# --- PAGE: REGISTRATION ---
def registration_page():
    if st.button("⬅️ Back to Dashboard"): nav("Home")
    st.header("📝 Farmer Registration")
    
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    
    with st.form("farmer_form", clear_on_submit=True):
        name = st.text_input("Farmer Full Name")
        f_type = st.selectbox("Farmer Type", ["Smallholder", "Commercial", "Large Scale", "Subsistence"])
        
        # Location Selection
        w_list = [w.name for w in woredas] if woredas else ["Sync Locations First"]
        sel_woreda = st.selectbox("Woreda", w_list)
        
        kebeles = []
        if woredas and sel_woreda != "Sync Locations First":
            w_obj = db.query(Woreda).filter(Woreda.name == sel_woreda).first()
            kebeles = [k.name for k in w_obj.kebeles]
        
        sel_kebele = st.selectbox("Kebele", kebeles if kebeles else ["No Kebeles Found"])
        phone = st.text_input("Phone Number")
        audio = st.file_uploader("🎤 Upload Audio Recording", type=['mp3', 'wav', 'm4a'])
        
        if st.form_submit_button("Submit Registration"):
            if not name or not kebeles:
                st.error("Please provide name and ensure location is selected.")
            else:
                with st.spinner("Uploading audio to Cloud..."):
                    url = upload_to_drive(audio, name) if audio else None
                
                new_farmer = Farmer(
                    name=name, f_type=f_type, woreda=sel_woreda, 
                    kebele=sel_kebele, phone=phone, audio_url=url,
                    registered_by=st.session_state.get('user', 'Unknown')
                )
                db.add(new_farmer)
                db.commit()
                st.success(f"✅ Record for {name} saved successfully!")
    db.close()

# --- PAGE: LOCATION MANAGER (EDIT/DELETE) ---
def location_page():
    if st.button("⬅️ Back"): nav("Home")
    st.header("📍 Edit/Delete Locations")
    db = SessionLocal()
    
    # Add New Woreda
    with st.expander("➕ Add New Woreda"):
        nw_name = st.text_input("Woreda Name")
        if st.button("Save New Woreda"):
            if nw_name:
                db.add(Woreda(name=nw_name))
                db.commit()
                st.rerun()

    # Manage Existing
    woredas = db.query(Woreda).all()
    for w in woredas:
        with st.expander(f"📌 {w.name}"):
            c1, c2 = st.columns([4, 1])
            new_name = c1.text_input("Rename Woreda", w.name, key=f"rw{w.id}")
            if c1.button("Update Woreda Name", key=f"ubw{w.id}"):
                w.name = new_name; db.commit(); st.rerun()
            if c2.button("🗑️ Delete", key=f"delw{w.id}"):
                db.delete(w); db.commit(); st.rerun()
            
            st.divider()
            st.write("Kebeles:")
            for k in w.kebeles:
                kc1, kc2 = st.columns([5, 1])
                kc1.text(f"• {k.name}")
                if kc2.button("🗑️", key=f"dk{k.id}"):
                    db.delete(k); db.commit(); st.rerun()
            
            nk_name = st.text_input("New Kebele Name", key=f"ink{w.id}")
            if st.button("Add Kebele", key=f"abk{w.id}"):
                if nk_name:
                    db.add(Kebele(name=nk_name, woreda_id=w.id))
                    db.commit(); st.rerun()
    db.close()

# --- PAGE: DATA VIEW & EXPORT ---
def data_page():
    if st.button("⬅️ Back"): nav("Home")
    st.header("📊 Survey Records & CSV Export")
    db = SessionLocal()
    
    try:
        farmers = db.query(Farmer).all()
        if farmers:
            # Prepare DataFrame for Download
            data = [{
                "Name": f.name, "Type": f.f_type, "Woreda": f.woreda,
                "Kebele": f.kebele, "Phone": f.phone, "Audio URL": f.audio_url
            } for f in farmers]
            df = pd.DataFrame(data)
            
            # Export Section
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download All Data (CSV)", csv, "Amhara_Survey_2025.csv", "text/csv")
            
            st.divider()
            st.write("### Edit/Delete Individual Records")
            for f in farmers:
                with st.expander(f"👤 {f.name} - {f.woreda}"):
                    en = st.text_input("Edit Name", f.name, key=f"enf{f.id}")
                    ep = st.text_input("Edit Phone", f.phone, key=f"epf{f.id}")
                    
                    ec1, ec2 = st.columns(2)
                    if ec1.button("💾 Save Changes", key=f"sf{f.id}"):
                        f.name, f.phone = en, ep; db.commit(); st.success("Updated"); st.rerun()
                    if ec2.button("🗑️ Delete Farmer", key=f"df{f.id}"):
                        db.delete(f); db.commit(); st.rerun()
                    
                    if f.audio_url:
                        st.write(f"🔗 [Listen to Recording]({f.audio_url})")
        else:
            st.info("No records found yet.")
    except Exception as e:
        st.error("⚠️ Database Error: Your database file might be out of date.")
        if st.button("Force Re-sync Database"):
            from sqlalchemy import text
            db.execute(text("ALTER TABLE farmers ADD COLUMN f_type TEXT"))
            db.commit()
            st.rerun()
    finally:
        db.close()

# --- MAIN LOGIN & ROUTING ---
def main():
    if "logged_in" not in st.session_state:
        st.title("🚜 2025 Amhara Login")
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Enter"):
            if u and p: # Simplified for logic; use auth.py for real security
                st.session_state.update({"logged_in": True, "user": u})
                st.rerun()
    else:
        st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
        pg = st.session_state["page"]
        if pg == "Home": home_page()
        elif pg == "Reg": registration_page()
        elif pg == "Loc": location_page()
        elif pg == "Data": data_page()

if __name__ == "__main__":
    main()
