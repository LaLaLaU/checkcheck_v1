import sqlite3
import os
from datetime import datetime

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
    os.makedirs(DB_DIR, exist_ok=True)
    conn = _connect()
    cursor = conn.cursor()
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
    # Try migrate old columns if present
    try:
        cursor.execute("PRAGMA table_info(history)")
        cols = [row[1] for row in cursor.fetchall()]
        old_cols = {"sign_text", "print_text", "similarity", "result"}
        if old_cols.issubset(set(cols)):
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    main_code TEXT,
                    head_code TEXT
                )
            ''')
            cursor.execute('''
                INSERT INTO history_new (id, timestamp, image_path, main_code, head_code)
                SELECT id, timestamp, image_path, sign_text, print_text FROM history
            ''')
            conn.commit()
            cursor.execute('DROP TABLE history')
            cursor.execute('ALTER TABLE history_new RENAME TO history')
            conn.commit()
    except Exception:
        pass
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def add_history_record(image_path: str, main_code: str, head_code: str):
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
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, image_path, main_code, head_code FROM history ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_history_records(keys):
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
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT 1 FROM history WHERE main_code = ? AND head_code = ? LIMIT 1
    ''', (main_code, head_code))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

if __name__ == '__main__':
    init_db()
    add_history_record('/path/to/image1.jpg', 'ABCD.1234.E.888.999', 'BG23')
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM history")
    rows = cursor.fetchall()
    print("\nCurrent History Records:")
    for row in rows:
        print(row)
    conn.close()
    print("\nFetching all history (newest first):")
    all_records = get_all_history()
    for record in all_records:
        print(record)
