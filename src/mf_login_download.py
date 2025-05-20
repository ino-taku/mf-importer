import asyncio
import base64
import gzip
import json
import os
from playwright.async_api import async_playwright, Page

async def _login_if_needed(page: Page):
    # Money Forward のログインページへ
    await page.goto("https://id.moneyforward.com/me", timeout=60_000)

    # ページ HTML を取得
    html = await page.content()

    # ログインフォームが無ければ失敗扱い
    if "ログイン" not in html and "login" not in html.lower():
        # 失敗時のみスクリーンショットを残す
        await page.screenshot(path="login_issue.png", full_page=True)
        # ログのため先頭を出力
        print(html[:1500], "...\n")
        raise RuntimeError("ログインフォームを検出できませんでした (iframe 含む)")

async def download_csv_async() -> str:
    async with async_playwright() as pw:
        # Chromium をステルス起動
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )

        # storageState を環境変数から復元
        storage_b64 = os.getenv("MF_STORAGE_B64", "")
        storage_json = json.loads(
            gzip.decompress(base64.b64decode(storage_b64)).decode()
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            storage_state=storage_json,
        )

        # stealth スクリプト
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
        """)
        page = await context.new_page()

        # ログインチェック（失敗時にのみスクショ＆例外）
        await _login_if_needed(page)

        # CSV ダウンロード処理（省略）
        # 例: await page.request.get(...)
        # ...

        await browser.close()
        return "downloaded.csv"

def main():
    asyncio.run(download_csv_async())

if __name__ == "__main__":
    main()
