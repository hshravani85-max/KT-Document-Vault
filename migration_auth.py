import sqlite3
import hashlib
import os

def create_auth_schema():
    conn = sqlite3.connect('data/kt_vault_v3.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE,
            password_hash BLOB,
            salt BLOB,
            full_name TEXT,
            role TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            expires_at DATETIME,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')
    
    # Seed Synthetic Data
    users_data = [
        ('KT-U-001', 'admin', 'admin123', 'System Admin', 'Admin'),
        ('KT-U-002', 'supervisor', 'super123', 'Senior Supervisor', 'Supervisor'),
        ('KT-U-003', 'staff', 'staff123', 'Junior Staff', 'Staff')
    ]

    for uid, username, password, full_name, role in users_data:
        # Check if user exists
        existing = cursor.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if not existing:
            salt = os.urandom(16)
            pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            cursor.execute('''
                INSERT INTO users (id, username, password_hash, salt, full_name, role)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (uid, username, pwd_hash, salt, full_name, role))

    conn.commit()
    conn.close()
    print("Authentication schema and synthetic users created successfully.")

if __name__ == "__main__":
    create_auth_schema()
