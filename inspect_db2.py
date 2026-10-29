import sqlite3

def print_query(conn, query, params=()):
    try:
        cursor = conn.execute(query, params)
        cols = [description[0] for description in cursor.description]
        print("\t".join(cols))
        rows = cursor.fetchall()
        for row in rows:
            print("\t".join([str(x) for x in row]))
        print(f"Total rows: {len(rows)}\n")
    except Exception as e:
        print(f"Error executing {query}: {e}\n")

conn = sqlite3.connect('data/kt_vault_v3.db')

print('--- Customers ---')
print_query(conn, 'SELECT id, name FROM customers')

print('--- Travellers ---')
print_query(conn, 'SELECT id, customer_id, name FROM travellers')

print('--- Trips ---')
print_query(conn, 'SELECT id, customer_id, trip_name FROM trips')

print('--- Trip Travellers ---')
print_query(conn, 'SELECT trip_id, traveller_id FROM trip_travellers')

print('--- Requirements for KT-T-0002 ---')
print_query(conn, "SELECT id, trip_id, name, traveller_id, expected_document_type FROM requirements WHERE trip_id = 'KT-T-0002'")

print('--- Documents for KT-T-0002 Requirements ---')
print_query(conn, "SELECT d.id, d.requirement_id, d.traveller_id, d.status FROM documents d JOIN requirements r ON d.requirement_id = r.id WHERE r.trip_id = 'KT-T-0002'")

print('--- Reusable Documents for KT-C-0002 ---')
print_query(conn, "SELECT id, requirement_id, traveller_id, customer_id, status FROM documents WHERE customer_id = 'KT-C-0002' AND trip_id IS NULL")
