import os
import re
import json
import time
import pathlib
from supabase import create_client, Client


# --- 1. Supabase 클라이언트 ---
def get_supabase() -> Client:
    try:
        import streamlit as st
        URL = st.secrets["SUPABASE_URL"]
        KEY = st.secrets["SUPABASE_KEY"]
        return create_client(URL, KEY)
    except Exception:
        pass

    try:
        import toml
        secrets_path = pathlib.Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
        if secrets_path.exists():
            s = toml.load(secrets_path)
            URL = s.get("SUPABASE_URL")
            KEY = s.get("SUPABASE_KEY")
            if URL and KEY:
                return create_client(URL, KEY)
    except Exception:
        pass

    URL = os.getenv("SUPABASE_URL")
    KEY = os.getenv("SUPABASE_KEY")
    if URL and KEY:
        return create_client(URL, KEY)

    raise RuntimeError("Supabase 연결 정보를 찾을 수 없습니다.")


# --- 2. 페이지 소스 가져오기 ---
def fetch_page_source(url):
    """
    curl_cffi → requests 순서로 시도
    curl_cffi : TLS 핑거프린트를 실제 브라우저처럼 위장 (Cloudflare 우회 효과)
    requests  : fallback
    """
    clean_url = url.split('?')[0]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;"
            "q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    # ── 방법 1: curl_cffi (TLS 위장, Cloudflare 우회율 높음) ──
    try:
        from curl_cffi import requests as cf_requests
        resp = cf_requests.get(
            clean_url,
            headers=headers,
            impersonate="chrome124",   # 실제 크롬124 TLS 핑거프린트로 위장
            timeout=30
        )
        if resp.status_code == 200 and len(resp.text) > 5000:
            print("  [curl_cffi] 성공")
            return resp.text, 200
        else:
            print(f"  [curl_cffi] 상태코드: {resp.status_code}, 길이: {len(resp.text)}")
    except ImportError:
        print("  [curl_cffi] 미설치 → requests로 시도")
    except Exception as e:
        print(f"  [curl_cffi] 실패: {e}")

    # ── 방법 2: requests fallback ──
    try:
        import requests
        session = requests.Session()
        resp = session.get(clean_url, headers=headers, timeout=30)
        if resp.status_code == 200 and len(resp.text) > 5000:
            print("  [requests] 성공")
            return resp.text, 200
        else:
            print(f"  [requests] 상태코드: {resp.status_code}")
            return None, resp.status_code
    except Exception as e:
        return None, str(e)


# --- 3. 비야타 데이터 파싱 ---
def parse_viator(html):
    """
    HTML 소스에서 popularityMetrics.count / reviewCount 추출
    """
    popularity_count = None
    review_count = None

    # ── 방법 1: <script id="__NEXT_DATA__"> JSON 파싱 ──
    try:
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if match:
            data = json.loads(match.group(1))
            product = (
                data.get('props', {})
                    .get('pageProps', {})
                    .get('pageModel', {})
                    .get('product', {})
            )
            popularity_count = product.get('popularityMetrics', {}).get('count')
            review_count     = product.get('rating', {}).get('reviewCount')

            if popularity_count is not None or review_count is not None:
                return popularity_count, review_count
    except Exception as e:
        print(f"  [WARN] JSON 파싱 실패: {e}")

    # ── 방법 2: 정규식 fallback ──
    pm = re.search(
        r'"popularityMetrics"\s*:\s*\{[^}]*"count"\s*:\s*(\d+)',
        html
    )
    rv = re.search(
        r'"rating"\s*:\s*\{[^}]*"reviewCount"\s*:\s*(\d+)',
        html
    )
    popularity_count = int(pm.group(1)) if pm else None
    review_count     = int(rv.group(1)) if rv else None

    return popularity_count, review_count


# --- 4. 비야타 데이터 수집 메인 함수 ---
def get_viator_data(url):
    """
    수집 대상:
      - popularityMetrics.count                    → popularity_count  (24시간 예약)
      - pageModel > product > rating > reviewCount → review_count      (누적 리뷰)
    """
    try:
        html, status = fetch_page_source(url)
        if html is None:
            return None, None, status

        popularity_count, review_count = parse_viator(html)
        return popularity_count, review_count, 200

    except Exception as e:
        return None, None, str(e)


# --- 5. 디버그: 소스에서 키 탐색 ---
def get_raw_keys_viator(url):
    """
    __NEXT_DATA__ 에서 popularityMetrics / reviewCount 위치 확인용
    """
    try:
        html, status = fetch_page_source(url)
        if html is None:
            return f"❌ 페이지 로드 실패 ({status})", []

        # __NEXT_DATA__ 추출 시도
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if not match:
            return "❌ __NEXT_DATA__ 없음 (Cloudflare 차단 가능성)", []

        data = json.loads(match.group(1))

        def find_key(obj, target, path="root"):
            results = []
            if isinstance(obj, dict):
                for k, v in obj.items():
                    cur = f"{path}.{k}"
                    if k == target:
                        results.append((cur, v))
                    results.extend(find_key(v, target, cur))
            elif isinstance(obj, list):
                for i, item in enumerate(obj[:5]):
                    results.extend(find_key(item, target, f"{path}[{i}]"))
            return results

        results = []
        results.append(("=== popularityMetrics ===", ""))
        for path, val in find_key(data, "popularityMetrics"):
            results.append((path, str(val)))

        results.append(("=== reviewCount ===", ""))
        for path, val in find_key(data, "reviewCount"):
            results.append((path, str(val)))

        return 200, results

    except Exception as e:
        return str(e), []


# --- 6. 로그 저장 + 최대 10개 유지 (product_logs2) ---
def save_log_with_limit_viator(product_url, popularity_count, review_count):
    supabase = get_supabase()

    supabase.table("product_logs2").insert({
        "product_url":      product_url,
        "popularity_count": popularity_count,
        "review_count":     review_count
    }).execute()

    all_logs = supabase.table("product_logs2").select("id, created_at") \
        .eq("product_url", product_url) \
        .order("created_at", desc=False) \
        .execute().data

    if len(all_logs) > 10:
        excess = all_logs[:len(all_logs) - 10]
        for log in excess:
            supabase.table("product_logs2").delete().eq("id", log["id"]).execute()