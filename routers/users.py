from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from database import run_sql

router = APIRouter()

def get_uid(x_user_id: Optional[str]) -> int:
    if not x_user_id or not x_user_id.isdigit():
        raise HTTPException(status_code=401, detail="請先選擇使用者")
    return int(x_user_id)

class UserCreate(BaseModel):
    name: str

class UserUpdate(BaseModel):
    name: str

class FolderCreate(BaseModel):
    name: str

class FavIn(BaseModel):
    judgment_id: str
    folder_id: Optional[int] = None
    note: str = ""

# --- 使用者 API ---
@router.get("/users")
def list_users():
    return {"data": run_sql("SELECT id, name FROM app_users ORDER BY id", fetch=True)}

@router.post("/users")
def create_user(u: UserCreate):
    name = u.name.strip()
    if not name or len(name) > 30:
        return JSONResponse(status_code=400, content={"error": "名稱需為 1 到 30 個字"})
    run_sql("INSERT INTO app_users (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))
    row = run_sql("SELECT id, name FROM app_users WHERE name = %s", (name,), fetch=True)[0]
    return {"user": row}

@router.put("/users/{user_id}")
def update_user(user_id: int, u: UserUpdate):
    name = u.name.strip()
    if not name or len(name) > 30:
        return JSONResponse(status_code=400, content={"error": "名稱需為 1 到 30 個字"})
    try:
        run_sql("UPDATE app_users SET name = %s WHERE id = %s", (name, user_id))
        return {"ok": True}
    except Exception as e:
        if "unique constraint" in str(e).lower():
            return JSONResponse(status_code=400, content={"error": "該使用者名稱已被其他人使用"})
        return JSONResponse(status_code=500, content={"error": "更新使用者失敗"})

@router.delete("/users/{user_id}")
def delete_user(user_id: int):
    try:
        run_sql("DELETE FROM app_users WHERE id = %s", (user_id,))
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "刪除使用者失敗"})

# --- 資料夾 API ---
@router.get("/folders")
def list_folders(x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    rows = run_sql("SELECT id, name FROM folders WHERE user_id = %s ORDER BY id", (uid,), fetch=True)
    return {"data": rows}

@router.post("/folders")
def create_folder(f: FolderCreate, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    name = f.name.strip()
    if not name:
        return JSONResponse(status_code=400, content={"error": "資料夾名稱不能為空"})
    try:
        run_sql("INSERT INTO folders (user_id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING", (uid, name))
        row = run_sql("SELECT id, name FROM folders WHERE user_id = %s AND name = %s", (uid, name), fetch=True)[0]
        return {"folder": row}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": "建立資料夾失敗"})

# --- 收藏 API ---
@router.get("/favorites")
def list_favorites(x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    rows = run_sql("""
        SELECT f.judgment_id, f.note, f.folder_id, fd.name as folder_name
        FROM favorites f
        LEFT JOIN folders fd ON f.folder_id = fd.id
        WHERE f.user_id = %s 
        ORDER BY f.created_at DESC
    """, (uid,), fetch=True)
    return {"data": rows}

@router.post("/favorites")
def add_favorite(f: FavIn, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    run_sql("""
        INSERT INTO favorites (user_id, judgment_id, folder_id, note) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (user_id, judgment_id) DO UPDATE 
        SET folder_id = EXCLUDED.folder_id, note = EXCLUDED.note
    """, (uid, f.judgment_id, f.folder_id, f.note[:500]))
    return {"ok": True}

@router.delete("/favorites")
def remove_favorite(judgment_id: str, x_user_id: Optional[str] = Header(None)):
    uid = get_uid(x_user_id)
    run_sql("DELETE FROM favorites WHERE user_id = %s AND judgment_id = %s", (uid, judgment_id))
    return {"ok": True}