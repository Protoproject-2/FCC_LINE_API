from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    print("Webhook received:", data)

    # LINE からのイベントを処理
    for event in data.get("events", []):
        user_id = event["source"].get("userId")
        event_type = event["type"]

        if event_type == "follow":
            print(f"新しい友達追加: {user_id}")
            # TODO: DBに userId を保存

        elif event_type == "message":
            message_text = event["message"].get("text")
            print(f"userId={user_id}, message={message_text}")
            # TODO: DB保存や応答処理

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    # ローカルテスト用
    app.run(host="0.0.0.0", port=5000, debug=True)
