import json
import re

def extract_main_text(content):
    """從判決書內文中萃取出「主文」段落"""
    # 模式 1：標準裁判書 (尋找「主文」到「理由/事實/二、」之間的文字)
    pattern_standard = r'(?:主\s*文[：:]?\s*\n)(.*?)(?=\n\s*(?:理\s*由|事\s*實|犯\s*罪\s*事\s*實|二、))'
    match = re.search(pattern_standard, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # 模式 2：支付命令 (尋找「一、債務人應向...」到「二、債權人...」之間的文字)
    pattern_payment = r'(一、債務人應向債權人.*?)(?=\n\s*二、債權人請求之原因事實)'
    match_pay = re.search(pattern_payment, content, re.DOTALL)
    if match_pay:
        return match_pay.group(1).strip()
        
    return "" # 如果都沒比對到，則回傳空字串

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
        main_text = ""  # 💡 新增主文變數
        jfullx = item.get("JFULLX")
        
        if jfullx:
            pdf_url = jfullx.get("JFULLPDF", "")
            raw_content = jfullx.get("JFULLCONTENT", "")
            
            if raw_content:
                # 採用溫和的清洗方式
                content = raw_content.replace('\r\n', '\n')
                content = re.sub(r'\n{3,}', '\n\n', content)
                content = content.strip()
                
                # 💡 呼叫正則表達式函式，將主文萃取出來
                main_text = extract_main_text(content)
                
        # 3. 重新組裝成乾淨、扁平化的字典結構
        cleaned_item = {
            "id": jid,
            "year": year,
            "case_type": case_type,
            "case_no": case_no,
            "date": date,
            "title": title,
            "main_text": main_text,  # 💡 將主文單獨存為一個新的 JSON 欄位
            "content": content,
            "pdf_url": pdf_url
        }
        cleaned_data.append(cleaned_item)
        
    # 將清洗後的資料存成新的 JSON 檔案
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(cleaned_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ 清洗完成！共處理 {len(cleaned_data)} 筆資料，已儲存至 {output_filename}")

if __name__ == "__main__":
    clean_judgments_data('all_judgments_raw.json', 'cleaned_judgments3_main.json')