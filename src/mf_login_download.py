import os
import sys
import asyncio
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError

# ──────────────────────────────
# 環境設定
# ──────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE  = BASE_DIR / "storageState.json"
load_dotenv(BASE_DIR / ".env")

DOWNLOAD_TIMEOUT = 60  # 秒


async def download_csv_async(save_dir=".", headless: bool = False) -> Path:
    """
    MoneyForward から当月 CSV をダウンロードして保存パスを返す
    """
    email    = os.getenv("MF_EMAIL")
    password = os.getenv("MF_PASSWORD")

    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:

        # ── 0) ブラウザ起動 ─────────────────────
        browser = await p.chromium.launch(
            headless=headless,
            args=["--disable-dev-shm-usage"],
        )

        # GUI と同じ解像度 / DPI のデバイス設定を使う
        device = p.devices["Desktop Chrome HiDPI"]

        # ── 1) コンテキスト作成 ─────────────────
        if STORAGE.exists():
            context = await browser.new_context(
                **device,
                storage_state=str(STORAGE),
                accept_downloads=True,
            )
            page = await context.new_page()
            await page.goto("https://moneyforward.com/cf")
        else:
            if not (email and password):
                raise EnvironmentError("MF_EMAIL / MF_PASSWORD が未設定です")

            context = await browser.new_context(
                **device,
                accept_downloads=True,
            )
            page = await context.new_page()
            await page.goto("https://moneyforward.com/cf")
            await page.fill('input[name="email"]', email)
            await page.fill('input[name="password"]', password)
            await page.click('button[type="submit"]')
            await page.wait_for_url("**/home")
            # Cookie 保存
            await context.storage_state(path=str(STORAGE))

        # ── 2) CSV ダウンロード ─────────────────
        try:
            # 「ダウンロード ▼」メニューをクリックで開く
            dl_btn = page.locator("a").filter(has_text="ダウンロード").first
            await dl_btn.scroll_into_view_if_needed()
            await dl_btn.click()
            await page.wait_for_timeout(300)   # アニメーション描画待ち

            csv_link = page.get_by_role("link", name="CSVファイル")
            await csv_link.wait_for(state="visible", timeout=5000)

            async with page.expect_download(timeout=DOWNLOAD_TIMEOUT * 1000) as dl_info:
                await csv_link.click()

            download = await dl_info.value
            csv_path = save_dir / download.suggested_filename
            await download.save_as(csv_path)

        except TimeoutError:
            raise RuntimeError("CSV ダウンロードが開始されませんでした。セレクタを再確認してください。")

        # ── 3) クリーンアップ ──────────────────
        await context.close()
        await browser.close()

    return csv_path


# ── CLI エントリポイント ─────────────────────
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="ヘッドレスモードで実行")
    args = ap.parse_args()

    try:
        out_path = asyncio.run(download_csv_async(
            save_dir=tempfile.gettempdir(),
            headless=args.headless
        ))
        print(f"Downloaded: {out_path}")
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
