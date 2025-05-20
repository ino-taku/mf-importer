import asyncio
from playwright.async_api import async_playwright, Page
import os

async def _login_if_needed(page: Page):
    # id.moneyforward.com にアクセス
    await page.goto("https://id.moneyforward.com/me", timeout=60_000)
    # ページソースを確認して iframe 内も探す
    html = await page.content()
    if "ログイン" not in html and "login" not in html.lower():
        # フォーム要素が見つからなかったらスクリーンショットを必ず保存
        await page.screenshot(path="login_issue.png", full_page=True)
        # HTML の先頭もログに出力
        print(html[:1500], "...\n")
        raise RuntimeError("ログインフォームを検出できませんでした (iframe 含む)")

async def download_csv_async():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        # stealth スクリプト
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
        """)
        page = await context.new_page()
        # ここで storage_state.json をロードする等の処理
        # …

        # ログインチェック
        await _login_if_needed(page)

        # CSV ダウンロード処理
        # …
        return "downloaded.csv"

def main():
    asyncio.run(download_csv_async())

if __name__ == "__main__":
    main()
