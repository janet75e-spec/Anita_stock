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
FINMIND_API_TOKEN = os.getenv("FINMIND_API_TOKEN")

# --- 驗證環境變數 ---
if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN 與 LINE_CHANNEL_SECRET 是否正確設定在 .env 中")
if not FINMIND_API_TOKEN:
    raise ValueError("❌ 請確認 FINMIND_API_TOKEN 已設定在 .env 檔案中")

# --- 初始化 LINE Bot SDK ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 要追蹤的台股代號 ---
TICKERS = ["0050", "0056", "00878", "00919", "2330", "2317", "2382", "2010"]


# --- 從 FinMind 抓取股價 ---
def get_stock_prices():
    results = []
    for stock_id in TICKERS:
        try:
            url = "https://api.finmindtrade.com/api/v4/data"
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": stock_id,
                "token": FINMIND_API_TOKEN,
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            if data.get("data"):
                latest = data["data"][-1]
                date = latest["date"]
                close = latest["close"]
                open_price = latest["open"]
                high = latest["max"]
                low = latest["min"]

                results.append(f"{stock_id}（{date}）\n收盤價：{close}\n開盤：{open_price}  最高：{high}  最低：{low}")
            else:
                results.append(f"{stock_id} 無法取得資料（可能 API Token 錯誤或流量限制）")

        except Exception as e:
            results.append(f"{stock_id} ❌ 抓取錯誤: {e}")

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
            print(f"✅ 已發送給 {uid}")
        except Exception as e:
            print(f"❌ 發送給 {uid} 失敗: {e}")


# --- 首頁測試 ---
@app.route("/")
def home():
    return "✅ Line Stock Bot is running."


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
    return "✅ 已發送股價訊息"


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