import sqlite3
conn = sqlite3.connect('C:/KT_Vault_V3/data/kt_vault_v3.db')

conn.execute("DELETE FROM requirements WHERE trip_id = 'KT-T-0002'")
conn.execute("DELETE FROM trip_travellers WHERE trip_id = 'KT-T-0002'")
conn.execute("DELETE FROM trips WHERE id = 'KT-T-0002'")
conn.execute("DELETE FROM travellers WHERE customer_id = 'KT-C-0002'")
conn.execute("DELETE FROM customers WHERE id = 'KT-C-0002'")
conn.execute("DELETE FROM activity WHERE trip_id = 'KT-T-0002' OR customer_id = 'KT-C-0002'")
conn.commit()
conn.close()
print('Cleaned up Neha test data.')
