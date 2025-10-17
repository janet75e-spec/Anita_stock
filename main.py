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

# --- 從環境變數取出設定 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_USER_IDS = [uid.strip() for uid in (os.getenv("LINE_USER_IDS") or "").split(",") if uid.strip()]

# --- 驗證環境變數是否存在 ---
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("❌ LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 未正確載入，請檢查 .env 檔案")

# --- 初始化 LINE Bot SDK ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 要追蹤的台股代號 ---
TICKERS = {
    "0050": "元大台灣50",
    "0056": "元大高股息",
    "00878": "國泰永續高股息",
    "00919": "群益台灣精選高息",
    "2330": "台積電",
    "2317": "鴻海",
    "2382": "廣達",
    "2101": "南港"
}

# --- 抓取 FinMind 股價 ---
def get_stock_prices():
    """從 FinMind API 抓取台股價格"""
    results = []
    today = datetime.now(pytz.timezone("Asia/Taipei")).strftime("%Y-%m-%d")

    for stock_id, name in TICKERS.items():
        try:
            url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id={stock_id}&date={today}"
            response = requests.get(url, timeout=10)
            data = response.json().get("data", [])

            if data:
                latest = data[-1]
                price = latest.get("close")
                change = latest.get("close") - latest.get("open")
                arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
                pct = (change / latest.get("open") * 100) if latest.get("open") else 0
                results.append(f"{stock_id} {name}\n💰 {price:.2f} ({arrow}{change:.2f}, {pct:.2f}%)")
            else:
                results.append(f"{stock_id} {name}\n⚠️ 無法取得今日資料")
        except Exception as e:
            results.append(f"{stock_id} {name}\n❌ 抓取錯誤: {e}")

    return "\n\n".join(results)


# --- 推播功能 ---
def push_stock_message():
    """推播股價到 LINE"""
    if not LINE_USER_IDS:
        print("尚未設定 LINE_USER_IDS，無法推播。")
        return

    tz = pytz.timezone("Asia/Taipei")
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    message = f"📈 台股追蹤（{now}）\n\n{get_stock_prices()}"

    for uid in LINE_USER_IDS:
        try:
            line_bot_api.push_message(uid, TextSendMessage(text=message))
            print(f"已發送給 {uid}")
        except Exception as e:
            print(f"發送給 {uid} 失敗: {e}")


# --- 首頁測試 ---
@app.route("/")
def home():
    return "Line Stock Bot (FinMind 版本) is running."


# --- LINE Webhook ---
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK"


# --- 手動推播測試 ---
@app.route("/push", methods=['GET'])
def manual_push():
    push_stock_message()
    return "✅ 已發送股價訊息（FinMind 版）"


# --- 處理使用者訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    if "股價" in user_text:
        reply = get_stock_prices()
    else:
        reply = "請輸入「股價」即可查詢最新台股資訊 📊"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()
