import sqlite3
import os
from datetime import datetime

# Define the database path relative to the project root
# Assuming the script runs from the project root or src directory
# Adjust if necessary based on final execution context
DB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data'))
DB_PATH = os.path.join(DB_DIR, 'history.db')

def init_db():
    """Initializes the database and creates the history table if it doesn't exist."""
    # Ensure the data directory exists
    os.makedirs(DB_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table with a unique constraint on (image_path, sign_text, print_text)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            image_path TEXT NOT NULL,
            sign_text TEXT,
            print_text TEXT,
            similarity REAL,
            result TEXT
            , UNIQUE(image_path, sign_text, print_text)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

def add_history_record(image_path: str, sign_text: str, print_text: str, similarity: float, result: str):
    """Adds a new record to the history table, ignoring duplicates based on the unique constraint."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Use INSERT OR IGNORE to handle the unique constraint gracefully
    cursor.execute('''
        INSERT OR IGNORE INTO history (timestamp, image_path, sign_text, print_text, similarity, result)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (timestamp, image_path, sign_text, print_text, similarity, result))
    
    conn.commit()
    conn.close()

def get_all_history():
    """Fetches all records from the history table, ordered by timestamp descending."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch all records, newest first
    cursor.execute("SELECT timestamp, image_path, sign_text, print_text, similarity, result FROM history ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    
    conn.close()
    return rows

# Example usage (for testing)
if __name__ == '__main__':
    init_db()
    # Example insert - duplicates based on (image_path, sign_text, print_text) will be ignored
    add_history_record('/path/to/image1.jpg', 'ABC', 'ABC', 1.0, '通过')
    add_history_record('/path/to/image1.jpg', 'ABC', 'ABC', 1.0, '通过') # Ignored
    add_history_record('/path/to/image2.jpg', 'DEF', 'DEG', 0.8, '不通过')
    add_history_record('/path/to/image1.jpg', 'ABC', 'ABD', 0.9, '不通过') # Added (different print_text)
    
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
