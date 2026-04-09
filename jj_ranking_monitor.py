import requests
from bs4 import BeautifulSoup
import re
import time
import random
from datetime import date
import json

import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://kmcgydyfnnelblhtyexv.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_GzL8hTs1moo6-NP5ErzERA_yuV37UYv")
from datetime import datetime, timezone, timedelta
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
            r = requests.post(url, headers=headers_api, json=data, verify=False, timeout=15)
            return r.status_code
        except Exception as e:
            print(f"    写入失败第{i+1}次：{e}")
            time.sleep(5)
    return 0

def get_fav_count(novel_url):
    try:
        # 把手机版URL转成PC版
        # https://wap.jjwxc.net/book2/10245485
        # → https://www.jjwxc.net/onebook.php?novelid=10245485
        novel_id = novel_url.rstrip("/").split("/")[-1]
        pc_url = f"https://www.jjwxc.net/onebook.php?novelid={novel_id}"
        
        resp = requests.get(pc_url, headers=headers, timeout=10)
        resp.encoding = "gb18030"
        soup = BeautifulSoup(resp.text, "lxml")
        full_text = soup.get_text("\n", strip=True)
        
        fav_lines = [line for line in full_text.split("\n") if "收藏" in line]
        print(f"    [调试] 含收藏的行：{fav_lines[:5]}")
        
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
        
        # 同时获取链接和对应的书名作者文本
        full_text = soup.get_text("\n", strip=True)
        start = full_text.find("【千字收益榜】")
        end = full_text.find("最后生成")
        ranking_text = full_text[start:end]
        
        # 解析书名作者
        lines = [l.strip() for l in ranking_text.split("\n") if l.strip()]
        lines = [l for l in lines if not re.match(r"\d{4}-\d{2}-\d{2}", l)
                 and l not in ["【千字收益榜】", "明日预告"]]
        
        # 获取所有book2链接
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
        "Content-Type": "application/json; charset=utf-8",
    }
    r = requests.patch(
        url,
        headers=headers_api,
        data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
        params=params,
        verify=False,
        timeout=30
    )
    return r.status_code
def main():
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y-%m-%d")
    print(f"📅 日期：{today}")
    
    books = crawl_ranking()
    if not books:
        print("未抓到数据，退出")
        return
    
    for i, book in enumerate(books, 1):
        print(f"\n[{i}/{len(books)}] 《{book['title']}》")
        print(f"  [调试] url: {book['url']}")
        
        fav = get_fav_count(book["url"])
        print(f"  收藏数：{fav}")
        
        data = {
            "rank_date": today,
            "rank_num": book["rank"],
            "title": book["title"],
            "author": book["author"],
            "fav_count": fav,
            "novel_id": book["url"].rstrip("/").split("/")[-1],
            "book_url": book["url"],
            "fav_start": fav,
            "novel_url": book["url"],
        }
        status = supabase_insert("rankings", data)
        print(f"  写入状态：{status}")
        time.sleep(random.uniform(2, 4))
    
    print(f"\n✅ 今日榜单完成！共记录 {len(books)} 本书")

    # 第二步：解析昨日快照，更新fav_end
    print("\n📸 开始处理昨日快照...")
    yesterday = (datetime.now(beijing_tz) - timedelta(days=1)).strftime("%Y-%m-%d")
    result = supabase_get("ranking_snapshots", {"snapshot_date": f"eq.{yesterday}"})
    
    if result and isinstance(result, list):
        snapshot_html = result[0]["html_content"]
        soup = BeautifulSoup(snapshot_html, "lxml")
        snapshot_books = []
        for a in soup.select("a[href*='book2']"):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if not href.startswith("http"):
                href = "https://wap.jjwxc.net" + href
            if title:
                snapshot_books.append({"title": title, "url": href})
        
        print(f"  昨日快照共 {len(snapshot_books)} 本书")
        for book in snapshot_books:
            fav_end = get_fav_count(book["url"])
            # 查昨日fav_start
            rows = supabase_get("rankings", {
                "rank_date": f"eq.{yesterday}",
                "title": f"eq.{book['title']}"
            })
            if rows and isinstance(rows, list):
                fav_start = rows[0].get("fav_start", 0) or 0
                fav_growth = fav_end - fav_start
                supabase_patch(
                    "rankings",
                    {"rank_date": f"eq.{yesterday}", "title": f"eq.{book['title']}"},
                    {"fav_end": fav_end, "fav_growth": fav_growth}
                )
                print(f"  《{book['title']}》fav_end:{fav_end} 涨幅:{fav_growth}")
            time.sleep(random.uniform(2, 4))
        print("✅ 昨日快照处理完成！")
    else:
        print("  未找到昨日快照，跳过")
if __name__ == "__main__":
    main()