import json
import time
import datetime
import re
from collections import Counter
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from database import get_db_connection

router = APIRouter()

_stats_cache = {}
CACHE_TTL = 1800
MAX_CACHE_ITEMS = 1000

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
    synonyms_expand: bool = False

# 常用法學關鍵詞同義詞辭典
LEGAL_SYNONYMS = {
    "車禍": ["車禍", "交通事故", "過失傷害", "肇事", "道路交通", "過失致死"],
    "交通事故": ["車禍", "交通事故", "過失傷害", "道路交通"],
    "借錢": ["借錢", "消費借貸", "清償借款", "返還借款", "借貸", "借據"],
    "借貸": ["借錢", "消費借貸", "清償借款", "返還借款", "借款"],
    "欠錢": ["欠款", "清償借款", "給付票款", "返還借款", "本票"],
    "離婚": ["離婚", "夫妻財產", "剩餘財產分配", "監護權", "親權", "侵害配偶權"],
    "外遇": ["侵害配偶權", "配偶身分法益", "通姦", "不正常男女交往"],
    "遺產": ["遺產", "繼承權", "特留分", "應繼分", "遺囑", "分割遺產"],
    "詐欺": ["詐欺", "詐騙", "洗錢防制法", "人頭帳戶", "車手", "加重詐欺"],
    "洗錢": ["洗錢防制法", "人頭帳戶", "詐欺取財", "洗錢"],
    "租屋": ["租賃", "租屋", "房屋租賃", "遷讓房屋", "給付租金", "押租金"],
    "房租": ["租金", "給付租金", "遷讓房屋", "租賃契約", "押金"],
    "資遣": ["資遣費", "勞基法", "勞動基準法", "非自願離職", "預告期間工資"],
    "開除": ["終止勞動契約", "確認僱傭關係", "非法解雇", "解僱", "勞資爭議"],
    "薪水": ["給付工資", "薪資", "工資", "加班費", "勞基法"],
    "毒品": ["毒品危害防制條例", "施用毒品", "販賣毒品", "持有毒品", "第二級毒品"],
    "妨害名譽": ["公然侮辱", "誹謗", "加重誹謗", "妨害名譽", "名譽權"],
    "罵人": ["公然侮辱", "誹謗", "妨害名譽", "名譽權損害"],
    "賠償": ["損害賠償", "侵權行為", "國家賠償", "精神慰撫金"],
    "違約": ["違約金", "債務不履行", "給付遲延", "解除契約", "損害賠償"],
    "房屋買賣": ["物之瑕疵擔保", "減少價金", "解除契約", "買賣價金", "違章建築"],
    "漏水": ["房屋漏水", "修繕義務", "物之瑕疵", "侵權行為損害賠償"]
}

class IdsQuery(BaseModel):
    ids: List[str]

def stats_cache_key(query: JudgmentSearchQuery) -> str:
    d = query.model_dump(exclude={"page", "sort_type"})
    return json.dumps(d, sort_keys=True, ensure_ascii=False)

def build_search_conditions(query: JudgmentSearchQuery):
    where_clauses = ["1=1"]
    params = []

    if query.court:
        if len(query.court) == 3:
            where_clauses.append("SUBSTRING(id, 1, 3) = %s")
            params.append(query.court)
        else:
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
            clean_kw = kw.strip()
            if not clean_kw:
                continue
            if query.synonyms_expand and clean_kw in LEGAL_SYNONYMS:
                syn_list = LEGAL_SYNONYMS[clean_kw]
                syn_subclauses = []
                for s in syn_list:
                    syn_subclauses.append("(title LIKE %s OR content LIKE %s OR case_no LIKE %s OR id LIKE %s)")
                    params.extend([f"%{s}%", f"%{s}%", f"%{s}%", f"%{s}%"])
                where_clauses.append("(" + " OR ".join(syn_subclauses) + ")")
            else:
                where_clauses.append("(title LIKE %s OR content LIKE %s OR case_no LIKE %s OR id LIKE %s)")
                params.extend([f"%{clean_kw}%", f"%{clean_kw}%", f"%{clean_kw}%", f"%{clean_kw}%"])
    
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
        param_count_before = len(params)
        for i, token in enumerate(tokens):
            if token == '+':
                if content_sql and content_sql[-1] not in ['AND', 'OR', 'NOT', 'AND NOT', '(']:
                    content_sql.append("OR")
            elif token == '&':
                if content_sql and content_sql[-1] not in ['AND', 'OR', 'NOT', 'AND NOT', '(']:
                    content_sql.append("AND")
            elif token == '-':
                if not content_sql or content_sql[-1] == '(':
                    content_sql.append("NOT")
                elif content_sql[-1] not in ['AND', 'OR', 'NOT', 'AND NOT']:
                    content_sql.append("AND NOT")
            elif token == '(':
                if i > 0 and content_sql and content_sql[-1] not in ['AND', 'OR', 'NOT', 'AND NOT', '(']:
                    content_sql.append("AND")
                content_sql.append("(")
            elif token == ')':
                if content_sql and content_sql[-1] not in ['AND', 'OR', 'NOT', 'AND NOT', '(']:
                    content_sql.append(")")
            else:
                if i > 0 and content_sql and content_sql[-1] not in ['AND', 'OR', 'NOT', 'AND NOT', '(']:
                    content_sql.append("AND")
                content_sql.append("content LIKE %s")
                params.append(f"%{token}%")

        while content_sql and content_sql[-1] in ['AND', 'OR', 'NOT', 'AND NOT', '(']:
            content_sql.pop()

        opens = content_sql.count('(')
        closes = content_sql.count(')')
        if opens > closes:
            content_sql.extend([")"] * (opens - closes))
        elif closes > opens:
            diff = closes - opens
            new_sql = []
            for item in content_sql:
                if item == ')' and diff > 0:
                    diff -= 1
                    continue
                new_sql.append(item)
            content_sql = new_sql

        if content_sql and any("content LIKE" in item for item in content_sql):
            where_clauses.append(f"({' '.join(content_sql)})")
        else:
            del params[param_count_before:]

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
        where_clauses.append("NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::bigint >= %s")
        params.append(query.adv_no_start)
    if query.adv_no_end is not None:
        where_clauses.append("NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::bigint <= %s")
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
            # 8 秒安全超時，防止長文 LIKE 掃描耗盡連線池
            cursor.execute("SET statement_timeout = 8000;")
            where_sql, params = build_search_conditions(query)
            
            order_clause = "ORDER BY date DESC"
            if query.sort_type == "date_asc": order_clause = "ORDER BY date ASC"
            elif query.sort_type == "no_desc": order_clause = "ORDER BY NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::bigint DESC NULLS LAST"
            elif query.sort_type == "no_asc": order_clause = "ORDER BY NULLIF(SUBSTRING(case_no FROM '^[0-9]+'), '')::bigint ASC NULLS LAST"
            elif query.sort_type == "size_desc": order_clause = "ORDER BY size_kb DESC"
            elif query.sort_type == "size_asc": order_clause = "ORDER BY size_kb ASC"
            
            limit = 10
            offset = (query.page - 1) * limit
            data_sql = f"SELECT id, year, case_type, case_no, date, title, content, pdf_url, main_text, reason FROM judgments {where_sql} {order_clause} LIMIT %s OFFSET %s"
            
            cursor.execute(data_sql, tuple(params + [limit, offset]))
            results = [dict(row) for row in cursor.fetchall()]
        return {"data": results}
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[stats] 統計計算發生異常或超時，安全降級: {e}")
        return {"total": 0, "facets": {"courts": {}, "years": {}, "categories": {}}}
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
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[stats] 統計計算發生異常或超時，安全降級: {e}")
        return {"total": 0, "facets": {"courts": {}, "years": {}, "categories": {}}}
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
            # 8 秒安全超時，防止統計大型查詢阻塞連線池
            cursor.execute("SET statement_timeout = 8000;")
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
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[stats] 統計計算發生異常或超時，安全降級: {e}")
        return {"total": 0, "facets": {"courts": {}, "years": {}, "categories": {}}}
    finally:
        if conn: conn.close()

# ==============================================================================
# 法官心證風格畫像與傾向統計 (Judge Analytics) & 損害賠償行情分析 (Compensation Analytics)
# ==============================================================================

CN_NUM = {
    '零': 0, '一': 1, '二': 2, '兩': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
    '壹': 1, '貳': 2, '參': 3, '肆': 4, '伍': 5, '陸': 6, '柒': 7, '捌': 8, '玖': 9,
    '拾': 10, '十': 10, '佰': 100, '百': 100, '仟': 1000, '千': 1000, '萬': 10000, '億': 100000000
}

COURT_NAME_MAP = {
    "TPH": "臺灣高等法院", "TPD": "臺北地方法院", "PCD": "新北地方法院", "SLD": "士林地方法院",
    "TYD": "桃園地方法院", "SCD": "新竹地方法院", "MLD": "苗栗地方法院", "TCD": "臺中地方法院",
    "TCH": "臺灣高等法院 臺中分院", "CHD": "彰化地方法院", "NTD": "南投地方法院", "ULD": "雲林地方法院",
    "CYD": "嘉義地方法院", "TND": "臺南地方法院", "TNH": "臺灣高等法院 臺南分院", "KSD": "高雄地方法院",
    "KSH": "臺灣高等法院 高雄分院", "PTD": "屏東地方法院", "TTD": "臺東地方法院", "HLD": "花蓮地方法院",
    "HLH": "臺灣高等法院 花蓮分院", "ILD": "宜蘭地方法院", "KLD": "基隆地方法院", "PHD": "澎湖地方法院",
    "KMD": "金門地方法院", "LCD": "連江地方法院", "TPS": "最高法院", "TPA": "最高行政法院",
    "TPB": "臺北高等行政法院", "TCB": "臺中高等行政法院", "KSB": "高雄高等行政法院", "IPC": "智慧財產及商業法院"
}

def parse_cn_amount(text: str) -> int:
    if not text:
        return 0
    text = str(text).replace(',', '').replace('，', '').replace(' ', '').strip()
    m = re.search(r'([0-9]+(?:\.[0-9]+)?)', text)
    if m:
        try:
            val = float(m.group(1))
            if '億' in text: val *= 100000000
            elif '萬' in text: val *= 10000
            return int(val)
        except ValueError:
            pass
    total = 0
    curr_section = 0
    curr_num = 0
    for ch in text:
        if ch in CN_NUM:
            n = CN_NUM[ch]
            if n in [10, 100, 1000]:
                curr_num = curr_num if curr_num > 0 else 1
                curr_section += curr_num * n
                curr_num = 0
            elif n == 10000:
                curr_section = (curr_section + curr_num) * 10000
                total += curr_section
                curr_section = 0
                curr_num = 0
            elif n == 100000000:
                curr_section = (curr_section + curr_num) * 100000000
                total += curr_section
                curr_section = 0
                curr_num = 0
            else:
                curr_num = n
    total += curr_section + curr_num
    return total

def extract_case_amounts(main_text: str, content: str = ""):
    awarded, status, solatium = 0, "其他", 0
    if not main_text:
        return awarded, status, solatium

    clean_main = main_text.replace('\n', ' ').strip()
    if re.search(r'(原告之訴.*?駁回|聲請駁回|上訴駁回|抗告駁回|全部駁回)', clean_main) and not re.search(r'應給付', clean_main):
        return 0, "完全駁回", solatium

    m_award = re.search(r'(?:應(?:連帶)?給付(?:原告)?|給付原告)\s*(?:新[臺台]幣)?\s*([0-9,，\u4e00-\u9fa5]{1,20})\s*元', clean_main)
    if m_award:
        awarded = parse_cn_amount(m_award.group(1))
        status = "一部准許" if re.search(r'其餘.*?駁回', clean_main) else "全部判准"
    elif "駁回" in clean_main:
        status = "完全駁回"

    m_sol = re.search(r'(?:精神)?慰撫金.*?(?:以|認|命)?\s*(?:新[臺台]幣)?\s*([0-9,，\u4e00-\u9fa5]{1,15})\s*元(?:為相當|為適當|為合理)?', clean_main + " " + (content[:3000] if content else ""))
    if m_sol:
        solatium = parse_cn_amount(m_sol.group(1))

    return awarded, status, solatium


class JudgeAnalyticsQuery(BaseModel):
    judge_name: str
    court: Optional[str] = ""
    limit: int = 100

@router.post("/judge_analytics")
def get_judge_analytics(q: JudgeAnalyticsQuery):
    raw_name = q.judge_name or ""
    clean_name = re.sub(r'[\(（].*?[\)）]', '', raw_name).replace('法官', '').replace('審判長', '').replace('公設', '').strip()
    if not clean_name or len(clean_name) < 2:
        return JSONResponse(status_code=400, content={"error": "請提供有效的法官姓名"})

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 10 秒安全超時防止長時間鎖定
            cursor.execute("SET statement_timeout = 10000;")
            
            rows = []
            court_raw = (q.court or "").strip().upper()
            court_code = court_raw.split(',')[0][:3] if court_raw else ""

            # 優先策略 1: 若指定了法院代碼（如 TNH），使用法院索引以毫秒級快速過濾
            if court_code and len(court_code) == 3:
                cursor.execute("""
                    SELECT id, year, case_type, case_no, date, title, main_text, case_category_name, doc_type
                    FROM judgments
                    WHERE SUBSTRING(id, 1, 3) = %s AND content LIKE %s
                    ORDER BY date DESC
                    LIMIT %s
                """, (court_code, f"%{clean_name}%", min(q.limit, 100)))
                rows = [dict(r) for r in cursor.fetchall()]

            # 策略 2: 若未指定法院或同法院資料為空，使用日期倒序檢索近期判決
            if not rows:
                cursor.execute("""
                    SELECT id, year, case_type, case_no, date, title, main_text, case_category_name, doc_type
                    FROM judgments
                    WHERE content LIKE %s
                    ORDER BY date DESC
                    LIMIT %s
                """, (f"%{clean_name}%", min(q.limit, 40)))
                rows = [dict(r) for r in cursor.fetchall()]

        total_cases = len(rows)
        if total_cases == 0:
            return {
                "judge_name": clean_name,
                "total_cases": 0,
                "message": f"本地資料庫中目前未檢索到法官「{clean_name}」之承審判決。"
            }

        cat_counts = Counter()
        cause_counts = Counter()
        court_counts = Counter()
        criminal_cases = []
        civil_cases = []
        years = []

        for r in rows:
            cat = r.get("case_category_name") or ("刑事" if "刑" in (r.get("case_type") or "") else "民事")
            cat_counts[cat] += 1

            title = (r.get("title") or "未登載案由").strip()
            if title: cause_counts[title] += 1

            cid = (r.get("id") or "")[:3]
            if cid: court_counts[cid] += 1

            y = r.get("year")
            if y and str(y).isdigit(): years.append(int(y))

            mt = r.get("main_text") or ""
            if "刑" in cat or "刑" in (r.get("case_type") or ""):
                criminal_cases.append(mt)
            else:
                civil_cases.append(mt)

        # 刑事傾向
        crim_total = len(criminal_cases)
        probation_count = sum(1 for m in criminal_cases if "緩刑" in m)
        commutable_count = sum(1 for m in criminal_cases if "易科罰金" in m)
        not_guilty_count = sum(1 for m in criminal_cases if "無罪" in m or "免訴" in m or "不受理" in m)

        # 民事傾向
        civil_total = len(civil_cases)
        dismiss_count = sum(1 for m in civil_cases if ("原告之訴" in m and "駁回" in m) or ("全部駁回" in m) or (m.startswith("駁回")))
        award_count = sum(1 for m in civil_cases if "應給付" in m or "准許" in m)

        recent_cases = []
        for r in rows[:6]:
            cid = (r.get("id") or "")[:3]
            court_name = COURT_NAME_MAP.get(cid, "法院")
            id_parts = (r.get("id") or "").split(',')
            yr = r.get("year") or (id_parts[1] if len(id_parts) > 1 else "")
            ct = r.get("case_type") or (id_parts[2] if len(id_parts) > 2 else "")
            cn = r.get("case_no") or (id_parts[3] if len(id_parts) > 3 else "")
            full_title = f"{court_name} {yr} 年度 {ct} 字第 {cn} 號"
            main_snippet = (r.get("main_text") or "（無主文摘要）").replace('\n', ' ')
            if len(main_snippet) > 80: main_snippet = main_snippet[:80] + "..."
            recent_cases.append({
                "id": r.get("id"),
                "date": r.get("date"),
                "full_title": full_title,
                "title": r.get("title") or "無",
                "main_snippet": main_snippet
            })

        return {
            "judge_name": clean_name,
            "total_cases": total_cases,
            "year_range": f"民國 {min(years)} 年 ～ {max(years)} 年" if years else "近幾年度",
            "categories": dict(cat_counts.most_common(5)),
            "top_causes": [{"name": k, "count": v} for k, v in cause_counts.most_common(6)],
            "courts": [{"name": COURT_NAME_MAP.get(k, k), "code": k, "count": v} for k, v in court_counts.most_common(4)],
            "criminal_stats": {
                "total": crim_total,
                "probation_rate": round(probation_count / crim_total * 100, 1) if crim_total else 0,
                "probation_count": probation_count,
                "commutable_rate": round(commutable_count / crim_total * 100, 1) if crim_total else 0,
                "commutable_count": commutable_count,
                "not_guilty_rate": round(not_guilty_count / crim_total * 100, 1) if crim_total else 0,
                "not_guilty_count": not_guilty_count
            },
            "civil_stats": {
                "total": civil_total,
                "dismiss_rate": round(dismiss_count / civil_total * 100, 1) if civil_total else 0,
                "dismiss_count": dismiss_count,
                "award_rate": round(award_count / civil_total * 100, 1) if civil_total else 0,
                "award_count": award_count
            },
            "recent_cases": recent_cases
        }
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        err_msg = str(e)
        if "statement timeout" in err_msg.lower() or "canceling statement" in err_msg.lower():
            return {
                "judge_name": clean_name,
                "total_cases": 0,
                "message": f"檢索法官「{clean_name}」資料庫超時（資料量龐大）。建議稍候再試，或於首頁以「法官姓名」進行精確檢索。"
            }
        return JSONResponse(status_code=500, content={"error": f"無法取得法官心證數據：{err_msg}"})
    finally:
        if conn: conn.close()


class CompensationAnalyticsQuery(BaseModel):
    keyword: Optional[str] = ""
    title: Optional[str] = ""
    court: Optional[str] = ""
    limit: int = 100

@router.post("/compensation_analytics")
def get_compensation_analytics(q: CompensationAnalyticsQuery):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SET statement_timeout = 10000;")
            where_clauses = ["main_text IS NOT NULL AND main_text != ''"]
            params = []

            kw = (q.keyword or "").strip()
            title_kw = (q.title or "").strip()

            if kw:
                # 使用有 GIN 索引的 title 與 main_text 欄位，秒級響應
                where_clauses.append("(title LIKE %s OR main_text LIKE %s)")
                params.extend([f"%{kw}%", f"%{kw}%"])
            elif title_kw:
                where_clauses.append("title LIKE %s")
                params.append(f"%{title_kw}%")
            else:
                where_clauses.append("(title LIKE '%損害賠償%' OR title LIKE '%侵權行為%' OR title LIKE '%給付%')")

            court_raw = (q.court or "").strip().upper()
            court_code = court_raw.split(',')[0][:3] if court_raw else ""
            if court_code and len(court_code) == 3:
                where_clauses.append("SUBSTRING(id, 1, 3) = %s")
                params.append(court_code)

            where_sql = "WHERE " + " AND ".join(where_clauses)
            sql = f"""
                SELECT id, year, case_type, case_no, date, title, main_text
                FROM judgments
                {where_sql}
                ORDER BY date DESC
                LIMIT %s
            """
            params.append(min(q.limit, 120))
            cursor.execute(sql, tuple(params))
            rows = [dict(r) for r in cursor.fetchall()]

        if not rows:
            return {
                "total_analyzed": 0,
                "keyword": kw or title_kw or "損害賠償",
                "message": "查無足夠之民事判賠判決以供統計行情。"
            }

        awarded_list = []
        solatium_list = []
        dismissed_count = 0
        partially_count = 0
        fully_count = 0
        sample_cases = []

        for r in rows:
            mt = r.get("main_text") or ""
            award, status, sol = extract_case_amounts(mt, "")

            if award > 0:
                awarded_list.append(award)
                if status == "一部准許": partially_count += 1
                else: fully_count += 1
            elif status == "完全駁回":
                dismissed_count += 1

            if sol > 0:
                solatium_list.append(sol)

            if len(sample_cases) < 8 and (award > 0 or status == "完全駁回"):
                cid = (r.get("id") or "")[:3]
                court_name = COURT_NAME_MAP.get(cid, "法院")
                id_parts = (r.get("id") or "").split(',')
                yr = r.get("year") or (id_parts[1] if len(id_parts) > 1 else "")
                case_type = r.get("case_type") or (id_parts[2] if len(id_parts) > 2 else "")
                case_no = r.get("case_no") or (id_parts[3] if len(id_parts) > 3 else "")
                full_case_no = f"{court_name} {yr} 年度 {case_type} 字第 {case_no} 號"

                sample_cases.append({
                    "id": r.get("id"),
                    "date": r.get("date"),
                    "full_case_no": full_case_no,
                    "title": r.get("title") or "損害賠償",
                    "awarded_amount": award,
                    "awarded_formatted": f"NT$ {award:,}" if award > 0 else "0 元 (原告之訴駁回)",
                    "solatium_amount": sol,
                    "status": status,
                    "main_snippet": (mt.replace('\n', ' ')[:90] + "...") if len(mt) > 90 else mt
                })

        # 計算統計分位數
        awarded_list.sort()
        n = len(awarded_list)

        min_val = awarded_list[0] if n > 0 else 0
        max_val = awarded_list[-1] if n > 0 else 0
        median_val = awarded_list[n // 2] if n > 0 else 0
        q25_val = awarded_list[int(n * 0.25)] if n > 0 else 0
        q75_val = awarded_list[int(n * 0.75)] if n > 0 else 0
        avg_val = int(sum(awarded_list) / n) if n > 0 else 0

        # 級距分佈
        brackets = {
            "10萬以下": sum(1 for a in awarded_list if a < 100000),
            "10萬 ~ 30萬": sum(1 for a in awarded_list if 100000 <= a < 300000),
            "30萬 ~ 50萬": sum(1 for a in awarded_list if 300000 <= a < 500000),
            "50萬 ~ 100萬": sum(1 for a in awarded_list if 500000 <= a < 1000000),
            "100萬以上": sum(1 for a in awarded_list if a >= 1000000),
        }

        # 慰撫金行情
        sol_avg = int(sum(solatium_list) / len(solatium_list)) if solatium_list else 0
        solatium_list.sort()
        sol_med = solatium_list[len(solatium_list) // 2] if solatium_list else 0

        total_analyzed = len(rows)
        return {
            "keyword": kw or title_kw or "損害賠償",
            "total_analyzed": total_analyzed,
            "award_rate": round(len(awarded_list) / total_analyzed * 100, 1) if total_analyzed else 0,
            "dismiss_rate": round(dismissed_count / total_analyzed * 100, 1) if total_analyzed else 0,
            "awarded_count": len(awarded_list),
            "dismissed_count": dismissed_count,
            "partially_count": partially_count,
            "fully_count": fully_count,
            "distribution": {
                "min": min_val,
                "q25": q25_val,
                "median": median_val,
                "average": avg_val,
                "q75": q75_val,
                "max": max_val
            },
            "brackets": brackets,
            "solatium_stats": {
                "count": len(solatium_list),
                "average": sol_avg,
                "median": sol_med
            },
            "sample_cases": sample_cases
        }
    except Exception as e:
        if conn:
            try: conn.rollback()
            except Exception: pass
        err_msg = str(e)
        if "statement timeout" in err_msg.lower() or "canceling statement" in err_msg.lower():
            return {
                "keyword": kw or title_kw or "損害賠償",
                "total_analyzed": 0,
                "message": "損害賠償行情分析查詢超時（資料庫運算量較大）。建議縮小法院或年度範圍重試。"
            }
        return JSONResponse(status_code=500, content={"error": f"無法取得損害賠償行情數據：{err_msg}"})
    finally:
        if conn: conn.close()


class SimilarCaseRequest(BaseModel):
    id: str


@router.post("/similar_cases")
def get_similar_cases(req: SimilarCaseRequest):
    """依據當前裁判的案由、類別與關鍵字，推薦 3~4 筆高度相關之相似判決"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, case_category_name, year, main_text FROM judgments WHERE id = %s", (req.id,))
            target = cur.fetchone()
            if not target:
                return {"similar_cases": []}

            category = target["case_category_name"] or "民事"
            title = (target["title"] or "").strip()
            clean_title = re.sub(r"[\(（].*?[\)）]", "", title).strip()
            title_kw = clean_title if clean_title else title

            # 優先搜尋同類別、相似案由之最新判決
            cur.execute("""
                SELECT id, year, case_type, case_no, date, title, main_text, doc_type, case_category_name
                FROM judgments
                WHERE id != %s AND case_category_name = %s AND title LIKE %s
                ORDER BY date DESC
                LIMIT 4;
            """, (req.id, category, f"%{title_kw}%"))
            rows = [dict(r) for r in cur.fetchall()]

            # 若比對數量較少，放寬至同類別最新案
            if len(rows) < 2:
                cur.execute("""
                    SELECT id, year, case_type, case_no, date, title, main_text, doc_type, case_category_name
                    FROM judgments
                    WHERE id != %s AND case_category_name = %s
                    ORDER BY date DESC
                    LIMIT 4;
                """, (req.id, category))
                rows = [dict(r) for r in cur.fetchall()]

            return {"similar_cases": rows}
    except Exception as e:
        print(f"[similar_cases] 查詢失敗: {e}")
        return {"similar_cases": []}
    finally:
        if conn: conn.close()


@router.post("/outcome_analytics")
def get_outcome_analytics(query: JudgmentSearchQuery):
    """
    大數據勝敗訴分析：
    分析目前搜尋條件下判決的主文特徵，歸納出「原告全勝」、「部分勝訴」、「敗訴駁回」之比例分佈
    """
    conn = None
    try:
        where_sql, params = build_search_conditions(query)
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT main_text, doc_type
                FROM judgments
                {where_sql} AND main_text IS NOT NULL AND main_text != ''
                ORDER BY date DESC
                LIMIT 300;
            """, tuple(params))
            rows = cur.fetchall()

        total = len(rows)
        if total == 0:
            return {
                "total_analyzed": 0,
                "full_win_count": 0,
                "partial_win_count": 0,
                "loss_count": 0,
                "other_count": 0,
                "full_win_pct": 0,
                "partial_win_pct": 0,
                "loss_pct": 0,
                "other_pct": 0
            }

        full_win = 0
        partial_win = 0
        loss = 0
        other = 0

        for r in rows:
            mt = (r["main_text"] or "").strip()

            if any(k in mt for k in ("原告之訴駁回", "原告之聲請駁回", "上訴駁回", "抗告駁回", "再審之訴駁回", "訴訟費用由原告負擔", "上訴費用由上訴人負擔")):
                if any(k in mt for k in ("其餘之訴駁回", "一部勝訴", "原告其餘")):
                    partial_win += 1
                else:
                    loss += 1
            elif any(k in mt for k in ("其餘之訴駁回", "原告其餘之訴駁回", "原告其餘", "各自分擔", "按比例")):
                partial_win += 1
            elif any(k in mt for k in ("被告應給付", "准原告", "被告應將", "應連帶給付", "准予", "照准", "訴訟費用由被告負擔")):
                full_win += 1
            elif "駁回" in mt:
                loss += 1
            else:
                other += 1

        return {
            "total_analyzed": total,
            "full_win_count": full_win,
            "partial_win_count": partial_win,
            "loss_count": loss,
            "other_count": other,
            "full_win_pct": round(full_win / total * 100, 1),
            "partial_win_pct": round(partial_win / total * 100, 1),
            "loss_pct": round(loss / total * 100, 1),
            "other_pct": round(other / total * 100, 1)
        }
    except Exception as e:
        print(f"[outcome_analytics] 分析失敗: {e}")
        return {
            "total_analyzed": 0,
            "error": str(e),
            "full_win_pct": 0,
            "partial_win_pct": 0,
            "loss_pct": 0,
            "other_pct": 0
        }
    finally:
        if conn: conn.close()
