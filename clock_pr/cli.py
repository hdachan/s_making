#!/usr/bin/env python3
"""
S-Marketing CLI - 터미널에서 클룩 마케팅 성과 분석
사용법: python cli.py
"""

import sys
import time
import argparse
from datetime import datetime

try:
    from supabase import create_client
except ImportError:
    print("❌ supabase 패키지가 없습니다: pip install supabase")
    sys.exit(1)

try:
    from utils import get_klook_data, get_raw_keys, save_log_with_limit
except ImportError:
    print("❌ utils.py를 찾을 수 없습니다. 같은 폴더에 utils.py가 있는지 확인하세요.")
    sys.exit(1)

# ── Supabase 설정 ──────────────────────────────────────────────
def get_supabase():
    """secrets.toml 또는 환경변수에서 Supabase 연결 정보 로드"""
    import os, toml, pathlib

    # 1) .streamlit/secrets.toml 시도
    secrets_path = pathlib.Path(".streamlit/secrets.toml")
    if secrets_path.exists():
        s = toml.load(secrets_path)
        url = s.get("SUPABASE_URL")
        key = s.get("SUPABASE_KEY")
        if url and key:
            return create_client(url, key)

    # 2) 환경변수 시도
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if url and key:
        return create_client(url, key)

    print("❌ Supabase 연결 정보를 찾을 수 없습니다.")
    print("   .streamlit/secrets.toml 또는 환경변수 SUPABASE_URL / SUPABASE_KEY 를 설정하세요.")
    sys.exit(1)


# ── 출력 헬퍼 ──────────────────────────────────────────────────
def hr(char="─", width=60):
    print(char * width)

def header(title):
    hr("═")
    print(f"  {title}")
    hr("═")

def fmt_num(n):
    return f"{n:,}" if n is not None else "수집 안됨"

def delta_str(new, old):
    if new is None or old is None:
        return ""
    d = new - old
    arrow = "▲" if d > 0 else ("▼" if d < 0 else "─")
    sign  = "+" if d > 0 else ""
    return f"  {arrow} {sign}{d:,}"


# ── 기능 함수 ──────────────────────────────────────────────────
def list_products(db):
    """등록된 상품 목록 출력"""
    items = db.table("tracked_products").select("*").execute().data
    if not items:
        print("  등록된 상품이 없습니다.")
        return items

    print(f"  {'#':<4} {'이름':<20} {'URL'}")
    hr()
    for i, it in enumerate(items, 1):
        name = (it.get("product_name") or "이름 없음")[:20]
        url  = it["url"][:55]
        print(f"  {i:<4} {name:<20} {url}")
    return items


def show_status(db, items=None):
    """각 상품의 최신 수치 + 변화량 출력"""
    if items is None:
        items = db.table("tracked_products").select("*").execute().data
    if not items:
        print("  등록된 상품이 없습니다.")
        return

    print(f"  {'이름':<20} {'참여자':>10} {'변화':>8}   {'리뷰':>8} {'변화':>8}   최종수집")
    hr()
    for it in items:
        name = (it.get("product_name") or "이름 없음")[:20]
        logs = db.table("product_logs").select("*") \
                 .eq("product_url", it["url"]) \
                 .order("created_at", desc=True) \
                 .limit(2).execute().data

        if not logs:
            print(f"  {name:<20} {'데이터 없음':>10}")
            continue

        cur_p = logs[0].get("participant_count")
        cur_r = logs[0].get("review_count")
        prev_p = logs[1].get("participant_count") if len(logs) > 1 else None
        prev_r = logs[1].get("review_count")     if len(logs) > 1 else None
        ts = logs[0]["created_at"][:16]

        dp = delta_str(cur_p, prev_p)
        dr = delta_str(cur_r, prev_r)
        print(f"  {name:<20} {fmt_num(cur_p):>10}{dp:<10}  {fmt_num(cur_r):>8}{dr:<10}  {ts}")


def collect_items(db, items):
    """주어진 상품 목록을 순차 수집"""
    total = len(items)
    ok = 0
    for i, it in enumerate(items, 1):
        name = it.get("product_name") or it["url"][:30]
        print(f"  [{i}/{total}] {name} ... ", end="", flush=True)
        p, r, code = get_klook_data(it["url"])
        if p is not None or r is not None:
            save_log_with_limit(it["url"], p, r)
            print(f"✅  참여자: {fmt_num(p)} / 리뷰: {fmt_num(r)}")
            ok += 1
        else:
            print(f"❌  실패 (HTTP {code})")
    print()
    print(f"  완료: {ok}/{total}개 성공")
    return ok


def add_product(db, url, name):
    """새 상품 등록 후 초기 수집"""
    db.table("tracked_products").insert({"url": url, "product_name": name}).execute()
    print(f"  ✅ 등록 완료: {name or url[:40]}")
    print("  초기 데이터 수집 중...", flush=True)
    p, r, code = get_klook_data(url)
    if p is not None or r is not None:
        save_log_with_limit(url, p, r)
        print(f"  참여자: {fmt_num(p)} / 리뷰: {fmt_num(r)}")
    else:
        print(f"  ⚠️ 초기 수집 실패 (HTTP {code})")


def delete_product(db, items, index):
    """번호로 상품 삭제"""
    it = items[index - 1]
    name = it.get("product_name") or it["url"][:40]
    confirm = input(f"  '{name}' 을(를) 삭제하시겠습니까? (y/N) ").strip().lower()
    if confirm == "y":
        db.table("tracked_products").delete().eq("url", it["url"]).execute()
        print("  🗑️  삭제되었습니다.")
    else:
        print("  취소했습니다.")


def change_url(db, items, index, new_url=None):
    """번호로 상품 URL 변경 (product_logs의 product_url도 함께 업데이트)"""
    it = items[index - 1]
    old_url  = it["url"]
    name     = it.get("product_name") or old_url[:40]

    print(f"  대상 상품  : {name}")
    print(f"  현재 주소  : {old_url}")

    if new_url is None:
        new_url = input("  새 주소    > ").strip()

    if not new_url:
        print("  URL을 입력하지 않아 취소했습니다.")
        return
    if new_url == old_url:
        print("  현재 주소와 동일합니다. 변경하지 않습니다.")
        return

    confirm = input(f"  위 주소로 변경하시겠습니까? (y/N) ").strip().lower()
    if confirm != "y":
        print("  취소했습니다.")
        return

    # 1) tracked_products 업데이트
    db.table("tracked_products") \
      .update({"url": new_url}) \
      .eq("url", old_url) \
      .execute()

    # 2) product_logs의 product_url도 일괄 업데이트
    log_result = db.table("product_logs") \
                   .update({"product_url": new_url}) \
                   .eq("product_url", old_url) \
                   .execute()

    updated_logs = len(log_result.data) if log_result.data else 0
    print(f"  ✅ 주소 변경 완료!")
    print(f"     로그 {updated_logs}건도 새 주소로 업데이트했습니다.")

    # 3) 새 주소로 즉시 수집 여부 확인
    collect_now = input("  새 주소로 즉시 수집하시겠습니까? (y/N) ").strip().lower()
    if collect_now == "y":
        print("  수집 중...", flush=True)
        p, r, code = get_klook_data(new_url)
        if p is not None or r is not None:
            save_log_with_limit(new_url, p, r)
            print(f"  참여자: {fmt_num(p)} / 리뷰: {fmt_num(r)}")
        else:
            print(f"  ⚠️ 수집 실패 (HTTP {code})")


def debug_url(url):
    """단일 URL 수집 테스트"""
    print(f"  수집 테스트: {url[:60]}")
    print("  브라우저 실행 중... (10~20초 소요)", flush=True)
    p, r, code = get_klook_data(url)
    print(f"  상태코드 : {code}")
    print(f"  참여자 수: {fmt_num(p)}")
    print(f"  리뷰  수: {fmt_num(r)}")
    if p is None and r is None:
        print("  ⚠️ 데이터 없음 → 키 분석(k)으로 소스 확인 필요")
    else:
        print("  ✅ 정상 수집!")


def debug_keys(url):
    """단일 URL 키 분석"""
    print(f"  키 분석: {url[:60]}")
    print("  브라우저 실행 중... (10~20초 소요)", flush=True)
    status, keys = get_raw_keys(url)
    print(f"  상태코드: {status}")
    if not keys:
        print("  ⚠️ 숫자형 키를 찾지 못했습니다.")
    else:
        sorted_keys = sorted(keys, key=lambda x: float(x[1]), reverse=True)
        print(f"  {'키명':<40} {'값':>12}")
        hr()
        for k, v in sorted_keys[:30]:
            print(f"  {k:<40} {v:>12}")
        if len(sorted_keys) > 30:
            print(f"  ... 외 {len(sorted_keys)-30}개")


def schedule_loop(db, interval_hours=2):
    """interval_hours 간격으로 전체 수집 반복"""
    print(f"  🔁 자동 수집 시작 (간격: {interval_hours}시간) — 중단: Ctrl+C")
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n  ⏰ {now} — 전체 수집 시작")
        items = db.table("tracked_products").select("*").execute().data
        collect_items(db, items)
        print(f"  다음 수집: {interval_hours}시간 후")
        time.sleep(interval_hours * 3600)


def schedule_daily(db, at_time="09:00"):
    """매일 지정 시각(HH:MM)에 전체 수집 — 터미널 켜두는 방식"""
    try:
        target_h, target_m = [int(x) for x in at_time.split(":")]
    except ValueError:
        print("  ❌ 시각 형식 오류. 예: 09:00")
        return

    print(f"  🗓️  매일 {at_time} 자동 수집 시작 — 중단: Ctrl+C")

    def seconds_until_next():
        now = datetime.now()
        target = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
        if target <= now:
            from datetime import timedelta
            target += timedelta(days=1)
        return (target - now).total_seconds()

    while True:
        wait = seconds_until_next()
        from datetime import timedelta
        next_dt = (datetime.now() + timedelta(seconds=wait)).strftime("%Y-%m-%d %H:%M")
        print(f"\n  ⏳ 다음 수집 예정: {next_dt}  ({wait/3600:.1f}시간 대기 중...)")

        while wait > 0:
            sleep_chunk = min(60, wait)
            time.sleep(sleep_chunk)
            wait -= sleep_chunk

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n  ⏰ {now_str} — 일일 수집 시작")
        items = db.table("tracked_products").select("*").execute().data
        collect_items(db, items)


# ── 대화형 메뉴 ───────────────────────────────────────────────
MENU = """
  [1] 상품 목록 보기
  [2] 최신 수치 현황
  [3] 전체 즉시수집
  [4] 선택 즉시수집
  [5] 상품 등록
  [6] 상품 삭제
  [a] 주소 변경
  [7] 수집 테스트 (단일 URL)
  [8] 키 분석 (단일 URL)
  [9] 자동 수집 시작 (간격 지정)
  [d] 매일 지정 시각 자동 수집
  [0] 종료
"""

def interactive(db):
    header("📈 S-Marketing CLI")
    while True:
        print(MENU)
        choice = input("  선택 > ").strip()

        if choice == "0":
            print("  종료합니다.")
            break

        elif choice == "1":
            header("📋 등록 상품 목록")
            list_products(db)

        elif choice == "2":
            header("📊 최신 수치 현황")
            show_status(db)

        elif choice == "3":
            header("🔁 전체 즉시수집")
            items = db.table("tracked_products").select("*").execute().data
            if not items:
                print("  등록된 상품이 없습니다.")
            else:
                collect_items(db, items)

        elif choice == "4":
            header("☑️ 선택 즉시수집")
            items = db.table("tracked_products").select("*").execute().data
            if not items:
                print("  등록된 상품이 없습니다.")
                continue
            list_products(db)
            raw = input("\n  수집할 번호 입력 (쉼표 구분, 예: 1,3,5) > ").strip()
            if not raw:
                continue
            try:
                indices = [int(x.strip()) for x in raw.split(",")]
                selected = [items[i-1] for i in indices if 1 <= i <= len(items)]
                if selected:
                    collect_items(db, selected)
                else:
                    print("  유효한 번호가 없습니다.")
            except (ValueError, IndexError):
                print("  올바른 번호를 입력하세요.")

        elif choice == "5":
            header("➕ 상품 등록")
            url  = input("  클룩 상품 URL > ").strip()
            name = input("  상품 별칭     > ").strip()
            if url:
                try:
                    add_product(db, url, name)
                except Exception as e:
                    print(f"  ❌ 오류: {e}")
            else:
                print("  URL을 입력하세요.")

        elif choice == "6":
            header("🗑️ 상품 삭제")
            items = db.table("tracked_products").select("*").execute().data
            if not items:
                print("  등록된 상품이 없습니다.")
                continue
            list_products(db)
            raw = input("\n  삭제할 번호 > ").strip()
            try:
                delete_product(db, items, int(raw))
            except (ValueError, IndexError):
                print("  올바른 번호를 입력하세요.")

        elif choice == "a":
            header("🔗 주소 변경")
            items = db.table("tracked_products").select("*").execute().data
            if not items:
                print("  등록된 상품이 없습니다.")
                continue
            list_products(db)
            raw = input("\n  변경할 상품 번호 > ").strip()
            try:
                change_url(db, items, int(raw))
            except (ValueError, IndexError):
                print("  올바른 번호를 입력하세요.")

        elif choice == "7":
            header("🔄 수집 테스트")
            url = input("  URL > ").strip()
            if url:
                debug_url(url)

        elif choice == "8":
            header("🔬 키 분석")
            url = input("  URL > ").strip()
            if url:
                debug_keys(url)

        elif choice == "9":
            header("⏰ 간격 자동 수집")
            raw = input("  수집 간격 (시간, 기본 2) > ").strip()
            hours = float(raw) if raw else 2.0
            try:
                schedule_loop(db, hours)
            except KeyboardInterrupt:
                print("\n  자동 수집을 중단했습니다.")

        elif choice == "d":
            header("🗓️ 매일 지정 시각 자동 수집")
            t = input("  수집 시각 (HH:MM, 기본 09:00) > ").strip() or "09:00"
            try:
                schedule_daily(db, t)
            except KeyboardInterrupt:
                print("\n  자동 수집을 중단했습니다.")
        else:
            print("  올바른 메뉴 번호를 선택하세요.")

        input("\n  [Enter] 계속...")


# ── CLI 인자 모드 (비대화형) ──────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="S-Marketing CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python cli.py                           # 대화형 메뉴
  python cli.py status                    # 현황 출력 후 종료
  python cli.py collect                   # 전체 즉시수집 후 종료
  python cli.py schedule --hours 2        # 2시간마다 자동수집
  python cli.py daily                     # 매일 09:00 자동수집
  python cli.py daily --at 18:30          # 매일 18:30 자동수집
  python cli.py add URL --name 이름       # 상품 등록
  python cli.py change 2 https://new-url  # 2번 상품 URL 변경
        """
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status",   help="최신 수치 현황 출력")
    sub.add_parser("list",     help="상품 목록 출력")
    sub.add_parser("collect",  help="전체 즉시수집")

    p_add = sub.add_parser("add", help="상품 등록")
    p_add.add_argument("url")
    p_add.add_argument("--name", default="")

    p_del = sub.add_parser("delete", help="상품 삭제 (번호)")
    p_del.add_argument("index", type=int)

    p_change = sub.add_parser("change", help="상품 URL 변경 (번호 새URL)")
    p_change.add_argument("index", type=int, help="변경할 상품 번호")
    p_change.add_argument("new_url", help="새 URL")

    p_sch = sub.add_parser("schedule", help="자동 수집 (간격 지정)")
    p_sch.add_argument("--hours", type=float, default=2.0)

    p_daily = sub.add_parser("daily", help="매일 지정 시각 자동수집")
    p_daily.add_argument("--at", default="09:00", metavar="HH:MM", help="수집 시각 (기본 09:00)")

    p_debug = sub.add_parser("debug", help="단일 URL 수집 테스트")
    p_debug.add_argument("url")

    p_keys = sub.add_parser("keys", help="단일 URL 키 분석")
    p_keys.add_argument("url")

    args = parser.parse_args()
    db   = get_supabase()

    if args.cmd is None:
        try:
            import toml
        except ImportError:
            print("⚠️  toml 패키지 없음: pip install toml")
        interactive(db)

    elif args.cmd == "status":
        header("📊 최신 수치 현황")
        show_status(db)

    elif args.cmd == "list":
        header("📋 등록 상품 목록")
        list_products(db)

    elif args.cmd == "collect":
        header("🔁 전체 즉시수집")
        items = db.table("tracked_products").select("*").execute().data
        collect_items(db, items)

    elif args.cmd == "add":
        header("➕ 상품 등록")
        add_product(db, args.url, args.name)

    elif args.cmd == "delete":
        items = db.table("tracked_products").select("*").execute().data
        delete_product(db, items, args.index)

    elif args.cmd == "change":
        header("🔗 주소 변경")
        items = db.table("tracked_products").select("*").execute().data
        if not items:
            print("  등록된 상품이 없습니다.")
            sys.exit(1)
        try:
            change_url(db, items, args.index, new_url=args.new_url)
        except IndexError:
            print(f"  ❌ {args.index}번 상품이 없습니다.")
            sys.exit(1)

    elif args.cmd == "schedule":
        schedule_loop(db, args.hours)

    elif args.cmd == "daily":
        try:
            schedule_daily(db, args.at)
        except KeyboardInterrupt:
            print("\n자동 수집을 중단했습니다.")

    elif args.cmd == "debug":
        debug_url(args.url)

    elif args.cmd == "keys":
        debug_keys(args.url)


if __name__ == "__main__":
    main()