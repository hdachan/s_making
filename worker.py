import os
import requests
import re
import time
from datetime import datetime
from supabase import create_client, Client

# --- 설정 (GitHub Actions 환경변수에서 읽기) ---
URL = os.environ.get("SUPABASE_URL")
KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(URL, KEY)

def save_log_with_limit(product_url, participant_count, review_count):
    supabase.table("product_logs").insert({
        "product_url": product_url,
        "participant_count": participant_count,
        "review_count": review_count
    }).execute()

    all_logs = supabase.table("product_logs").select("id, created_at") \
        .eq("product_url", product_url) \
        .order("created_at", desc=False) \
        .execute().data

    if len(all_logs) > 10:
        excess = all_logs[:len(all_logs) - 10]
        for log in excess:
            supabase.table("product_logs").delete().eq("id", log["id"]).execute()

def run_worker():
    print(f"[{datetime.now()}] 수집 시작...")
    
    products = supabase.table("tracked_products").select("url, product_name").execute().data

    if not products:
        print("수집할 상품이 없습니다.")
        return

    for p in products:
        url = p['url']
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8',
            'Connection': 'keep-alive',
        }

        try:
            session = requests.Session()
            session.get("https://www.klook.com", headers=headers, timeout=10)
            time.sleep(3)
            response = session.get(url, headers=headers, timeout=15)

            if response.status_code == 200:
                text = response.text
                participant_match = re.search(r'"product_participant_count"\s*:\s*(\d+)', text)
                review_match = re.search(r'"reviewCount"\s*:\s*(\d+)', text)

                participant_count = int(participant_match.group(1)) if participant_match else None
                review_count = int(review_match.group(1)) if review_match else None

                if participant_count is not None or review_count is not None:
                    save_log_with_limit(url, participant_count, review_count)
                    print(f"✅ {p['product_name'] or url} → 참여자: {participant_count} / 리뷰: {review_count}")
                else:
                    print(f"❌ {url} → 데이터 없음")
            else:
                print(f"❌ {url} → 상태코드: {response.status_code}")

        except Exception as e:
            print(f"❌ {url} → 오류: {e}")

        time.sleep(5)  # 상품 간 5초 간격

if __name__ == "__main__":
    run_worker()