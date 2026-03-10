import time
import requests
import re
from datetime import datetime
from supabase import create_client, Client

# --- 설정 ---
URL = "https://olqxbazcyyorqtkqmjjo.supabase.co"
KEY = "sb_publishable_FlvMFCwWYsR7ysJgllgTgA_NWRmqW5S"
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
    print(f"[{datetime.now()}] 정기 수집을 시작합니다...")
    try:
        products = supabase.table("tracked_products").select("url, product_name").execute().data

        if not products:
            print("수집할 상품이 없습니다.")
            return

        for p in products:
            url = p['url']
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

            try:
                res = requests.get(url, headers=headers, timeout=10)
                text = res.text

                participant_match = re.search(r'"product_participant_count"\s*:\s*(\d+)', text)
                review_match = re.search(r'"reviewCount"\s*:\s*(\d+)', text)

                participant_count = int(participant_match.group(1)) if participant_match else None
                review_count = int(review_match.group(1)) if review_match else None

                if participant_count is not None or review_count is not None:
                    save_log_with_limit(url, participant_count, review_count)
                    print(f" ✅ 완료: {p['product_name'] or url} -> 참여자: {participant_count} / 리뷰: {review_count}")
                else:
                    print(f" ❌ 실패: {url} (패턴 찾지 못함)")

            except Exception as e:
                print(f" ❌ 오류: {url} -> {e}")

            time.sleep(2)

    except Exception as e:
        print(f"전체 오류 발생: {e}")

if __name__ == "__main__":
    while True:
        run_worker()
        print("2시간 대기 중... (창을 끄지 마세요)")
        time.sleep(7200)