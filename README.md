
# Judgment-Search
執行 fetch_docs.py 取得七天內裁判書異動清單（all_judrgments_raw.json）,利用此清單查詢所有裁判書內文並清洗後存入（cleand_judgment2.json）
執行步驟
1.進入虛擬環境
source .venv/bin/activate
2.修改fetch_docs.py第9,10行爲自己的司法院開放資料平台帳密
3.終端機輸入 python fetch_docs.py 取得資料並清洗
4.到https://ai.google.dev/gemini-api/docs?hl=zh-tw申請API並修改main.py中的api_key
5.終端機輸入 uvicorn main:app --reload 啟動api及爬蟲伺服器
6.點開index_final.html打開網頁
