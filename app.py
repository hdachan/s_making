import streamlit as st
from supabase import create_client, Client
import requests
import re
import pandas as pd
import time

# --- 1. Supabase 설정 ---
URL = st.secrets["SUPABASE_URL"]
KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(URL, KEY)

# --- 2. 크롤링 함수 (403 우회 + 재시도) ---
def get_klook_data(url, retries=3):
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36',
    ]
    for attempt in range(retries):
        headers = {
            'User-Agent': user_agents[attempt % len(user_agents)],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        try:
            session = requests.Session()
            session.get("https://www.klook.com", headers=headers, timeout=10)
            time.sleep(2 + attempt * 2)  # 2초, 4초, 6초 간격
            response = session.get(url, headers=headers, timeout=15)

            if response.status_code == 403:
                time.sleep(3 + attempt * 2)
                continue

            if response.status_code != 200:
                return None, None, response.status_code

            text = response.text
            participant_match = re.search(r'"product_participant_count"\s*:\s*(\d+)', text)
            review_match = re.search(r'"reviewCount"\s*:\s*(\d+)', text)

            participant_count = int(participant_match.group(1)) if participant_match else None
            review_count = int(review_match.group(1)) if review_match else None

            return participant_count, review_count, response.status_code

        except Exception as e:
            if attempt == retries - 1:
                return None, None, str(e)
            time.sleep(3)

    return None, None, 403

# --- 3. 로그 저장 + 최대 10개 유지 ---
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

# --- 4. UI 설정 ---
st.set_page_config(page_title="S-Marketing 분석 프로", layout="wide")
st.title("📈 클룩 마케팅 성과 분석 대시보드")

# 사이드바
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
                    st.success(f"등록 완료! (상태코드: {code})")
                    st.rerun()
                except:
                    st.error("이미 등록된 URL입니다.")

    st.divider()

    # 🔍 디버그 패널
    with st.expander("🔍 크롤링 디버그", expanded=False):
        debug_url = st.text_input("테스트할 URL 입력", key="debug_url")
        if st.button("소스 분석하기", use_container_width=True):
            if debug_url:
                with st.spinner("요청 중..."):
                    try:
                        p, r, code = get_klook_data(debug_url)
                        st.write(f"**상태코드:** `{code}`")
                        st.write(f"**참여자 수:** `{p}`")
                        st.write(f"**리뷰 수:** `{r}`")
                        if code == 403:
                            st.error("❌ 여전히 403 차단됨")
                        elif p is None and r is None:
                            st.warning("⚠️ 200인데 데이터 없음 - 키워드가 소스에 없음")
                        else:
                            st.success("✅ 정상 수집!")
                    except Exception as e:
                        st.error(f"오류: {e}")

    st.divider()
    st.info("데이터는 worker.py를 통해 2시간마다 자동 수집됩니다.\n최대 10개 데이터 유지.")

# --- 5. 메인 화면 ---
try:
    items = supabase.table("tracked_products").select("*").execute().data

    if not items:
        st.info("좌측 메뉴에서 상품을 먼저 등록해 주세요.")
    else:
        for item in items:
            with st.expander(f"📍 {item.get('product_name') or '이름 없음'}  |  {item['url'][:50]}...", expanded=True):
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
                        with col_r:
                            if current_r is not None:
                                st.metric("⭐ 리뷰 수", f"{current_r:,}")
                                if len(logs_res) > 1 and logs_res[1].get('review_count') is not None:
                                    diff = current_r - logs_res[1]['review_count']
                                    color = 'green' if diff >= 0 else 'red'
                                    st.write(f"변화: :{color}[{'+' if diff >= 0 else ''}{diff:,}]")

                        st.caption(f"최종 업데이트: {logs_res[0]['created_at'][:19]}")
                    else:
                        st.write("아직 수집된 데이터가 없습니다.")

                    st.write("---")
                    btn_col1, btn_col2 = st.columns(2)

                    if btn_col1.button("🔄 즉시 수집", key=f"upd_{item['url']}"):
                        p, r, code = get_klook_data(item['url'])
                        if p is not None or r is not None:
                            save_log_with_limit(item['url'], p, r)
                            st.toast(f"✅ 수집 완료! 참여자: {p:,} / 리뷰: {r:,}")
                            st.rerun()
                        else:
                            st.error(f"데이터를 가져오지 못했습니다. (상태코드: {code})")

                    if btn_col2.button("🗑️ 삭제", key=f"del_{item['url']}"):
                        supabase.table("tracked_products").delete().eq("url", item['url']).execute()
                        st.warning("상품이 삭제되었습니다.")
                        st.rerun()

                with col_chart:
                    all_logs = supabase.table("product_logs").select("participant_count, review_count, created_at") \
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