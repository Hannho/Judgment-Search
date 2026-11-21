import os
import re
import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.sync_service import sync_daily_judgments, JudicialOfficialApi
from services.scheduler import get_scheduler_status
from database import get_recent_sync_logs

router = APIRouter()


class CredentialsRequest(BaseModel):
    user: str
    password: str


class TriggerSyncRequest(BaseModel):
    user: Optional[str] = None
    password: Optional[str] = None


@router.get("/status")
def get_sync_status():
    """
    取得每日排程器狀態、帳號配置情形與最近同步歷史日誌
    """
    scheduler = get_scheduler_status()
    logs = get_recent_sync_logs(limit=10)

    user = os.getenv("JUDICIAL_API_USER", "").strip()
    has_credentials = bool(user and os.getenv("JUDICIAL_API_PASSWORD", "").strip())
    masked_user = f"{user[:3]}***" if len(user) >= 3 else (user or "")

    now = datetime.datetime.now()
    is_service_hours = (0 <= now.hour < 6)

    return {
        "scheduler": scheduler,
        "recent_logs": logs,
        "has_credentials": has_credentials,
        "configured_user": masked_user,
        "is_service_hours": is_service_hours,
        "current_time": now.strftime("%Y-%m-%d %H:%M:%S")
    }


@router.post("/save_credentials")
def save_credentials(req: CredentialsRequest):
    """
    儲存司法院開放平臺之帳號密碼至 .env 設定檔
    """
    user = (req.user or "").strip()
    password = (req.password or "").strip()

    if not user or not password:
        raise HTTPException(status_code=400, detail="請輸入有效的帳號與密碼")

    os.environ["JUDICIAL_API_USER"] = user
    os.environ["JUDICIAL_API_PASSWORD"] = password

    # 寫入或更新 .env
    env_path = os.path.join(os.getcwd(), ".env")
    env_content = ""
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            env_content = f.read()

    # 更新或附加 JUDICIAL_API_USER
    if "JUDICIAL_API_USER=" in env_content:
        env_content = re.sub(r"JUDICIAL_API_USER=.*", f"JUDICIAL_API_USER={user}", env_content)
    else:
        env_content += f"\nJUDICIAL_API_USER={user}"

    # 更新或附加 JUDICIAL_API_PASSWORD
    if "JUDICIAL_API_PASSWORD=" in env_content:
        env_content = re.sub(r"JUDICIAL_API_PASSWORD=.*", f"JUDICIAL_API_PASSWORD={password}", env_content)
    else:
        env_content += f"\nJUDICIAL_API_PASSWORD={password}"

    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content.strip() + "\n")

    return {"success": True, "message": "司法院 API 帳號密碼已儲存！"}


@router.post("/test_auth")
def test_authentication(req: CredentialsRequest = None):
    """
    即時測試司法院開放 API /api/Auth 驗證權限
    """
    user = (req.user.strip() if req and req.user else None) or os.getenv("JUDICIAL_API_USER", "")
    pwd = (req.password.strip() if req and req.password else None) or os.getenv("JUDICIAL_API_PASSWORD", "")

    if not user or not pwd:
        return {"success": False, "error": "尚未輸入帳號密碼"}

    try:
        api = JudicialOfficialApi(user=user, password=pwd)
        token = api.get_token(force_refresh=True)
        return {
            "success": True,
            "message": "身分驗證成功！已成功取得 Token（有效期限 6 小時）。",
            "token_snippet": f"{token[:6]}...{token[-4:]}"
        }
    except Exception as e:
        err_str = str(e)
        now_hour = datetime.datetime.now().hour
        if not (0 <= now_hour < 6) and ("連線" in err_str or "403" in err_str or "timed out" in err_str):
            err_str += "（提示：司法院官方 API 開放時段為每日凌晨 00:00~06:00，非服務時段伺服器可能拒絕連線）"
        return {"success": False, "error": err_str}


@router.post("/trigger")
def trigger_manual_sync(req: TriggerSyncRequest = None):
    """
    手動即時觸發依司法院異動清單 API 同步裁判書
    """
    user = req.user.strip() if (req and req.user) else None
    pwd = req.password.strip() if (req and req.password) else None
    result = sync_daily_judgments(user=user, password=pwd)
    return result
