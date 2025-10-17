from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta
import pytz
from flask import Flask, request
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

# --- 載入環境變數 ---
load_dotenv()
app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
FINMIND_API_TOKEN = os.getenv("FINMIND_API_TOKEN")

if not FINMIND_API_TOKEN:
    raise ValueError("❌ 請確認 FINMIND_API_TOKEN 已設定在 .env 檔案中")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 使用者追蹤清單（存在記憶體中） ---
tracked_stocks = set(["0050", "0056", "00878", "00919", "2330", "2317", "2382", "2010"])

# --- FinMind 抓取股價 ---
def get_stock_info(stock_code):
    """取得股票名稱與收盤價"""
    url = "https://api.finmindtrade.com/api/v4/data"

    # 日期往前找兩天，避免假日沒資料
    today = datetime.now().date()
    for i in range(3):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_code,
            "token": FINMIND_API_TOKEN,
            "date": date_str
        }
        r = requests.get(url, params=params)
        data = r.json()
        if data.get("data"):
            latest = data["data"][-1]
            price = latest.get("close")
            name = get_stock_name(stock_code)
            return f"{stock_code} {name}\n收盤價：{price}（{latest['date']}）"

    return f"{stock_code} 無法取得資料（可能代碼錯誤或今日無交易）"

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

# --- 顯示追蹤清單股價 ---
def get_tracked_stocks_info():
    if not tracked_stocks:
        return "目前追蹤清單是空的。"
    results = [get_stock_info(code) for code in tracked_stocks]
    return "\n\n".join(results)

# --- 處理 LINE 訊息 ---
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

    # --- 追蹤股票 ---
    if user_text.startswith("追蹤"):
        code = user_text.replace("追蹤", "").strip()
        if not code.isdigit():
            reply = "請輸入正確股票代碼，例如：追蹤 2330"
        else:
            tracked_stocks.add(code)
            info = get_stock_info(code)
            reply = f"✅ 已新增 {code} 到追蹤清單\n{info}"

    # --- 刪除股票 ---
    elif user_text.startswith("刪除"):
        code = user_text.replace("刪除", "").strip()
        if code in tracked_stocks:
            tracked_stocks.remove(code)
            reply = f"🗑 已從追蹤清單移除 {code}"
        else:
            reply = f"{code} 不在追蹤清單中。"

    # --- 顯示清單 ---
    elif user_text == "清單":
        if not tracked_stocks:
            reply = "目前追蹤清單是空的。"
        else:
            reply = "📋 目前追蹤清單：\n" + "\n".join(sorted(tracked_stocks))

    # --- 查詢所有追蹤股價 ---
    elif user_text == "股價":
        reply = get_tracked_stocks_info()

    # --- 直接查單一股票 ---
    elif user_text.isdigit():
        reply = get_stock_info(user_text)

    # --- 指令提示 ---
    else:
        reply = (
            "📊 可用指令：\n"
            "📈 追蹤 [代碼] → 加入追蹤\n"
            "🗑 刪除 [代碼] → 移除追蹤\n"
            "📋 清單 → 查看追蹤股票\n"
            "💰 股價 → 查看清單中股價\n"
            "🏦 直接輸入股票代碼（例：2330）→ 查單一股價"
        )

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))

@app.route("/")
def home():
    return "Line Stock Bot is running."

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))