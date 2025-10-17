from dotenv import load_dotenv
import os, json, requests
from datetime import datetime
import pytz
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- 載入 .env ---
load_dotenv()

app = Flask(__name__)

# --- 讀取環境變數 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_USER_IDS = [uid.strip() for uid in (os.getenv("LINE_USER_IDS") or "").split(",") if uid.strip()]
FINMIND_API_TOKEN = os.getenv("FINMIND_API_TOKEN")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_CHANNEL_SECRET 已設定於 .env")

if not FINMIND_API_TOKEN:
    raise ValueError("❌ 請確認 FINMIND_API_TOKEN 已設定於 .env")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

TRACK_FILE = "tracked_stocks.json"

# --- 讀取或初始化追蹤清單 ---
def load_tracked():
    if os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_tracked(stocks):
    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(stocks, f, ensure_ascii=False, indent=2)

# --- 從 FinMind 取得股價 ---
def get_stock_price(stock_id):
    try:
        url = "https://api.finmindtrade.com/api/v4/data"
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "token": FINMIND_API_TOKEN,
            "date": datetime.now().strftime("%Y-%m-%d")
        }
        r = requests.get(url, params=params)
        data = r.json()

        if not data.get("data"):
            return f"{stock_id} 無法取得資料（可能 API Token 錯誤或今日尚無資料）"

        latest = data["data"][-1]
        price = latest["close"]
        name = latest.get("stock_name", "")
        return f"{stock_id} {name}\n收盤價：{price}"
    except Exception as e:
        return f"{stock_id} 抓取錯誤：{e}"

# --- 處理推播追蹤清單 ---
def push_stock_message():
    stocks = load_tracked()
    if not stocks:
        print("目前追蹤清單為空。")
        return

    tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")

    messages = [f"📈 台股追蹤（{now}）"]
    for sid in stocks:
        messages.append(get_stock_price(sid))

    message = "\n\n".join(messages)

    for uid in LINE_USER_IDS:
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=message))
        except Exception as e:
            print(f"發送給 {uid} 失敗: {e}")

@app.route("/")
def home():
    return "Line Stock Bot is running."

@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()
    reply = ""

    stocks = load_tracked()

    if user_text.startswith("追蹤"):
        code = user_text.replace("追蹤", "").strip()
        if not code:
            reply = "請輸入股票代碼，例如：追蹤 2330"
        elif code in stocks:
            reply = f"{code} 已在追蹤清單中"
        else:
            stocks.append(code)
            save_tracked(stocks)
            reply = f"✅ 已新增 {code} 到追蹤清單"

    elif user_text.startswith("刪除"):
        code = user_text.replace("刪除", "").strip()
        if code in stocks:
            stocks.remove(code)
            save_tracked(stocks)
            reply = f"🗑 已從追蹤清單移除 {code}"
        else:
            reply = f"{code} 不在追蹤清單中"

    elif user_text == "清單":
        if not stocks:
            reply = "目前追蹤清單是空的。"
        else:
            reply = "📋 目前追蹤清單：\n" + "\n".join(stocks)

    elif user_text.startswith("股價"):
        code = user_text.replace("股價", "").strip()
        if not code:
            reply = "請輸入股票代碼，例如：股價 2330"
        else:
            reply = get_stock_price(code)

    else:
        reply = "可用指令：\n📈 追蹤 [代碼]\n🗑 刪除 [代碼]\n📋 清單\n💰 股價 [代碼]"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()