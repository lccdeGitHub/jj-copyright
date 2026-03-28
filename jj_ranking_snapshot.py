import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime, timezone, timedelta

SUPABASE_URL = os.environ.get("SUPABASE_URL", "你的url")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "你的key")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

def supabase_insert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers_api = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    r = requests.post(url, headers=headers_api, json=data, verify=False, timeout=30)
    return r.status_code

def main():
    beijing_tz = timezone(timedelta(hours=8))
    today = datetime.now(beijing_tz).strftime("%Y-%m-%d")
    print(f"📸 23:59快照 日期：{today}")
    
    url = "https://wap.jjwxc.net/my/novelincome"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.encoding = "gb18030"
    
    status = supabase_insert("ranking_snapshots", {
        "snapshot_date": today,
        "html_content": resp.text,
    })
    print(f"  快照存储状态：{status}")
    print("✅ 完成！")

if __name__ == "__main__":
    main()