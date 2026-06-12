import psycopg2
import psycopg2.extras
import os

DB_CONFIG = {
    "dbname": "cabinet_medical",
    "user": "cabinet_user",
    "password": "BabaMouneissa2026!",
    "host": "localhost",
    "port": "5432"
}

def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        yield conn
    finally:
        conn.close()
