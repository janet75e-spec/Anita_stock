from dotenv import load_dotenv
import os
import requests
import json
from datetime import datetime
import pytz
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- 載入環境變數 ---
load_dotenv()

app = Flask(__name__)

# --- LINE 與 FinMind Token ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
FINMIND_API_TOKEN = os.getenv("FINMIND_API_TOKEN")

# --- 初始化 LINE Bot ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 使用者追蹤清單儲存 (in-memory) ---
user_watchlist = {}

# === FinMind 股票資料 ===
def get_stock_info(stock_code):
    """使用新版 FinMind API 取得股票名稱與最新收盤價"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_code,
        "token": FINMIND_API_TOKEN,
    }

    try:
        r = requests.get(url, params=params)
        data = r.json()

        if not data.get("data"):
            return f"{stock_code} 無法取得資料（可能代碼錯誤或今日無交易）"

        latest = data["data"][-1]
        price = latest.get("close")
        date = latest.get("date", "")
        stock_name = get_stock_name(stock_code)
        return f"{stock_code} {stock_name}\n收盤價：{price}（{date}）"

    except Exception as e:
        return f"{stock_code} 抓取錯誤：{str(e)}"


def get_stock_name(stock_code):
    """查詢股票名稱"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockInfo",
        "data_id": stock_code,
        "token": FINMIND_API_TOKEN,
    }

    r = requests.get(url, params=params)
    data = r.json()
    if data.get("data"):
        return data["data"][0].get("stock_name", "")
    return ""

# === 使用者指令 ===
def handle_command(user_id, text):
    """處理使用者輸入指令"""
    words = text.strip().split()
    cmd = words[0].lower()

    # 初始化使用者清單
    if user_id not in user_watchlist:
        user_watchlist[user_id] = []

    # ➕ 追蹤股票
    if cmd == "追蹤" and len(words) > 1:
        code = words[1]
        if code not in user_watchlist[user_id]:
            user_watchlist[user_id].append(code)
            return f"✅ 已新增 {code} 到追蹤清單"
        else:
            return f"⚠️ {code} 已在追蹤清單中"

    # 🗑️ 刪除股票
    elif cmd == "刪除" and len(words) > 1:
        code = words[1]
        if code in user_watchlist[user_id]:
            user_watchlist[user_id].remove(code)
            return f"🗑️ 已從追蹤清單移除 {code}"
        else:
            return f"⚠️ {code} 不在追蹤清單中"

    # 📋 顯示清單
    elif cmd == "清單":
        if not user_watchlist[user_id]:
            return "📭 目前追蹤清單是空的。"
        return "📋 目前追蹤清單：\n" + "\n".join(user_watchlist[user_id])

    # 💰 查詢清單股價
    elif cmd == "股價":
        if not user_watchlist[user_id]:
            return "📭 目前沒有追蹤任何股票。\n可輸入『追蹤 2330』來新增。"
        reply_list = [get_stock_info(code) for code in user_watchlist[user_id]]
        return "\n\n".join(reply_list)

    # 🧾 查詢單一股票（直接輸入代碼）
    elif cmd.isdigit():
        return get_stock_info(cmd)

    # ❓幫助指令
    else:
        return (
            "可用指令：\n"
            "📈 追蹤 [代碼]\n"
            "🗑️ 刪除 [代碼]\n"
            "📋 清單\n"
            "💰 股價\n"
            "例如：追蹤 2330、股價、2881"
        )

# === LINE Webhook ===
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK"

# === 處理使用者訊息 ===
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    user_text = event.message.text.strip()
    reply = handle_command(user_id, user_text)
    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/")
def home():
    return "✅ Line Stock Bot is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)