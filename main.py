import requests
from bs4 import BeautifulSoup
import os
import json
import random

import firebase_admin
from firebase_admin import credentials, firestore

from flask import Flask, render_template, request, jsonify

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

# ======================
# 首頁
# ======================

@app.route("/")
def index():
    R = "<h1>歡迎進入動畫推薦網站</h1>"
    R += "<a href='/crawl'>更新動畫資料</a><br><hr>"
    R += "<a href='/all'>查看全部動畫</a><br><hr>"
    R += "<a href='/random'>隨機推薦動畫</a><br><hr>"
    R += "<a href='/search'>查詢動漫</a><br><hr>"
    R += "<a href='/webhook'>webhook測試</a><br><hr>"
    return R

# ======================
# 爬動畫瘋並存 Firebase
# ======================

@app.route("/crawl")
def crawl():
    url = "https://ani.gamer.com.tw/"

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    response = requests.get(url, headers=headers)
    response.encoding = "utf-8"

    soup = BeautifulSoup(response.text, "html.parser")

    cards = soup.select("a.theme-list-main")

    anime_list = []

    for card in cards:
        name = card.select_one(".theme-name").text.strip()

        year = card.select_one(".theme-time").text.strip()
        year = year.replace("年份：", "")

        episode = card.select_one(".theme-number").text.strip()
        episode = episode.replace("共", "")
        episode = episode.replace("集", "")

        link = "https://ani.gamer.com.tw/" + card.get("href")

        anime = {
            "name": name,
            "year": year,
            "episode": episode,
            "link": link
        }

        anime_list.append(anime)

    # 去除重複動畫
    anime_dict = {}

    for anime in anime_list:
        anime_dict[anime["name"]] = anime

    # 先清空舊資料
    old_docs = db.collection("anime").stream()

    delete_count = 0

    for doc in old_docs:
        doc.reference.delete()
        delete_count += 1

    # 寫入新資料
    for name, anime in anime_dict.items():
        doc_id = name
        doc_id = doc_id.replace("/", "_")
        doc_id = doc_id.replace("\\", "_")

        db.collection("anime").document(doc_id).set(anime)

    R = "<h2>動畫資料更新完成</h2>"
    R += f"原本抓到：{len(anime_list)} 筆<br>"
    R += f"去除重複後：{len(anime_dict)} 筆<br>"
    R += f"刪除舊資料：{delete_count} 筆<br>"
    R += f"成功寫入：{len(anime_dict)} 筆<br>"
    R += "<br><a href='/'>回首頁</a>"

    return R

# ======================
# 查看全部動畫
# ======================

@app.route("/all")
def all_anime():
    docs = db.collection("anime").stream()

    R = "<h2>全部動畫資料</h2>"

    count = 0

    for doc in docs:
        anime = doc.to_dict()
        count += 1

        R += f"<b>{count}. {anime['name']}</b><br>"
        R += f"年份：{anime['year']}<br>"
        R += f"集數：{anime['episode']}<br>"
        R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br>"
        R += "<hr>"

    R += "<br><a href='/'>回首頁</a>"

    return R

# ======================
# 關鍵字查詢
# ======================

@app.route("/search")
def search():

    keyword = request.args.get("keyword", "")

    docs = db.collection("anime").stream()

    results = []

    for doc in docs:

        anime = doc.to_dict()

        if keyword in anime["name"]:
            results.append(anime)

    return render_template(
        "search.html",
        keyword=keyword,
        results=results
    )

# ======================
# 隨機推薦動畫
# ======================

@app.route("/random")
def random_anime():
    docs = db.collection("anime").stream()

    anime_list = []

    for doc in docs:
        anime_list.append(doc.to_dict())

    if len(anime_list) == 0:
        return "目前沒有動畫資料，請先更新資料：<a href='/crawl'>更新動畫資料</a>"

    anime = random.choice(anime_list)

    R = "<h2>今日隨機推薦動畫</h2>"
    R += f"<b>{anime['name']}</b><br>"
    R += f"年份：{anime['year']}<br>"
    R += f"集數：{anime['episode']}<br>"
    R += f"<a href='{anime['link']}' target='_blank'>觀看連結</a><br>"
    R += "<br><a href='/'>回首頁</a>"

    return R

# ======================
# 給 Dialogflow / LINE 用的 JSON API
# ======================

@app.route("/api/search")
def api_search():
    keyword = request.args.get("keyword", "")

    docs = db.collection("anime").stream()

    results = []

    for doc in docs:
        anime = doc.to_dict()

        if keyword in anime["name"]:
            results.append(anime)

    return jsonify(results)

@app.route("/api/random")
def api_random():
    docs = db.collection("anime").stream()

    anime_list = []

    for doc in docs:
        anime_list.append(doc.to_dict())

    if len(anime_list) == 0:
        return jsonify({"message": "目前沒有動畫資料"})

    anime = random.choice(anime_list)

    return jsonify(anime)

# ======================
# Dialogflow Webhook
# ======================

@app.route("/webhook", methods=["POST"])
def webhook():
    req = request.get_json(force=True)

    action = req["queryResult"]["action"]

    result = ""

    # 查詢動畫
    if action == "anime.search":
        keyword = req["queryResult"]["parameters"].get("anime", "")

        docs = db.collection("anime").stream()

        for doc in docs:
            anime = doc.to_dict()

            if keyword in anime["name"]:
                result += "動畫名稱：" + anime["name"] + "\n"
                result += "年份：" + anime["year"] + "\n"
                result += "集數：" + anime["episode"] + "\n"
                result += "連結：" + anime["link"] + "\n\n"

        if result == "":
            result = "查無符合「" + keyword + "」的動畫"

    # 隨機推薦動畫
    elif action == "anime.random":
        docs = db.collection("anime").stream()

        anime_list = []

        for doc in docs:
            anime_list.append(doc.to_dict())

        if len(anime_list) == 0:
            result = "目前沒有動畫資料，請先更新動畫資料"
        else:
            anime = random.choice(anime_list)

            result = "今日推薦動畫：\n"
            result += "動畫名稱：" + anime["name"] + "\n"
            result += "年份：" + anime["year"] + "\n"
            result += "集數：" + anime["episode"] + "\n"
            result += "連結：" + anime["link"]

    else:
        result = "我目前還不懂這個問題"

    return jsonify({
        "fulfillmentText": result
    })

# ======================
# 執行 Flask
# ======================

if __name__ == "__main__":
    app.run(debug=True)
