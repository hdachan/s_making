import os
import re
import time
import streamlit as st
from supabase import create_client, Client
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# --- 1. Supabase 클라이언트 ---
def get_supabase() -> Client:
    URL = st.secrets["SUPABASE_URL"]
    KEY = st.secrets["SUPABASE_KEY"]
    return create_client(URL, KEY)


# --- 2. Selenium 브라우저 설정 ---
def get_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
        driver = webdriver.Chrome(service=Service("/usr/bin/chromedriver"), options=options)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


# --- 3. 클룩 데이터 크롤링 ---
def get_klook_data(url):
    participant_patterns = [
        r'"product_participant_count"\s*:\s*(\d+)',
        r'"participantCount"\s*:\s*(\d+)',
        r'"sold_count"\s*:\s*(\d+)',
        r'"soldCount"\s*:\s*(\d+)',
        r'"booked_count"\s*:\s*(\d+)',
        r'"bookingCount"\s*:\s*(\d+)',
        r'"totalBooked"\s*:\s*(\d+)',
        r'"sales_volume"\s*:\s*(\d+)',
    ]
    review_patterns = [
        r'"review_count"\s*:\s*(\d+)',
        r'"reviewCount"\s*:\s*(\d+)',
        r'"totalReview"\s*:\s*(\d+)',
        r'"total_reviews"\s*:\s*(\d+)',
        r'"ratingCount"\s*:\s*(\d+)',
        r'"numReviews"\s*:\s*(\d+)',
        r'"comment_count"\s*:\s*(\d+)',
    ]

    driver = None
    try:
        clean_url = url.split('?')[0]
        driver = get_driver()
        driver.get(clean_url)
        time.sleep(10)

        try:
            klook_json = driver.execute_script("return JSON.stringify(window.__KLOOK__)") or ""
        except Exception:
            klook_json = ""
        text = klook_json + driver.page_source

        participant_count = None
        for pattern in participant_patterns:
            match = re.search(pattern, text)
            if match:
                participant_count = int(match.group(1))
                break

        review_count = None
        for pattern in review_patterns:
            match = re.search(pattern, text)
            if match:
                review_count = int(match.group(1))
                break

        return participant_count, review_count, 200

    except Exception as e:
        return None, None, str(e)
    finally:
        if driver:
            driver.quit()


# --- 4. 디버그용: 소스에서 숫자형 키 전체 추출 ---
def get_raw_keys(url):
    driver = None
    try:
        clean_url = url.split('?')[0]
        driver = get_driver()
        driver.get(clean_url)
        time.sleep(10)

        try:
            klook_json = driver.execute_script("return JSON.stringify(window.__KLOOK__)") or ""
        except Exception:
            klook_json = ""
        text = klook_json + driver.page_source

        all_matches = re.findall(r'"([a-zA-Z_][a-zA-Z0-9_]*)"\s*:\s*(\d{2,})', text)
        seen = {}
        for k, v in all_matches:
            if k not in seen:
                seen[k] = v
        return 200, list(seen.items())

    except Exception as e:
        return str(e), []
    finally:
        if driver:
            driver.quit()


# --- 5. 로그 저장 + 최대 10개 유지 ---
def save_log_with_limit(product_url, participant_count, review_count):
    supabase = get_supabase()

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