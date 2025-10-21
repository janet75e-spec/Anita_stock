from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta
import pytz
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import threading
import time

# --- 載入 .env ---
load_dotenv()

# --- Flask 啟動 ---
app = Flask(__name__)

# --- 環境變數 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_USER_IDS = [uid.strip() for uid in (os.getenv("LINE_USER_IDS") or "").split(",") if uid.strip()]
FINMIND_API_TOKEN = os.getenv("FINMIND_API_TOKEN")

if not FINMIND_API_TOKEN:
    raise ValueError("❌ 請確認 FINMIND_API_TOKEN 已設定在 .env 檔案中")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 檔案存追蹤清單 ---
TICKER_FILE = "tickers.txt"
if not os.path.exists(TICKER_FILE):
    with open(TICKER_FILE, "w") as f:
        f.write("0050\n0056\n00878\n00919\n2330\n2317\n2382\n2010")

def load_tickers():
    with open(TICKER_FILE, "r") as f:
        return [x.strip() for x in f.readlines() if x.strip()]

def save_tickers(tickers):
    with open(TICKER_FILE, "w") as f:
        f.write("\n".join(sorted(set(tickers))))

# --- FinMind 取得股票名稱 ---
def get_stock_name(stock_code):
    if not stock_code.endswith(".TW"):
        stock_code += ".TW"
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {"dataset": "TaiwanStockInfo", "data_id": stock_code, "token": FINMIND_API_TOKEN}
    r = requests.get(url, params=params)
    data = r.json()
    if data.get("data"):
        return data["data"][0].get("stock_name", "")
    return ""

# --- 取得股票價格（自動往前補資料） ---
def get_stock_info(stock_code):
    if not stock_code.endswith(".TW"):
        stock_code += ".TW"

    url = "https://api.finmindtrade.com/api/v4/data"
    today = datetime.now(pytz.timezone("Asia/Taipei")).date()
    date = today

    for _ in range(5):  # 最多往前5天
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_code,
            "token": FINMIND_API_TOKEN,
            "date": date.strftime("%Y-%m-%d"),
        }
        r = requests.get(url, params=params)
        data = r.json()
        if data.get("data"):
            latest = data["data"][-1]
            name = get_stock_name(stock_code)
            return f"{stock_code.replace('.TW', '')} {name}\n收盤價：{latest['close']}（{latest['date']}）"
        date -= timedelta(days=1)

    return f"{stock_code.replace('.TW', '')} 無法取得資料（可能代碼錯誤或近期無交易）"

# --- 批次抓取追蹤清單 ---
def get_stock_prices():
    tickers = load_tickers()
    results = [get_stock_info(code) for code in tickers]
    return "\n\n".join(results)

# --- LINE 推播 ---
def push_stock_message():
    if not LINE_USER_IDS:
        print("尚未設定 LINE_USER_IDS，無法推播。")
        return
    tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    message = f"📈 台股追蹤（{now}）\n\n{get_stock_prices()}"
    for uid in LINE_USER_IDS:
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=message))
        except Exception as e:
            print(f"發送給 {uid} 失敗: {e}")

# --- 自動排程：每日 13:00 與 14:00 推播 ---
def scheduler():
    tz = pytz.timezone("Asia/Taipei")
    while True:
        now = datetime.now(tz)
        if now.hour in [13, 14] and now.minute == 0:
            print("⏰ 自動推播追蹤清單股價中...")
            push_stock_message()
            time.sleep(60)
        time.sleep(30)

threading.Thread(target=scheduler, daemon=True).start()

# --- Flask routes ---
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

# --- 處理使用者訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text.strip()
    tickers = load_tickers()

    if text == "清單":
        reply = "📋 目前追蹤清單：\n" + "\n".join(tickers) if tickers else "目前追蹤清單是空的。"
    elif text.startswith("追蹤"):
        code = text.replace("追蹤", "").strip()
        if code:
            tickers.append(code)
            save_tickers(tickers)
            reply = f"✅ 已新增 {code} 到追蹤清單"
        else:
            reply = "請輸入格式：追蹤 [代碼]"
    elif text.startswith("刪除"):
        code = text.replace("刪除", "").strip()
        if code in tickers:
            tickers.remove(code)
            save_tickers(tickers)
            reply = f"🗑️ 已刪除 {code} 從追蹤清單"
        else:
            reply = f"{code} 不在清單中"
    elif text == "股價":
        reply = get_stock_prices()
    elif text.isdigit():
        reply = get_stock_info(text)
    else:
        reply = "可用指令：\n📈 追蹤 [代碼]\n🗑️ 刪除 [代碼]\n📋 清單\n💰 股價 [代碼]"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)