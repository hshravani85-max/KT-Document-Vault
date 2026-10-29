import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kt_vault_v3.db')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    c = conn.cursor()
    
    c.executescript('''
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            name TEXT,
            customer_type TEXT,
            status TEXT
        );
        CREATE TABLE IF NOT EXISTS travellers (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            name TEXT,
            type TEXT,
            role TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            customer_id TEXT,
            name TEXT,
            destination TEXT,
            start_date TEXT,
            end_date TEXT,
            trip_type TEXT,
            service TEXT,
            department TEXT,
            status TEXT,
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        );
        CREATE TABLE IF NOT EXISTS trip_travellers (
            trip_id TEXT,
            traveller_id TEXT,
            PRIMARY KEY(trip_id, traveller_id),
            FOREIGN KEY(trip_id) REFERENCES trips(id),
            FOREIGN KEY(traveller_id) REFERENCES travellers(id)
        );
        CREATE TABLE IF NOT EXISTS requirements (
            id TEXT PRIMARY KEY,
            trip_id TEXT,
            traveller_id TEXT,
            name TEXT,
            type TEXT,
            UNIQUE(trip_id, traveller_id, name)
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            requirement_id TEXT,
            status TEXT,
            extracted_data TEXT,
            file_path TEXT,
            uploaded_at TEXT,
            FOREIGN KEY(requirement_id) REFERENCES requirements(id)
        );
        CREATE TABLE IF NOT EXISTS user_profile (
            customer_id TEXT PRIMARY KEY,
            full_name TEXT,
            dob TEXT,
            nationality TEXT,
            passport_number TEXT,
            passport_expiry TEXT
        );
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trip_id TEXT,
            customer_id TEXT,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    
    # Safely apply migrations for V3 onboarding requirements
    try:
        c.execute("ALTER TABLE customers ADD COLUMN mobile TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE customers ADD COLUMN email TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE travellers ADD COLUMN dob TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE travellers ADD COLUMN relationship TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE activity ADD COLUMN customer_id TEXT")
    except sqlite3.OperationalError:
        pass
    
    c.execute("INSERT OR IGNORE INTO customers (id, name, customer_type, status) VALUES (?, ?, ?, ?)",
              ('KT-C-0001', 'Amit Mehta', 'Individual', 'Active'))
    
    c.execute("INSERT OR IGNORE INTO travellers (id, customer_id, name, type, role) VALUES (?, ?, ?, ?, ?)",
              ('KT-TR-0001', 'KT-C-0001', 'Amit Mehta', 'Adult', 'Lead Traveller'))
              
    c.execute("INSERT OR IGNORE INTO trips (id, customer_id, name, destination, start_date, end_date, trip_type, service, department, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              ('KT-T-0001', 'KT-C-0001', 'Dubai Holiday', 'Dubai, UAE', '2026-12-12', '2026-12-18', 'Holiday', 'International Package', 'Operations', 'Documents In Progress'))
              
    c.execute("INSERT OR IGNORE INTO trip_travellers (trip_id, traveller_id) VALUES (?, ?)",
              ('KT-T-0001', 'KT-TR-0001'))
              
    reqs = [
        ('REQ-TR-01', 'KT-T-0001', 'KT-TR-0001', 'Passport', 'TRAVELLER'),
        ('REQ-TR-02', 'KT-T-0001', 'KT-TR-0001', 'Visa / Entry Document', 'TRAVELLER'),
        ('REQ-T-01', 'KT-T-0001', None, 'Flight Ticket', 'TRIP'),
        ('REQ-T-02', 'KT-T-0001', None, 'Hotel Voucher', 'TRIP'),
        ('REQ-T-03', 'KT-T-0001', None, 'Travel Insurance', 'TRIP'),
        ('REQ-T-04', 'KT-T-0001', None, 'Transfer Voucher', 'TRIP'),
        ('REQ-T-05', 'KT-T-0001', None, 'Sightseeing Voucher', 'TRIP'),
        ('REQ-T-06', 'KT-T-0001', None, 'Arrival / Entry Document', 'TRIP'),
        ('REQ-T-07', 'KT-T-0001', None, 'Itinerary', 'TRIP')
    ]
    for r in reqs:
        c.execute("INSERT OR IGNORE INTO requirements (id, trip_id, traveller_id, name, type) VALUES (?, ?, ?, ?, ?)", r)
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
