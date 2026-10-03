import json
import time
import datetime
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from database import get_db_connection

router = APIRouter()

_stats_cache = {}
CACHE_TTL = 600
MAX_CACHE_ITEMS = 200

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

class IdsQuery(BaseModel):
    ids: List[str]

def stats_cache_key(query: JudgmentSearchQuery) -> str:
    d = query.model_dump(exclude={"page", "sort_type"})
    return json.dumps(d, sort_keys=True, ensure_ascii=False)

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

@router.post("/list")
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
            data_sql = f"SELECT id, year, case_type, case_no, date, title, content, pdf_url, main_text, reason FROM judgments {where_sql} {order_clause} LIMIT %s OFFSET %s"
            
            cursor.execute(data_sql, tuple(params + [limit, offset]))
            results = [dict(row) for row in cursor.fetchall()]
        return {"data": results}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if conn: conn.close()

@router.post("/by_ids")
def get_judgments_by_ids(q: IdsQuery):
    ids = q.ids[:200]
    if not ids:
        return {"data": []}
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, year, case_type, case_no, date, title, content, pdf_url, main_text, reason "
                "FROM judgments WHERE id = ANY(%s)",
                (ids,)
            )
            rows = {r["id"]: dict(r) for r in cursor.fetchall()}
        return {"data": [rows[i] for i in ids if i in rows]}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        if conn: conn.close()

@router.post("/stats")
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