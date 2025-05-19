# src/mf_login_download.py
# ---------------------------------------------------------------------------
# MoneyForward 家計簿から CSV をダウンロードするユーティリティ
# * ローカル: GUI/ヘッドレスどちらでも可
# * GitHub Actions (ubuntu-latest): --no-sandbox 等を自動付与
# ---------------------------------------------------------------------------
import asyncio
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

from playwright.async_api import async_playwright, TimeoutError as PWTimeout


# GitHub Actions(Linux) の headless Chrome を安定させる追加フラグ
EXTRA_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

# 家計簿トップとダウンロード用リンク
HOME_URL = "https://moneyforward.com/cf"
DL_MENU_SELECTOR = 'a:has-text("ダウンロード")'
CSV_LINK_SELECTOR = 'a:has-text("CSVファイル")'


async def _login(page) -> None:
    """MoneyForward ID ログイン"""
    await page.goto("https://id.moneyforward.com/sign_in", wait_until="networkidle")

    email = os.environ["MF_EMAIL"]
    password = os.environ["MF_PASSWORD"]

    try:
        await page.fill('input[name="email"]', email, timeout=60_000)
        await page.fill('input[name="password"]', password)
        await page.click('button[type="submit"]')
    except PWTimeout:
        raise RuntimeError("ログインフォームが描画されずタイムアウトしました")


async def _download_csv(page, tmp_dir: str) -> str:
    """家計簿画面から CSV をダウンロードし、保存先パスを返す"""
    await page.goto(HOME_URL, wait_until="domcontentloaded")

    # 「ダウンロード」メニュー → 「CSVファイル」クリック
    await page.locator(DL_MENU_SELECTOR).click()
    async with page.expect_download() as dl_info:
        await page.locator(CSV_LINK_SELECTOR).click()
    download = await dl_info.value

    # 保存ファイル名を明示したいのでここで move
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = Path(tmp_dir) / f"mf_{ts}.csv"
    await download.save_as(str(dst))
    return str(dst)


async def download_csv_async(tmp_dir: str, *, headless: bool = True) -> str:
    """CSV を非同期で取得しファイルパスを返す"""
    async with async_playwright() as p:
        launch_opts = {"headless": headless}
        if headless and sys.platform == "linux":
            launch_opts["args"] = EXTRA_ARGS

        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            **p.devices["Desktop Chrome HiDPI"], locale="ja-JP"
        )
        page = await context.new_page()

        await _login(page)
        csv_path = await _download_csv(page, tmp_dir)

        await context.close()
        await browser.close()
        return csv_path


# ---------------------------------------------------------------------------
# CLI 兼 同期ラッパー
# ---------------------------------------------------------------------------
def download_csv(tmp_dir: str, *, headless: bool = True) -> str:
    """同期で呼び出したい場合用のラッパー"""
    return asyncio.run(download_csv_async(tmp_dir, headless=headless))


if __name__ == "__main__":
    path = download_csv(tempfile.gettempdir(), headless=("--headful" not in sys.argv))
    print("Downloaded:", path)
