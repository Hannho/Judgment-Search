
# Judgment-Search
執行 `fetch_docs.py` 取得七天內裁判書異動清單 (`debug_jlist.json`)，利用此清單查詢所有裁判書內文並清洗後存入 (`cleand_judgment2.json`)。

## 執行步驟

1. **進入虛擬環境**
  ```bash
  source .venv/bin/activate
  ```
2.**設定帳密**
  修改 fetch_docs.py 第 9、10 行，填入你自己的司法院開放資料平台帳密。

3.**取得並清洗資料**
  執行以下指令取得資料並進行清洗：
  ```bash
    python fetch_docs.py
  ```
4.**設定 API Key**
  至 Google Gemini API 官方文件 申請 API Key，並修改 main.py 中的 api_key。

5.**啟動 API 伺服器**
  輸入指令啟動 FastAPI 伺服器：
  ```base
    uvicorn main:app --reload
  ```

6.**點開index_final.html打開網頁**


全面支援所有文字欄位：

快速檢索：各個關鍵字可分別散落在案號、案由、主文或內文中。

裁判案由：支援如 過失 傷害 多重過濾。

裁判主文：支援如 有期徒刑 易科罰金 共同條件篩選。

全文內容：支援任意數量的全文關鍵字聯集比對。



