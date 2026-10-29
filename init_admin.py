import sqlite3
import hashlib
import os
import getpass

def setup_admin():
    print("KT Vault V3 - Secure Admin Initialization")
    username = input("Enter new Admin username: ").strip()
    if not username:
        print("Username cannot be empty.")
        return
        
    pwd1 = getpass.getpass("Enter new password: ")
    pwd2 = getpass.getpass("Confirm password: ")
    
    if pwd1 != pwd2:
        print("Passwords do not match.")
        return
    if len(pwd1) < 8:
        print("Password must be at least 8 characters long.")
        return
        
    conn = sqlite3.connect('data/kt_vault_v3.db')
    cursor = conn.cursor()
    
    # Check if exists
    existing = cursor.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        print("Username already exists. Updating password...")
        user_id = existing[0]
    else:
        import uuid
        user_id = f"KT-U-{uuid.uuid4().hex[:6]}"
        
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', pwd1.encode('utf-8'), salt, 100000)
    
    if existing:
        cursor.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (pwd_hash, salt, user_id))
    else:
        cursor.execute("INSERT INTO users (id, username, password_hash, salt, full_name, role) VALUES (?, ?, ?, ?, ?, ?)",
                       (user_id, username, pwd_hash, salt, "System Administrator", "Admin"))
                       
    conn.commit()
    conn.close()
    print(f"Admin user '{username}' configured successfully.")

if __name__ == "__main__":
    setup_admin()
