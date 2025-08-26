from flask import Flask, request, redirect, jsonify, session
import requests
import supabase_db
import config
import send_msg

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# --- 招待リンク発行 ---
@app.route("/generate_invite/<int:user_id>", methods=["GET"])
def generate_invite(user_id):
    print("starting generate URL")
    token = supabase_db.get_or_create_invite_token(user_id)
    print("token =", token)
    invite_url = f"{config.CALLBACK_URL.replace('/callback','')}/invite/{token}"
    print("URL generating compleated! invite_url =", invite_url)
    return jsonify({"invite_url": invite_url})

# --- 招待リンクアクセス (LINEログインへリダイレクト) ---
@app.route("/invite/<token>")
def invite(token):
    print("user accessing")
    user_id = supabase_db.get_invite_user(token)
    print("user_id =", user_id)
    if not user_id:
        return "無効な招待リンク", 400

    session["invite_user_id"] = user_id

    print("LINE login now")
    line_login_url = (
        "https://access.line.me/oauth2/v2.1/authorize"
        "?response_type=code"
        f"&client_id={config.LINE_CHANNEL_ID}"
        f"&redirect_uri={config.CALLBACK_URL}"
        "&state=randomstate"
        "&scope=profile%20openid"
    )
    return redirect(line_login_url)

# --- LINEログインコールバック ---
@app.route("/callback")
def callback():
    print("catch callback")
    code = request.args.get("code")
    invite_user_id = session.get("invite_user_id")
    # print("invite_user_id =", invite_user_id)

    if not code or not invite_user_id:
        return "エラー: codeまたはinvite_user_idが無効", 400

    # アクセストークン取得
    token_url = "https://api.line.me/oauth2/v2.1/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.CALLBACK_URL,
        "client_id": config.LINE_CHANNEL_ID,
        "client_secret": config.LINE_CHANNEL_SECRET
    }
    res = requests.post(token_url, data=data)
    token_data = res.json()
    access_token = token_data.get("access_token")

    # プロフィール取得
    profile_url = "https://api.line.me/v2/profile"
    headers = {"Authorization": f"Bearer {access_token}"}
    profile_res = requests.get(profile_url, headers=headers).json()
    print("profile_res =", profile_res)
    line_user_id = profile_res["userId"]

    # Supabase に保存
    contact_id = supabase_db.get_or_create_contact(line_user_id)
    supabase_db.add_friend(invite_user_id, contact_id, relationship="friend")
    print("save successful")

    return "友達登録が完了しました！"

# --- 緊急メッセージ送信例 ---
@app.route("/send_emergency", methods=["POST"])
def send_emergency():
    data = request.get_json()
    user_id = data.get("user_id")
    contact_id = data.get("contact_id")
    message = data.get("message")

    if not all([user_id, contact_id, message]):
        return "user_id, contact_id, message が必要", 400

    # まず Supabase に保存
    supabase_db.send_emergency_message(user_id, contact_id, message)

    # contact_id から LINE userId を取得
    contact_res = supabase_db.supabase.table("line_contacts").select("line_user_id").eq("id", contact_id).execute()
    if not contact_res.data:
        return "contact_id が見つかりません", 404

    line_user_id = contact_res.data[0]["line_user_id"]

    # LINE送信
    res = send_msg.SendMsg(message, line_user_id)
    print("LINE送信結果:", res)

    return jsonify({"status": "ok", "message": "緊急メッセージ登録完了", "line_result": res})

# --- Webhook受信 ---
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print("Webhook received:", data)

    for event in data.get("events", []):
        user_id = event["source"].get("userId")
        event_type = event["type"]

        if event_type == "follow":
            print(f"新しい友達追加: {user_id}")
        elif event_type == "message":
            message_text = event["message"].get("text")
            print(f"userId={user_id}, message={message_text}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
