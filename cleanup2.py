import sqlite3
conn = sqlite3.connect('C:/KT_Vault_V3/data/kt_vault_v3.db')
c = conn.execute("SELECT id FROM customers WHERE name = 'Test Customer'").fetchone()
if c:
    conn.execute("DELETE FROM activity WHERE customer_id = ?", (c[0],))
    conn.execute("DELETE FROM customers WHERE id = ?", (c[0],))
    conn.commit()
conn.close()
print('Cleaned up test customer.')
