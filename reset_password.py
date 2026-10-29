import sqlite3
import hashlib
import os

def reset_password(username, new_password):
    conn = sqlite3.connect('data/kt_vault_v3.db')
    c = conn.cursor()
    
    # Check if user exists
    user = c.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        print(f"User {username} not found.")
        return
        
    user_id = user[0]
    salt = os.urandom(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', new_password.encode('utf-8'), salt, 100000)
    
    c.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (pwd_hash, salt, user_id))
    conn.commit()
    conn.close()
    print(f"Password reset successfully for {username}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        reset_password(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python reset_password.py <username> <new_password>")
