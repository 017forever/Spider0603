import requests
from bs4 import BeautifulSoup
import os
import json
import random

import firebase_admin
from firebase_admin import credentials, firestore

from flask import Flask, render_template, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
# ======================
# Firebase 連線
# ======================

if os.path.exists("serviceAccountKey.json"):
    cred = credentials.Certificate("serviceAccountKey.json")
else:
    firebase_config = os.getenv("FIREBASE_CONFIG")
    cred_dict = json.loads(firebase_config)
    cred = credentials.Certificate(cred_dict)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()

app = Flask(__name__)
line_bot_api = LineBotApi(os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))
# ======================
# 首頁
# ======================

@app.route("/")
def index():
    R = "<h1>歡迎進入動畫推薦網站</h1>"
    R += "<a href='/crawl'>更新動畫資料</a><br><hr>"
    R += "<a href='/all'>查看全部動畫</a><br><hr>"
    R += "<a href='/hot'>近期熱播排行</a><br><hr>"
    R += "<a href='/new'>本季新番</a><br><hr>"
    R += "<a href='/newArrive'>新上架</a><br><hr>"
    R += "<a href='/random'>隨機推薦動畫</a><br><hr>"
    R += "<a href='/search'>查詢動漫</a><br><hr>"
    return R

# ======================
# 爬蟲主函式
# ======================

def crawl_anime():
    url = "https://ani.gamer.com.tw/"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"
    soup = BeautifulSoup(response.text, "html.parser")

    anime_list = []

    # --- 近期熱播 ---
    hot_block = soup.select("#blockHotAnime a.theme-list-main")
    for card in hot_block:
        name_tag = card.select_one(".theme-name")
        episode_tag = card.select_one(".theme-number")
        if not name_tag:
            continue
        name = name_tag.text.strip()
        episode = episode_tag.text.strip().replace("共", "").replace("集", "").strip() if episode_tag else "?"
        href = card.get("href", "")
        link = "https://ani.gamer.com.tw/" + href
        anime_list.append({"name": name, "episode": episode, "link": link, "category": "熱播"})

    # --- 新上架 ---
    new_arrive_block = soup.select("#blockAnimeNewArrive a.theme-list-main")
    for card in new_arrive_block:
        name_tag = card.select_one(".theme-name")
        episode_tag = card.select_one(".theme-number")
        date_tag = card.select_one(".theme-time")
        if not name_tag:
            continue
        name = name_tag.text.strip()
        episode = episode_tag.text.strip().replace("共", "").replace("集", "").strip() if episode_tag else "?"
        date = date_tag.text.strip().replace("上架日：", "") if date_tag else "?"
        href = card.get("href", "")
        link = "https://ani.gamer.com.tw/" + href
        anime_list.append({"name": name, "episode": episode, "link": link, "category": "新上架", "date": date})

    # --- 本季新番 ---
    new_season_block = soup.select("div.newanime-date-area a.anime-card-block")
    for card in new_season_block:
        name_tag = card.select_one(".anime-name")
        episode_tag = card.select_one(".anime-episode p")
        if not name_tag:
            continue
        name = name_tag.text.strip()
        episode = episode_tag.text.strip() if episode_tag else "?"
        href = card.get("href", "")
        link = "https://ani.gamer.com.tw/" + href
        anime_list.append({"name": name, "episode": episode, "link": link, "category": "新番"})

    return anime_list

# ======================
# 更新資料庫
# ======================

@app.route("/crawl")
def crawl():
    anime_list = crawl_anime()

    # 清空舊資料
    old_docs = db.collection("anime").stream()
    delete_count = sum(1 for doc in old_docs if doc.reference.delete() or True)

    # 寫入新資料（去重）
    anime_dict = {a["name"]: a for a in anime_list}
    for name, anime in anime_dict.items():
        doc_id = name.replace("/", "_").replace("\\", "_")
        db.collection("anime").document(doc_id).set(anime)

    R = "<h2>動畫資料更新完成</h2>"
    R += f"共抓到：{len(anime_list)} 筆<br>"
    R += f"去重後：{len(anime_dict)} 筆<br>"
    R += "<br><a href='/'>回首頁</a>"
    return R

# ======================
# 查看全部
# ======================

@app.route("/all")
def all_anime():
    docs = db.collection("anime").stream()
    R = "<h2>全部動畫資料</h2>"
    count = 0
    for doc in docs:
        anime = doc.to_dict()
        count += 1
        R += f"<b>{count}. [{anime.get('category','?')}] {anime['name']}</b><br>"
        R += f"集數：{anime['episode']}<br>"
        R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br><hr>"
    R += "<br><a href='/'>回首頁</a>"
    return R

# ======================
# 近期熱播
# ======================

@app.route("/hot")
def hot_anime():
    docs = db.collection("anime").where("category", "==", "熱播").stream()
    R = "<h2>近期熱播</h2>"
    count = 0
    for doc in docs:
        anime = doc.to_dict()
        count += 1
        R += f"<b>{count}. {anime['name']}</b><br>"
        R += f"集數：{anime['episode']}<br>"
        R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br><hr>"
    R += "<br><a href='/'>回首頁</a>"
    return R

# ======================
# 本季新番
# ======================

@app.route("/new")
def new_anime():
    docs = db.collection("anime").where("category", "==", "新番").stream()
    R = "<h2>本季新番</h2>"
    count = 0
    for doc in docs:
        anime = doc.to_dict()
        count += 1
        R += f"<b>{count}. {anime['name']}</b><br>"
        R += f"集數：{anime['episode']}<br>"
        R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br><hr>"
    R += "<br><a href='/'>回首頁</a>"
    return R

# ======================
# 新上架
# ======================

@app.route("/newArrive")
def new_arrive():
    docs = db.collection("anime").where("category", "==", "新上架").stream()
    R = "<h2>新上架</h2>"
    count = 0
    for doc in docs:
        anime = doc.to_dict()
        count += 1
        R += f"<b>{count}. {anime['name']}</b><br>"
        R += f"集數：{anime['episode']}<br>"
        R += f"上架日：{anime.get('date','?')}<br>"
        R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br><hr>"
    R += "<br><a href='/'>回首頁</a>"
    return R

# ======================
# 隨機推薦
# ======================

@app.route("/random")
def random_anime():
    docs = db.collection("anime").stream()
    anime_list = [doc.to_dict() for doc in docs]
    if not anime_list:
        return "目前沒有資料，請先 <a href='/crawl'>更新動畫資料</a>"
    anime = random.choice(anime_list)
    R = "<h2>隨機推薦動畫</h2>"
    R += f"<b>[{anime.get('category','?')}] {anime['name']}</b><br>"
    R += f"集數：{anime['episode']}<br>"
    R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br>"
    R += "<br><a href='/'>回首頁</a>"
    return R

# ======================
# 關鍵字查詢
# ======================

@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    docs = db.collection("anime").stream()
    results = [doc.to_dict() for doc in docs if keyword in doc.to_dict().get("name", "")]
    return render_template("search.html", keyword=keyword, results=results)

# ======================
# API（給 LINE Bot 用）
# ======================

@app.route("/api/search")
def api_search():
    keyword = request.args.get("keyword", "")
    docs = db.collection("anime").stream()
    results = [doc.to_dict() for doc in docs if keyword in doc.to_dict().get("name", "")]
    return jsonify(results)

@app.route("/api/random")
def api_random():
    docs = db.collection("anime").stream()
    anime_list = [doc.to_dict() for doc in docs]
    if not anime_list:
        return jsonify({"message": "目前沒有動畫資料"})
    return jsonify(random.choice(anime_list))

@app.route("/api/hot")
def api_hot():
    docs = db.collection("anime").where("category", "==", "熱播").stream()
    return jsonify([doc.to_dict() for doc in docs])

@app.route("/api/new")
def api_new():
    docs = db.collection("anime").where("category", "==", "新番").stream()
    return jsonify([doc.to_dict() for doc in docs])

@app.route("/api/newArrive")
def api_new_arrive():
    docs = db.collection("anime").where("category", "==", "新上架").stream()
    return jsonify([doc.to_dict() for doc in docs])

# ======================
# Dialogflow Webhook
# ======================

@app.route("/webhook", methods=["POST"])
def webhook():
    req = request.get_json(force=True)
    action = req["queryResult"].get("action", "")
    result = ""

    if action == "anime.search":
        keyword = req["queryResult"].get("queryText", "")
        for w in ["查詢", "搜尋", "動畫", "動漫"]:
            keyword = keyword.replace(w, "")
        keyword = keyword.strip()

        if not keyword:
            result = "請告訴我要查詢哪一部動畫"
        else:
            docs = db.collection("anime").stream()
            for doc in docs:
                anime = doc.to_dict()
                if keyword in anime.get("name", ""):
                    result += f"【{anime.get('category','?')}】{anime['name']}\n"
                    result += f"集數：{anime['episode']}\n"
                    result += f"連結：{anime['link']}\n\n"
            if not result:
                result = f"查無符合「{keyword}」的動畫"

    elif action == "anime.random":
        docs = db.collection("anime").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            result = "目前沒有動畫資料，請先更新"
        else:
            anime = random.choice(anime_list)
            result = f"今日推薦【{anime.get('category','?')}】\n"
            result += f"動畫名稱：{anime['name']}\n"
            result += f"集數：{anime['episode']}\n"
            result += f"連結：{anime['link']}"

    elif action == "anime.hot":
        docs = db.collection("anime").where("category", "==", "熱播").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            result = "目前沒有熱播資料，請先更新"
        else:
            result = "🔥 近期熱播：\n"
            for i, anime in enumerate(anime_list[:5], 1):
                result += f"{i}. {anime['name']}（{anime['episode']}集）\n"

    elif action == "anime.new":
        docs = db.collection("anime").where("category", "==", "新番").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            result = "目前沒有新番資料，請先更新"
        else:
            result = "🌟 本季新番：\n"
            for i, anime in enumerate(anime_list[:5], 1):
                result += f"{i}. {anime['name']}（{anime['episode']}）\n"

    elif action == "anime.newArrive":
        docs = db.collection("anime").where("category", "==", "新上架").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            result = "目前沒有新上架資料，請先更新"
        else:
            result = "🆕 新上架：\n"
            for i, anime in enumerate(anime_list[:5], 1):
                result += f"{i}. {anime['name']}（{anime['episode']}集）\n"

    else:
        result = "我目前還不懂這個問題，你可以問我：\n查詢動畫、隨機推薦、熱播排行、本季新番、新上架"

    return jsonify({"fulfillmentText": result})
@app.route("/line", methods=["POST"])
def line_callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        return "Invalid signature", 400
    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()

    # 判斷指令
    if any(k in user_msg for k in ["熱播", "排行", "熱門"]):
        docs = db.collection("anime").where("category", "==", "熱播").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            reply = "目前沒有熱播資料，請先更新"
        else:
            reply = "🔥 近期熱播：\n"
            for i, anime in enumerate(anime_list[:5], 1):
                reply += f"{i}. {anime['name']}（{anime['episode']}集）\n{anime['link']}\n\n"

    elif any(k in user_msg for k in ["新番", "本季"]):
        docs = db.collection("anime").where("category", "==", "新番").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            reply = "目前沒有新番資料，請先更新"
        else:
            reply = "🌟 本季新番：\n"
            for i, anime in enumerate(anime_list[:5], 1):
                reply += f"{i}. {anime['name']}（{anime['episode']}）\n{anime['link']}\n\n"

    elif any(k in user_msg for k in ["新上架", "剛上架"]):
        docs = db.collection("anime").where("category", "==", "新上架").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            reply = "目前沒有新上架資料，請先更新"
        else:
            reply = "🆕 新上架：\n"
            for i, anime in enumerate(anime_list[:5], 1):
                reply += f"{i}. {anime['name']}（{anime['episode']}集）\n{anime['link']}\n\n"

    elif any(k in user_msg for k in ["隨機", "推薦", "隨便"]):
        docs = db.collection("anime").stream()
        anime_list = [doc.to_dict() for doc in docs]
        if not anime_list:
            reply = "目前沒有資料，請先更新"
        else:
            anime = random.choice(anime_list)
            reply = f"🎲 今日推薦【{anime.get('category','?')}】\n"
            reply += f"{anime['name']}（{anime['episode']}集）\n"
            reply += anime['link']

    elif any(k in user_msg for k in ["查詢", "搜尋", "找"]):
        keyword = user_msg
        for w in ["查詢", "搜尋", "找", "動畫", "動漫"]:
            keyword = keyword.replace(w, "").strip()
        if not keyword:
            reply = "請告訴我要查詢哪一部動畫，例如：查詢排球少年！！"
        else:
            docs = db.collection("anime").stream()
            reply = ""
            for doc in docs:
                anime = doc.to_dict()
                if keyword in anime.get("name", ""):
                    reply += f"【{anime.get('category','?')}】{anime['name']}\n"
                    reply += f"集數：{anime['episode']}\n"
                    reply += f"{anime['link']}\n\n"
            if not reply:
                reply = f"查無「{keyword}」相關動畫"

    else:
        reply = "你好！我是動畫推薦Bot 🎌\n\n你可以問我：\n🔥 熱播排行\n🌟 本季新番\n🆕 新上架\n🎲 隨機推薦\n🔍 查詢＋動畫名稱"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply)
    )
# ======================
# 執行 Flask
# ======================

if __name__ == "__main__":
    app.run(debug=True)
