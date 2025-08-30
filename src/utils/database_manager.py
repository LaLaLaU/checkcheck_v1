import sqlite3
import os
from datetime import datetime

# Define the database path relative to the project root
# Assuming the script runs from the project root or src directory
# Adjust if necessary based on final execution context
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
DB_PATH = os.path.join(DB_DIR, 'history.db')

def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    try:
        cur = conn.cursor()
        cur.execute('PRAGMA journal_mode=WAL;')
        cur.execute('PRAGMA synchronous=NORMAL;')
        conn.commit()
    except Exception:
        pass
    return conn

def init_db():
    """Initializes the database. If old schema is detected, migrates to the new schema.

    New schema (v2): history(id, timestamp, image_path, main_code, head_code)
    """
    os.makedirs(DB_DIR, exist_ok=True)

    conn = _connect()
    cursor = conn.cursor()

    # Create table if not exists (new schema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            image_path TEXT NOT NULL,
            main_code TEXT,
            head_code TEXT
        )
    ''')
    conn.commit()

    # Detect old columns to migrate if necessary
    try:
        cursor.execute("PRAGMA table_info(history)")
        cols = [row[1] for row in cursor.fetchall()]
        old_cols = {"sign_text", "print_text", "similarity", "result"}
        if old_cols.issubset(set(cols)):
            # Migration path: create new table, copy data, drop old, rename new
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    main_code TEXT,
                    head_code TEXT
                )
            ''')
            # Copy old data: map sign_text -> main_code, print_text -> head_code
            cursor.execute('''
                INSERT INTO history_new (id, timestamp, image_path, main_code, head_code)
                SELECT id, timestamp, image_path, sign_text, print_text FROM history
            ''')
            conn.commit()
            cursor.execute('DROP TABLE history')
            cursor.execute('ALTER TABLE history_new RENAME TO history')
            conn.commit()
    except Exception:
        # If PRAGMA fails or any issue occurs, keep the created new schema
        pass

    conn.close()
    print(f"Database initialized at {DB_PATH}")

def add_history_record(image_path: str, main_code: str, head_code: str):
    """Adds a new record (timestamp, image_path, main_code, head_code)."""
    conn = _connect()
    cursor = conn.cursor()

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute('''
        INSERT INTO history (timestamp, image_path, main_code, head_code)
        VALUES (?, ?, ?, ?)
    ''', (timestamp, image_path, main_code, head_code))

    conn.commit()
    conn.close()

def get_all_history():
    """Fetches all records (timestamp, image_path, main_code, head_code) newest first."""
    conn = _connect()
    cursor = conn.cursor()

    cursor.execute("SELECT timestamp, image_path, main_code, head_code FROM history ORDER BY id DESC")
    rows = cursor.fetchall()

    conn.close()
    return rows

def delete_history_records(keys):
    """Delete records by (timestamp, image_path, main_code, head_code).
    keys: list of tuples (timestamp, image_path, main_code, head_code)
    """
    if not keys:
        return
    conn = _connect()
    cursor = conn.cursor()
    try:
        for ts, img, main_code, head_code in keys:
            cursor.execute(
                "DELETE FROM history WHERE timestamp=? AND image_path=? AND main_code=? AND head_code=?",
                (ts, img, main_code, head_code)
            )
        conn.commit()
    finally:
        conn.close()

def check_history_exists(main_code: str, head_code: str) -> bool:
    """Checks if a record with the exact same codes exists for latest image path is not required here.
    For compatibility, simply checks for any row with same codes in recent entries.
    """
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM history WHERE main_code = ? AND head_code = ? LIMIT 1
    ''', (main_code, head_code))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

# Example usage (for testing)
if __name__ == '__main__':
    init_db()
    add_history_record('/path/to/image1.jpg', 'ABCD.1234.E.888.999', 'BG23')
    # Verify content (optional)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM history")
    rows = cursor.fetchall()
    print("\nCurrent History Records:")
    for row in rows:
        print(row)
    conn.close()
    # Test get_all_history
    print("\nFetching all history (newest first):")
    all_records = get_all_history()
    for record in all_records:
        print(record)
