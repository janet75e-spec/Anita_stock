from dotenv import load_dotenv
import os
import requests
from datetime import datetime, timedelta
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
    raise ValueError("❌ 請確認 LINE_CHANNEL_ACCESS_TOKEN、LINE_CHANNEL_SECRET 已設定在 .env 檔案中")
if not FINMIND_API_TOKEN:
    raise ValueError("❌ 請確認 FINMIND_API_TOKEN 已設定在 .env 檔案中")

# --- 初始化 LINE Bot ---
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 要追蹤的股票代號與名稱 ---
STOCKS = {
    "0050": "元大台灣50",
    "0056": "元大高股息",
    "00878": "國泰永續高股息",
    "00919": "群益台灣精選高息",
    "2330": "台積電",
    "2317": "鴻海",
    "2382": "廣達",
    "2101": "南港"
}


# --- 抓取台股股價（FinMind API）---
def fetch_stock_price(code):
    """從 FinMind 抓取單一股票資料"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        url = (
            f"https://api.finmindtrade.com/api/v4/data?"
            f"dataset=TaiwanStockPrice&data_id={code}"
            f"&start_date={start_date}&end_date={end_date}"
            f"&token={FINMIND_API_TOKEN}"
        )
        r = requests.get(url)
        data = r.json()

        if data.get("msg") != "success" or not data.get("data"):
            return f"{code} ⚠️ 無法取得資料（API Token 錯誤或流量限制）"

        latest = data["data"][-1]
        price = latest["close"]
        change = latest["close"] - latest["open"]
        pct = (change / latest["open"]) * 100 if latest["open"] else 0
        arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")

        name = STOCKS.get(code, "未知名稱")
        return f"{code} {name}\n收盤價 {price:.2f} ({arrow}{change:.2f}, {pct:.2f}%)"

    except Exception as e:
        return f"{code} ❌ 抓取錯誤: {e}"


def get_stock_prices():
    """抓取多檔股票"""
    return "\n\n".join([fetch_stock_price(code) for code in STOCKS.keys()])


# --- 推播功能 ---
def push_stock_message():
    """推播股價到 LINE"""
    if not LINE_USER_IDS:
        print("⚠️ 尚未設定 LINE_USER_IDS，無法推播。")
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
    return "✅ Line Stock Bot is running on Render!"


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


# --- 手動推播測試用 ---
@app.route("/push", methods=['GET'])
def manual_push():
    push_stock_message()
    return "✅ 已手動發送股價訊息！"


# --- 處理使用者訊息 ---
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_text = event.message.text.strip()

    # 若輸入「股價」：顯示全部
    if user_text == "股價":
        reply = get_stock_prices()

    # 若輸入的是代碼（例如 2330）
    elif user_text in STOCKS.keys():
        reply = fetch_stock_price(user_text)

    # 若輸入的是股票名稱（例如 台積電）
    elif user_text in STOCKS.values():
        # 反查代碼
        code = [k for k, v in STOCKS.items() if v == user_text][0]
        reply = fetch_stock_price(code)

    else:
        reply = "請輸入『股價』查看全部，或直接輸入股票代碼（例如：2330）📊"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )


if __name__ == "__main__":
    app.run()
