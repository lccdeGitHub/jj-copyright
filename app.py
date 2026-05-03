from flask import Flask, render_template, jsonify, request
import json
import os
import requests as req
import base64
import time
import re
app = Flask(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kmcgydyfnnelblhtyexv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_GzL8hTs1moo6-NP5ErzERA_yuV37UYv")

_data_cache = None
_cache_time = 0


def supabase_get(table, filters=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    params = filters or {}
    r = req.get(url, headers=headers, params=params)
    return r.json()

def supabase_upsert(table, data):
    import json as json_lib
    # 先查是否存在
    check_url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json; charset=utf-8",
    }
    # 用PATCH更新或POST新增
    existing = req.get(check_url, headers=headers_api,
                      params={"book_name": f"eq.{data.get('book_name', '')}"})
    
    if existing.json():
        # 已存在，用PATCH更新
        r = req.patch(
            check_url,
            headers={**headers_api, "Prefer": "return=minimal"},
            params={"book_name": f"eq.{data.get('book_name', '')}"},
            data=json_lib.dumps(data, ensure_ascii=False).encode("utf-8")
        )
    else:
        # 不存在，用POST新增
        r = req.post(
            check_url,
            headers={**headers_api, "Prefer": "resolution=merge-duplicates"},
            data=json_lib.dumps(data, ensure_ascii=False).encode("utf-8")
        )
    return r.status_code


def _read_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return default
            return json.loads(content)
    except (json.JSONDecodeError, OSError):
        return default

def load_data():
    global _data_cache, _cache_time
    now = time.time()
    if _data_cache is not None and now - _cache_time < 600:
        return _data_cache
    with open("data.json", "r", encoding="utf-8") as f:
        _data_cache = json.load(f)
    _cache_time = now
    return _data_cache
_notes_cache = None
_notes_cache_time = 0

def get_notes_cached():
    global _notes_cache, _notes_cache_time
    now = time.time()
    if _notes_cache is not None and now - _notes_cache_time < 300:
        return _notes_cache
    url = f"{SUPABASE_URL}/rest/v1/notes"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}"
    }
    resp = req.get(url, headers=headers, params={"select": "book_name,status", "limit": 9999})
    _notes_cache = resp.json()
    _notes_cache_time = now
    return _notes_cache

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

import random

@app.route("/api/books")
def api_books():
    data = load_data()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    channel = request.args.get("channel", "")
    read_status = request.args.get("read_status", "")
    fav_min = request.args.get("fav_min", "")
    fav_max = request.args.get("fav_max", "")
    page = int(request.args.get("page", 1))
    seed = request.args.get("seed", "")
    era = request.args.get("era", "")
    tag = request.args.get("tag", "")
    page_size = 50

    # 如果需要按阅读状态筛选，先从notes表拿对应书名
    if read_status:
        try:
            notes = get_notes_cached()
            read_books = {item["book_name"] for item in notes if item.get("status") == read_status}
            data = [b for b in data if b.get("书名") in read_books]
        except:
            data = []
    if q:
        data = [b for b in data if q in b.get("书名", "") or q in b.get("作者", "")]
    if status:
        data = [b for b in data if b.get("投诉状态") == status]
    if channel:
        # 频道藏在类型字段里，如"原创-纯爱-近代现代-剧情"
        data = [b for b in data if channel in b.get("类型", "")]
    if tag:
        data = [b for b in data if tag in b.get("内容标签", "")]
    # 收藏数筛选，去掉逗号转int
    def parse_fav(s):
        try:
            return int(str(s).replace(",", ""))
        except:
            return 0

    if fav_min:
        data = [b for b in data if parse_fav(b.get("收藏数", 0)) >= int(fav_min)]
    if fav_max:
        data = [b for b in data if parse_fav(b.get("收藏数", 0)) <= int(fav_max)]
    if era:
        data = [b for b in data if era in b.get("类型", "")]
    if seed:
        random.seed(int(seed))
    random.shuffle(data)

    total = len(data)
    start = (page - 1) * page_size
    end = start + page_size

    return jsonify({
        "total": total,
        "page": page,
        "page_size": page_size,
        "seed": seed,
        "data": data[start:end]
    })
@app.route("/api/author_data")
def api_author_data():
    # 获取最新一次抓取时间
    latest = supabase_get("author_stats", {
        "select": "scraped_at",
        "order": "scraped_at.desc",
        "limit": 1
    })
    if not latest or not isinstance(latest, list):
        return jsonify([])
    
    latest_time = latest[0]["scraped_at"]
    
    # 获取该次抓取的所有书目数据
    data = supabase_get("author_stats", {
        "scraped_at": f"eq.{latest_time}",
        "order": "id.asc"
    })
    return jsonify(data if isinstance(data, list) else [])

@app.route("/api/update_status", methods=["POST"])
def update_status():
    body = request.json
    book_name = body.get("书名")
    new_status = body.get("投诉状态")
    data = load_data()
    for book in data:
        if book["书名"] == book_name:
            book["投诉状态"] = new_status
            break
    path = os.path.join(os.path.dirname(__file__), "data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})

@app.route("/api/notes", methods=["GET"])
def get_notes():
    result = supabase_get("notes")
    return jsonify(result if isinstance(result, list) else [])

@app.route("/api/notes", methods=["POST"])
def save_note():
    body = request.json or {}
    book_name = str(body.get("book_name", "")).strip()
    if not book_name:
        return jsonify({"ok": False}), 400

    data = {
        "book_name": book_name,
        "author": str(body.get("author", "")),
        "rating": max(0, min(5, int(body.get("rating", 0) or 0))),
        "status": body.get("status", "想读"),
        "note": str(body.get("note", "")),
    }
    supabase_upsert("notes", data)
    return jsonify({"ok": True})

@app.route("/api/notes/<book_name>", methods=["GET"])
def get_note(book_name):
    result = supabase_get("notes", {"book_name": f"eq.{book_name}"})
    if result and isinstance(result, list):
        return jsonify({"ok": True, "data": result[0]})
    return jsonify({"ok": True, "data": None})

@app.route("/api/media")
def api_media():
    category = request.args.get("category", "")
    params = {}
    if category:
        params["category"] = f"eq.{category}"
    result = supabase_get("media", params)
    return jsonify(result if isinstance(result, list) else [])

@app.route("/api/media/note", methods=["POST"])
def save_media_note():
    body = request.json or {}
    title = str(body.get("title", "")).strip()
    if not title:
        return jsonify({"ok": False}), 400
    data = {
        "note": str(body.get("note", "")),
        "watched": body.get("watched", False),
        "tags": str(body.get("tags", "")),
    }
    url = f"{SUPABASE_URL}/rest/v1/media"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    import requests as req
    req.patch(url, headers=headers_api, json=data, params={"title": f"eq.{title}"})
    return jsonify({"ok": True})

@app.route("/api/bookmarks", methods=["GET"])
def get_bookmarks():
    tag = request.args.get("tag", "")
    params = {}
    if tag:
        params["tags"] = f"like.*{tag}*"
    result = supabase_get("bookmarks", params)
    return jsonify(result if isinstance(result, list) else [])

@app.route("/api/bookmarks", methods=["POST"])
def add_bookmark():
    body = request.json or {}
    url_val = str(body.get("url", "")).strip()
    if not url_val:
        return jsonify({"ok": False}), 400
    data = {
        "url": url_val,
        "title": str(body.get("title", "")),
        "description": str(body.get("description", "")),
        "tags": str(body.get("tags", "")),
        "note": str(body.get("note", "")),
    }
    supabase_upsert("bookmarks", data)
    return jsonify({"ok": True})

@app.route("/api/bookmarks/<int:bookmark_id>", methods=["DELETE"])
def delete_bookmark(bookmark_id):
    url_api = f"{SUPABASE_URL}/rest/v1/bookmarks"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    req.delete(url_api, headers=headers_api, params={"id": f"eq.{bookmark_id}"})
    return jsonify({"ok": True})

@app.route("/api/upload", methods=["POST"])
def upload_image():
    try:
        if "file" not in request.files:
            return jsonify({"ok": False, "error": "no file"}), 400
        
        file = request.files["file"]
        ext = file.filename.rsplit(".", 1)[-1].lower()
        filename = f"{int(time.time())}_{re.sub(r'[^a-zA-Z0-9]', '', file.filename.rsplit('.', 1)[0])}.{ext}"
        if not filename.replace(f".{ext}", ""):
            filename = f"{int(time.time())}.{ext}"
        
        file_data = file.read()
        upload_url = f"{SUPABASE_URL}/storage/v1/object/images/{filename}"
        headers_api = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": file.content_type,
        }
        r = req.post(upload_url, headers=headers_api, data=file_data, verify=False)
        
        if r.status_code in (200, 201):
            public_url = f"{SUPABASE_URL}/storage/v1/object/public/images/{filename}"
            return jsonify({"ok": True, "url": public_url})
        else:
            return jsonify({"ok": False, "error": r.text}), 500
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500
@app.route("/api/images", methods=["GET"])
def get_images():
    list_url = f"{SUPABASE_URL}/storage/v1/object/list/images"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    r = req.post(list_url, headers=headers_api, json={})
    files = r.json() if r.status_code == 200 else []
    result = []
    for f in files:
        name = f.get("name", "")
        url = f"{SUPABASE_URL}/storage/v1/object/public/images/{name}"
        result.append({"name": name, "url": url})
    return jsonify(result)

@app.route("/api/rankings/dates", methods=["GET"])
def get_ranking_dates():
    # 用order+limit只取rank_date列，Supabase侧去重
    url = f"{SUPABASE_URL}/rest/v1/rankings"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer": "count=none"
    }
    params = {
        "select": "rank_date",
        "order": "rank_date.desc",
        "limit": 9999
    }
    r = req.get(url, headers=headers, params=params)
    result = r.json()
    if isinstance(result, list):
        dates = list(set([item["rank_date"] for item in result if item.get("rank_date")]))
        dates.sort(reverse=True)
        return jsonify(dates)
    return jsonify([])

@app.route("/api/rankings", methods=["GET"])
def get_rankings():
    rank_date = request.args.get("date", "")
    params = {}
    if rank_date:
        params["rank_date"] = f"eq.{rank_date}"
    params["order"] = "rank_num.asc"
    result = supabase_get("rankings", params)
    return jsonify(result if isinstance(result, list) else [])
@app.route("/api/weekly_rankings", methods=["GET"])
def get_weekly_rankings():
    period = request.args.get("period", "")
    channel = request.args.get("channel", "")
    params = {}
    if period:
        params["period"] = f"eq.{period}"
    if channel:
        params["channel"] = f"eq.{channel}"
    result = supabase_get("weekly_rankings", params)
    return jsonify(result if isinstance(result, list) else [])

@app.route("/api/weekly_rankings/periods", methods=["GET"])
def get_weekly_periods():
    result = supabase_get("weekly_periods", {"order": "period.desc"})
    if isinstance(result, list):
        periods = [r["period"] for r in result if r.get("period")]
        return jsonify(periods)
    return jsonify([])

@app.route("/api/topten")
def get_topten():
    orderstr = request.args.get("orderstr", "21")
    t = request.args.get("t", "1")
    result = supabase_get("topten_rankings", {
        "orderstr": f"eq.{orderstr}",
        "t": f"eq.{t}",
        "order": "rank_num.asc",
        "limit": 200
    })
    return jsonify(result if isinstance(result, list) else [])


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)