import requests
from bs4 import BeautifulSoup
import re
import time
import random
from datetime import datetime, timezone, timedelta
import os

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kmcgydyfnnelblhtyexv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "你的key")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
    "Referer": "https://www.jjwxc.net",
}

def supabase_insert(table, data, retries=3):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    for i in range(retries):
        try:
            r = requests.post(url, headers=headers_api, json=data, verify=False, timeout=30)
            return r.status_code
        except Exception as e:
            print(f"    写入失败第{i+1}次：{e}")
            time.sleep(5)
    return 0

def supabase_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    r = requests.get(url, headers=headers_api, params=params, verify=False, timeout=30)
    return r.json()

def supabase_patch(table, params, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.patch(url, headers=headers_api, json=data, params=params, verify=False, timeout=30)
    return r.status_code

def get_fav_count(novel_url):
    try:
        novel_id = novel_url.rstrip("/").split("/")[-1]
        pc_url = f"https://www.jjwxc.net/onebook.php?novelid={novel_id}"
        resp = requests.get(pc_url, headers=headers, timeout=10)
        resp.encoding = "gb18030"
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text("\n", strip=True)
        for pattern in [
            r"当前被收藏数[：:\s]*([0-9,]+)",
            r"前被收藏[：:\s]*([0-9,]+)",
            r"被收藏[：:\s]*([0-9,]+)",
        ]:
            match = re.search(pattern, full_text)
            if match:
                return int(match.group(1).replace(",", ""))
    except Exception as e:
        print(f"    详情页失败：{e}")
    return 0

def crawl_ranking():
    print("📊 开始抓取千字收益榜...")
    url = "https://wap.jjwxc.net/my/novelincome"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = "gb18030"
        soup = BeautifulSoup(resp.text, "lxml")
        books = []
        rank = 1
        full_text = soup.get_text("\n", strip=True)
        start = full_text.find("【千字收益榜】")
        end = full_text.find("最后生成")
        ranking_text = full_text[start:end]
        lines = [l.strip() for l in ranking_text.split("\n") if l.strip()]
        lines = [l for l in lines if not re.match(r"\d{4}-\d{2}-\d{2}", l)
                 and l not in ["【千字收益榜】", "明日预告"]]
        links = {a.get_text(strip=True): "https://wap.jjwxc.net" + a.get("href")
                 for a in soup.select("a[href*='book2']")}
        i = 0
        while i < len(lines):
            if i + 2 < len(lines) and lines[i+1] == "-":
                title = lines[i]
                author = lines[i+2]
                url_book = links.get(title, "")
                if title and author and url_book:
                    books.append({
                        "rank": rank,
                        "title": title,
                        "author": author,
                        "url": url_book,
                    })
                    print(f"  {rank}. 《{title}》{author}")
                    rank += 1
                i += 3
            else:
                i += 1
        print(f"  共找到 {len(books)} 本书")
        return books
    except Exception as e:
        print(f"抓取榜单失败：{e}")
        return []

def get_yesterday_snapshot():
    beijing_tz = timezone(timedelta(hours=8))
    yesterday = (datetime.now(beijing_tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    result = supabase_get("ranking_snapshots", {"snapshot_date": f"eq.{yesterday}"})
    if result and isinstance(result, list):
        return yesterday, result[0]["html_content"]
    return yesterday, None

def parse_snapshot_books(html):
    soup = BeautifulSoup(html, "lxml")
    books = []
    for a in soup.select("a[href*='book2']"):
        title = a.get_text(strip=True)
        href = a.get("href", "")
        if not href.startswith("http"):
            href = "https://wap.jjwxc.net" + href
        if title:
            books.append({"title": title, "url": href})
    return books

def update_fav_end(rank_date, title, fav_end):
    result = supabase_get("rankings", {
        "rank_date": f"eq.{rank_date}",
        "title": f"eq.{title}"
    })
    if not result or not isinstance(result, list):
        print(f"    未找到昨日记录：{title}")
        return 0
    fav_start = result[0].get("fav_start", 0) or 0
    fav_growth = fav_end - fav_start
    status = supabase_patch(
        "rankings",
        {"rank_date": f"eq.{rank_date}", "title": f"eq.{title}"},
        {"fav_end": fav_end, "fav_growth": fav_growth}
    )
    return status

def main():
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y-%m-%d")
    print(f"📅 日期：{today}")

    # 第一步：抓今日榜单
    books = crawl_ranking()
    if not books:
        print("未抓到数据，退出")
        return

    for i, book in enumerate(books, 1):
        print(f"\n[{i}/{len(books)}] 《{book['title']}》")
        fav = get_fav_count(book["url"])
        print(f"  收藏数：{fav}")
        data = {
            "rank_date": today,
            "rank_num": book["rank"],
            "title": book["title"],
            "author": book["author"],
            "fav_start": fav,
            "fav_count": fav,
        }
        status = supabase_insert("rankings", data)
        print(f"  写入状态：{status}")
        time.sleep(random.uniform(2, 4))

    print(f"\n✅ 今日榜单完成！共记录 {len(books)} 本书")

    # 第二步：解析昨日快照，更新fav_end
    print("\n📸 开始处理昨日快照...")
    yesterday, snapshot_html = get_yesterday_snapshot()

    if snapshot_html:
        snapshot_books = parse_snapshot_books(snapshot_html)
        print(f"  昨日快照共 {len(snapshot_books)} 本书")
        for book in snapshot_books:
            fav_end = get_fav_count(book["url"])
            status = update_fav_end(yesterday, book["title"], fav_end)
            print(f"  《{book['title']}》fav_end:{fav_end} → {status}")
            time.sleep(random.uniform(2, 4))
        print("✅ 昨日快照处理完成！")
    else:
        print("  未找到昨日快照，跳过")

if __name__ == "__main__":
    main()