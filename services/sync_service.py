import os
import re
import json
import time
import datetime
import urllib.parse
from typing import Optional, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

from database import get_db_connection, run_sql
from psycopg2.extras import execute_values

# 司法院官方開放 API 端點 (依據 114.08.22 最新規格)
API_AUTH_URL = "https://data.judicial.gov.tw/jdg/api/Auth"
API_JLIST_URL = "https://data.judicial.gov.tw/jdg/api/JList"
API_JDOC_URL = "https://data.judicial.gov.tw/jdg/api/JDoc"

_cached_token: Optional[str] = None
_token_expire_time: float = 0


# ==============================================================================
# 裁判文字結構化萃取工具 (Regex Parsing)
# ==============================================================================

def extract_main_and_reason(full_text: str) -> Tuple[str, str]:
    """
    從裁判書全文 (JFULLCONTENT) 中精確切分出【主文】與【理由/事實及理由】
    """
    if not full_text:
        return "", ""

    text = full_text.replace('\r\n', '\n').replace('\r', '\n')
    main_text = ""
    reason = ""

    # 尋找「主文」
    m_main = re.search(r'\n\s*主\s*文\s*\n', text)
    if not m_main:
        m_main = re.search(r'主\s*文\s*[:：\n]', text)

    # 尋找「事實及理由」或「理由」
    m_reason = re.search(r'\n\s*(?:事實及理由|事\s*實\s*及\s*理\s*由|理\s*由)\s*\n', text)
    if not m_reason:
        m_reason = re.search(r'(?:事實及理由|理\s*由)\s*[:：\n]', text)

    # 尋找文末署名時點（例如「中華民國...年...月...日」）
    m_date = re.search(r'\n\s*中\s*華\s*民\s*國\s*[0-9\u4e00-\u9fa5\s]+年[0-9\u4e00-\u9fa5\s]+月[0-9\u4e00-\u9fa5\s]+日', text)

    if m_main:
        start_main = m_main.end()
        if m_reason and m_reason.start() > start_main:
            main_text = text[start_main:m_reason.start()].strip()
            end_reason = m_date.start() if m_date and m_date.start() > m_reason.end() else len(text)
            reason = text[m_reason.end():end_reason].strip()
        else:
            end_main = m_date.start() if m_date and m_date.start() > start_main else len(text)
            main_text = text[start_main:end_main].strip()
    elif m_reason:
        end_reason = m_date.start() if m_date and m_date.start() > m_reason.end() else len(text)
        reason = text[m_reason.end():end_reason].strip()

    return main_text, reason


def extract_doc_type(case_type: str, content: str) -> str:
    """判斷裁判種類：裁定 或 判決"""
    if "裁定" in (case_type or ""):
        return "裁定"
    if "判決" in (case_type or ""):
        return "判決"
    head = (content or "")[:200]
    if "裁定" in head:
        return "裁定"
    return "判決"


def extract_case_category(case_id: str, case_type: str, content: str) -> str:
    """判斷案件類別：民事、刑事、行政、憲法、懲戒"""
    court_prefix = case_id.split(',')[0].upper() if ',' in case_id else case_id[:4].upper()

    if court_prefix.startswith("CPC") or "憲" in (case_type or ""):
        return "憲法"
    if court_prefix.startswith("TPC") or "懲" in (case_type or "") or "懲戒" in (content or "")[:200]:
        return "懲戒"
    if "B" in court_prefix or court_prefix.startswith("TPA") or "行" in (case_type or ""):
        return "行政"

    # 刑事 (第四碼為 M，如 TPDM, TCHM, TPSM, TNHM, KSHM, SLDM, PCDM)
    if len(court_prefix) >= 4 and court_prefix[3] == 'M':
        return "刑事"
    # 民事 (第四碼為 V 或 C，如 TPDV, TNHV, TCHV)
    if len(court_prefix) >= 4 and court_prefix[3] in ('V', 'C'):
        return "民事"

    if any(k in (case_type or "") for k in ("刑", "易", "交", "附民", "秩")):
        return "刑事"
    if any(k in (case_type or "") for k in ("民", "重", "簡", "勞", "家", "破", "促", "票")):
        return "民事"

    return "民事" if "民" in (content or "")[:200] else ("刑事" if "刑" in (content or "")[:200] else "民事")


def parse_jdoc_to_record(doc: dict) -> Optional[dict]:
    """
    將司法院 JDoc API 回傳之 JSON 物件映射為資料庫欄位
    """
    jid = (doc.get("JID") or "").strip()
    if not jid:
        return None

    jyear = str(doc.get("JYEAR") or "").strip()
    jcase = str(doc.get("JCASE") or "").strip()
    jno = str(doc.get("JNO") or "").strip()
    jdate = str(doc.get("JDATE") or "").strip()
    jtitle = str(doc.get("JTITLE") or "").strip()

    jfullx = doc.get("JFULLX") or {}
    jfull = str(jfullx.get("JFULLCONTENT") or "").strip()
    pdf_url = str(jfullx.get("JFULLPDF") or "").strip()

    # 嘗試從 JID 補齊 metadata (格式: 法院,年度,案類,字號,日期,序號)
    if (not jyear or not jcase or not jno) and ',' in jid:
        parts = jid.split(',')
        if len(parts) >= 4:
            jyear = jyear or parts[1]
            jcase = jcase or parts[2]
            jno = jno or parts[3]
        if len(parts) >= 5 and not jdate:
            jdate = parts[4]

    # 日期正規化為 YYYYMMDD
    clean_date = re.sub(r'[^0-9]', '', jdate)
    if len(clean_date) == 7:  # 民國年 1150831 -> 轉西元 20260831
        clean_date = f"{int(clean_date[:3]) + 1911}{clean_date[3:]}"

    main_text, reason = extract_main_and_reason(jfull)
    doc_type = extract_doc_type(jcase, jfull)
    case_category = extract_case_category(jid, jcase, jfull)
    size_kb = round((len(jfull.encode('utf-8')) / 1024), 1)

    if not pdf_url:
        pdf_url = f"https://judgment.judicial.gov.tw/FJUD/data.aspx?ty=JD&id={urllib.parse.quote(jid)}"

    return {
        "id": jid,
        "year": jyear,
        "case_type": jcase,
        "case_no": jno,
        "date": clean_date,
        "title": jtitle,
        "content": jfull,
        "pdf_url": pdf_url,
        "main_text": main_text,
        "reason": reason,
        "doc_type": doc_type,
        "case_category_name": case_category,
        "size_kb": size_kb
    }


# ==============================================================================
# 資料庫批次寫入與下架刪除
# ==============================================================================

def batch_upsert_judgments(records: List[dict]) -> int:
    """
    使用 psycopg2.extras.execute_values 高速批次寫入資料庫
    注意：case_category_name, doc_type, size_kb, main_text, reason 為 PostgreSQL 之 GENERATED ALWAYS 生成欄位，
    由資料庫依 content 與 id 自動計算，寫入時不可指定非 DEFAULT 值。
    """
    if not records:
        return 0

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            query = """
                INSERT INTO judgments (
                    id, year, case_type, case_no, date, title, content, pdf_url
                ) VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    year = EXCLUDED.year,
                    case_type = EXCLUDED.case_type,
                    case_no = EXCLUDED.case_no,
                    date = EXCLUDED.date,
                    title = EXCLUDED.title,
                    content = EXCLUDED.content,
                    pdf_url = COALESCE(NULLIF(EXCLUDED.pdf_url, ''), judgments.pdf_url)
            """
            data = [
                (
                    r["id"],
                    r["year"],
                    r["case_type"],
                    r["case_no"],
                    r["date"],
                    r["title"],
                    r["content"],
                    r["pdf_url"]
                )
                for r in records
            ]
            execute_values(cur, query, data, page_size=1000)
        conn.commit()
        return len(records)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def remove_judgments_by_ids(jids: List[str]) -> int:
    """
    依照司法院規範：若 API 回傳查無資料或已下架，必須從本地資料庫中刪除，以免損及當事人隱私
    """
    if not jids:
        return 0
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM judgments WHERE id = ANY(%s)", (jids,))
            deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        conn.rollback()
        print(f"[sync] 執行下架刪除失敗：{e}")
        return 0
    finally:
        conn.close()


# ==============================================================================
# 司法院官方開放 API 客戶端
# ==============================================================================

class JudicialOfficialApi:
    """
    封裝司法院 114.08.22 規格之 Auth / JList / JDoc API
    """

    def __init__(self, user: Optional[str] = None, password: Optional[str] = None):
        self.user = user or os.getenv("JUDICIAL_API_USER", "")
        self.password = password or os.getenv("JUDICIAL_API_PASSWORD", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JudicialSyncBot/2.0"
        })

    def get_token(self, force_refresh: bool = False) -> str:
        """
        向 /api/Auth 取得 Token (有效時間 6 小時)
        """
        global _cached_token, _token_expire_time
        now = time.time()
        if not force_refresh and _cached_token and now < _token_expire_time:
            return _cached_token

        if not self.user or not self.password:
            raise ValueError("尚未設定司法院開放平臺帳號密碼（請於 .env 設定 JUDICIAL_API_USER / JUDICIAL_API_PASSWORD）")

        payload = {"user": self.user, "password": self.password}
        print(f"[api] 正在向司法院進行身分驗證 ({self.user[:3]}***)...")

        resp = self.session.post(API_AUTH_URL, json=payload, timeout=20)
        if resp.status_code != 200:
            raise RuntimeError(f"司法院驗證 API 回應失敗 (HTTP {resp.status_code})：{resp.text}")

        res_json = resp.json()
        if "Token" in res_json:
            _cached_token = res_json["Token"]
            _token_expire_time = now + (5.5 * 3600)  # 保守抓 5.5 小時後過期
            print("[api] 驗證成功，已取得 6 小時有效 Token")
            return _cached_token
        elif "error" in res_json:
            raise RuntimeError(f"司法院驗證失敗：{res_json['error']}")
        else:
            raise RuntimeError(f"未知的 API 回應格式：{res_json}")

    def fetch_jlist(self, token: Optional[str] = None) -> List[dict]:
        """
        向 /api/JList 取得 7 日前裁判書異動清單
        回傳格式: [ {"date": "YYYY-MM-DD", "list": ["JID1", ...]} ]
        """
        tok = token or self.get_token()
        print("[api] 正在調閱裁判書異動清單 (/api/JList)...")

        resp = self.session.post(API_JLIST_URL, json={"token": tok}, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"調閱異動清單失敗 (HTTP {resp.status_code})：{resp.text}")

        data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            # 若 Token 失效，強制重取一次重試
            if "驗證失敗" in str(data.get("error")):
                tok = self.get_token(force_refresh=True)
                resp = self.session.post(API_JLIST_URL, json={"token": tok}, timeout=30)
                data = resp.json()

        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"司法院異動清單回應錯誤：{data.get('error')}")
        return []

    def fetch_jdoc(self, jid: str, token: Optional[str] = None) -> Tuple[str, Optional[dict]]:
        """
        向 /api/JDoc 取回單筆裁判書全文內容
        回傳: (status: 'UPSERT'|'DELETE'|'ERROR', record_or_none)
        """
        tok = token or self.get_token()
        payload = {"token": tok, "j": jid.strip()}

        try:
            resp = self.session.post(API_JDOC_URL, json=payload, timeout=25)
            if resp.status_code != 200:
                return 'ERROR', None

            data = resp.json()
            if isinstance(data, dict):
                # 遵循規則二：若為未公開或已下架移除，需刪除
                err = str(data.get("error") or "")
                if "查無資料" in err or "已從系統移除" in err:
                    return 'DELETE', {"id": jid}

                if data.get("JID"):
                    parsed = parse_jdoc_to_record(data)
                    return 'UPSERT', parsed

            return 'ERROR', None
        except Exception:
            return 'ERROR', None


# ==============================================================================
# 每日異動同步主流程 (Daily Sync Engine)
# ==============================================================================

def sync_daily_judgments(user: Optional[str] = None, password: Optional[str] = None) -> dict:
    """
    透過司法院每日異動清單 API 執行每日增量同步：
    1. 驗證權限取得 Token
    2. 呼叫 /api/JList 取得異動清單
    3. 針對異動 JID 呼叫 /api/JDoc 取得全文
    4. 依異動規則覆蓋更新 (UPSERT) 或依下架指示刪除 (DELETE)
    5. 紀錄日誌至 sync_logs
    """
    started_at = datetime.datetime.now()
    today_str = started_at.strftime("%Y-%m-%d")

    # 檢查服務時段 (規格要求：每日凌晨 0 時至 6 時止)
    current_hour = started_at.hour
    is_off_peak = (0 <= current_hour < 6)
    if not is_off_peak:
        print(f"[warning] 當前時間為 {started_at.strftime('%H:%M')}，非司法院 API 官方服務時段 (00:00~06:00)。若伺服器拒絕連線屬正常現象。")

    log_id = None
    try:
        run_sql("""
            INSERT INTO sync_logs (sync_date, status, started_at)
            VALUES (%s, 'RUNNING', now())
        """, (today_str,))
        rows = run_sql("SELECT id FROM sync_logs ORDER BY id DESC LIMIT 1", fetch=True)
        if rows:
            log_id = rows[0]["id"]
    except Exception as e:
        print(f"[sync] 寫入日誌失敗：{e}")

    try:
        api = JudicialOfficialApi(user=user, password=password)
        token = api.get_token()

        # 取得異動清單
        jlist_data = api.fetch_jlist(token)
        if not jlist_data:
            msg = "司法院異動清單為空（今日可能無發布異動，或非伺服器服務開放時段）。"
            if log_id:
                run_sql("""
                    UPDATE sync_logs
                    SET status = 'SUCCESS', total_downloaded = 0, total_inserted = 0, total_removed = 0,
                        error_message = %s, finished_at = now()
                    WHERE id = %s
                """, (msg, log_id))
            return {
                "success": True,
                "sync_date": today_str,
                "message": msg,
                "total_changed": 0,
                "total_inserted": 0,
                "total_removed": 0
            }

        # 整理所有需要同步的 JID
        all_jids = []
        sync_dates = []
        for group in jlist_data:
            d = group.get("date")
            sync_dates.append(d)
            jids = group.get("list") or []
            all_jids.extend(jids)

        # 去重
        all_jids = list(dict.fromkeys(all_jids))
        total_jids = len(all_jids)
        print(f"[sync] 本次異動清單共有 {total_jids} 筆裁判需同步（涵蓋日期：{', '.join(filter(None, sync_dates))}）")

        total_inserted = 0
        total_removed = 0
        total_skipped = 0
        batch_upsert = []
        batch_remove = []

        # 採用適度並行線程池抓取 JDoc (控制在 5~8 個連線，保護司法院伺服器)
        max_workers = 6

        def _worker(jid):
            status, res = api.fetch_jdoc(jid, token)
            return status, jid, res

        print(f"[sync] 啟動多執行緒並行調閱裁判全文 (線程數: {max_workers})...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_jid = {executor.submit(_worker, jid): jid for jid in all_jids}

            for idx, future in enumerate(as_completed(future_to_jid), 1):
                status, jid, res = future.result()
                if status == 'UPSERT' and res:
                    batch_upsert.append(res)
                elif status == 'DELETE':
                    batch_remove.append(jid)
                else:
                    total_skipped += 1

                # 批次寫入資料庫
                if len(batch_upsert) >= 50:
                    cnt = batch_upsert_judgments(batch_upsert)
                    total_inserted += cnt
                    batch_upsert.clear()

                # 批次執行下架刪除
                if len(batch_remove) >= 20:
                    del_cnt = remove_judgments_by_ids(batch_remove)
                    total_removed += del_cnt
                    batch_remove.clear()

                if idx % 100 == 0 or idx == total_jids:
                    print(f"[sync] 進度：{idx}/{total_jids} 已處理 (已入庫: {total_inserted}, 已下架: {total_removed})...")

        # 處理剩餘批次
        if batch_upsert:
            cnt = batch_upsert_judgments(batch_upsert)
            total_inserted += cnt
            batch_upsert.clear()

        if batch_remove:
            del_cnt = remove_judgments_by_ids(batch_remove)
            total_removed += del_cnt
            batch_remove.clear()

        duration = round((datetime.datetime.now() - started_at).total_seconds(), 1)
        print(f"[sync] 司法院異動同步大功告成！耗時 {duration} 秒，更新入庫 {total_inserted} 筆，遵規下架移除 {total_removed} 筆。")

        if log_id:
            run_sql("""
                UPDATE sync_logs
                SET status = 'SUCCESS',
                    total_downloaded = %s,
                    total_inserted = %s,
                    total_removed = %s,
                    total_skipped = %s,
                    finished_at = now()
                WHERE id = %s
            """, (total_jids, total_inserted, total_removed, total_skipped, log_id))

        return {
            "success": True,
            "sync_date": today_str,
            "target_dates": sync_dates,
            "total_changed": total_jids,
            "total_inserted": total_inserted,
            "total_removed": total_removed,
            "total_skipped": total_skipped,
            "duration_seconds": duration
        }

    except Exception as e:
        err_msg = str(e)
        if not is_off_peak and ("連線" in err_msg or "403" in err_msg or "timed out" in err_msg):
            err_msg += " (提示：司法院官方 API 開放時段為每日凌晨 00:00~06:00，夜間排程將於時段內正常執行)"

        print(f"[sync] 異動同步任務中止：{err_msg}")
        if log_id:
            try:
                run_sql("""
                    UPDATE sync_logs
                    SET status = 'FAILED', error_message = %s, finished_at = now()
                    WHERE id = %s
                """, (err_msg, log_id))
            except Exception:
                pass
        return {
            "success": False,
            "sync_date": today_str,
            "error": err_msg
        }


# ==============================================================================
# CLI 命令列入口
# ==============================================================================
if __name__ == "__main__":
    print("=== 啟動司法院裁判書每日異動清單 API 同步 ===")
    res = sync_daily_judgments()
    print("執行結果：", json.dumps(res, ensure_ascii=False, indent=2))
