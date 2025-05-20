import asyncio
import base64
import gzip
import json
import os
from playwright.async_api import async_playwright, Page

async def _login_if_needed(page: Page):
    # ログインページに遷移
    await page.goto("https://id.moneyforward.com/me", timeout=60_000)
    # ページ HTML を取得
    html = await page.content()
    # フォーム要素が見つからなければスクリーンショットを残して例外
    if "ログイン" not in html and "login" not in html.lower():
        await page.screenshot(path="login_issue.png", full_page=True)
        print(html[:1500], "...\n")
        raise RuntimeError("ログインフォームを検出できませんでした (iframe 含む)")

async def download_csv_async(
    download_dir: str,
    year: int,
    month: int,
    headless: bool = True
) -> str:
    async with async_playwright() as pw:
        # Chromium をステルスモードで起動
        browser = await pw.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )

        # storageState を環境変数から復元
        storage_b64 = os.getenv("MF_STORAGE_B64", "")
        storage_state = json.loads(
            gzip.decompress(base64.b64decode(storage_b64)).decode()
        )

        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
            storage_state=storage_state,
        )

        # stealth 化スクリプト
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
        """)

        page = await context.new_page()

        # ログインチェック（失敗時にのみ screenshot & 例外）
        await _login_if_needed(page)

        # CSV のダウンロード
        csv_url = (
            f"https://moneyforward.com/cf/csv?"
            f"from={year:04d}/{month:02d}/01&month={month}&year={year}"
        )
        response = await page.request.get(csv_url)
        if response.status != 200:
            await page.screenshot(path="login_issue.png", full_page=True)
            raise RuntimeError(f"CSVダウンロードに失敗しました: status={response.status}")

        # バイトデータを書き出し
        content = await response.body()
        csv_filename = f"mf_{year}_{month:02d}.csv"
        csv_path = os.path.join(download_dir, csv_filename)
        with open(csv_path, "wb") as f:
            f.write(content)

        await browser.close()
        return csv_path
