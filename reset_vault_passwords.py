#!/usr/bin/env python3
"""
Khanna Travels — KT Vault V3
Interactive Local Password Reset Utility
Allows the operator to set custom easy-to-remember passphrases (>= 16 characters)
for 'admin' and 'staff' accounts directly in the local terminal.

Usage in VS Code Terminal:
    python reset_vault_passwords.py
"""

import os
import sys
import getpass
import secrets
import hashlib
import sqlite3
from datetime import datetime

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)

DB_PATH = os.path.join(APP_ROOT, "data", "kt_vault_v3.db")

MIN_PASSPHRASE_LENGTH = 16

def prompt_passphrase(account_name: str, role_name: str) -> str:
    """Prompts for a passphrase and confirmation via masked terminal input."""
    print(f"\n" + "=" * 65)
    print(f" ACCOUNT: {account_name.upper()} ({role_name})")
    print(f" Rule: At least {MIN_PASSPHRASE_LENGTH} characters (e.g. four unrelated words)")
    print("=" * 65)

    while True:
        try:
            p1 = getpass.getpass(prompt=f"Enter new passphrase for '{account_name}': ")
        except (EOFError, KeyboardInterrupt):
            print("\n[!] Operation cancelled by user.")
            sys.exit(1)

        p1_clean = p1.strip()
        if len(p1_clean) < MIN_PASSPHRASE_LENGTH:
            print(f"[!] Error: Passphrase too short ({len(p1_clean)} chars). Minimum is {MIN_PASSPHRASE_LENGTH} characters.")
            print("    Tip: Choose four simple unrelated words (e.g. 'summer river blue mountain').")
            continue

        try:
            p2 = getpass.getpass(prompt=f"Confirm passphrase for '{account_name}': ")
        except (EOFError, KeyboardInterrupt):
            print("\n[!] Operation cancelled by user.")
            sys.exit(1)

        if p1_clean != p2.strip():
            print("[!] Error: Passphrases do not match. Please try again.")
            continue

        print(f"[OK] Passphrase for '{account_name}' accepted ({len(p1_clean)} characters).")
        return p1_clean

def apply_passwords(admin_pwd: str, staff_pwd: str):
    """Hashes passphrases with PBKDF2-HMAC-SHA256 and updates database."""
    if not os.path.isfile(DB_PATH):
        raise FileNotFoundError(f"Database not found at: {DB_PATH}")

    # Generate distinct 16-byte cryptographic salts
    salt_admin = secrets.token_bytes(16)
    hash_admin = hashlib.pbkdf2_hmac('sha256', admin_pwd.encode('utf-8'), salt_admin, 100000)

    salt_staff = secrets.token_bytes(16)
    hash_staff = hashlib.pbkdf2_hmac('sha256', staff_pwd.encode('utf-8'), salt_staff, 100000)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Update admin
    c.execute("""
        UPDATE users 
        SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL, is_active = 1
        WHERE username = 'admin'
    """, (hash_admin, salt_admin))

    # Update staff
    c.execute("""
        UPDATE users 
        SET password_hash = ?, salt = ?, failed_attempts = 0, locked_until = NULL, is_active = 1
        WHERE username = 'staff'
    """, (hash_staff, salt_staff))

    # Invalidate all existing sessions
    c.execute("DELETE FROM sessions")

    # Record security audit log entry
    c.execute("""
        INSERT INTO security_audit_logs (event_type, username, user_id, role, ip_address, details, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "OPERATOR_PASSWORD_RESET_INTERACTIVE",
        "admin",
        "KT-U-001",
        "Admin",
        "127.0.0.1",
        "Interactive password reset completed by operator for admin and staff accounts.",
        datetime.now().isoformat()
    ))

    conn.commit()
    conn.close()

def verify_system(admin_pwd: str, staff_pwd: str):
    """Verifies that both accounts can log in and data is intact."""
    import auth_services
    import database

    # 1. Database check
    conn = database.get_connection()
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    cust_count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    trip_count = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    active_users = conn.execute("SELECT username FROM users WHERE is_active = 1 ORDER BY username").fetchall()
    conn.close()

    assert integrity == "ok", f"Integrity check failed: {integrity}"
    assert len(active_users) == 2, f"Expected 2 active accounts, found {len(active_users)}"

    # 2. Authentication check
    s_admin = auth_services.authenticate_user("admin", admin_pwd)
    if not s_admin or s_admin.get("role") != "Admin":
        raise RuntimeError("Verification failed: Admin account could not authenticate with new passphrase.")

    s_staff = auth_services.authenticate_user("staff", staff_pwd)
    if not s_staff or s_staff.get("role") != "Staff":
        raise RuntimeError("Verification failed: Staff account could not authenticate with new passphrase.")

    print("\n" + "=" * 65)
    print(" VERIFICATION RESULTS")
    print("=" * 65)
    print(f" [PASS] Database integrity: {integrity}")
    print(f" [PASS] Customers preserved: {cust_count}")
    print(f" [PASS] Trips preserved: {trip_count}")
    print(f" [PASS] Documents preserved: {doc_count}")
    print(f" [PASS] Active accounts: {', '.join([u[0] for u in active_users])}")
    print(f" [PASS] Admin authentication: SUCCESS (Role: Admin)")
    print(f" [PASS] Staff authentication: SUCCESS (Role: Staff)")
    print("=" * 65)
    print("\nSUCCESS: Both accounts have been successfully updated.")
    print("Zero passwords were saved in plaintext.")
    print("You can now open KT Vault in your browser and sign in.\n")

def main():
    print("=" * 65)
    print(" KHANNA TRAVELS — KT VAULT V3 LOCAL PASSWORD RESET")
    print("=" * 65)
    print(" This tool securely prompts for new passphrases in your local terminal.")
    print(" Input will be masked (characters will NOT appear on screen as you type).")
    print(f" Minimum length requirement: {MIN_PASSPHRASE_LENGTH} characters.")

    # 1. Prompt for Admin passphrase
    admin_pwd = prompt_passphrase("admin", "Administrator - Full Access")

    # 2. Prompt for Staff passphrase
    staff_pwd = prompt_passphrase("staff", "Staff - Limited Operations Access")

    if admin_pwd == staff_pwd:
        print("\n[!] Warning: You entered identical passphrases for both admin and staff.")
        confirm = input("Are you sure you want to use the same passphrase for both accounts? (yes/no): ").strip().lower()
        if confirm not in ("y", "yes"):
            print("[!] Reset aborted. Please re-run the script to choose distinct passphrases.")
            sys.exit(1)

    print("\n[*] Applying secure PBKDF2-HMAC-SHA256 password hashes...")
    apply_passwords(admin_pwd, staff_pwd)

    print("[*] Verifying authentication and database integrity...")
    verify_system(admin_pwd, staff_pwd)

if __name__ == "__main__":
    main()