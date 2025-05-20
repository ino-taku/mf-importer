# src/mf_login_download.py

import asyncio
from playwright.async_api import async_playwright, Page
import json

async def _login_if_needed(page: Page):
    # ログインページに遷移
    await page.goto("https://id.moneyforward.com/me", timeout=60_000)

    # **【追加】** 常にスクリーンショットを撮ってログ保存
    await page.screenshot(path="login_issue.png", full_page=True)

    # ページソースを確認
    html = await page.content()
    if "ログイン" not in html and "login" not in html.lower():
        # フォーム要素が見つからない場合はログと例外
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
        # ストレージ状態（環境変数から）
        storage_b64 = os.getenv("MF_STORAGE_B64", "")
        storage_json = json.loads(
            asyncio.get_event_loop().run_in_executor(None,
                lambda: json.loads(
                    gzip.decompress(base64.b64decode(storage_b64)).decode()
                )
            )
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

        # ログインチェック（常にスクショ済み）
        await _login_if_needed(page)

        # CSV ダウンロードのロジック（省略）
        # ...
        await browser.close()
        return "downloaded.csv"

def main():
    asyncio.run(download_csv_async())

if __name__ == "__main__":
    main()
