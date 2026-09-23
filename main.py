import os
import time
import asyncio
import pymysql
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from dotenv import load_dotenv
import uvicorn

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
# 0. 資料庫連線設定
# ==========================================
DB_HOST = os.getenv("DB_HOST", "35.221.215.146")
DB_USER = os.getenv("DB_USER", "admin1")
DB_PASSWORD = os.getenv("DB_PASSWORD", "12345678")
DB_NAME = os.getenv("DB_NAME", "judgment")         
INSTANCE_CONNECTION_NAME = os.getenv("INSTANCE_CONNECTION_NAME", "judgmentsearch:asia-east1:judgment-search") 

def get_db_connection():
    if os.environ.get("K_SERVICE"):
        return pymysql.connect(
            unix_socket=f'/cloudsql/{INSTANCE_CONNECTION_NAME}',
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    else:
        return pymysql.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

# ==========================================
# 1. 靜態檔案與資料庫資料 API 
# ==========================================
@app.get("/")
def read_index():
    if os.path.exists("index_final.html"):
        return FileResponse("index_final.html")
    return {"message": "index_final.html not found"}

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
    page: int = 1
    sort_type: str = "date_desc"
    case_categories: List[str] = []
    doc_type: str = ""
    adv_case_type: str = ""
    adv_no_start: Optional[int] = None
    adv_no_end: Optional[int] = None
    adv_size_min: Optional[float] = None
    adv_size_max: Optional[float] = None

@app.post("/api/judgments")
def get_judgments_from_db(query: JudgmentSearchQuery):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            where_clauses = ["1=1"]
            params = []

            # 基礎搜尋條件
            if query.court:
                where_clauses.append("id LIKE %s")
                params.append(f"{query.court}%") 
            if query.start_date:
                where_clauses.append("date >= %s")
                sd = query.start_date.replace('-', '')
                if len(sd) == 8: 
                    sd = f"{sd[:4]}-{sd[4:6]}-{sd[6:8]}"
                params.append(sd)
                
            if query.end_date:
                where_clauses.append("date <= %s")
                ed = query.end_date.replace('-', '')
                if len(ed) == 8: 
                    ed = f"{ed[:4]}-{ed[4:6]}-{ed[6:8]}"
                params.append(ed)
            if query.year:
                where_clauses.append("year = %s")
                params.append(query.year)
            
            # 關鍵字條件
            if query.keyword:
                for kw in query.keyword.split():
                    where_clauses.append("(title LIKE %s OR content LIKE %s OR case_no LIKE %s OR id LIKE %s)")
                    params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%", f"%{kw}%"])
            if query.title_kw:
                for kw in query.title_kw.split():
                    where_clauses.append("title LIKE %s")
                    params.append(f"%{kw}%")
                    
            # 全文內容 (支援進階語法：+, -, &, ())
            if query.content_kw:
                s = query.content_kw.replace('+', ' + ').replace('-', ' - ').replace('&', ' & ').replace('(', ' ( ').replace(')', ' ) ')
                tokens = [t for t in s.split() if t.strip()]
                
                content_sql = []
                for i, token in enumerate(tokens):
                    if token == '+':
                        content_sql.append("OR")
                    elif token == '&':
                        content_sql.append("AND")
                    elif token == '-':
                        if not content_sql or content_sql[-1] == '(':
                            content_sql.append("NOT")
                        else:
                            content_sql.append("AND NOT")
                    elif token == '(':
                        if i > 0 and tokens[i-1] not in ['+', '&', '-', '(']:
                            content_sql.append("AND")
                        content_sql.append("(")
                    elif token == ')':
                        content_sql.append(")")
                    else:
                        if i > 0 and tokens[i-1] not in ['+', '&', '-', '(']:
                            content_sql.append("AND")
                        content_sql.append("content LIKE %s")
                        params.append(f"%{token}%")
                
                opens = content_sql.count('(')
                closes = content_sql.count(')')
                if opens > closes:
                    content_sql.extend([")"] * (opens - closes))
                
                if content_sql:
                    where_clauses.append(f"({' '.join(content_sql)})")

            # 裁判書類別
            if query.doc_type == "判決":
                where_clauses.append("(content LIKE '判決%%' OR content LIKE '%%判決如下%%')")
            elif query.doc_type == "裁定":
                where_clauses.append("(content LIKE '裁定%%' OR content LIKE '%%裁定如下%%' OR content LIKE '支付命令%%')")

            # 案件類別
            if query.case_categories:
                cat_conditions = []
                for cat in query.case_categories:
                    if cat == "刑事":
                        cat_conditions.append("(id LIKE '___M%%' OR content LIKE '刑事%%' OR case_type IN ('訴', '簡', '易', '金重訴', '交易', '交簡'))")
                    elif cat == "民事":
                        cat_conditions.append("(id LIKE '___V%%' OR id LIKE '___E%%' OR content LIKE '民事%%' OR content LIKE '支付命令%%' OR case_type IN ('司促', '司拍', '執事聲', '宜訴', '羅簡', '苗小', '苗簡', '壢小', '壢保險簡', '壢司他'))")
                    elif cat == "行政":
                        cat_conditions.append("(id LIKE '___A%%' OR content LIKE '行政%%')")
                    elif cat == "憲法":
                        cat_conditions.append("(content LIKE '憲法%%')")
                    elif cat == "懲戒":
                        cat_conditions.append("(content LIKE '懲戒%%')")
                if cat_conditions:
                    where_clauses.append("(" + " OR ".join(cat_conditions) + ")")

            # 進階案號與大小過濾
            if query.adv_case_type:
                where_clauses.append("case_type LIKE %s")
                params.append(f"%{query.adv_case_type}%")
            if query.adv_no_start is not None:
                where_clauses.append("CAST(case_no AS UNSIGNED) >= %s")
                params.append(query.adv_no_start)
            if query.adv_no_end is not None:
                where_clauses.append("CAST(case_no AS UNSIGNED) <= %s")
                params.append(query.adv_no_end)
            if query.adv_size_min is not None:
                where_clauses.append("(CHAR_LENGTH(content) * 2 / 1024) >= %s")
                params.append(query.adv_size_min)
            if query.adv_size_max is not None:
                where_clauses.append("(CHAR_LENGTH(content) * 2 / 1024) <= %s")
                params.append(query.adv_size_max)

            where_sql = " WHERE " + " AND ".join(where_clauses)

            # 1. 獲取符合條件的總筆數
            count_sql = f"SELECT COUNT(*) as total FROM (SELECT 1 FROM judgments {where_sql} LIMIT 1000) as dummy"
            cursor.execute(count_sql, tuple(params))
            total_count = cursor.fetchone()['total']

            # 2. 依據分頁獲取當頁資料
            order_clause = "ORDER BY date DESC"
            if query.sort_type == "date_asc": order_clause = "ORDER BY date ASC"
            elif query.sort_type == "no_desc": order_clause = "ORDER BY CAST(case_no AS UNSIGNED) DESC"
            elif query.sort_type == "no_asc": order_clause = "ORDER BY CAST(case_no AS UNSIGNED) ASC"
            elif query.sort_type == "size_desc": order_clause = "ORDER BY CHAR_LENGTH(content) DESC"
            elif query.sort_type == "size_asc": order_clause = "ORDER BY CHAR_LENGTH(content) ASC"

            # 智慧索引選擇
            force_index = ""
            if len(where_clauses) == 1 and query.sort_type in ["date_desc", "date_asc"]:
                force_index = "FORCE INDEX (idx_date)"
            elif query.year and len(where_clauses) == 2 and query.sort_type in ["date_desc", "date_asc"]:
                force_index = "FORCE INDEX (idx_year_date)"

            limit = 10
            offset = (query.page - 1) * limit
            
            data_sql = f"SELECT id, year, case_type, case_no, date, title, content, pdf_url FROM judgments {force_index} {where_sql} {order_clause} LIMIT %s OFFSET %s"
            
            data_params = params + [limit, offset]
            cursor.execute(data_sql, tuple(data_params))
            results = cursor.fetchall()
            
        return {"total": total_count, "data": results}
    except Exception as e:
        error_msg = f"❌ 資料庫讀取失敗: {str(e)}"
        print(error_msg)
        return JSONResponse(status_code=500, content={"error": error_msg})
    finally:
        if conn:
            conn.close()

# ==========================================
# 2. 爬蟲 API 區塊 (/api/get_history)
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
    "CLE": "臺灣桃園地方法院中壢簡易庭", "TYE": "臺灣桃園地方法院桃園簡易庭",
    "PCE": "臺灣新北地方法院板橋簡易庭", "STE": "臺灣新北地方法院三重簡易庭",
    "TPE": "臺灣臺北地方法院臺北簡易庭", "SLE": "臺灣士林地方法院士林簡易庭",
    "NIE": "臺灣士林地方法院內湖簡易庭", "ILE": "臺灣宜蘭地方法院宜蘭簡易庭",
    "LTE": "臺灣宜蘭地方法院羅東簡易庭", "KSE": "臺灣高雄地方法院高雄簡易庭",
    "FSE": "臺灣高雄地方法院鳳山簡易庭", "KSY": "臺灣高雄少年及家事法院", 
    "IPC": "智慧財產及商業法院"
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
# 3. AI 問答 API 區塊 (多階段分類與動態 Prompt)
# ==========================================
class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# 🛑 [階段 1] 案件分類 Prompt
classify_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的台灣法院書記官。請根據以下裁判書的開頭與內容，判斷這是哪一種案件類別。\n"
               "你只能從以下選項中回答一個詞：【民事】、【刑事】、【行政】、【懲戒】、【憲法】。\n"
               "請直接輸出該詞彙，不要加上任何標點符號或其他解釋文字。"),
    ("human", "【裁判書開頭內容】：\n{text}")
])

# 🛑 [階段 2] 擷取資訊 (Map) 專屬 Prompts
civil_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇民事裁判書】中精確擷取資訊。\n"
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

# 🛑 [階段 3] 統整回答 (Reduce) 專屬 Prompts
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

        # ==========================================
        # 🟢 階段 1：讓 AI 判斷案件類型
        # ==========================================
        sample_text = valid_cases[0][:1000] # 取第一篇的前 1000 字讓 AI 快速判斷
        classify_chain = classify_prompt | llm
        try:
            category_res = await classify_chain.ainvoke({"text": sample_text})
            category = category_res.content.strip()
        except Exception as e:
            print(f"⚠️ 分類失敗: {e}")
            category = "未知"
            
        print(f"🤖 AI 自動分類結果：[{category}]")

        # ==========================================
        # 🟢 階段 2 & 3：動態載入對應的 Prompt
        # ==========================================
        if "刑事" in category:
            map_chain = criminal_map_prompt | llm
            reduce_chain = criminal_reduce_prompt | llm
        elif "民事" in category:
            map_chain = civil_map_prompt | llm
            reduce_chain = civil_reduce_prompt | llm
        else:
            map_chain = generic_map_prompt | llm
            reduce_chain = generic_reduce_prompt | llm

        # ==========================================
        # 🟢 執行 Map (逐篇擷取) -> Reduce (比較統整)
        # ==========================================
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
                print(f"⚠️ 案件 {idx+1} 擷取失敗: {single_err}")
                extracted_summaries.append(f"=== 【案件 {idx+1} 抽取資料】 ===\n（此案件抽取失敗，略過）\n")

        combined_context = "\n".join(extracted_summaries)

        final_response = await reduce_chain.ainvoke({
            "context": combined_context,
            "input": query.question
        })

        return {"answer": final_response.content}

    except Exception as e:
        print(f"❌ 處理發生錯誤: {e}")
        return {"answer": f"本地 AI 處理失敗，錯誤詳情：{str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)