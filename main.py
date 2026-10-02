import os
import json
import time
import asyncio
import psycopg2
import psycopg2.extras
import datetime
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv
import uvicorn
from dbutils.pooled_db import PooledDB

# 爬蟲相關套件
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# AI 相關套件（Ollama）
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

# 載入環境變數
load_dotenv()

app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 0. 資料庫連線設定 (本機 PostgreSQL 連線池)
# ==========================================
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

_stats_cache = {}
CACHE_TTL = 600  # 秒
MAX_CACHE_ITEMS = 200

def stats_cache_key(query: "JudgmentSearchQuery") -> str:
    d = query.model_dump(exclude={"page", "sort_type"})
    return json.dumps(d, sort_keys=True, ensure_ascii=False)

def get_db_connection():
    return db_pool.connection()

# ==========================================
# 1. 靜態檔案與共用邏輯
# ==========================================
@app.get("/")
def read_index():
    if os.path.exists("index_final.html"):
        return FileResponse("index_final.html")
    return {"message": "HTML template not found"}

@app.get("/style.css")
def get_css():
    if os.path.exists("style.css"):
        return FileResponse("style.css")
    return {"message": "style.css not found"}

class JudgmentSearchQuery(BaseModel):
    court: Optional[str] = ""
    start_date: Optional[str] = ""
    end_date: Optional[str] = ""
    keyword: Optional[str] = ""
    year: Optional[str] = ""
    title_kw: Optional[str] = ""
    content_kw: Optional[str] = ""
    main_text_kw: Optional[str] = ""
    page: int = 1
    sort_type: str = "date_desc"
    case_categories: List[str] = []
    doc_type: str = ""
    adv_case_type: str = ""
    adv_no_start: Optional[int] = None
    adv_no_end: Optional[int] = None
    adv_size_min: Optional[float] = None
    adv_size_max: Optional[float] = None

def build_search_conditions(query: JudgmentSearchQuery):
    where_clauses = ["1=1"]
    params = []

    if query.court:
        where_clauses.append("id LIKE %s")
        params.append(f"{query.court}%") 
    
    if query.start_date:
        where_clauses.append("date >= %s")
        params.append(query.start_date.replace('-', ''))
    if query.end_date:
        where_clauses.append("date <= %s")
        params.append(query.end_date.replace('-', ''))
    
    if query.year:
        if query.year == "其他年度":
            current_roc_year = datetime.datetime.now().year - 1911
            where_clauses.append("(year IS NULL OR year = '' OR CAST(NULLIF(year, '') AS INTEGER) <= %s)")
            params.append(current_roc_year - 3)
        else:
            where_clauses.append("year = %s")
            params.append(query.year)
    
    if query.keyword:
        for kw in query.keyword.split():
            where_clauses.append("(title LIKE %s OR content LIKE %s OR case_no LIKE %s OR id LIKE %s)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    
    if query.title_kw:
        for kw in query.title_kw.split():
            where_clauses.append("title LIKE %s")
            params.append(f"%{kw}%")

    if query.main_text_kw:
        for kw in query.main_text_kw.split():
            where_clauses.append("main_text LIKE %s")
            params.append(f"%{kw}%")
            
    if query.content_kw:
        s = query.content_kw.replace('+', ' + ').replace('-', ' - ').replace('&', ' & ').replace('(', ' ( ').replace(')', ' ) ')
        tokens = [t for t in s.split() if t.strip()]
        content_sql = []
        for i, token in enumerate(tokens):
            if token == '+': content_sql.append("OR")
            elif token == '&': content_sql.append("AND")
            elif token == '-':
                if not content_sql or content_sql[-1] == '(': content_sql.append("NOT")
                else: content_sql.append("AND NOT")
            elif token == '(':
                if i > 0 and tokens[i-1] not in ['+', '&', '-', '(']: content_sql.append("AND")
                content_sql.append("(")
            elif token == ')': content_sql.append(")")
            else:
                if i > 0 and tokens[i-1] not in ['+', '&', '-', '(']: content_sql.append("AND")
                content_sql.append("content LIKE %s")
                params.append(f"%{token}%")
        
        opens = content_sql.count('(')
        closes = content_sql.count(')')
        if opens > closes: content_sql.extend([")"] * (opens - closes))
        if content_sql: where_clauses.append(f"({' '.join(content_sql)})")

    if query.doc_type and query.doc_type in ["判決", "裁定"]:
        where_clauses.append("doc_type = %s")
        params.append(query.doc_type)

    if query.case_categories:
        placeholders = ", ".join(["%s"] * len(query.case_categories))
        where_clauses.append(f"case_category_name IN ({placeholders})")
        params.extend(query.case_categories)

    if query.adv_case_type:
        where_clauses.append("case_type LIKE %s")
        params.append(f"%{query.adv_case_type}%")
        
    if query.adv_no_start is not None:
        where_clauses.append("NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::int >= %s")
        params.append(query.adv_no_start)
    if query.adv_no_end is not None:
        where_clauses.append("NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::int <= %s")
        params.append(query.adv_no_end)
        
    if query.adv_size_min is not None:
        where_clauses.append("size_kb >= %s")
        params.append(query.adv_size_min)
    if query.adv_size_max is not None:
        where_clauses.append("size_kb <= %s")
        params.append(query.adv_size_max)

    where_sql = " WHERE " + " AND ".join(where_clauses)
    return where_sql, params

# ==========================================
# API 1：高速讀取前 10 筆資料 (包含 main_text)
# ==========================================
@app.post("/api/judgments/list")
def get_judgments_list(query: JudgmentSearchQuery):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            where_sql, params = build_search_conditions(query)
            
            order_clause = "ORDER BY date DESC"
            if query.sort_type == "date_asc": order_clause = "ORDER BY date ASC"
            elif query.sort_type == "no_desc": order_clause = "ORDER BY NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::int DESC NULLS LAST"
            elif query.sort_type == "no_asc": order_clause = "ORDER BY NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::int ASC NULLS LAST"
            elif query.sort_type == "size_desc": order_clause = "ORDER BY size_kb DESC"
            elif query.sort_type == "size_asc": order_clause = "ORDER BY size_kb ASC"
            
            limit = 10
            offset = (query.page - 1) * limit
            data_sql = f"SELECT id, year, case_type, case_no, date, title, content, pdf_url, main_text FROM judgments {where_sql} {order_clause} LIMIT %s OFFSET %s"
            
            cursor.execute(data_sql, tuple(params + [limit, offset]))
            results = [dict(row) for row in cursor.fetchall()]
        return {"data": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if conn: conn.close()

# ==========================================
# API 1-2：依判決 id 取回資料 (我的最愛 / 批次查詢用)
# ==========================================
class IdsQuery(BaseModel):
    ids: List[str]

@app.post("/api/judgments/by_ids")
def get_judgments_by_ids(q: IdsQuery):
    ids = q.ids[:200]
    if not ids:
        return {"data": []}
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, year, case_type, case_no, date, title, content, pdf_url, main_text "
                "FROM judgments WHERE id = ANY(%s)",
                (ids,)
            )
            rows = {r["id"]: dict(r) for r in cursor.fetchall()}
        return {"data": [rows[i] for i in ids if i in rows]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if conn: conn.close()

# ==========================================
# 使用者、資料夾、我的最愛 與 畫重點
# ==========================================
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
        -- 畫重點用資料表
        CREATE TABLE IF NOT EXISTS highlights (
            user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            judgment_id TEXT NOT NULL,
            highlights_json TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (user_id, judgment_id)
        );
    """)

@app.on_event("startup")
def on_startup():
    try:
        init_user_tables()
    except Exception as e:
        print(f"⚠️ 建立資料表失敗：{e}")

def get_uid(x_user_id: Optional[str]) -> int:
    if not x_user_id or not x_user_id.isdigit():
        raise HTTPException(status_code=401, detail="請先選擇使用者")
    return int(x_user_id)

class UserCreate(BaseModel):
    name: str

class FolderCreate(BaseModel):
    name: str

class FavIn(BaseModel):
    judgment_id: str
    folder_id: Optional[int] = None
    note: str = ""

class UserUpdate(BaseModel):
    name: str

class HighlightData(BaseModel):
    highlights: list

@app.get("/api/users")
def list_users():
    return {"data": run_sql("SELECT id, name FROM app_users ORDER BY id", fetch=True)}

@app.post("/api/users")
def create_user(u: UserCreate):
    name = u.name.strip()
    if not name or len(name) > 30:
        return JSONResponse(status_code=400, content={"error": "名稱需為 1 到 30 個字"})
    run_sql("INSERT INTO app_users (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))
    row = run_sql("SELECT id, name FROM app_users WHERE name = %s", (name,), fetch=True)[0]
    return {"user": row}

@app.put("/api/users/{user_id}")
def update_user(user_id: int, u: UserUpdate):
    name = u.name.strip()
    if not name or len(name) > 30:
        return JSONResponse(status_code=400, content={"error": "名稱需為 1 到 30 個字"})
    try:
        run_sql("UPDATE app_users SET name = %s WHERE id = %s", (name, user_id))
        return {"ok": True}
    except Exception as e:
        if "unique constraint" in str(e).lower():
            return JSONResponse(status_code=400, content={"error": "該使用者名稱已被其他人使用"})
        return JSONResponse(status_code=500, content={"error": "更新使用者失敗"})

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int):
    try:
        run_sql("DELETE FROM app_users WHERE id = %s", (user_id,))
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "刪除使用者失敗"})

# --- 資料夾 API ---
@app.get("/api/folders")
def list_folders(x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    rows = run_sql("SELECT id, name FROM folders WHERE user_id = %s ORDER BY id", (uid,), fetch=True)
    return {"data": rows}

@app.post("/api/folders")
def create_folder(f: FolderCreate, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    name = f.name.strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "資料夾名稱不能為空"})
    try:
        run_sql("INSERT INTO folders (user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (uid, name))
        row = run_sql("SELECT id, name FROM folders WHERE user_id = %s AND name = %s", (uid, name), fetch=True)[0]
        return {"folder": row}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "建立資料夾失敗"})

# --- 收藏 API ---
@app.get("/api/favorites")
def list_favorites(x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    rows = run_sql("""
        SELECT f.judgment_id, f.note, f.folder_id, fd.name as folder_name
        FROM favorites f
        LEFT JOIN folders fd ON f.folder_id = fd.id
        WHERE f.user_id = %s 
        ORDER BY f.created_at DESC
    """, (uid,), fetch=True)
    return {"data": rows}

@app.post("/api/favorites")
def add_favorite(f: FavIn, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    run_sql("""
        INSERT INTO favorites (user_id, judgment_id, folder_id, note) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (user_id, judgment_id) DO UPDATE 
        SET folder_id = EXCLUDED.folder_id, note = EXCLUDED.note
    """, (uid, f.judgment_id, f.folder_id, f.note[:500]))
    return {"ok": True}

@app.delete("/api/favorites")
def remove_favorite(judgment_id: str, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    run_sql("DELETE FROM favorites WHERE user_id = %s AND judgment_id = %s", (uid, judgment_id))
    return {"ok": True}

# --- 畫重點 API ---
@app.get("/api/highlights/{judgment_id}")
def get_highlights(judgment_id: str, x_user_id: Optional[str] = Header(None)):
    try:
        uid = get_uid(x_user_id)
        rows = run_sql("SELECT highlights_json FROM highlights WHERE user_id = %s AND judgment_id = %s", (uid, judgment_id), fetch=True)
        if rows:
            return {"data": json.loads(rows[0]["highlights_json"])}
        return {"data": []}
    except Exception:
        return {"data": []}

@app.post("/api/highlights/{judgment_id}")
def save_highlights(judgment_id: str, payload: HighlightData, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    hl_json = json.dumps(payload.highlights)
    run_sql("""
        INSERT INTO highlights (user_id, judgment_id, highlights_json) 
        VALUES (%s, %s, %s) 
        ON CONFLICT (user_id, judgment_id) DO UPDATE 
        SET highlights_json = EXCLUDED.highlights_json
    """, (uid, judgment_id, hl_json))
    return {"ok": True}

@app.delete("/api/highlights/{judgment_id}")
def clear_highlights(judgment_id: str, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    run_sql("DELETE FROM highlights WHERE user_id = %s AND judgment_id = %s", (uid, judgment_id))
    return {"ok": True}

# ==========================================
# API 2：背景計算統計與總數 (非同步載入)
# ==========================================
@app.post("/api/judgments/stats")
def get_judgments_stats(query: JudgmentSearchQuery):
    key = stats_cache_key(query)
    hit = _stats_cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            where_sql, params = build_search_conditions(query)
            facets = {"courts": {}, "years": {}, "categories": {}}

            if len(params) == 0:
                cursor.execute("SELECT reltuples::bigint AS total FROM pg_class WHERE relname = 'judgments';")
                schema_res = cursor.fetchone()
                total_count = schema_res['total'] if schema_res and schema_res['total'] > 0 else 1234303
            else:
                current_roc_year = datetime.datetime.now().year - 1911
                y_label = {
                    current_roc_year: f"今年 ({current_roc_year})",
                    current_roc_year - 1: f"去年 ({current_roc_year-1})",
                    current_roc_year - 2: f"前年 ({current_roc_year-2})",
                }
                y_stats = {v: 0 for v in y_label.values()}
                y_stats["其他年度"] = 0
                total_count = 0

                cursor.execute(f"""
                    SELECT year,
                           SUBSTRING(id, 1, 3) AS court,
                           case_category_name AS cat,
                           GROUPING(year) AS g_year,
                           GROUPING(SUBSTRING(id, 1, 3)) AS g_court,
                           GROUPING(case_category_name) AS g_cat,
                           COUNT(*) AS cnt
                    FROM judgments {where_sql}
                    GROUP BY GROUPING SETS ((year), (SUBSTRING(id, 1, 3)), (case_category_name), ())
                """, tuple(params))

                for row in cursor.fetchall():
                    if row["g_year"] == 0:
                        y_str = str(row["year"] or "").strip()
                        if y_str.isdigit() and int(y_str) in y_label:
                            y_stats[y_label[int(y_str)]] += row["cnt"]
                        else:
                            y_stats["其他年度"] += row["cnt"]
                    elif row["g_court"] == 0:
                        if row["court"]:
                            facets["courts"][row["court"]] = row["cnt"]
                    elif row["g_cat"] == 0:
                        if row["cat"] and row["cat"] != '其他':
                            facets["categories"][row["cat"]] = row["cnt"]
                    else:
                        total_count = row["cnt"]

                facets["years"] = {k: v for k, v in y_stats.items() if v > 0}

        result = {"total": total_count, "facets": facets}
        if len(_stats_cache) >= MAX_CACHE_ITEMS:
            _stats_cache.pop(next(iter(_stats_cache)))
        _stats_cache[key] = (time.time(), result)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if conn: conn.close()

# ==========================================
# 2. 歷審紀錄爬蟲 API (/api/get_history)
# ==========================================
class JudgmentRequest(BaseModel):
    id: str
    year: str
    case_type: str
    case_no: str
    date: str

COURT_MAPPING = {
    "TPS": "最高法院", "TPA": "最高行政法院", "TPC": "懲戒法院", "CPC": "司法院憲法法庭",
    "TPH": "臺灣高等法院", "TCH": "臺灣高等法院臺中分院", "TNH": "臺灣高等法院臺南分院",
    "KSH": "臺灣高等法院高雄分院", "HLH": "臺灣高等法院花蓮分院", "KMH": "福建高等法院金門分院",
    "TPB": "臺北高等行政法院", "TCB": "臺中高等行政法院", "KSB": "高雄高等行政法院",
    "TPD": "臺灣臺北地方法院", "SLD": "臺灣士林地方法院", "PCD": "臺灣新北地方法院",
    "TYD": "臺灣桃園地方法院", "SCD": "臺灣新竹地方法院", "MLD": "臺灣苗栗地方法院",
    "TCD": "臺灣臺中地方法院", "CHD": "臺灣彰化地方法院", "NTD": "臺灣南投地方法院",
    "YLD": "臺灣雲林地方法院", "CYD": "臺灣嘉義地方法院", "TND": "臺灣臺南地方法院",
    "KSD": "臺灣高雄地方法院", "PTD": "臺灣屏東地方法院", "TTD": "臺灣臺東地方法院",
    "HLD": "臺灣花蓮地方法院", "ILD": "臺灣宜蘭地方法院", "KLD": "臺灣基隆地方法院",
    "PHD": "臺灣澎湖地方法院", "KMD": "福建金門地方法院", "LCD": "福建連江地方法院",
    "CTD": "臺灣橋頭地方法院", "ULD": "臺灣雲林地方法院", 
    "TPE": "臺灣臺北地方法院臺北簡易庭", "SDE": "臺灣臺北地方法院新店簡易庭",
    "SLE": "臺灣士林地方法院士林簡易庭", "NIE": "臺灣士林地方法院內湖簡易庭", "NHE": "臺灣臺北地方法院內湖簡易庭",
    "PCE": "臺灣新北地方法院板橋簡易庭", "STE": "臺灣新北地方法院三重簡易庭",
    "KLE": "臺灣基隆地方法院基隆簡易庭", 
    "TYE": "臺灣桃園地方法院桃園簡易庭", "CLE": "臺灣桃園地方法院中壢簡易庭",
    "SJE": "臺灣新竹地方法院新竹簡易庭", "CDE": "臺灣新竹地方法院竹東簡易庭",
    "MLE": "臺灣苗栗地方法院苗栗簡易庭",
    "TCE": "臺灣臺中地方法院臺中簡易庭", "FYE": "臺灣臺中地方法院豐原簡易庭", "CSE": "臺灣臺中地方法院清水簡易庭", 
    "CHE": "臺灣彰化地方法院彰化簡易庭", "YLE": "臺灣彰化地方法院員林簡易庭", "PDE": "臺灣彰化地方法院北斗簡易庭", "OLE": "臺灣彰化地方法院員林簡易庭",
    "NTE": "臺灣南投地方法院南投簡易庭", "PLE": "臺灣南投地方法院埔里簡易庭",
    "ULE": "臺灣雲林地方法院雲林簡易庭", "TLE": "臺灣雲林地方法院斗六簡易庭", "HUE": "臺灣雲林地方法院虎尾簡易庭", "PKE": "臺灣雲林地方法院北港簡易庭",
    "CYE": "臺灣嘉義地方法院嘉義簡易庭", "PZE": "臺灣嘉義地方法院朴子簡易庭",
    "TNE": "臺灣臺南地方法院臺南簡易庭", "SYE": "臺灣臺南地方法院新營簡易庭", "SSE": "臺灣臺南地方法院新市簡易庭", "LYE": "臺灣臺南地方法院柳營簡易庭",
    "KSE": "臺灣高雄地方法院高雄簡易庭", "FSE": "臺灣高雄地方法院鳳山簡易庭", "GSE": "臺灣橋頭地方法院岡山簡易庭", "CCE": "臺灣橋頭地方法院橋頭簡易庭", "CTE": "臺灣橋頭地方法院橋頭簡易庭",
    "PTE": "臺灣屏東地方法院屏東簡易庭", "CPE": "臺灣屏東地方法院潮州簡易庭",
    "ILE": "臺灣宜蘭地方法院宜蘭簡易庭", "LTE": "臺灣宜蘭地方法院羅東簡易庭",
    "HLE": "臺灣花蓮地方法院花蓮簡易庭", 
    "TTE": "臺灣臺東地方法院臺東簡易庭",
    "MKE": "臺灣澎湖地方法院馬公簡易庭", 
    "KME": "福建金門地方法院金城簡易庭", 
    "LCE": "福建連江地方法院連江簡易庭",
    "KSY": "臺灣高雄少年及家事法院", "IPC": "智慧財產及商業法院"
}

@app.post("/api/get_history")
def get_history(req: JudgmentRequest):
    court_code = req.id.split(",")[0][:3]
    court_name = COURT_MAPPING.get(court_code, "未知法院")
    
    tw_year = str(int(req.date[:4]) - 1911)
    target_date_str = f"{tw_year}.{req.date[4:6]}.{req.date[6:8]}"
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-notifications')
    options.add_argument('--single-process')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    if os.path.exists("/usr/bin/chromedriver"):
        service = Service("/usr/bin/chromedriver")
    elif os.path.exists("/usr/lib/chromium-browser/chromedriver"):
        service = Service("/usr/lib/chromium-browser/chromedriver")
    else:
        service = Service(ChromeDriverManager().install())
        
    driver = None
    history_results = []
    
    try:
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 12)
        
        driver.get("https://judgment.judicial.gov.tw/FJUD/default.aspx")
        
        search_query = f"{court_name}{req.year}{req.case_type}{req.case_no}"
        search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[placeholder*='可輸入法院名稱']")))
        search_input.clear()
        search_input.send_keys(search_query)
        search_input.send_keys(Keys.RETURN)

        wait.until(EC.frame_to_be_available_and_switch_to_it((By.ID, "iframe-data")))
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        
        xpath_query = f"//tr[td[contains(text(), '{target_date_str}')]]//a"
        exact_match_link = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_query)))
        exact_match_link.click()
            
        history_links = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.panel-body ul li a[href*='data.aspx']")))
        for link in history_links:
            title = link.text.strip()
            url = link.get_attribute("href")
            if not url.startswith("http"):
                url = "https://judgment.judicial.gov.tw/FJUD/" + url
            history_results.append({"title": title, "url": url})
            
    except Exception as e:
        print(f"❌ 爬蟲發生錯誤: {e}")
    finally:
        if driver:
            driver.quit()
        
    return {"history": history_results}

# ==========================================
# 3. AI 智慧分析 API (/api/ask_multiple)
# ==========================================
class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

classify_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的台灣法院書記官。請根據以下裁判書的開頭與內容，判斷這是哪一種案件類別。\n"
               "你只能從以下選項中回答一個詞：【民事】、【刑事】、【行政】、【懲戒】、【憲法】。\n"
               "請直接輸出該詞彙，不要加上任何標點符號或其他解釋文字。"),
    ("human", "【裁判書開頭內容】：\n{text}")
])

civil_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇民事裁判書】中精精確擷取資訊。\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、案件事實經過：（原被告發生何事、爭議經過、受損情形）\n"
               "二、原告請求：（各項請求項目與各自金額）\n"
               "三、法院認定結果：（准許金額、駁回金額）\n"
               "四、法院裁判理由：（准許或駁回理由、單據審核、折舊、過失相抵比例等）\n"
               "五、核心關鍵考量因素："),
    ("human", "【單篇裁判書內容】：\n{single_case_text}")
])

criminal_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇刑事裁判書】中精確擷取資訊。\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、犯罪事實經過：（被告做了何事、犯罪手法、被害人受害情形）\n"
               "二、檢察官起訴法條與罪名：\n"
               "三、法院認定結果：（宣告罪名、宣告刑度、是否緩刑或易科罰金、沒收情形）\n"
               "四、法院量刑理由：（法定加減刑條件、犯後態度、和解情形、犯罪動機等）\n"
               "五、核心關鍵考量因素："),
    ("human", "【單篇裁判書內容】：\n{single_case_text}")
])

generic_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇裁判書】中精確擷取資訊。\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、案件背景事實：\n"
               "二、當事人主張：\n"
               "三、法院認定結果：\n"
               "四、法院裁判理由：\n"
               "五、核心關鍵考量因素："),
    ("human", "【單篇裁判書內容】：\n{single_case_text}")
])

civil_reduce_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一個專門分析中華民國【民事判決】的司法 AI。
請嚴格根據提供的判決內容回答問題，不得自行捏造事實。
分析多個案件時，必須進行比較。

【逐案分析格式】
【案件一】判決字號：
一、案件事實
二、原告請求金額與項目
三、法院最後核准金額
四、法院判斷理由 (准駁原因、過失比例、折舊等)
五、影響結果的關鍵因素

【案件比較表格】
| 比較項目 | 案件一 | 案件二 | 案件三 |
|---|---|---|---|
| 案件事實 | | | |
| 原告請求 | | | |
| 法院准許金額 | | | |
| 法院考量要點 | | | |

【綜合分析與回答】
1. 整理多數判決的共通標準
2. 說明導致金額差異的原因
3. 直接回答使用者的問題
【提供的判決資料】：\n{context}"""),
    ("human", "{input}")
])

criminal_reduce_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一個專門分析中華民國【刑事判決】的司法 AI。
請嚴格根據提供的判決內容回答問題，不得自行捏造事實。
分析多個案件時，必須進行比較。

【逐案分析格式】
【案件一】判決字號：
一、犯罪事實
二、檢察官起訴與被告抗辯
三、法院判決結果 (罪名、刑度、緩刑、易科罰金)
四、法院量刑理由 (犯後態度、和解、犯罪動機)
五、影響刑度的關鍵因素

【案件比較表格】
| 比較項目 | 案件一 | 案件二 | 案件三 |
|---|---|---|---|
| 犯罪事實 | | | |
| 被告態度與和解 | | | |
| 宣告罪名 | | | |
| 判決刑度 | | | |
| 是否緩刑/易科罰金 | | | |

【綜合分析與回答】
1. 整理多數判決的量刑趨勢
2. 說明導致刑度輕重差異的關鍵因素
3. 直接回答使用者的問題
【提供的判決資料】：\n{context}"""),
    ("human", "{input}")
])

generic_reduce_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一個專門分析中華民國法院判決的司法 AI。
請嚴格根據提供的判決內容回答問題，不得自行捏造事實。

【逐案分析格式】
【案件一】判決字號：
一、案件背景事實
二、雙方主張
三、法院認定結果
四、法院裁判理由
五、關鍵考量因素

【案件比較表格】
| 比較項目 | 案件一 | 案件二 | 案件三 |
|---|---|---|---|
| 案件事實 | | | |
| 當事人主張 | | | |
| 法院認定 | | | |
| 判決理由 | | | |

【綜合分析與回答】
直接回答使用者的問題，並說明結論來自哪些案件的證據。
【提供的判決資料】：\n{context}"""),
    ("human", "{input}")
])

@app.post("/api/ask_multiple")
async def ask_ai_multiple(query: MultiQAQuery):
    if not query.judgments_content:
        return {"answer": "目前沒有任何案件資料可供閱讀。"}

    try:
        llm = ChatOllama(
            model="taide-law",
            base_url=OLLAMA_BASE_URL,
            temperature=0.1
        )

        valid_cases = [c.strip() for c in query.judgments_content if c and c.strip()][:10]
        if not valid_cases:
            return {"answer": "提供的判決內容為空，無法進行分析。"}

        sample_text = valid_cases[0][:1000]
        classify_chain = classify_prompt | llm
        try:
            category_res = await classify_chain.ainvoke({"text": sample_text})
            category = category_res.content.strip()
        except Exception as e:
            category = "未知"

        if "刑事" in category:
            map_chain = criminal_map_prompt | llm
            reduce_chain = criminal_reduce_prompt | llm
        elif "民事" in category:
            map_chain = civil_map_prompt | llm
            reduce_chain = civil_reduce_prompt | llm
        else:
            map_chain = generic_map_prompt | llm
            reduce_chain = generic_reduce_prompt | llm

        extracted_summaries = []
        for idx, content in enumerate(valid_cases):
            header = content[:200]
            core_reason = ""
            
            for kw in ["得心證之理由", "事實及理由", "理    由", "理  由", "理由："]:
                if kw in content:
                    core_reason = content.split(kw, 1)[1]
                    break
            
            if not core_reason:
                core_reason = content[200:]

            clean_case_text = f"{header}\n\n【核心裁判理由】\n{core_reason[:2000]}"

            try:
                summary_res = await map_chain.ainvoke({"single_case_text": clean_case_text})
                extracted_summaries.append(f"=== 【案件 {idx+1} 抽取資料】 ===\n{summary_res.content}\n")
            except Exception as single_err:
                extracted_summaries.append(f"=== 【案件 {idx+1} 抽取資料】 ===\n（此案件抽取失敗，略過）\n")

        combined_context = "\n".join(extracted_summaries)

        final_response = await reduce_chain.ainvoke({
            "context": combined_context,
            "input": query.question
        })

        return {"answer": final_response.content}

    except Exception as e:
        return {"answer": f"本地 AI 處理失敗，錯誤詳情：{str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)