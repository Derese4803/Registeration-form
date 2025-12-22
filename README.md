from database import SessionLocal
from models import User

def register_user(username, password):
    db = SessionLocal()
    existing_user = db.query(User).filter(User.username == username).first()
    if existing_user:
        db.close()
        return False
    new_user = User(username=username, password=password)
    db.add(new_user)
    db.commit()
    db.close()
    return True

def login_user(username, password):
    db = SessionLocal()
    user = db.query(User).filter(User.username == username, User.password == password).first()
    db.close()
    return user is not None
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
# ... (rest of JSON)
