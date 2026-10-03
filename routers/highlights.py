import json
from fastapi import APIRouter, Header
from pydantic import BaseModel
from typing import Optional
from database import run_sql
from routers.users import get_uid 

router = APIRouter()

class HighlightData(BaseModel):
    highlights: list

@router.get("/{judgment_id}")
def get_highlights(judgment_id: str, x_user_id: Optional[str] = Header(None)):
    try:
        uid = get_uid(x_user_id)
        rows = run_sql("SELECT highlights_json FROM highlights WHERE user_id = %s AND judgment_id = %s", (uid, judgment_id), fetch=True)
        if rows:
            return {"data": json.loads(rows[0]["highlights_json"])}
        return {"data": []}
    except Exception:
        return {"data": []}

@router.post("/{judgment_id}")
def save_highlights(judgment_id: str, payload: HighlightData, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    hl_json = json.dumps(payload.highlights)
    run_sql("""
        INSERT INTO highlights (user_id, judgment_id, highlights_json) 
        VALUES (%s, %s, %s) 
        ON CONFLICT (user_id, judgment_id) DO UPDATE 
        SET highlights_json = EXCLUDED.highlights_json
    """, (uid, judgment_id, hl_json))
    return {"ok": True}

@router.delete("/{judgment_id}")
def clear_highlights(judgment_id: str, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    run_sql("DELETE FROM highlights WHERE user_id = %s AND judgment_id = %s", (uid, judgment_id))
    return {"ok": True}