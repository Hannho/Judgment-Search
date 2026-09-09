import json
import re

def clean_judgments_data(input_filename, output_filename):
    # 讀取原始抓下來的 JSON 檔案
    with open(input_filename, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
        
    cleaned_data = []
    
    for item in raw_data:
        # 1. 萃取基礎欄位
        jid = item.get("JID", "")
        year = item.get("JYEAR", "")
        case_type = item.get("JCASE", "")
        case_no = item.get("JNO", "")
        date = item.get("JDATE", "")
        title = item.get("JTITLE", "無案由")
        
        # 2. 處理巢狀的內文與 PDF 連結
        content = ""
        pdf_url = ""
        jfullx = item.get("JFULLX")
        
        if jfullx:
            pdf_url = jfullx.get("JFULLPDF", "")
            raw_content = jfullx.get("JFULLCONTENT", "")
            
            if raw_content:
                # 清除大量的 \r\n 換行符號，替換為空白
                content = re.sub(r'[\r\n]+', ' ', raw_content)
                # 清除連續多餘的空白字元，縮減為單一空白
                content = re.sub(r'\s+', ' ', content).strip()
                
        # 3. 重新組裝成乾淨、扁平化的字典結構
        cleaned_item = {
            "id": jid,
            "year": year,
            "case_type": case_type,
            "case_no": case_no,
            "date": date,
            "title": title,
            "content": content,
            "pdf_url": pdf_url
        }
        cleaned_data.append(cleaned_item)
        
    # 將清洗後的資料存成新的 JSON 檔案
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ 清洗完成！共處理 {len(cleaned_data)} 筆資料，已儲存至 {output_filename}")

if __name__ == "__main__":
    clean_judgments_data('all_100_judgments.json', 'cleaned_judgments.json')