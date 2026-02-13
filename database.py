"""
Database Connection Helper
--------------------------
This file handles the connection to our SQLite database ('quiz.db').

Why do we need a separate file?
- It keeps our code clean (Separation of Concerns).
- We can import `get_db_connection` in `app.py` or any other script.
- It ensures we always connect with the same settings (like row_factory).

What is SQLite?
- It's a lightweight database that saves everything in a single file (quiz.db).
- No need to install a big server like MySQL or PostgreSQL.
"""

import sqlite3

def get_db_connection():
    """
    Establishes a connection to the 'quiz.db' SQLite database file.
    
    Returns:
        conn (sqlite3.Connection): The connection object used to interact with the database.
    """
    
    # Connect to the file 'quiz.db'. If it doesn't exist, SQLite creates it automatically.
    conn = sqlite3.connect('quiz.db')
    
    # Set row_factory to sqlite3.Row.
    # This allows us to access columns by name (e.g., row['email']) instead of index (row[2]).
    # It makes the code much more readable!
    conn.row_factory = sqlite3.Row
    
    return conn
