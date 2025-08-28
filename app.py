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
    line_user_id = profile_res["userId"]

    # Supabase に保存
    contact_id = supabase_db.get_or_create_contact(line_user_id)

    # 追加前に存在チェック
    exists = supabase_db.check_friend_exists(invite_user_id, contact_id)
    if exists:
        return "既に追加済みです", 200

    supabase_db.add_friend(invite_user_id, contact_id, relationship="friend")
    print("save successful")

    return "友達登録が完了しました！"


# --- 緊急メッセージ送信例 ---
@app.route("/get_contactable_user", methods=["POST"])
def get_contactable_user():
    data = request.get_json()
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "user_id is required"}), 400

    try:
        # user_friends → line_contacts に join
        friends_res = (
            supabase_db.supabase.table("user_friends")
            .select("contact_id, line_contacts(display_name)")
            .eq("user_id", user_id)
            .execute()
        )

        if not friends_res.data:
            return jsonify({"user_id": user_id, "contacts": []})

        # unknown補間
        contacts = []
        for row in friends_res.data:
            contact_id = row["contact_id"]

            display_name = "Unknown"
            if "line_contacts" in row and row["line_contacts"]:
                if row["line_contacts"]["display_name"]:
                    display_name = row["line_contacts"]["display_name"]

            contacts.append({
                "contact_id": contact_id,
                "display_name": display_name
            })

        return jsonify({
            "user_id": user_id,
            "contacts": contacts
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- 緊急メッセージ送信例 ---
@app.route("/send_emergency", methods=["POST"])
def send_emergency():
    data = request.get_json()
    user_id = data.get("user_id")
    contact_ids = data.get("contact_ids")
    message = data.get("message")

    # バリデーション
    if not user_id or not contact_ids or not message:
        return "user_id, contact_ids, message が必要", 400

    # 送信結果をまとめるリスト
    line_results = []

    # 受信側 DB と LINE 送信をループで処理
    for contact_id in contact_ids:
        # Supabase に保存
        supabase_db.send_emergency_message(user_id, contact_id, message)

        # contact_id から LINE userId を取得
        contact_res = (
            supabase_db.supabase.table("line_contacts")
            .select("line_user_id")
            .eq("id", contact_id)
            .execute()
        )

        if not contact_res.data:
            line_results.append({"contact_id": contact_id, "status": "contact not found"})
            continue

        line_user_id = contact_res.data[0]["line_user_id"]

        # LINE送信
        res = send_msg.SendMsg(message, line_user_id)
        line_results.append({"contact_id": contact_id, "line_result": res})

    return jsonify({"status": "ok", "message": "緊急メッセージ登録完了", "results": line_results})

# id発行
@app.route("/get_id", methods=["POST"])
def upsert_app_user():
    """
    name と line_user_id が送られてきたら app_users に追加（重複は無視）
    line_user_id が送られてきたら対応する id を返す
    """
    data = request.get_json()
    name = data.get("name")
    line_user_id = data.get("line_user_id")

    if not line_user_id:
        return "line_user_id が必要です", 400

    # まず line_user_id が既にあるか確認
    result = supabase_db.supabase.table("app_users").select("id").eq("line_user_id", line_user_id).execute()
    existing = result.data[0]["id"] if result.data else None

    # まだ存在しなければ追加
    if not existing and name:
        insert_data = {"name": name, "line_user_id": line_user_id}
        res = supabase_db.supabase.table("app_users").insert(insert_data).execute()
        existing = res.data[0]["id"]

    return jsonify({"id": existing})


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