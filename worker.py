import time
import requests
import re
from datetime import datetime
from supabase import create_client, Client

# --- 설정 ---
URL = "https://olqxbazcyyorqtkqmjjo.supabase.co"
KEY = "sb_publishable_FlvMFCwWYsR7ysJgllgTgA_NWRmqW5S"
supabase: Client = create_client(URL, KEY)

def run_worker():
    print(f"[{datetime.now()}] 정기 수집을 시작합니다...")
    try:
        # 1. 등록된 상품 목록 가져오기
        products = supabase.table("tracked_products").select("url, product_name").execute().data
        
        if not products:
            print("수집할 상품이 없습니다.")
            return

        for p in products:
            url = p['url']
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            
            # 2. 크롤링
            res = requests.get(url, headers=headers, timeout=10)
            match = re.search(r'"product_participant_count"\s*:\s*(\d+)', res.text)
            
            if match:
                count = int(match.group(1))
                # 3. DB 저장
                supabase.table("product_logs").insert({
                    "product_url": url, 
                    "participant_count": count
                }).execute()
                print(f" ✅ 완료: {p['product_name'] or url} -> {count}")
            else:
                print(f" ❌ 실패: {url} (패턴 찾지 못함)")
            time.sleep(2) # 매너 타임
            
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    while True:
        run_worker()
        print("2시간 대기 중... (창을 끄지 마세요)")
        time.sleep(7200)