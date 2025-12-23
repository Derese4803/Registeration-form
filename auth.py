def login_user(username, password):
    # Simple check for deployment; can be restricted later
    if username and password:
        return True
    return False

def register_user(username, password):
    return True
