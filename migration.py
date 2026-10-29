import sqlite3

def migrate_db():
    conn = sqlite3.connect('data/kt_vault_v3.db')
    cursor = conn.cursor()
    
    # Check if document_history exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='document_history'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE document_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT,
                event_type TEXT,
                previous_status TEXT,
                new_status TEXT,
                actor TEXT,
                reason TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(document_id) REFERENCES documents(id)
            )
        ''')
        print("Created document_history table.")
    else:
        print("document_history table already exists.")
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    migrate_db()
