"""
MoneyForward CSV downloader – Chromium stealth版
"""
from __future__ import annotations

import asyncio, base64, gzip, json, os, tempfile
from pathlib import Path
from typing import Final

from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Frame

LOGIN_URL:  Final = "https://id.moneyforward.com/sign_in"
CSV_URL_TPL: Final = "https://moneyforward.com/cf/csv?from={y}/{m:02d}/01&month={m}&year={y}"

EMAIL_SEL  = 'input[name="email"], input[name="mfid_user[email]"]'
PASS_SEL   = 'input[type="password"]'
SUBMIT_SEL = 'button[type="submit"]'

# ───────────────────────── storageState helper
def _decode_storage_state(b64: str) -> Path:
    raw = base64.b64decode(b64)
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    json.loads(raw)  # validate JSON
    fp = Path(tempfile.mkdtemp()) / "state.json"
    fp.write_bytes(raw)
    return fp

# ───────────────────────── login helper
async def _find_login_frame(page: Page) -> Frame | None:
    try:
        await page.wait_for_selector(EMAIL_SEL, timeout=5_000)
        return page.main_frame
    except Exception:
        pass
    for fr in page.frames:
        try:
            if await fr.query_selector(EMAIL_SEL):
                return fr
        except Exception:
            continue
    return None

async def _login_if_needed(page: Page) -> None:
    # 既にログイン済みページであればスキップ
    if page.url.startswith("https://moneyforward.com"):
        return
    # サインインページへ移動
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    # フレーム内も含めてログインフォームを探す
    frame = await _find_login_frame(page)
    if frame is None:
        # デバッグ情報出力
        ua = await page.evaluate("() => navigator.userAgent")
        print("=== UA:", ua)
        html = await page.content()
        print(html[:1500], "...\n")
        try:
            await page.screenshot(path="login_issue.png", full_page=True)
            print("Screenshot saved to login_issue.png")
        except Exception as e:
            print("Screenshot failed:", e)
        raise RuntimeError("ログインフォームを検出できませんでした (iframe 含む)")

    # フォーム入力 & ログイン
    await frame.fill(EMAIL_SEL, os.environ["MF_EMAIL"])
    await frame.fill(PASS_SEL,  os.environ["MF_PASSWORD"])
    async with page.expect_navigation():
        await frame.click(SUBMIT_SEL)

# ───────────────────────── main
async def download_csv_async(out_dir: str | os.PathLike, year: int, month: int, *, headless=True):
    # storageState.json のデコード
    storage_state = None
    if b64 := os.environ.get("MF_STORAGE_B64"):
        storage_state = str(_decode_storage_state(b64))

    async with async_playwright() as pw:
        # Chromium ヘッドレス起動 + stealth 用 args
        browser: Browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        # CH-UA ヘッダー
        ch_headers = {
            "Sec-CH-UA": '"Chromium";v="125", "Google Chrome";v="125", ";Not A Brand";v="99"',
            "Sec-CH-UA-Mobile": '?0',
            "Sec-CH-UA-Platform": '"Linux"',
        }
        # コンテキスト生成（UA偽装 + locale + storage）
        context: BrowserContext = await browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            locale="ja-JP",
            extra_http_headers=ch_headers,
            storage_state=storage_state,
        )
        # stealth スクリプト追加
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['ja-JP', 'ja'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            """
        )

        page = await context.new_page()
        # ログイン処理
        await _login_if_needed(page)

        # CSV ダウンロード
        csv_url = CSV_URL_TPL.format(y=year, m=month)
        resp = await context.request.get(csv_url)
        if resp.status != 200:
            raise RuntimeError(f"CSV ダウンロード失敗: {resp.status} {csv_url}")

        out_path = Path(out_dir) / f"moneyforward_{year}{month:02d}.csv"
        out_path.write_bytes(await resp.body())
        print("✓ CSV saved:", out_path)

        await context.close()
        await browser.close()
        return out_path

if __name__ == "__main__":
    asyncio.run(download_csv_async(tempfile.gettempdir(), 2025, 5, headless=False))
