import config
import requests

headers = {
    "Content_Type": "application/json",
    "Authorization": "Bearer " + config.LINE_CHANNEL_ACCESS_TOKEN
}

def SendMsg(text,uid):
    res = requests.post("https://api.line.me/v2/bot/message/push", 
                        headers=headers, 
                        json={
                            "to": uid,
                            "messages": [{
                                            "type": "text",
                                            "text": text
                                        }]
                        }
                        ).json()