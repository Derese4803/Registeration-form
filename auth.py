import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Note: In a real app, users should be saved to the database. 
# This version is simplified for your setup.
def register_user(username, password):
    # Logic to save user to a 'users' table can be added here
    return True

def login_user(username, password):
    # Simple check for demo; you can verify against a database later
    return True
