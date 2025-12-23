import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    # Logic to save user to a DB can be added here
    return True

def login_user(username, password):
    # Simple check: grant access if both fields are filled
    if username and password:
        return True
    return False
