#!/usr/bin/env python3
"""
S-Marketing CLI (Viator 버전)
수집은 크롬 확장프로그램으로, 이 CLI는 등록/현황 확인용
사용법: python cli_viator.py
"""

import sys
import argparse
import pathlib

try:
    from supabase import create_client
except ImportError:
    print("❌ supabase 패키지가 없습니다: pip install supabase")
    sys.exit(1)


# ── Supabase 설정 ──────────────────────────────────────────────
def get_supabase():
    import os

    try:
        import toml
        secrets_path = pathlib.Path(".streamlit/secrets.toml")
        if secrets_path.exists():
            s = toml.load(secrets_path)
            url = s.get("SUPABASE_URL")
            key = s.get("SUPABASE_KEY")
            if url and key:
                return create_client(url, key)
    except Exception:
        pass

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if url and key:
        return create_client(url, key)

    print("❌ Supabase 연결 정보를 찾을 수 없습니다.")
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


def show_status(db):
    """최신 수치 + 변화량 출력"""
    items = db.table("tracked_products").select("*").execute().data
    if not items:
        print("  등록된 상품이 없습니다.")
        return

    print(f"  {'이름':<20} {'24h예약':>10} {'변화':>10}   {'리뷰':>8} {'변화':>10}   최종수집")
    hr()
    for it in items:
        name = (it.get("product_name") or "이름 없음")[:20]
        logs = db.table("product_logs2").select("*") \
                 .eq("product_url", it["url"]) \
                 .order("created_at", desc=True) \
                 .limit(2).execute().data

        if not logs:
            print(f"  {name:<20} {'크롬 확장으로 수집하세요':>10}")
            continue

        cur_p  = logs[0].get("popularity_count")
        cur_r  = logs[0].get("review_count")
        prev_p = logs[1].get("popularity_count") if len(logs) > 1 else None
        prev_r = logs[1].get("review_count")     if len(logs) > 1 else None
        ts     = logs[0]["created_at"][:16]

        dp = delta_str(cur_p, prev_p)
        dr = delta_str(cur_r, prev_r)
        print(f"  {name:<20} {fmt_num(cur_p):>10}{dp:<12}  {fmt_num(cur_r):>8}{dr:<12}  {ts}")


def add_product(db, url, name):
    """수집 없이 URL만 등록"""
    # URL 끝 슬래시 제거
    url = url.rstrip("/").split("?")[0]
    try:
        db.table("tracked_products").insert({
            "url": url,
            "product_name": name
        }).execute()
        print(f"  ✅ 등록 완료: {name or url[:40]}")
        print(f"  💡 크롬에서 해당 페이지를 열면 확장프로그램이 자동 수집합니다.")
    except Exception as e:
        if "duplicate" in str(e).lower() or "23505" in str(e):
            print(f"  ⚠️ 이미 등록된 URL입니다.")
        else:
            print(f"  ❌ 오류: {e}")


def delete_product(db, items, index):
    it   = items[index - 1]
    name = it.get("product_name") or it["url"][:40]
    confirm = input(f"  '{name}' 을(를) 삭제하시겠습니까? (y/N) ").strip().lower()
    if confirm == "y":
        db.table("tracked_products").delete().eq("url", it["url"]).execute()
        print("  🗑️  삭제되었습니다.")
    else:
        print("  취소했습니다.")


def change_url(db, items, index, new_url=None):
    it      = items[index - 1]
    old_url = it["url"]
    name    = it.get("product_name") or old_url[:40]

    print(f"  대상 상품  : {name}")
    print(f"  현재 주소  : {old_url}")

    if new_url is None:
        new_url = input("  새 주소    > ").strip().rstrip("/").split("?")[0]

    if not new_url:
        print("  URL을 입력하지 않아 취소했습니다.")
        return
    if new_url == old_url:
        print("  현재 주소와 동일합니다.")
        return

    confirm = input(f"  위 주소로 변경하시겠습니까? (y/N) ").strip().lower()
    if confirm != "y":
        print("  취소했습니다.")
        return

    db.table("tracked_products").update({"url": new_url}).eq("url", old_url).execute()

    log_result = db.table("product_logs2") \
                   .update({"product_url": new_url}) \
                   .eq("product_url", old_url) \
                   .execute()

    updated = len(log_result.data) if log_result.data else 0
    print(f"  ✅ 변경 완료! 로그 {updated}건도 업데이트했습니다.")
    print(f"  💡 크롬에서 새 주소 페이지를 열면 확장프로그램이 자동 수집합니다.")


# ── 대화형 메뉴 ───────────────────────────────────────────────
MENU = """
  [1] 상품 목록 보기
  [2] 최신 수치 현황
  [3] 상품 등록
  [4] 상품 삭제
  [5] 주소 변경
  [0] 종료

  💡 수집은 크롬 확장프로그램으로 자동 진행됩니다.
     등록된 Viator 페이지를 크롬으로 열면 자동 저장됩니다.
"""

def interactive(db):
    header("📈 S-Marketing CLI  [Viator 버전]")
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
            header("➕ 상품 등록")
            url  = input("  Viator 상품 URL > ").strip()
            name = input("  상품 별칭       > ").strip()
            if url:
                add_product(db, url, name)
            else:
                print("  URL을 입력하세요.")

        elif choice == "4":
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

        elif choice == "5":
            header("🔗 주소 변경")
            items = db.table("tracked_products").select("*").execute().data
            if not items:
                print("  등록된 상품이 없습니다.")
                continue
            list_products(db)
            raw = input("\n  변경할 번호 > ").strip()
            try:
                change_url(db, items, int(raw))
            except (ValueError, IndexError):
                print("  올바른 번호를 입력하세요.")

        else:
            print("  올바른 메뉴 번호를 선택하세요.")

        input("\n  [Enter] 계속...")


# ── CLI 인자 모드 ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="S-Marketing CLI (Viator) - 등록/현황 관리",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  python cli_viator.py              # 대화형 메뉴
  python cli_viator.py status       # 현황 출력
  python cli_viator.py list         # 상품 목록
  python cli_viator.py add URL --name 이름
  python cli_viator.py delete 2
  python cli_viator.py change 2 https://new-url
        """
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("status", help="최신 수치 현황")
    sub.add_parser("list",   help="상품 목록")

    p_add = sub.add_parser("add", help="상품 등록")
    p_add.add_argument("url")
    p_add.add_argument("--name", default="")

    p_del = sub.add_parser("delete", help="상품 삭제")
    p_del.add_argument("index", type=int)

    p_chg = sub.add_parser("change", help="URL 변경")
    p_chg.add_argument("index", type=int)
    p_chg.add_argument("new_url")

    args = parser.parse_args()
    db   = get_supabase()

    if args.cmd is None:
        interactive(db)

    elif args.cmd == "status":
        header("📊 최신 수치 현황")
        show_status(db)

    elif args.cmd == "list":
        header("📋 등록 상품 목록")
        list_products(db)

    elif args.cmd == "add":
        header("➕ 상품 등록")
        add_product(db, args.url, args.name)

    elif args.cmd == "delete":
        items = db.table("tracked_products").select("*").execute().data
        if not items:
            print("  등록된 상품이 없습니다.")
            sys.exit(1)
        try:
            delete_product(db, items, args.index)
        except IndexError:
            print(f"  ❌ {args.index}번 상품이 없습니다.")

    elif args.cmd == "change":
        items = db.table("tracked_products").select("*").execute().data
        if not items:
            print("  등록된 상품이 없습니다.")
            sys.exit(1)
        try:
            change_url(db, items, args.index, new_url=args.new_url)
        except IndexError:
            print(f"  ❌ {args.index}번 상품이 없습니다.")


if __name__ == "__main__":
    main()