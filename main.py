import os
import time
import pymysql
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
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

# RAG 相關套件
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

# 載入環境變數
load_dotenv()

app = FastAPI()

# 💡 關鍵優化 1：開啟 Gzip 壓縮，將大型判決書 JSON 傳輸量直接壓低 85%，秒速載入
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 0. 資料庫連線設定 (Google Cloud SQL)
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

@app.post("/api/judgments")
def get_judgments_from_db(query: JudgmentSearchQuery):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            sql = "SELECT id, year, case_type, case_no, date, title, content, pdf_url FROM judgments WHERE 1=1"
            params = []

            if query.court:
                sql += " AND id LIKE %s"
                params.append(f"%{query.court}%")
            if query.start_date:
                sql += " AND date >= %s"
                params.append(query.start_date)
            if query.end_date:
                sql += " AND date <= %s"
                params.append(query.end_date)
            if query.year:
                sql += " AND year = %s"
                params.append(query.year)
            if query.keyword:
                for kw in query.keyword.split():
                    sql += " AND (title LIKE %s OR content LIKE %s OR case_no LIKE %s)"
                    params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
            if query.title_kw:
                for kw in query.title_kw.split():
                    sql += " AND title LIKE %s"
                    params.append(f"%{kw}%")
            if query.content_kw:
                for kw in query.content_kw.split():
                    sql += " AND content LIKE %s"
                    params.append(f"%{kw}%")

            sql += " ORDER BY date DESC LIMIT 500"
            cursor.execute(sql, tuple(params))
            results = cursor.fetchall()
            
        return results
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
# 3. AI 問答 API 區塊 (/api/ask_multiple)
# ==========================================
class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

@app.post("/api/ask_multiple")
def ask_ai_multiple(query: MultiQAQuery):
    if not query.judgments_content:
        return {"answer": "目前沒有任何案件資料可供閱讀。"}

    try:
        # 1. 建立 LangChain Documents
        docs = []
        for content in query.judgments_content:
            if content and content.strip():
                docs.append(Document(page_content=content))

        # 2. 進行段落切塊（Chunking）：每塊 500 字，重疊 50 字保持文意連貫
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50,
            separators=["\n\n", "\n", "。", "；", " "]
        )
        splits = text_splitter.split_documents(docs)

        # 3. 呼叫本機 Ollama Embedding 模型進行向量化
        embeddings = OllamaEmbeddings(
            model="nomic-embed-text",  # 或使用 bge-m3
            base_url=OLLAMA_BASE_URL
        )

        # 4. 在記憶體中建立即時向量索引 (In-Memory FAISS)
        vectorstore = FAISS.from_documents(documents=splits, embedding=embeddings)

        # 5. 檢索與使用者問題最相關的 Top 5 關鍵段落
        retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        relevant_docs = retriever.invoke(query.question)
        
        # 組裝檢索到的核心段落
        context = "\n\n---\n\n".join([doc.page_content for doc in relevant_docs])

        # 6. 交給本地 TAIDE 8B 模型進行整合回答
        llm = ChatOllama(
            model="taide-law",
            base_url=OLLAMA_BASE_URL,
            temperature=0.3
        )

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", "你是一位專業的中華民國法律助理。請依據以下從相關裁判書中檢索出的 [關鍵理由段落] 來回答使用者的問題。\n"
                       "回答時，請務必明確指出是依據哪一個案號的判決理由，並詳細條列說明。\n"
                       "如果你檢索到的內容不足以回答問題，請如實告知，不要編造資訊。\n\n"
                       "[關鍵理由段落]：\n{context}"),
            ("human", "{input}")
        ])

        chain = prompt_template | llm

        response = chain.invoke({
            "context": context,
            "input": query.question
        })
        return {"answer": response.content}

    except Exception as e:
        print(f"❌ RAG 處理發生錯誤: {e}")
        return {"answer": f"本地 AI 處理失敗，請確認 Ollama 服務是否已正常啟動，且已下載 nomic-embed-text 模型。錯誤詳情：{str(e)}"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)