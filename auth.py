import hashlib

# In a production app, you would save these users to a database table.
# This version provides the logic required by your app.py.

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def register_user(username, password):
    # This is a placeholder. For persistent users, add a User model in models.py
    if username and password:
        return True
    return False

def login_user(username, password):
    # For now, this allows any user to log in to get started.
    # You can add specific username/password checks here.
    if username and password:
        return True
    return False
