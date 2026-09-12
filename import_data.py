import json
import pymysql

# 1. 讀取 JSON 檔案
with open('cleaned_judgments2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 2. 連線到 Cloud SQL（請繼續使用您目前權限正確的使用者與密碼）
connection = pymysql.connect(
    host='35.221.215.146',
    user='admin1',           # 請維持您目前能成功連線的使用者帳號
    password='12345678',      # 請填入對應的密碼
    database='judgment',
    charset='utf8mb4',
    cursorclass=pymysql.cursors.DictCursor
)

try:
    with connection.cursor() as cursor:
        # 3. 讓程式自動檢查並建立表格（如果已經存在會自動略過）
        create_table_sql = """
            CREATE TABLE IF NOT EXISTS judgments (
                id VARCHAR(50) PRIMARY KEY,
                year VARCHAR(10),
                case_type VARCHAR(20),
                case_no VARCHAR(20),
                date VARCHAR(20),
                title VARCHAR(100),
                content LONGTEXT,
                pdf_url VARCHAR(255)
            );
        """
        cursor.execute(create_table_sql)
        print("✅ 資料表檢查/建立成功！")

        # 4. 準備插入資料的 SQL
        sql = """
            INSERT INTO judgments (id, year, case_type, case_no, date, title, content, pdf_url) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            year=VALUES(year), title=VALUES(title), content=VALUES(content), pdf_url=VALUES(pdf_url);
        """
        
        # 5. 逐筆寫入資料
        for item in data:
            cursor.execute(sql, (
                item.get('id'),
                item.get('year'),
                item.get('case_type'),
                item.get('case_no'),
                item.get('date'),
                item.get('title'),
                item.get('content'),
                item.get('pdf_url')
            ))
            
    connection.commit()
    print("🎉 所有資料成功匯入 jjudgment 資料庫！")
except Exception as e:
    print(f"❌ 發生錯誤：{e}")
finally:
    connection.close()