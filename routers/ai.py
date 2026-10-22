import os
import asyncio
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

router = APIRouter()

class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str
    task_mode: Optional[str] = "general"        # general, issues, damages, criminal, custom
    custom_instruction: Optional[str] = ""     # 使用者自訂的高級提示詞

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")

# ==========================================
# 案件分類 Prompt（保留原版）
# ==========================================
classify_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的台灣法院書記官。請根據以下裁判書的開頭與內容，判斷這是哪一種案件類別。\n"
               "你只能從以下選項中回答一個詞：【民事】、【刑事】、【行政】、【懲戒】、【憲法】。\n"
               "請直接輸出該詞彙，不要加上任何標點符號或其他解釋文字。"),
    ("human", "【裁判書開頭內容】：\n{text}")
])

# ==========================================
# 1. 損害賠償與民事專用 Prompts（保留原版）
# ==========================================
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

# ==========================================
# 2. 刑事量刑專用 Prompts（保留原版）
# ==========================================
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

# ==========================================
# 3. 訴訟爭點整理專用 Prompts（新增）
# ==========================================
issues_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法官助理。請從以下提供的【單篇裁判書】中精確萃取訴訟爭點與雙方攻防：\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、原告/上訴人主要主張與起訴法條：\n"
               "二、被告/被上訴人主要抗辯與答辯要旨：\n"
               "三、法院整理的核心爭點（爭執與不爭執事項）：\n"
               "四、法院對各項爭點之採證與心證論理：\n"
               "五、關鍵勝敗訴決定因素："),
    ("human", "【單篇裁判書內容】：\n{single_case_text}")
])

issues_reduce_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一個專門分析中華民國法院裁判書爭點的司法 AI 助理。
請嚴格根據提供的判決內容，為訴訟律師整理深入的【爭點攻防與心證比對報告】。

【逐案爭點摘要】
【案件一】判決字號：
一、雙方主張與攻防焦點
二、法院認定的爭點
三、法院心證理由與採信證據

【爭點攻防比較表格】
| 核心爭點 | 案件一裁判立場與論理 | 案件二裁判立場與論理 | 案件三裁判立場與論理 |
|---|---|---|---|
| 爭點一 | | | |
| 爭點二 | | | |
| 舉證責任分配 | | | |
| 最終判決結果 | | | |

【綜合分析與法律建議】
1. 歸納多數法院在該類型爭點上的主流心證標準
2. 說明哪些舉證方式（證人、書證、鑑定）最容易被法院採信
3. 直接回答使用者的具體提問
【提供的判決資料】：\n{context}"""),
    ("human", "{input}")
])

# ==========================================
# 4. 通用 / 自由自訂指令 Prompts（保留原版並加強）
# ==========================================
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

custom_reduce_prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一位專業的中華民國司法 AI 研究顧問。
請嚴格根據以下提供的裁判書摘要，徹底貫徹執行使用者的【自訂法務指令】。
不得憑空捏造判決未載明的事實。若指令要求產出表格或清單，請以標準 Markdown 格式呈現。

【案件資料彙整】：\n{context}"""),
    ("human", "【使用者的自訂法務分析指令】：\n{instruction}\n\n【具體問題】：\n{input}")
])

# ==========================================
# 核心 API 端點
# ==========================================
@router.post("/ask_multiple")
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

        mode = (query.task_mode or "general").lower()

        # 根據任務模式選擇對應的 Map 與 Reduce Chain
        if mode == "issues":
            map_chain = issues_map_prompt | llm
            reduce_chain = issues_reduce_prompt | llm
        elif mode == "damages":
            map_chain = civil_map_prompt | llm
            reduce_chain = civil_reduce_prompt | llm
        elif mode == "criminal":
            map_chain = criminal_map_prompt | llm
            reduce_chain = criminal_reduce_prompt | llm
        elif mode == "custom" and query.custom_instruction and query.custom_instruction.strip():
            map_chain = generic_map_prompt | llm
            reduce_chain = custom_reduce_prompt | llm
        else:
            # 預設 general 模式：保留原版的自動分類（民事 / 刑事 / 通用）
            sample_text = valid_cases[0][:1000]
            classify_chain = classify_prompt | llm
            try:
                category_res = await classify_chain.ainvoke({"text": sample_text})
                category = category_res.content.strip()
            except Exception:
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

        # 定義單篇抽取的非同步輔助函式 (Map 階段)
        async def extract_single_case(idx: int, content: str) -> str:
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
                return f"=== 【案件 {idx+1} 抽取資料】 ===\n{summary_res.content}\n"
            except Exception as single_err:
                return f"=== 【案件 {idx+1} 抽取資料】 ===\n（此案件抽取失敗，略過：{str(single_err)}）\n"

        # 使用 asyncio.gather 並行執行所有單篇案件的抽取，大幅縮短等待時間
        extracted_summaries = await asyncio.gather(
            *(extract_single_case(idx, content) for idx, content in enumerate(valid_cases))
        )

        combined_context = "\n".join(extracted_summaries)

        # Reduce 階段：跨案件彙整
        if mode == "custom" and query.custom_instruction and query.custom_instruction.strip():
            final_response = await reduce_chain.ainvoke({
                "context": combined_context,
                "instruction": query.custom_instruction.strip(),
                "input": query.question
            })
        else:
            final_response = await reduce_chain.ainvoke({
                "context": combined_context,
                "input": query.question
            })

        return {"answer": final_response.content}

    except Exception as e:
        return {"answer": f"本地 AI 處理失敗，錯誤詳情：{str(e)}"}