import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- SYSTEM INIT ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
    from auth import login_user
except:
    st.error("⚠️ Files Missing!")
    st.stop()

st.set_page_config(page_title="2025 Amhara Survey", layout="wide")
create_tables()

if "page" not in st.session_state: st.session_state["page"] = "Home"
def nav(p): 
    st.session_state["page"] = p
    st.rerun()

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
        st.header("📝 New Record")
        name = st.text_input("Farmer Name")
        ftype = st.selectbox("Type", ["Smallholder", "Commercial", "Large Scale"])
        w_name = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Add Woredas First"])
        
        keb_list = []
        if woredas and w_name != "Add Woredas First":
            w_obj = db.query(Woreda).filter(Woreda.name == w_name).first()
            keb_list = [k.name for k in w_obj.kebeles]
        
        k_name = st.selectbox("Kebele", keb_list if keb_list else ["No Kebeles"])
        phone = st.text_input("Phone")
        audio = st.file_uploader("🎤 Audio Note", type=['mp3','wav'])
        
        if st.form_submit_button("Save & Upload"):
            url = upload_to_drive(audio, name) if audio else None
            db.add(Farmer(name=name, f_type=ftype, woreda=w_name, kebele=k_name, phone=phone, audio_url=url, registered_by=st.session_state['user']))
            db.commit(); st.success("✅ Saved!"); st.rerun()
    db.close()

# --- UI: MANAGE LOCATIONS (Edit/Delete Unified) ---
def location_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    st.header("📍 Edit/Delete Locations")
    
    with st.expander("➕ Add New Woreda"):
        nw = st.text_input("Woreda Name")
        if st.button("Save"): db.add(Woreda(name=nw)); db.commit(); st.rerun()

    for w in db.query(Woreda).all():
        with st.expander(f"📌 {w.name}"):
            c1, c2 = st.columns([3, 1])
            new_wn = c1.text_input("Rename", w.name, key=f"rw{w.id}")
            if c1.button("Update Name", key=f"uw{w.id}"): 
                w.name = new_wn; db.commit(); st.rerun()
            if c2.button("🗑️ Delete Woreda", key=f"dw{w.id}"): 
                db.delete(w); db.commit(); st.rerun()
            
            st.divider()
            for k in w.kebeles:
                kc1, kc2 = st.columns([3, 1])
                kc1.text(f"• {k.name}")
                if kc2.button("🗑️", key=f"dk{k.id}"): db.delete(k); db.commit(); st.rerun()
            
            nk = st.text_input(f"New Kebele for {w.name}", key=f"nk{w.id}")
            if st.button("Add Kebele", key=f"bk{w.id}"): 
                db.add(Kebele(name=nk, woreda_id=w.id)); db.commit(); st.rerun()
    db.close()

# --- UI: DATA MANAGEMENT (Edit/Delete Farmers) ---
def data_page():
    if st.button("⬅️ Home"): nav("Home")
    db = SessionLocal()
    st.header("🛠️ Edit/Delete Records")
    for f in db.query(Farmer).all():
        with st.expander(f"👤 {f.name} ({f.woreda})"):
            en = st.text_input("Name", f.name, key=f"en{f.id}")
            ep = st.text_input("Phone", f.phone, key=f"ep{f.id}")
            c1, c2 = st.columns(2)
            if c1.button("💾 Save", key=f"sf{f.id}"):
                f.name, f.phone = en, ep; db.commit(); st.success("Updated")
            if c2.button("🗑️ Delete Record", key=f"df{f.id}"):
                db.delete(f); db.commit(); st.rerun()
            if f.audio_url: st.audio(f.audio_url)
    db.close()

# --- MAIN ---
def main():
    if "logged_in" not in st.session_state:
        st.title("🌾 2025 Survey Login")
        u, p = st.text_input("User"), st.text_input("Pass", type="password")
        if st.button("Login"):
            if login_user(u, p):
                st.session_state.update({"logged_in":True, "user":u})
                st.rerun()
    else:
        st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
        pg = st.session_state["page"]
        if pg == "Home":
            st.title("Dashboard")
            if st.button("📝 NEW REGISTRATION", use_container_width=True): nav("Reg")
            if st.button("📍 EDIT LOCATIONS", use_container_width=True): nav("Loc")
            if st.button("🛠️ EDIT RECORDS", use_container_width=True): nav("Data")
        elif pg == "Reg": registration_page()
        elif pg == "Loc": location_page()
        elif pg == "Data": data_page()

if __name__ == "__main__": main()
