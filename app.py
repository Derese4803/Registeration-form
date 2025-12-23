import streamlit as st
import pandas as pd
import os
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- IMPORTS ---
try:
    from database import SessionLocal
    from models import Farmer, Woreda, Kebele, create_tables
    from auth import login_user
except ImportError:
    st.error("Missing system files in GitHub!")
    st.stop()

# --- INIT ---
st.set_page_config(page_title="2025 Amhara Survey", layout="wide")
create_tables()

if "current_page" not in st.session_state:
    st.session_state["current_page"] = "Home"

def nav(page):
    st.session_state["current_page"] = page
    st.rerun()

# --- GOOGLE HELPERS ---
@st.cache_resource
def get_creds():
    info = st.secrets["gcp_service_account"]
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    return ServiceAccountCredentials.from_json(info, scope)

def upload_audio(file, filename):
    try:
        drive = build('drive', 'v3', credentials=get_creds())
        meta = {'name': filename}
        media = MediaIoBaseUpload(file, mimetype='audio/mpeg', resumable=True)
        f = drive.files().create(body=meta, media_body=media, fields='id').execute()
        fid = f.get('id')
        drive.permissions().create(fileId=fid, body={'type': 'anyone', 'role': 'viewer'}).execute()
        return f"https://drive.google.com/uc?id={fid}"
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

# --- PAGES ---
def home():
    st.title("🌾 2025 Amhara Planting Survey")
    st.write(f"User: **{st.session_state['username']}**")
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📝 NEW REGISTRATION", use_container_width=True, type="primary"): nav("Reg")
        if st.button("📍 MANAGE LOCATIONS", use_container_width=True): nav("Loc")
    with c2:
        if st.button("💾 DOWNLOAD DATA", use_container_width=True): nav("Down")
        if st.button("🛠️ EDIT RECORDS", use_container_width=True): nav("Edit")

def registration():
    if st.button("⬅️ Back"): nav("Home")
    db = SessionLocal()
    woredas = db.query(Woreda).all()
    with st.form("reg"):
        name = st.text_input("Farmer Name")
        w_sel = st.selectbox("Woreda", [w.name for w in woredas] if woredas else ["Sync first"])
        kebs = []
        if woredas and w_sel != "Sync first":
            w_obj = db.query(Woreda).filter(Woreda.name == w_sel).first()
            kebs = [k.name for k in w_obj.kebeles]
        k_sel = st.selectbox("Kebele", kebs if kebs else ["No Kebeles"])
        phone = st.text_input("Phone")
        aud = st.file_uploader("Audio Note", type=['mp3','wav'])
        if st.form_submit_button("Submit"):
            url = upload_audio(aud, f"{name}_{datetime.now().strftime('%H%M')}.mp3") if aud else None
            db.add(Farmer(name=name, woreda=w_sel, kebele=k_sel, phone=phone, audio_url=url, registered_by=st.session_state['username']))
            db.commit(); st.success("✅ Saved!")
    db.close()

def locations():
    if st.button("⬅️ Back"): nav("Home")
    db = SessionLocal()
    t1, t2 = st.tabs(["Sync/Upload", "Edit List"])
    with t1:
        if st.button("🔄 Sync from GSheet"):
            try:
                client = gspread.authorize(get_creds())
                sh = client.open('2025 Amhara Planting Survey').get_worksheet(0)
                for r in sh.get_all_records():
                    wn = str(r.get("Woreda", "")).strip()
                    if wn and not db.query(Woreda).filter(Woreda.name == wn).first():
                        db.add(Woreda(name=wn))
                db.commit(); st.success("Synced!")
            except: st.error("Check GSheet name or Secrets")
    with t2:
        for w in db.query(Woreda).all():
            with st.expander(f"📌 {w.name}"):
                if st.button(f"Delete {w.name}", key=w.id):
                    db.delete(w); db.commit(); st.rerun()
    db.close()

def download():
    if st.button("⬅️ Back"): nav("Home")
    db = SessionLocal()
    fs = db.query(Farmer).all()
    if fs:
        df = pd.DataFrame([{"Name":f.name,"Woreda":f.woreda,"Kebele":f.kebele,"Phone":f.phone,"Audio":f.audio_url} for f in fs])
        st.dataframe(df)
        st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'), "survey.csv")
    db.close()

def edit():
    if st.button("⬅️ Back"): nav("Home")
    db = SessionLocal()
    for f in db.query(Farmer).all():
        with st.expander(f"{f.name} ({f.woreda})"):
            if st.button("Delete Entry", key=f"del{f.id}"):
                db.delete(f); db.commit(); st.rerun()
    db.close()

# --- MAIN ---
if "logged_in" not in st.session_state:
    st.title("🚜 2025 Survey Login")
    u, p = st.text_input("User"), st.text_input("Pass", type="password")
    if st.button("Login"):
        if login_user(u, p):
            st.session_state.update({"logged_in":True, "username":u})
            st.rerun()
else:
    st.sidebar.button("Logout", on_click=lambda: st.session_state.clear())
    p = st.session_state["current_page"]
    if p=="Home": home()
    elif p=="Reg": registration()
    elif p=="Loc": locations()
    elif p=="Down": download()
    elif p=="Edit": edit()
