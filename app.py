import os
import re
import time
import streamlit as st
import pandas as pd
from supabase import create_client, Client
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# --- 1. Supabase 설정 ---
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)


# --- 2. Selenium 브라우저 설정 (로컬/클라우드 자동 감지) ---
def get_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Streamlit Cloud (Linux) vs 로컬 Windows 자동 감지
    if os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"
        driver = webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),
            options=options
        )
    elif os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
        driver = webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),
            options=options
        )
    else:
        # 로컬 환경 (Windows/Mac)
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    return driver


# --- 3. 크롤링 함수 ---
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
        time.sleep(5)

        # window.__KLOOK__ JS 추출 + page_source 둘 다 합쳐서 탐색 (가장 안정적)
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


# --- 3-1. 디버그용: 소스에서 숫자형 키 전체 추출 ---
def get_raw_keys(url):
    driver = None
    try:
        clean_url = url.split('?')[0]
        driver = get_driver()
        driver.get(clean_url)
        time.sleep(5)

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


# --- 4. 로그 저장 + 최대 10개 유지 ---
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


# --- 5. UI 설정 ---
st.set_page_config(page_title="S-Marketing 분석 프로", layout="wide")
st.title("📈 클룩 마케팅 성과 분석 대시보드")

with st.sidebar:
    st.header("⚙️ 관리 메뉴")

    with st.expander("➕ 새 상품 등록", expanded=False):
        item_url = st.text_input("클룩 상품 URL")
        item_name = st.text_input("상품 별칭")
        if st.button("등록하기", use_container_width=True):
            if item_url:
                try:
                    supabase.table("tracked_products").insert({
                        "url": item_url,
                        "product_name": item_name
                    }).execute()
                    p, r, code = get_klook_data(item_url)
                    if p is not None or r is not None:
                        save_log_with_limit(item_url, p, r)
                    st.success(f"등록 완료! (참여자: {p} / 리뷰: {r})")
                    st.rerun()
                except Exception as e:
                    st.error(f"오류: {e}")

    st.divider()

    with st.expander("🔍 크롤링 디버그", expanded=False):
        debug_url = st.text_input("테스트할 URL 입력", key="debug_url")
        col_d1, col_d2 = st.columns(2)

        if col_d1.button("🔄 수집 테스트", use_container_width=True):
            if debug_url:
                with st.spinner("브라우저 실행 중... (10~20초 소요)"):
                    try:
                        p, r, code = get_klook_data(debug_url)
                        st.write(f"**상태코드:** `{code}`")
                        st.write(f"**참여자 수:** `{p}`")
                        st.write(f"**리뷰 수:** `{r}`")
                        if p is None and r is None:
                            st.warning("⚠️ 데이터 없음 → '키 분석'으로 소스 확인 필요")
                        else:
                            st.success("✅ 정상 수집!")
                    except Exception as e:
                        st.error(f"오류: {e}")

        if col_d2.button("🔬 키 분석", use_container_width=True):
            if debug_url:
                with st.spinner("브라우저 실행 중... (10~20초 소요)"):
                    try:
                        status, keys = get_raw_keys(debug_url)
                        st.write(f"**상태코드:** `{status}`")
                        if not keys:
                            st.warning("⚠️ 숫자형 키를 찾지 못했습니다.")
                        else:
                            st.success(f"✅ {len(keys)}개 키 발견")
                            df_keys = pd.DataFrame(keys, columns=["키명", "값"])
                            df_keys["값"] = pd.to_numeric(df_keys["값"])
                            df_keys = df_keys.sort_values("값", ascending=False)
                            st.dataframe(df_keys, use_container_width=True)
                            st.caption("💡 참여자수/리뷰수에 해당하는 키명을 확인하세요")
                    except Exception as e:
                        st.error(f"오류: {e}")

    st.divider()
    if st.button("🔁 전체 새로고침", use_container_width=True):
        st.rerun()
    st.info("데이터는 worker.py를 통해 2시간마다 자동 수집됩니다.\n최대 10개 데이터 유지.")


# --- 6. 메인 화면 ---
try:
    items = supabase.table("tracked_products").select("*").execute().data

    if not items:
        st.info("좌측 메뉴에서 상품을 먼저 등록해 주세요.")
    else:
        for item in items:
            with st.expander(
                f"📍 {item.get('product_name') or '이름 없음'}  |  {item['url'][:50]}...",
                expanded=True
            ):
                st.markdown(f"🔗 [클룩 페이지 바로가기]({item['url']})", unsafe_allow_html=True)

                col_info, col_chart = st.columns([1, 2])

                with col_info:
                    logs_res = supabase.table("product_logs").select("*") \
                        .eq("product_url", item['url']) \
                        .order("created_at", desc=True) \
                        .limit(2).execute().data

                    if logs_res:
                        current_p = logs_res[0].get('participant_count')
                        current_r = logs_res[0].get('review_count')

                        col_p, col_r = st.columns(2)
                        with col_p:
                            if current_p is not None:
                                st.metric("👥 참여자 수", f"{current_p:,}")
                                if len(logs_res) > 1 and logs_res[1].get('participant_count') is not None:
                                    diff = current_p - logs_res[1]['participant_count']
                                    color = 'green' if diff >= 0 else 'red'
                                    st.write(f"변화: :{color}[{'+' if diff >= 0 else ''}{diff:,}]")
                            else:
                                st.metric("👥 참여자 수", "수집 안됨")
                        with col_r:
                            if current_r is not None:
                                st.metric("⭐ 리뷰 수", f"{current_r:,}")
                                if len(logs_res) > 1 and logs_res[1].get('review_count') is not None:
                                    diff = current_r - logs_res[1]['review_count']
                                    color = 'green' if diff >= 0 else 'red'
                                    st.write(f"변화: :{color}[{'+' if diff >= 0 else ''}{diff:,}]")
                            else:
                                st.metric("⭐ 리뷰 수", "수집 안됨")

                        st.caption(f"최종 업데이트: {logs_res[0]['created_at'][:19]}")
                    else:
                        st.write("아직 수집된 데이터가 없습니다.")

                    st.write("---")
                    btn_col1, btn_col2 = st.columns(2)

                    collecting_key = f"collecting_{item['url']}"
                    if collecting_key not in st.session_state:
                        st.session_state[collecting_key] = False
                    is_collecting = st.session_state[collecting_key]

                    if btn_col1.button(
                        "⏳ 수집 중..." if is_collecting else "🔄 즉시 수집",
                        key=f"upd_{item['url']}",
                        disabled=is_collecting,
                        use_container_width=True
                    ):
                        st.session_state[collecting_key] = True
                        st.rerun()

                    if is_collecting:
                        with st.spinner("브라우저 실행 중... (10~20초 소요)"):
                            p, r, code = get_klook_data(item['url'])
                        st.session_state[collecting_key] = False
                        if p is not None or r is not None:
                            save_log_with_limit(item['url'], p, r)
                            p_str = f"{p:,}" if p is not None else "없음"
                            r_str = f"{r:,}" if r is not None else "없음"
                            st.toast(f"✅ 수집 완료! 참여자: {p_str} / 리뷰: {r_str}")
                        else:
                            st.error(f"데이터를 가져오지 못했습니다. (코드: {code})\n💡 디버그 > 키 분석으로 소스를 확인해보세요.")
                        st.rerun()

                    if btn_col2.button("🗑️ 삭제", key=f"del_{item['url']}", disabled=is_collecting):
                        supabase.table("tracked_products").delete().eq("url", item['url']).execute()
                        st.warning("상품이 삭제되었습니다.")
                        st.rerun()

                with col_chart:
                    all_logs = supabase.table("product_logs") \
                        .select("participant_count, review_count, created_at") \
                        .eq("product_url", item['url']) \
                        .order("created_at", desc=False) \
                        .execute().data

                    if len(all_logs) >= 2:
                        df = pd.DataFrame(all_logs)
                        df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%m/%d %H:%M')
                        df = df.rename(columns={
                            'created_at': '시간',
                            'participant_count': '참여자 수',
                            'review_count': '리뷰 수'
                        })
                        df = df.set_index('시간')

                        tab1, tab2 = st.tabs(["👥 참여자 수 추이", "⭐ 리뷰 수 추이"])
                        with tab1:
                            if df['참여자 수'].notna().any():
                                st.line_chart(df['참여자 수'])
                            else:
                                st.write("참여자 수 데이터 없음")
                        with tab2:
                            if df['리뷰 수'].notna().any():
                                st.line_chart(df['리뷰 수'])
                            else:
                                st.write("리뷰 수 데이터 없음")

                        st.caption(f"최근 {len(all_logs)}개 데이터 표시 중 (최대 10개 유지)")
                    elif len(all_logs) == 1:
                        st.info("데이터가 1개입니다. 즉시 수집을 한 번 더 눌러 그래프를 확인하세요.")
                    else:
                        st.write("수집된 데이터가 없습니다.")

except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")