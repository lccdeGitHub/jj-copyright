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
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    r = req.post(url, headers=headers, json=data)
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
    path = os.path.join(os.path.dirname(__file__), "data.json")
    data = _read_json_file(path, [])
    return data if isinstance(data, list) else []

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/books")
def api_books():
    data = load_data()
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    if q:
        data = [b for b in data if q in b["书名"] or q in b["作者"]]
    if status:
        data = [b for b in data if b.get("投诉状态") == status]
    return jsonify(data)

@app.route("/api/author_data")
def api_author_data():
    path = os.path.join(os.path.dirname(__file__), "author_data.json")
    data = _read_json_file(path, [])
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
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "no file"}), 400
    
    file = request.files["file"]
    
    # 清理文件名，只保留英文数字和后缀
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
    r = req.post(upload_url, headers=headers_api, data=file_data)
    
    if r.status_code in (200, 201):
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/images/{filename}"
        return jsonify({"ok": True, "url": public_url})
    else:
        return jsonify({"ok": False, "error": r.text}), 500
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


    
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)