// ── Viator 상품 페이지에서 자동으로 데이터 추출 ──

// Supabase 설정 (여기에 본인 값 입력)
const SUPABASE_URL = "https://olqxbazcyyorqtkqmjjo.supabase.co";
const SUPABASE_KEY = "sb_publishable_FlvMFCwWYsR7ysJgllgTgA_NWRmqW5S";

waitForData();

async function waitForData() {
  const maxTry = 20;
  const interval = 1000;

  for (let i = 0; i < maxTry; i++) {
    const result = extractData();
    if (result.popularityCount !== null || result.reviewCount !== null) {
      console.log(`[S-Marketing] 데이터 발견! (${i + 1}초 후)`);
      console.log(`[S-Marketing] 24h예약: ${result.popularityCount}`);
      console.log(`[S-Marketing] 리뷰수: ${result.reviewCount}`);
      await saveToSupabase(result.popularityCount, result.reviewCount);
      return;
    }
    console.log(`[S-Marketing] 대기 중... (${i + 1}/${maxTry}초)`);
    await sleep(interval);
  }

  console.warn("[S-Marketing] 20초 내에 데이터를 찾지 못했습니다.");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function extractData() {
  let popularityCount = null;
  let reviewCount = null;

  const scripts = document.querySelectorAll("script");
  for (const script of scripts) {
    const text = script.textContent || "";

    // 1. popularityCount → ApolloSSRDataTransport
    if (
      popularityCount === null &&
      text.includes("ApolloSSRDataTransport") &&
      text.includes("popularityMetrics")
    ) {
      const m = text.match(/"popularityMetrics"[^}]*?"count"\s*:\s*(\d+)/);
      if (m) {
        popularityCount = parseInt(m[1]);
        console.log(`[S-Marketing] popularityCount: ${popularityCount}`);
      }
    }

    // 2. reviewCount → pageModel
    if (
      reviewCount === null &&
      text.includes("pageModel") &&
      text.includes("reviewCount")
    ) {
      const m = text.match(
        /"pageModel"\s*:\s*\{[^]*?"rating"\s*:\s*\{[^}]*?"reviewCount"\s*:\s*(\d+)/,
      );
      if (m) {
        reviewCount = parseInt(m[1]);
        console.log(`[S-Marketing] reviewCount: ${reviewCount}`);
      }
    }

    if (popularityCount !== null && reviewCount !== null) break;
  }

  // Apollo 직접 접근 (보조)
  if (popularityCount === null) {
    try {
      const apolloData = window[Symbol.for("ApolloSSRDataTransport")];
      if (apolloData) {
        for (const item of apolloData) {
          const rehydrate = item?.rehydrate;
          if (!rehydrate) continue;
          for (const key of Object.keys(rehydrate)) {
            const count =
              rehydrate[key]?.data?.product?.popularityMetrics?.count;
            if (count !== undefined && count !== null) {
              popularityCount = count;
              break;
            }
          }
          if (popularityCount !== null) break;
        }
      }
    } catch (e) {}
  }

  return { popularityCount, reviewCount };
}

async function saveToSupabase(popularityCount, reviewCount) {
  try {
    const productUrl = window.location.href.split("?")[0];

    // ── ✅ tracked_products에 이 URL이 등록되어 있는지 먼저 확인 ──
    const checkRes = await fetch(
      `${SUPABASE_URL}/rest/v1/tracked_products?url=eq.${encodeURIComponent(productUrl)}&select=url`,
      {
        headers: {
          apikey: SUPABASE_KEY,
          Authorization: `Bearer ${SUPABASE_KEY}`,
        },
      },
    );
    const existing = await checkRes.json();

    if (!existing || existing.length === 0) {
      // 등록 안 된 URL → 배지만 표시하고 저장 안 함
      console.warn(
        `[S-Marketing] ⚠️ 미등록 URL - CLI에서 먼저 등록하세요: ${productUrl}`,
      );
      showUnregisteredBadge(productUrl);
      return;
    }

    console.log(`[S-Marketing] 등록된 URL 확인 ✅`);

    // ── product_logs2 저장 ──
    const insertRes = await fetch(`${SUPABASE_URL}/rest/v1/product_logs2`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        apikey: SUPABASE_KEY,
        Authorization: `Bearer ${SUPABASE_KEY}`,
        Prefer: "return=representation",
      },
      body: JSON.stringify({
        product_url: productUrl,
        popularity_count: popularityCount,
        review_count: reviewCount,
      }),
    });

    if (insertRes.ok) {
      console.log("[S-Marketing] ✅ Supabase 저장 완료!");
      await trimLogs(productUrl);
      showBadge(popularityCount, reviewCount);
    } else {
      const err = await insertRes.text();
      console.error("[S-Marketing] 저장 실패:", err);
    }
  } catch (e) {
    console.error("[S-Marketing] 저장 오류:", e.message);
  }
}

// ── 로그 10개 초과분 삭제 ──
async function trimLogs(productUrl) {
  try {
    const res = await fetch(
      `${SUPABASE_URL}/rest/v1/product_logs2?product_url=eq.${encodeURIComponent(productUrl)}&select=id,created_at&order=created_at.asc`,
      {
        headers: {
          apikey: SUPABASE_KEY,
          Authorization: `Bearer ${SUPABASE_KEY}`,
        },
      },
    );
    const logs = await res.json();
    if (logs.length > 10) {
      const excess = logs.slice(0, logs.length - 10);
      for (const log of excess) {
        await fetch(`${SUPABASE_URL}/rest/v1/product_logs2?id=eq.${log.id}`, {
          method: "DELETE",
          headers: {
            apikey: SUPABASE_KEY,
            Authorization: `Bearer ${SUPABASE_KEY}`,
          },
        });
      }
    }
  } catch (e) {
    console.warn("[S-Marketing] 로그 정리 실패:", e);
  }
}

// ── 수집 완료 배지 ──
function showBadge(popularity, review) {
  const badge = document.createElement("div");
  badge.style.cssText = `
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 99999;
    background: #1a73e8;
    color: white;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-family: sans-serif;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    line-height: 1.6;
  `;
  badge.innerHTML = `
    ✅ S-Marketing 수집 완료<br>
    24h예약: <b>${popularity ?? "없음"}</b><br>
    리뷰수: <b>${review ?? "없음"}</b>
  `;
  document.body.appendChild(badge);
  setTimeout(() => badge.remove(), 5000);
}

// ── 미등록 URL 안내 배지 ──
function showUnregisteredBadge(url) {
  const badge = document.createElement("div");
  badge.style.cssText = `
    position: fixed;
    top: 16px;
    right: 16px;
    z-index: 99999;
    background: #e65100;
    color: white;
    padding: 10px 16px;
    border-radius: 8px;
    font-size: 12px;
    font-family: sans-serif;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    line-height: 1.6;
    max-width: 300px;
  `;
  badge.innerHTML = `
    ⚠️ 미등록 상품<br>
    CLI에서 먼저 등록하세요<br>
    <small>python cli_viator.py → [5]</small>
  `;
  document.body.appendChild(badge);
  setTimeout(() => badge.remove(), 6000);
}
