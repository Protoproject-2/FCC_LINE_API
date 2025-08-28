from supabase import create_client, Client
import config
import uuid
from typing import Optional
from datetime import datetime

# Supabase 接続
supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

# -------------------------------
# 招待トークン
# -------------------------------
def get_or_create_invite_token(user_id: int) -> str:
    res = supabase.table("invite_tokens").select("token").eq("user_id", user_id).execute()
    if res.data:
        return res.data[0]["token"]

    token = str(uuid.uuid4())
    supabase.table("invite_tokens").insert({"token": token, "user_id": user_id}).execute()
    return token

def get_invite_user(token: str) -> Optional[int]:
    res = supabase.table("invite_tokens").select("user_id").eq("token", token).execute()
    if res.data:
        return res.data[0]["user_id"]
    return None

# -------------------------------
# LINE友達
# -------------------------------
def get_or_create_contact(line_user_id: str, display_name: str = None, is_app_user: bool = False) -> int:
    res = supabase.table("line_contacts").select("id").eq("line_user_id", line_user_id).execute()
    if res.data:
        return res.data[0]["id"]

    insert_res = supabase.table("line_contacts").insert({
        "line_user_id": line_user_id,
        "display_name": display_name,
        "is_app_user": is_app_user
    }).execute()
    return insert_res.data[0]["id"]

# -------------------------------
# user_friends (関係追加)
# -------------------------------
def add_friend(user_id: int, contact_id: int, relationship: str = "friend"):
    return supabase.table("user_friends").insert({
        "user_id": user_id,
        "contact_id": contact_id,
        "relationship": relationship
    }).execute()

# -------------------------------
# 緊急メッセージ
# -------------------------------
def send_emergency_message(user_id: int, contact_id: int, message: str, status: str = "pending"):
    """
    emergency_messages に新規メッセージを登録
    status: pending / sent / failed
    """
    return supabase.table("emergency_messages").insert({
        "user_id": user_id,
        "contact_id": contact_id,
        "message": message,
        "status": status,
        "created_at": datetime.utcnow().isoformat()
    }).execute()

# -------------------------------
# 同一データは保存しない
# -------------------------------
def check_friend_exists(invite_user_id: int, contact_id: int) -> bool:
    """
    user_id と contact_id の組がすでに存在するか確認する
    """
    result = supabase.table("user_friends") \
        .select("*") \
        .eq("user_id", invite_user_id) \
        .eq("contact_id", contact_id) \
        .execute()
    
    # データが1件以上あれば存在する
    return bool(result.data and len(result.data) > 0)