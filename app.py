from flask import Flask, render_template, jsonify, request
import json
import os

app = Flask(__name__)

def load_data():
    path = os.path.join(os.path.dirname(__file__), "data.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/books")
def api_books():
    data = load_data()
    # 支持搜索
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    if q:
        data = [b for b in data if q in b["书名"] or q in b["作者"]]
    if status:
        data = [b for b in data if b.get("投诉状态") == status]
    return jsonify(data)

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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
```

新建 `requirements.txt`：
```
flask
gunicorn