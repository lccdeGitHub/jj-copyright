import requests
# from JJWXC.jj_topten import save_to_supabase
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime
import time

AUTHOR_ID = "4699680"
AUTHOR_URL = f"https://www.jjwxc.net/oneauthor.php?authorid={AUTHOR_ID}"
OUTPUT_FILE = "author_data.json"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kmcgydyfnnelblhtyexv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_GzL8hTs1moo6-NP5ErzERA_yuV37UYv")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

def save_to_supabase(scraped_at, author_fav, books):
    rows = []
    for book in books:
        try:
            fav = int(book.get("收藏数", 0))
        except:
            fav = None
        try:
            comment = int(book.get("评论数", 0))
        except:
            comment = None

        rows.append({
            "scraped_at": scraped_at,
            "author_fav": int(author_fav) if str(author_fav).isdigit() else None,
            "book_name": book.get("书名"),
            "book_type": book.get("类型"),
            "progress": book.get("进度"),
            "word_count": book.get("字数"),
            "score": book.get("积分"),
            "fav_count": fav,
            "comment_count": comment,
            "novel_url": book.get("链接"),
        })

    url = f"{SUPABASE_URL}/rest/v1/author_stats"
    resp = requests.post(
        url,
        headers=SUPABASE_HEADERS,
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8")
    )
    print(f"Supabase 保存状态：{resp.status_code}")
    if resp.status_code not in (200, 201):
        print(resp.text)

def get_book_stats(novel_url):
    stats = {"收藏数": "未获取", "评论数": "未获取"}
    try:
        resp = requests.get(novel_url, headers=headers, timeout=10)
        resp.encoding = "gb18030"
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text("\n", strip=True)

        match = re.search(r"当前被收藏数[：:\s]*([0-9,]+)", full_text)
        if match:
            stats["收藏数"] = match.group(1).replace(",", "")
            print(f"    收藏数：{stats['收藏数']}")

        comment_match = re.search(r"总书评数[：:\s]*([0-9,]+)", full_text)
        if comment_match:
            stats["评论数"] = comment_match.group(1).replace(",", "")

    except Exception as e:
        print(f"    详情页失败：{e}")
    return stats
def fetch_author_data():
    print("📊 开始抓取作者数据...")
    
    # 启动浏览器
    # from selenium import webdriver
    # from selenium.webdriver.edge.options import Options
    # options = Options()
    # options.add_argument("--headless")
    # options.add_argument("--disable-gpu")
    # options.add_argument("--no-sandbox")
    # driver = webdriver.Edge(options=options)

    try:
        resp = requests.get(AUTHOR_URL, headers=headers, timeout=10)
        resp.encoding = "gb18030"
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text("\n", strip=True)

        # 作者被收藏数
        author_fav = "未获取"
        match = re.search(r"被收藏数[：:\s]*([0-9,]+)", full_text)
        if match:
            author_fav = match.group(1).replace(",", "")
        print(f"  作者被收藏：{author_fav}")

        # 每本书基础信息
        books = []
        for row in soup.select("table tr"):
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
            book_a = row.select_one("a[href*='novelid']")
            if not book_a:
                continue

            book_name = book_a.get_text(strip=True)
            if not book_name:
                continue

            book_href = book_a.get("href", "")
            if book_href.startswith("http"):
                pass
            elif book_href.startswith("/"):
                book_href = "https://www.jjwxc.net" + book_href
            else:
                book_href = "https://www.jjwxc.net/" + book_href

            book_type  = cols[1].get_text(strip=True) if len(cols) > 1 else ""
            progress   = cols[2].get_text(strip=True) if len(cols) > 2 else ""
            word_count = cols[3].get_text(strip=True) if len(cols) > 3 else ""
            score      = cols[4].get_text(strip=True) if len(cols) > 4 else ""

            if progress not in ["连载", "完结"]:
                continue

            print(f"  📖 《{book_name}》 获取详情...")
            stats = get_book_stats(book_href)

            books.append({
                "书名":   book_name,
                "类型":   book_type,
                "进度":   progress,
                "字数":   word_count,
                "积分":   score,
                "收藏数": stats["收藏数"],
                "评论数": stats["评论数"],
                "链接":   book_href,
            })
            time.sleep(1)

        # 读取历史数据
        history = []
        if os.path.exists(OUTPUT_FILE):
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    history = json.loads(content)

        # 追加新数据
        history.append({
            "抓取时间":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "作者被收藏": author_fav,
            "作品列表":   books,
        })

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

        # 存 Supabase
            scraped_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            save_to_supabase(scraped_at, author_fav, books)

            print(f"\n✅ 完成！共 {len(books)} 本书，数据已保存到 {OUTPUT_FILE}")
            return history
    

    except Exception as e:
        print(f"抓取失败：{e}")
        return []

    # finally:
    #     driver.quit()
    #     print("浏览器已关闭")
if __name__ == "__main__":
    fetch_author_data()