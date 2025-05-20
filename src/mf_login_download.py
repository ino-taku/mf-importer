import asyncio
import gzip
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page

# ==== 環境変数 ====
import base64
import json
import os

MF_EMAIL = os.getenv("MF_EMAIL")
MF_PASSWORD = os.getenv("MF_PASSWORD")
MF_STORAGE_B64 = os.getenv("MF_STORAGE_B64")  # gzip+base64 or plain base64

LOGIN_URL = "https://id.moneyforward.com/sign_in"
CSV_BASE = "https://moneyforward.com/cf/csv"

# ------------------------------------------------------------------------------
# 内部ヘルパ
# ------------------------------------------------------------------------------


async def _login(page: Page) -> None:
    """メール＋パスワードでサインイン。二要素認証には未対応。"""
    await page.goto(LOGIN_URL)
    await page.fill('input[name="mfid_user[email]"]', MF_EMAIL)
    await page.fill('input[name="mfid_user[password]"]', MF_PASSWORD)
    # ログイン → 自動リダイレクト完了を待つ
    async with page.expect_navigation(url_regex=r"https://moneyforward\.com/.*"):
        await page.click('button[type="submit"]')


def _build_csv_url(year: int, month: int) -> str:
    from_day = date(year, month, 1)
    return (
        f"{CSV_BASE}"
        f"?from={from_day:%Y/%m/%d}"
        f"&month={month}"
        f"&year={year}"
    )


def _decode_storage() -> Optional[dict]:
    """MF_STORAGE_B64 → dict（Playwright storageState 形式）"""
    if not MF_STORAGE_B64:
        return None
    raw = base64.b64decode(MF_STORAGE_B64)
    try:
        raw = gzip.decompress(raw)
    except gzip.BadGzipFile:
        pass  # 非 gzip
    return json.loads(raw)


# ------------------------------------------------------------------------------
# 公開 API
# ------------------------------------------------------------------------------


async def download_csv_async(
    out_dir: str,
    year: int,
    month: int,
    *,
    headless: bool = True,
) -> Path:
    """指定年月（1–12）の CSV をダウンロードして保存し、ファイルパスを返す"""
    storage = _decode_storage()
    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=headless)
        context = (
            await browser.new_context(storage_state=storage)
            if storage
            else await browser.new_context()
        )
        page = await context.new_page()

        # Cookieが無効ならログインして storageState をキャッシュ（次回用）
        if not storage:
            await _login(page)
            state = await context.storage_state()
            packed = gzip.compress(json.dumps(state).encode())
            print(
                "\n=== 新しい MF_STORAGE_B64（gzip+base64） ===\n"
                + base64.b64encode(packed).decode()
                + "\n=========================================\n"
            )

        # 直接 GET で取得
        csv_url = _build_csv_url(year, month)
        resp = await context.request.get(csv_url)
        if resp.status != 200:
            raise RuntimeError(f"CSV ダウンロード失敗: {resp.status} {csv_url}")

        csv_path = Path(out_dir) / f"mf_{year}{month:02d}.csv"
        csv_path.write_bytes(await resp.body())

        await context.close()
        await browser.close()
        return csv_path


# ------------------------------------------------------------------------------
# 手動実行用
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    async def _run() -> None:
        tmp = tempfile.gettempdir()
        # 例: 最新月を自動計算
        today = date.today()
        await download_csv_async(tmp, today.year, today.month)
        print("download OK ->", tmp)

    asyncio.run(_run())
