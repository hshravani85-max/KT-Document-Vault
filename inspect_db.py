import sqlite3
import pandas as pd
pd.set_option('display.max_columns', None)

conn = sqlite3.connect('data/kt_vault_v3.db')

print('--- Customers ---')
print(pd.read_sql('SELECT id, name FROM customers', conn))

print('\n--- Travellers ---')
print(pd.read_sql('SELECT id, customer_id, name FROM travellers', conn))

print('\n--- Trips ---')
print(pd.read_sql('SELECT id, customer_id, trip_name FROM trips', conn))

print('\n--- Trip Travellers ---')
print(pd.read_sql('SELECT trip_id, traveller_id FROM trip_travellers', conn))

print('\n--- Requirements for KT-T-0002 ---')
print(pd.read_sql("SELECT id, trip_id, name, traveller_id, expected_document_type FROM requirements WHERE trip_id = 'KT-T-0002'", conn))

print('\n--- Documents for KT-T-0002 Requirements ---')
print(pd.read_sql("SELECT d.id, d.requirement_id, d.traveller_id, d.status FROM documents d JOIN requirements r ON d.requirement_id = r.id WHERE r.trip_id = 'KT-T-0002'", conn))

print('\n--- Documents linked directly to Trip 2 ---')
print(pd.read_sql("SELECT id, requirement_id, traveller_id, status FROM documents WHERE trip_id = 'KT-T-0002'", conn))

print('\n--- Reusable Documents for KT-C-0002 ---')
print(pd.read_sql("SELECT id, requirement_id, traveller_id, customer_id, status FROM documents WHERE customer_id = 'KT-C-0002' AND trip_id IS NULL", conn))
