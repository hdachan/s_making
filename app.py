import streamlit as st
from supabase import create_client, Client
import requests
import re
import pandas as pd
from datetime import datetime

# --- 1. Supabase 설정 ---
URL = "https://olqxbazcyyorqtkqmjjo.supabase.co"
KEY = "sb_publishable_FlvMFCwWYsR7ysJgllgTgA_NWRmqW5S"
supabase: Client = create_client(URL, KEY)

# --- 2. 크롤링 함수 ---
def get_klook_count(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        # 소스코드에서 직접 'product_participant_count'를 정확히 추출
        match = re.search(r'"product_participant_count"\s*:\s*(\d+)', response.text)
        return int(match.group(1)) if match else None
    except:
        return None

# --- 3. UI 설정 ---
st.set_page_config(page_title="S-Marketing 분석 프로", layout="wide")
st.title("📈 클룩 마케팅 성과 분석 대시보드")

# [추가] 사이드바: 관리 메뉴
with st.sidebar:
    st.header("⚙️ 관리 메뉴")
    
    with st.expander("➕ 새 상품 등록", expanded=False):
        item_url = st.text_input("클룩 상품 URL")
        item_name = st.text_input("상품 별칭")
        if st.button("등록하기", use_container_width=True):
            if item_url:
                try:
                    supabase.table("tracked_products").insert({"url": item_url, "product_name": item_name}).execute()
                    count = get_klook_count(item_url)
                    if count:
                        supabase.table("product_logs").insert({"product_url": item_url, "participant_count": count}).execute()
                    st.success("등록 완료!")
                    st.rerun()
                except:
                    st.error("이미 등록된 URL입니다.")

    st.divider()
    st.info("데이터는 worker.py를 통해 2시간마다 자동 수집됩니다.")

# --- 4. 메인 화면: 분석 대시보드 ---

try:
    # 상품 목록 가져오기
    items = supabase.table("tracked_products").select("*").execute().data

    if not items:
        st.info("좌측 메뉴에서 상품을 먼저 등록해 주세요.")
    else:
        for item in items:
            # 개별 상품 섹션
            with st.expander(f"📍 {item.get('product_name') or '이름 없음'} ({item['url'][:30]}...)", expanded=True):
                col_info, col_chart = st.columns([1, 2])
                
                # 1. 왼쪽: 현재 정보 및 액션
                with col_info:
                    # 최신 로그 2개 가져오기 (증감 확인용)
                    logs_res = supabase.table("product_logs").select("*").eq("product_url", item['url']).order("created_at", desc=True).limit(2).execute().data
                    
                    if logs_res:
                        current = logs_res[0]['participant_count']
                        st.metric("현재 참여자 수", f"{current:,} 명")
                        
                        if len(logs_res) > 1:
                            diff = current - logs_res[1]['participant_count']
                            st.write(f"최근 변화량: :{'green' if diff >=0 else 'red'}[{'+' if diff >=0 else ''}{diff:,}]")
                        
                        st.caption(f"최종 업데이트: {logs_res[0]['created_at'][:19]}")
                    
                    st.write("---")
                    btn_col1, btn_col2 = st.columns(2)
                    if btn_col1.button("🔄 즉시 수집", key=f"upd_{item['url']}"):
                        count = get_klook_count(item['url'])
                        if count:
                            supabase.table("product_logs").insert({"product_url": item['url'], "participant_count": count}).execute()
                            st.toast("업데이트 완료!")
                            st.rerun()
                    
                    if btn_col2.button("🗑️ 삭제", key=f"del_{item['url']}"):
                        supabase.table("tracked_products").delete().eq("url", item['url']).execute()
                        st.warning("상품이 삭제되었습니다.")
                        st.rerun()

                # 2. 오른쪽: 변화 그래프 (분석 핵심)
                with col_chart:
                    # 전체 로그 가져와서 그래프 그리기
                    all_logs = supabase.table("product_logs").select("participant_count, created_at").eq("product_url", item['url']).order("created_at", desc=False).execute().data
                    
                    if all_logs:
                        df = pd.DataFrame(all_logs)
                        df['created_at'] = pd.to_datetime(df['created_at'])
                        df = df.rename(columns={'created_at': '시간', 'participant_count': '참여자 수'})
                        
                        # 선 그래프 표시
                        st.line_chart(df.set_index('시간')['참여자 수'])
                    else:
                        st.write("충분한 데이터가 쌓이지 않았습니다.")

except Exception as e:
    st.error(f"데이터 로드 중 오류 발생: {e}")