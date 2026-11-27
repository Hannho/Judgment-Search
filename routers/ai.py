import os
import json
import asyncio
import re
from typing import Optional
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatLlamaCpp

router = APIRouter()


class ClientDisconnectedError(Exception):
    """用戶端主動關閉或中斷連線"""
    pass


async def run_cancellable_chain(
    chain,
    inputs: dict,
    request: Request,
    timeout: Optional[float] = None,
    on_token=None,
) -> str:
    """
    以串流 (astream) 方式執行 LLM，於每個 token 生成後立即檢查：
    1. 用戶端是否已關閉/中斷連線 (request.is_disconnected())
    2. 是否超過指定 timeout
    一旦偵測到中斷或超時，立刻關閉生成器 (aclose)，讓底層 llama.cpp 在下一個 token 即刻停止運算並釋放鎖。
    """
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    chunks = []

    async with _llm_lock:
        if await request.is_disconnected():
            raise ClientDisconnectedError("Client disconnected before generation")

        agen = chain.astream(inputs)
        try:
            async for chunk in agen:
                if await request.is_disconnected():
                    print("[AI Cancel] 偵測到用戶端已關閉功能視窗，立即中止 LLM 運算")
                    raise ClientDisconnectedError("Client disconnected")

                if timeout is not None and (loop.time() - start_time) > timeout:
                    print(f"[AI Timeout] LLM 生成超過 {timeout} 秒，立即中止運算")
                    raise asyncio.TimeoutError(f"LLM exceeded {timeout}s")

                token_text = chunk.content if hasattr(chunk, "content") else str(chunk)
                if token_text:
                    chunks.append(token_text)
                    if on_token is not None:
                        await on_token(token_text)
        finally:
            try:
                await agen.aclose()
            except Exception:
                pass

    return "".join(chunks).strip()

class MultiQAQuery(BaseModel):
    judgments_content: list[str]
    question: str
    task_mode: Optional[str] = "general"        # general, issues, damages, criminal, custom
    custom_instruction: Optional[str] = ""     # 使用者自訂的高級提示詞

MODEL_PATH = os.getenv(
    "MODEL_PATH",
    r"C:\Users\nuc\Desktop\Local LLM\qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
)

_llm = None
_llm_lock = asyncio.Lock()

def get_llm():
    global _llm
    if _llm is not None:
        return _llm
    
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"找不到本地 AI 模型檔案（路徑：{MODEL_PATH}）。請確認檔案是否存在，或於 .env 設定 MODEL_PATH。"
        )
    
    _llm = ChatLlamaCpp(
        model_path=MODEL_PATH,
        temperature=0.2,
        n_ctx=4096,
        max_tokens=1024,
        n_gpu_layers=-1,
        chat_format="chatml",
        verbose=False
    )
    return _llm

# ==========================================
# 1. 損害賠償與民事專用 Prompts
# ==========================================
civil_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇民事裁判書】中精確擷取資訊。\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、案件事實經過：\n"
               "二、原告請求金額與項目：\n"
               "三、法院認定結果（准許/駁回金額）：\n"
               "四、法院裁判理由（過失相抵、單據、折舊等）：\n"
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
四、法院判斷理由
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
# 2. 刑事量刑專用 Prompts
# ==========================================
criminal_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇刑事裁判書】中精確擷取資訊。\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、犯罪事實經過：\n"
               "二、檢察官起訴法條與罪名：\n"
               "三、法院認定結果（罪名、刑度、緩刑/易科罰金）：\n"
               "四、法院量刑理由（態度、和解、動機等）：\n"
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
三、法院判決結果
四、法院量刑理由
五、影響刑度的關鍵因素

【案件比較表格】
| 比較項目 | 案件一 | 案件二 | 案件三 |
|---|---|---|---|
| 犯罪事實 | | | |
| 宣告罪名與刑度 | | | |
| 是否緩刑/易科罰金 | | | |
| 量刑關鍵因素 | | | |

【綜合分析與回答】
1. 整理多數判決的量刑趨勢
2. 說明導致刑度輕重差異的關鍵因素
3. 直接回答使用者的問題
【提供的判決資料】：\n{context}"""),
    ("human", "{input}")
])

# ==========================================
# 3. 訴訟爭點整理專用 Prompts
# ==========================================
issues_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法官助理。請從以下提供的【單篇裁判書】中精確萃取訴訟爭點與雙方攻防：\n"
               "【重要原則】：只記錄文中明確記載的內容，禁止臆測；若未提及請填寫「判決未載明」。\n\n"
               "請依固定格式輸出：\n"
               "判決字號與案由：\n"
               "一、原告/上訴人主要主張：\n"
               "二、被告/被上訴人主要抗辯：\n"
               "三、法院整理的核心爭點：\n"
               "四、法院對各項爭點的心證論理與採證：\n"
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
| 最終判決結果 | | | |

【綜合分析與法律建議】
1. 歸納多數法院在該類型爭點上的主流心證標準
2. 直接回答使用者的具體提問
【提供的判決資料】：\n{context}"""),
    ("human", "{input}")
])

# ==========================================
# 4. 通用 / 自訂 Prompts
# ==========================================
generic_map_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一位專業的法院司法助理。請從以下提供的【單篇裁判書】中精確擷取重點：\n"
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
async def ask_ai_multiple(query: MultiQAQuery, request: Request):
    if not query.judgments_content:
        return {"answer": "目前沒有任何案件資料可供閱讀。"}

    try:
        valid_cases = [c.strip() for c in query.judgments_content if c and c.strip()][:5]
        if not valid_cases:
            return {"answer": "提供的判決內容為空，無法進行分析。"}

        mode = (query.task_mode or "general").lower()
        print(f"\n[AI Info] 模式: {mode} | 案件筆數: {len(valid_cases)}")
        llm = get_llm()

        # ----------------------------------------------------
        # 情境 A：單篇案件（跳過 Map-Reduce，直出答案以節省時間）
        # ----------------------------------------------------
        if len(valid_cases) == 1:
            print("[AI Info] 執行單篇直出模式...")
            single_doc = valid_cases[0][:4000]
            
            direct_prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一位專業的中華民國司法 AI 助理。請依據提供的判決書內容回答問題，切勿憑空捏造。"),
                ("human", """【裁判書內容】：
{context}

【問題】：
{question}

請根據上方判決的【主文】與【理由】，詳細分析並說明法院判斷的具體原因：""")
            ])
            
            direct_chain = direct_prompt | llm
            output_text = await run_cancellable_chain(
                direct_chain,
                {"context": single_doc, "question": query.question},
                request,
            )
            
            # 若仍輸出空字串，提供防呆回傳
            if not output_text:
                output_text = "模型未能順利生成文字，請嘗試稍微調整提問方式或縮短送入的案件長度。"
                
            return {"answer": output_text}

        # ----------------------------------------------------
        # 情境 B：多篇案件（標準 Map-Reduce，改為安全循序執行）
        # ----------------------------------------------------
        print(f"[AI Info] 執行多篇 Map-Reduce 分析模式（共 {len(valid_cases)} 篇）...")

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
            map_chain = generic_map_prompt | llm
            reduce_chain = generic_reduce_prompt | llm

        # Map 階段：循序抽取各案重點，避免 llama.cpp C++ 底層指標競爭當機
        print(f"[AI Info] 正在循序進行 {len(valid_cases)} 篇裁判書重點萃取...")
        extracted_summaries = []
        for i, c in enumerate(valid_cases):
            if await request.is_disconnected():
                raise ClientDisconnectedError("Client disconnected during map phase")
            clean_case_text = c[:3500]
            try:
                res_text = await run_cancellable_chain(
                    map_chain,
                    {"single_case_text": clean_case_text},
                    request,
                )
                extracted_summaries.append(f"=== 【案件 {i+1} 摘要】 ===\n{res_text}\n")
            except ClientDisconnectedError:
                raise
            except Exception as e:
                extracted_summaries.append(f"=== 【案件 {i+1} 摘要】 ===\n（此案件抽取失敗：{str(e)}）\n")

        if await request.is_disconnected():
            raise ClientDisconnectedError("Client disconnected before reduce phase")

        combined_context = "\n".join(extracted_summaries)
        print("[AI Info] 所有案件萃取完成，正在執行 Reduce 跨案比對彙整...")

        # Reduce 階段：跨案件比對與統整
        reduce_inputs = {
            "context": combined_context,
            "input": query.question
        }
        if mode == "custom" and query.custom_instruction and query.custom_instruction.strip():
            reduce_inputs["instruction"] = query.custom_instruction.strip()

        final_text = await run_cancellable_chain(reduce_chain, reduce_inputs, request)
        return {"answer": final_text}

    except ClientDisconnectedError:
        print("[AI Cancel] /ask_multiple 已依用戶端中斷請求停止執行")
        return {"answer": "已停止生成。"}
    except Exception as e:
        return {"answer": f"本地 AI 處理失敗，錯誤詳情：{str(e)}"}


# ==========================================
# 串流 API 端點 (SSE 逐字輸出與即時進度更新)
# ==========================================
@router.post("/ask_stream")
async def ask_ai_stream(query: MultiQAQuery, request: Request):
    async def event_generator():
        if not query.judgments_content:
            yield f"data: {json.dumps({'type': 'error', 'text': '目前沒有任何案件資料可供閱讀。'}, ensure_ascii=False)}\n\n"
            return

        valid_cases = [c.strip() for c in query.judgments_content if c and c.strip()][:5]
        if not valid_cases:
            yield f"data: {json.dumps({'type': 'error', 'text': '提供的判決內容為空，無法進行分析。'}, ensure_ascii=False)}\n\n"
            return

        try:
            llm = get_llm()
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'text': f'本地 AI 初始化失敗：{str(e)}'}, ensure_ascii=False)}\n\n"
            return

        mode = (query.task_mode or "general").lower()

        try:
            # 情境 A：單篇案件直出
            if len(valid_cases) == 1:
                yield f"data: {json.dumps({'type': 'status', 'text': '正在閱讀並分析裁判書核心爭點與理由...'}, ensure_ascii=False)}\n\n"
                single_doc = valid_cases[0][:4000]
                direct_prompt = ChatPromptTemplate.from_messages([
                    ("system", "你是一位專業的中華民國司法 AI 助理。請依據提供的判決書內容回答問題，切勿憑空捏造。"),
                    ("human", "【裁判書內容】：\n{context}\n\n【問題】：\n{question}\n\n請根據上方判決的【主文】與【理由】，詳細分析並說明法院判斷的具體原因：")
                ])
                direct_chain = direct_prompt | llm
                token_queue: asyncio.Queue = asyncio.Queue()

                async def _on_token(tok: str):
                    await token_queue.put(tok)

                async def _run():
                    try:
                        await run_cancellable_chain(
                            direct_chain,
                            {"context": single_doc, "question": query.question},
                            request,
                            on_token=_on_token,
                        )
                    finally:
                        await token_queue.put(None)

                task = asyncio.create_task(_run())
                while True:
                    tok = await token_queue.get()
                    if tok is None:
                        break
                    yield f"data: {json.dumps({'type': 'token', 'text': tok}, ensure_ascii=False)}\n\n"
                await task
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # 情境 B：多篇案件依序 Map-Reduce（即時回報進度）
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
                map_chain = generic_map_prompt | llm
                reduce_chain = generic_reduce_prompt | llm

            extracted_summaries = []
            for i, c in enumerate(valid_cases):
                if await request.is_disconnected():
                    raise ClientDisconnectedError("Client disconnected during map phase")
                yield f"data: {json.dumps({'type': 'status', 'text': f'正在萃取第 {i+1}/{len(valid_cases)} 篇裁判書重點與爭點...'}, ensure_ascii=False)}\n\n"
                clean_case_text = c[:3500]
                try:
                    res_text = await run_cancellable_chain(
                        map_chain,
                        {"single_case_text": clean_case_text},
                        request,
                    )
                    extracted_summaries.append(f"=== 【案件 {i+1} 摘要】 ===\n{res_text}\n")
                except ClientDisconnectedError:
                    raise
                except Exception as e:
                    extracted_summaries.append(f"=== 【案件 {i+1} 摘要】 ===\n（此案件抽取失敗：{str(e)}）\n")

            if await request.is_disconnected():
                raise ClientDisconnectedError("Client disconnected before reduce phase")

            combined_context = "\n".join(extracted_summaries)
            yield f"data: {json.dumps({'type': 'status', 'text': '各案重點萃取完成，正在生成跨案綜合比對報告...'}, ensure_ascii=False)}\n\n"

            reduce_inputs = {
                "context": combined_context,
                "input": query.question
            }
            if mode == "custom" and query.custom_instruction and query.custom_instruction.strip():
                reduce_inputs["instruction"] = query.custom_instruction.strip()

            token_queue: asyncio.Queue = asyncio.Queue()

            async def _on_reduce_token(tok: str):
                await token_queue.put(tok)

            async def _run_reduce():
                try:
                    await run_cancellable_chain(
                        reduce_chain,
                        reduce_inputs,
                        request,
                        on_token=_on_reduce_token,
                    )
                finally:
                    await token_queue.put(None)

            task = asyncio.create_task(_run_reduce())
            while True:
                tok = await token_queue.get()
                if tok is None:
                    break
                yield f"data: {json.dumps({'type': 'token', 'text': tok}, ensure_ascii=False)}\n\n"
            await task
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except ClientDisconnectedError:
            print("[AI Cancel] /ask_stream 串流已依用戶端中斷請求停止執行")
            return
        except Exception as err:
            yield f"data: {json.dumps({'type': 'error', 'text': f'生成失敗：{str(err)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class CaseBriefRequest(BaseModel):
    id: str
    title: Optional[str] = ""
    content: str
    main_text: Optional[str] = ""
    reason: Optional[str] = ""


@router.post("/case_brief")
async def generate_case_brief(req: CaseBriefRequest, request: Request):
    """
    一鍵生成 AI 案件速覽小卡 (Case Brief)
    萃取：核心主文結論、爭點聚焦、原告主張 vs. 被告抗辯、法院關鍵理由心證
    """
    llm = None
    try:
        llm = get_llm()
    except Exception:
        llm = None

    if llm:
        case_sample = (req.main_text or "") + "\n\n" + (req.reason or req.content[:3000])
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一位專業的法院司法助理。請將以下裁判書內容精準整理成一份【案件速覽小卡】。\n"
                       "必須條理分明、文字精練：\n"
                       "【一、核心主文結論】：一句話說明判決結果（誰勝誰敗、命給付金額或刑期）。\n"
                       "【二、核心訴訟爭點】：本案雙方爭執的最關鍵法律或事實問題。\n"
                       "【三、原告主張 vs. 被告抗辯】：摘要雙方立場。\n"
                       "【四、法院判斷心證】：法院支持或駁回的核心理由與考量。\n"
                       "【五、適用法條與原則】：本案引用的重要法律條文或法理原則。"),
            ("human", "判決字號/案由：{title}\n裁判書內容：\n{case_sample}\n\n請輸出速覽小卡：")
        ])
        chain = prompt | llm
        try:
            brief_text = await run_cancellable_chain(
                chain,
                {"title": req.title or "", "case_sample": case_sample[:3000]},
                request,
                timeout=5.0,
            )
            return {"success": True, "brief": brief_text, "source": "ai"}
        except ClientDisconnectedError:
            print("[case_brief] 用戶端已收起速覽小卡，停止 LLM 生成")
            return {"success": False, "cancelled": True}
        except Exception as e:
            print(f"[case_brief] LLM 生成超時或異常，已中止背景運算並退回結構化萃取: {e}")

    # Fallback 結構化秒級解析
    full_text = req.content or ""
    clean_main = (req.main_text or "主文未載明").replace('\r', '').strip()

    claims_text = "判決書中記載原告訴之聲明與請求事項"
    claims_match = re.search(r'(?:原告主張|原告起訴主張|上訴人主張|聲請人主張)[：:\s]*([\s\S]{10,250}?)(?:被告抗辯|被上訴人|經查|本院查|理由)', full_text)
    if claims_match:
        claims_text = re.sub(r'\s+', ' ', claims_match.group(1)).strip()[:180] + "..."

    defense_text = "判決書中記載被告答辯要領"
    defense_match = re.search(r'(?:被告抗辯|被告則以|被上訴人抗辯|相對人陳述)[：:\s]*([\s\S]{10,250}?)(?:經查|本院查|本院得心證|本院審酌|理由)', full_text)
    if defense_match:
        defense_text = re.sub(r'\s+', ' ', defense_match.group(1)).strip()[:180] + "..."

    reason_snippet = (req.reason or full_text)[:300]
    reason_snippet = re.sub(r'\s+', ' ', reason_snippet).strip()[:200] + "..."

    fallback_brief = f"""**【一、核心主文結論】**
{clean_main}

**【二、核心訴訟爭點】**
本案主要聚焦於「{req.title or '實體權益爭執'}」之構成要件、責任歸屬與法律效果。

**【三、兩造主張要領】**
* 原告/聲請方主張：{claims_text}
* 被告/抗辯方答辯：{defense_text}

**【四、法院核心心證】**
{reason_snippet}

**【五、合議庭裁判提示】**
本案經審酌兩造全辯論意旨及卷內各項證據調查結果，綜合認定判斷如主文。"""

    return {"success": True, "brief": fallback_brief, "source": "rule_based"}


class CompareDiffRequest(BaseModel):
    id_a: str
    title_a: str
    content_a: str
    main_text_a: Optional[str] = ""
    id_b: str
    title_b: str
    content_b: str
    main_text_b: Optional[str] = ""


@router.post("/compare_diff")
async def compare_judgments_diff(req: CompareDiffRequest, request: Request):
    """
    一鍵歷審翻轉 / 爭點變更智慧對照：
    比對兩件裁判（例如原審與上訴審，或兩篇爭議裁判）的主文差異、爭點心證逆轉與認定變更
    """
    llm = None
    try:
        llm = get_llm()
    except Exception:
        llm = None

    if llm:
        sample_a = f"【裁判A ({req.title_a})】\n主文：{req.main_text_a or '無'}\n全文重點：{req.content_a[:2200]}"
        sample_b = f"【裁判B ({req.title_b})】\n主文：{req.main_text_b or '無'}\n全文重點：{req.content_b[:2200]}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一位精通台灣司法實務與訴訟程序的資深法官助理。請針對以下兩件關聯判決（通常為原審與上訴審，或同類爭點之兩案）進行深度異動比對分析：\n"
                       "請依序條列：\n"
                       "【一、主文裁判結果差異】：明確對比誰勝誰敗、命給付金額或刑度是否有增減、撤銷、廢棄或維持。\n"
                       "【二、核心爭點與事實認定異動】：二審或對照案推翻或改變了哪些原審事實認定或法律見解？\n"
                       "【三、法院關鍵心證翻轉/維持原因】：上級審改判或維持的核心論理為何？\n"
                       "【四、法務訴訟策略啟示】：從此兩案演變中獲得的實務攻防策略借鏡。"),
            ("human", "{sample_a}\n\n{sample_b}\n\n請給出專業的對照分析報告：")
        ])
        chain = prompt | llm
        try:
            diff_text = await run_cancellable_chain(
                chain,
                {"sample_a": sample_a, "sample_b": sample_b},
                request,
                timeout=5.0,
            )
            return {"success": True, "diff": diff_text, "source": "ai"}
        except ClientDisconnectedError:
            print("[compare_diff] 用戶端已關閉對照視窗，停止 LLM 生成")
            return {"success": False, "cancelled": True}
        except Exception as e:
            print(f"[compare_diff] LLM 生成超時或異常，已中止背景運算並轉為結構化對照: {e}")

    # Fallback 結構化對照分析
    main_a = (req.main_text_a or "").strip()
    main_b = (req.main_text_b or "").strip()

    status_diff = "主文維持或程序處理"
    if ("駁回" in main_b and "駁回" not in main_a) or ("廢棄" in main_b) or ("原判決廢棄" in main_b) or ("撤銷" in main_b):
        status_diff = "裁判結果產生重大逆轉（原判決遭撤銷、廢棄或改判）"
    elif "駁回上訴" in main_b or "上訴駁回" in main_b:
        status_diff = "上訴遭駁回，維持原審認定"
    elif ("一部" in main_b) or ("其餘" in main_b):
        status_diff = "上訴一部有理由、一部無理由（部分改判）"

    fallback_diff = f"""**【一、裁判結果與審級演變】**
* 審級走向：{status_diff}
* 案件 A 主文：{main_a if main_a else '主文未載明'}
* 案件 B 主文：{main_b if main_b else '主文未載明'}

**【二、兩案核心主文實體對照】**
* 給付與負擔義務：兩案主文記載之訴訟標的與判命履行事項存在實體變動或維持。
* 訴訟費用負擔：視上訴准駁情況由敗訴方或兩造按比例分擔。

**【三、爭點心證與論理觀察】**
* 兩審級法院就案件之事實調查、證據證明力評價與法律構成要件適用進行前後審酌。
* 建議重點比對兩案之【理由】章節中針對爭點之論斷差異。

**【四、法務實戰啟示】**
* 檢視上級審所持之法律爭點闡明，作為後續類似案件之攻防主張與舉證重點。"""

    return {"success": True, "diff": fallback_diff, "source": "rule_based"}
