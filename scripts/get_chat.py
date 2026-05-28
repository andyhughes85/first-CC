import requests
s = requests.Session()
s.proxies = {"https": "socks5h://127.0.0.1:1080"}
r = s.post("https://api.telegram.org/bot8991675281:AAFbGF0xvlpzs9RZafY8U6k8cmwEoYKe02s/getUpdates")
data = r.json()
for u in data.get("result", []):
    msg = u.get("message", {})
    chat = msg.get("chat", {})
    print(f"chat_id: {chat.get('id')}, type: {chat.get('type')}, title: {chat.get('title','')}, text: {str(msg.get('text',''))[:50]}")
