import os
import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "cabinet_medical"),
    "user": os.getenv("DB_USER", "cabinet_user"),
    "password": os.getenv("DB_PASSWORD", "BabaMouneissa2026!"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5433"),
}

def get_db():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        conn = psycopg2.connect(database_url)
    else:
        conn = psycopg2.connect(**DB_CONFIG)

    conn.cursor_factory = psycopg2.extras.RealDictCursor
    try:
        yield conn
    finally:
        conn.close()
