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
        -- (保留你原有的 app_users, folders 等資料表)
        
        CREATE TABLE IF NOT EXISTS api_logs (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES app_users(id) ON DELETE SET NULL, -- 若無登入可為 NULL
            endpoint TEXT NOT NULL,       -- 呼叫的 API 路徑 (例如 /search)
            method TEXT NOT NULL,         -- HTTP 方法 (GET, POST)
            process_time FLOAT NOT NULL,  -- 處理速度 (秒)
            status_code INTEGER NOT NULL, -- HTTP 狀態碼 (200, 500 等)
            error_message TEXT,           -- 錯誤訊息 (若有的話)
            created_at TIMESTAMPTZ DEFAULT now() -- 發生時間
        );
    """)
def log_api_usage(user_id, endpoint, method, process_time, status_code, error_message=""):
    run_sql("""
        INSERT INTO api_logs (user_id, endpoint, method, process_time, status_code, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (user_id, endpoint, method, process_time, status_code, error_message))