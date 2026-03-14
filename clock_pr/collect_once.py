#!/usr/bin/env python3
"""
collect_once.py
───────────────
Windows 작업 스케줄러가 직접 호출하는 스크립트.
실행 시 등록된 모든 상품을 한 번 수집하고 종료합니다.

로그 파일: 이 스크립트와 같은 폴더의 collect_log.txt
"""

import sys
import pathlib
import traceback
from datetime import datetime

# ── 경로 설정: 이 파일이 있는 폴더를 sys.path에 추가 ──────────
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

LOG_FILE = HERE / "collect_log.txt"


def log(msg: str):
    """콘솔 + 파일에 동시 출력"""
    ts  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def trim_log(max_lines: int = 500):
    """로그 파일이 max_lines를 초과하면 오래된 줄 제거"""
    if not LOG_FILE.exists():
        return
    lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
    if len(lines) > max_lines:
        LOG_FILE.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")


def get_supabase():
    import os, toml
    from supabase import create_client

    secrets_path = HERE / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        s = toml.load(secrets_path)
        url = s.get("SUPABASE_URL")
        key = s.get("SUPABASE_KEY")
        if url and key:
            return create_client(url, key)

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if url and key:
        return create_client(url, key)

    raise RuntimeError("Supabase 연결 정보를 찾을 수 없습니다.")


def main():
    trim_log()
    log("=== 자동 수집 시작 ===")

    try:
        from utils import get_klook_data, save_log_with_limit
        db    = get_supabase()
        items = db.table("tracked_products").select("*").execute().data

        if not items:
            log("등록된 상품이 없습니다. 종료.")
            return

        log(f"수집 대상: {len(items)}개")
        ok = 0
        for i, it in enumerate(items, 1):
            name = it.get("product_name") or it["url"][:40]
            log(f"  [{i}/{len(items)}] {name} 수집 중...")
            try:
                p, r, code = get_klook_data(it["url"])
                if p is not None or r is not None:
                    save_log_with_limit(it["url"], p, r)
                    p_str = f"{p:,}" if p is not None else "없음"
                    r_str = f"{r:,}" if r is not None else "없음"
                    log(f"  ✅ 참여자: {p_str} / 리뷰: {r_str}")
                    ok += 1
                else:
                    log(f"  ❌ 실패 (HTTP {code})")
            except Exception:
                log(f"  ❌ 예외 발생:\n{traceback.format_exc()}")

        log(f"=== 수집 완료: {ok}/{len(items)}개 성공 ===\n")

    except Exception:
        log(f"[FATAL] 수집 중 오류:\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()