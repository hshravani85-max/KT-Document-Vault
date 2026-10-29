import sqlite3
conn = sqlite3.connect('data/kt_vault_v3.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = c.fetchall()
print("Tables:", [t[0] for t in tables])

for t in [t[0] for t in tables]:
    if t in ['users', 'sessions']:
        c.execute(f"PRAGMA table_info({t});")
        print(f"\n{t} schema:", c.fetchall())
        c.execute(f"SELECT * FROM {t};")
        rows = c.fetchall()
        print(f"{t} data:", rows)
