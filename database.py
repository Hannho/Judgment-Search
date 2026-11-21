import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from dbutils.pooled_db import PooledDB

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "12345678") 
DB_NAME = os.getenv("DB_NAME", "judgment")         
DB_PORT = os.getenv("DB_PORT", "5432")

db_pool = PooledDB(
    creator=psycopg2,
    maxconnections=15,
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    dbname=DB_NAME,
    port=DB_PORT,
    cursor_factory=psycopg2.extras.DictCursor 
)

def get_db_connection():
    return db_pool.connection()

def run_sql(sql, params=(), fetch=False):
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()] if fetch else None
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_user_tables():
    run_sql("""
        CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS folders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(user_id, name)
        );
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            judgment_id TEXT NOT NULL,
            folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT now(),
            PRIMARY KEY (user_id, judgment_id)
        );
        CREATE TABLE IF NOT EXISTS highlights (
            user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            judgment_id TEXT NOT NULL,
            highlights_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (user_id, judgment_id)
        );
    """)

    run_sql("""
        CREATE TABLE IF NOT EXISTS api_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES app_users(id) ON DELETE SET NULL,
            endpoint TEXT NOT NULL,
            method TEXT NOT NULL,
            process_time FLOAT NOT NULL,
            status_code INTEGER NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now()
        );
    """)

    run_sql("""
        CREATE TABLE IF NOT EXISTS crawler_cache (
            judgment_id TEXT PRIMARY KEY,
            history_json TEXT NOT NULL DEFAULT '[]',
            laws_json TEXT NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ DEFAULT now()
        );
        CREATE TABLE IF NOT EXISTS sync_logs (
            id SERIAL PRIMARY KEY,
            sync_date VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            total_downloaded INTEGER DEFAULT 0,
            total_inserted INTEGER DEFAULT 0,
            total_skipped INTEGER DEFAULT 0,
            total_removed INTEGER DEFAULT 0,
            error_message TEXT,
            started_at TIMESTAMPTZ DEFAULT now(),
            finished_at TIMESTAMPTZ
        );
        ALTER TABLE sync_logs ADD COLUMN IF NOT EXISTS total_removed INTEGER DEFAULT 0;
    """)

def get_recent_sync_logs(limit=10):
    try:
        return run_sql("""
            SELECT id, sync_date, status, total_downloaded, total_inserted, total_skipped, total_removed,
                   error_message, started_at, finished_at
            FROM sync_logs
            ORDER BY id DESC
            LIMIT %s
        """, (limit,), fetch=True) or []
    except Exception:
        return []

def log_api_usage(user_id, endpoint, method, process_time, status_code, error_message=""):
    run_sql("""
        INSERT INTO api_logs (user_id, endpoint, method, process_time, status_code, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (user_id, endpoint, method, process_time, status_code, error_message))

def get_cached_crawler_data(judgment_id):
    try:
        rows = run_sql("SELECT history_json, laws_json FROM crawler_cache WHERE judgment_id = %s", (judgment_id,), fetch=True)
        if rows:
            return rows[0]
        return None
    except Exception:
        return None

def set_cached_crawler_data(judgment_id, history_json, laws_json):
    try:
        run_sql("""
            INSERT INTO crawler_cache (judgment_id, history_json, laws_json)
            VALUES (%s, %s, %s)
            ON CONFLICT (judgment_id) DO UPDATE
            SET history_json = EXCLUDED.history_json,
                laws_json = EXCLUDED.laws_json,
                created_at = now()
        """, (judgment_id, history_json, laws_json))
    except Exception as e:
        print(f"[crawler_cache] 快取寫入失敗: {e}")