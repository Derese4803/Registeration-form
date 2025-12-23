import streamlit as st
import pandas as pd
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- SYSTEM INIT ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
except:
    st.error("⚠️ Files Missing in GitHub!")
    st.stop()

st.set_page_config(page_title="2025 Amhara Survey", layout="wide")
create_tables()

# Navigation & Auth
if "page" not in st.session_state: st.session_state["page"] = "Home"
def nav(p): 
    st.session_state["page"] = p
    st.rerun()

def login_user(u, p): return u and p # Simplified for setup

# --- GOOGLE DRIVE UPLOAD ---
def upload_to_drive(file, name):
    try:
        creds = ServiceAccountCredentials.from_json(st.secrets["gcp_service_account"], 
                ['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        meta = {'name': f"{name}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp3"}
        media = MediaIoBaseUpload(file, mimetype='audio/mpeg')
        f = service.files().create(body=meta, media_body=media, fields='id').execute()
        fid = f.get('id')
        service.permissions().create(fileId=fid, body={'type': 'anyone', 'role': 'viewer'}).execute()
        return f"https://drive.google.com/uc?id={fid}"
    except: return None

# --- UI: REGISTRATION ---
def registration_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    with st.form("reg"):
        st.header("📝 New Farmer Registration")
        name = st.text_input("Farmer Name")
        ftype = st.selectbox("Farmer Type", ["Smallholder", "Commercial", "Large Scale", "Subsistence"])
        w_name = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Add Woredas First"])
        
        keb_list = []
        if woredas and w_name != "Add Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == w_name).first()
            keb_list = [k.name for k in w_obj.kebeles]
        
        k_name = st.selectbox("Kebele", keb_list if keb_list else ["No Kebeles"])
        phone = st.text_input("Phone Number")
        audio = st.file_uploader("🎤 Upload Audio Note", type=['mp3','wav','m4a'])
        
        if st.form_submit_button("Save Record"):
            if not name or not keb_list:
                st.error("Name and Location required!")
            else:
                url = upload_to_drive(audio, name) if audio else None
                db.add(Farmer(name=name, f_type=ftype, woreda=w_name, kebele=k_name, phone=phone, audio_url=url, registered_by=st.session_state['user']))
                db.commit(); st.success("✅ Saved Successfully!")
    db.close()

# --- UI: LOCATION MANAGER (Edit/Delete) ---
def location_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    st.header("📍 Location Management")
    
    with st.expander("➕ Add New Woreda"):
        nw = st.text_input("Woreda Name")
        if st.button("Save Woreda"):
            if nw: db.add(Woreda(name=nw)); db.commit(); st.rerun()

    for w in db.query(Woreda).all():
        with st.expander(f"📌 Woreda: {w.name}"):
            c1, c2 = st.columns([3, 1])
            new_wn = c1.text_input("Rename Woreda", w.name, key=f"rw{w.id}")
            if c1.button("Update Name", key=f"uw{w.id}"): 
                w.name = new_wn; db.commit(); st.rerun()
            if c2.button("🗑️ Delete Woreda", key=f"dw{w.id}"): 
                db.delete(w); db.commit(); st.rerun()
            
            st.divider()
            for k in w.kebeles:
                kc1, kc2 = st.columns([4, 1])
                kc1.text(f"• Kebele: {k.name}")
                if kc2.button("🗑️", key=f"dk{k.id}"): db.delete(k); db.commit(); st.rerun()
            
            nk = st.text_input(f"New Kebele for {w.name}", key=f"nk{w.id}")
            if st.button("Add Kebele", key=f"bk{w.id}"): 
                if nk: db.add(Kebele(name=nk, woreda_id=w.id)); db.commit(); st.rerun()
    db.close()

# --- UI: DATA VIEW & DOWNLOAD ---
def data_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    farmers = db.query(Farmer).all()
    
    st.header("📊 Survey Records")
    
    if farmers:
        df = pd.DataFrame([{
            "Name": f.name, "Type": f.f_type, "Woreda": f.woreda, 
            "Kebele": f.kebele, "Phone": f.phone, "Audio URL": f.audio_url
        } for f in farmers])
        
        # Download Button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV for Excel", csv, "Amhara_Survey_2025.csv", "text/csv")
        
        st.divider()
        st.write("### Edit/Delete Records")
        for f in farmers:
            with st.expander(f"👤 {f.name} ({f.woreda})"):
                en = st.text_input("Name", f.name, key=f"en{f.id}")
                ep = st.text_input("Phone", f.phone, key=f"ep{f.id}")
                c1, c2 = st.columns(2)
                if c1.button("💾 Save Changes", key=f"sf{f.id}"):
                    f.name, f.phone = en, ep; db.commit(); st.success("Updated")
                if c2.button("🗑️ Delete Record", key=f"df{f.id}"):
                    db.delete(f); db.commit(); st.rerun()
                if f.audio_url: st.write(f"🔗 [Listen to Audio Note]({f.audio_url})")
    else:
        st.info("No records found.")
    db.close()

# --- MAIN NAVIGATION ---
def main():
    if "logged_in" not in st.session_state:
        st.title("🚜 2025 Amhara Survey Login")
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.button("Enter System"):
            if login_user(u, p):
                st.session_state.update({"logged_in":True, "user":u})
                st.rerun()
    else:
        st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
        pg = st.session_state["page"]
        if pg == "Home":
            st.title("🌾 Survey Dashboard")
            if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"): nav("Reg")
            if st.button("📍 MANAGE LOCATIONS", use_container_width=True): nav("Loc")
            if st.button("📊 VIEW & DOWNLOAD DATA", use_container_width=True): nav("Data")
        elif pg == "Reg": registration_page()
        elif pg == "Loc": location_page()
        elif pg == "Data": data_page()

if __name__ == "__main__": main()
