from dotenv import load_dotenv
import os
import requests
from datetime import datetime
import pytz
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

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

# --- 初始化 LINE Bot SDK ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 預設追蹤股票清單 ---
TICKERS = ["0050", "0056", "00878", "00919", "2330", "2317", "2382", "2010"]

# --- 從 FinMind 取得股票資料 ---
def get_stock_info(stock_code):
    """用 FinMind API 抓取股票名稱與收盤價"""
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_code,
        "token": FINMIND_API_TOKEN,
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    r = requests.get(url, params=params)
    data = r.json()

    if not data.get("data"):
        return f"{stock_code} 無法取得資料（可能代碼錯誤或今日無交易）"

    latest = data["data"][-1]
    price = latest["close"]
    stock_name = get_stock_name(stock_code)
    return f"{stock_code} {stock_name}\n收盤價：{price}"

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

# --- 批次抓取追蹤股票 ---
def get_stock_prices():
    results = [get_stock_info(code) for code in TICKERS]
    return "\n\n".join(results)

# --- 推播功能 ---
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
    user_text = event.message.text.strip()

    if user_text == "股價":
        reply = get_stock_prices()
    elif user_text.isdigit():  # 使用者輸入股票代碼
        reply = get_stock_info(user_text)
    else:
        reply = "請輸入股票代碼（例如：2330）或輸入『股價』查看清單股票。"

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

if __name__ == "__main__":
    app.run()